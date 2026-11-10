"""Independent checks of the three lead-time cases (November, October-December, OND dekads).

Each check recomputes a method from the saved inputs and outputs, or asks the data
source directly, instead of trusting the notebooks. Run in the full PyCPT environment
after the three notebooks have been executed (it reads their case folders):

    python research/scripts/audit_lead_time_cases.py

Writes research/audits/lead-time/audit-checks.json. Network: a few small IRI Data
Library requests (CFSv2 member counts, GEFS server-side dekad sums). One extra CPT fit
(dekad lead 1, CCA) for the probability and ensemble-size checks.
"""
from pathlib import Path
import datetime as dt
import json
import shutil
import sys
import time
import urllib.request

import numpy as np
import pandas as pd
import xarray as xr
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research/scripts"))
OUT = ROOT / "research/audits/lead-time"
HOME = Path.home() / "PyCPT"
CASES = {"november": (HOME / "indonesia-nov-2023-leads", "local-CHIRPS3-Nov-1991-2020.nc", "Nov-Nov", 11),
         "ond": (HOME / "indonesia-ond-2023-leads", "local-CHIRPS3-OND-1991-2020-dekads.nc", "Oct-Dec", 10)}
DOMAIN = "85W-155E_to_-20S-20N"
UA = {"User-Agent": "pycpt-tutorial-audit/1.0 (python urllib)"}
results = {"date": dt.date.today().isoformat()}


def log(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def get(url, timeout=180):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # network hiccups: wait and retry, then fail loudly
            if attempt == 3:
                raise
            log("retry after", type(e).__name__, e)
            time.sleep(15 * (attempt + 1))


def open_nc(body, path):
    path.write_bytes(body)
    return xr.open_dataset(path, decode_times=False, decode_timedelta=False).load()


def hazen_bounds(y):
    q = np.quantile(y.transpose("T", "Y", "X").values, [0.33, 0.67], axis=0, method="hazen")
    return (xr.DataArray(q[0], coords={"Y": y["Y"], "X": y["X"]}, dims=("Y", "X")),
            xr.DataArray(q[1], coords={"Y": y["Y"], "X": y["X"]}, dims=("Y", "X")))


def reconstruct(forecast, y, df):
    """CPT tercile probabilities (%) from the forecast, its error variance and hazen terciles of y."""
    lower, upper = hazen_bounds(y)
    det = forecast.deterministic.where(forecast.deterministic > -999)
    pev = forecast.prediction_error_variance.where(forecast.prediction_error_variance > -999)
    lower = lower.reindex(Y=det["Y"], X=det["X"], method="nearest", tolerance=1e-3)
    upper = upper.reindex(Y=det["Y"], X=det["X"], method="nearest", tolerance=1e-3)
    below = student_t.cdf(((lower - det) / np.sqrt(pev)).transpose(*det.dims).values, df) * 100
    above = student_t.sf(((upper - det) / np.sqrt(pev)).transpose(*det.dims).values, df) * 100
    return det, below, above


def compare_probabilities(forecast, y, n_train, positive_only, x_modes=3):
    """Largest |reconstructed - CPT| in percentage points for several degrees of freedom.

    positive_only: rainfall totals are zero-bounded by CPT after the probabilities are
    computed, so cells with a forecast of exactly 0 are left out (their unbounded centre is unknown).
    """
    prob = forecast.probabilistic.where(forecast.probabilistic > -999)
    out = {}
    for df in (n_train - x_modes - 1, n_train - 2, n_train - 1):
        det, below, above = reconstruct(forecast, y, df)
        keep = np.isfinite(det.values) & np.isfinite(below)
        if positive_only:
            keep &= det.values > 0
        cpt_below = prob.isel(C=0).transpose(*det.dims).values
        cpt_above = prob.isel(C=2).transpose(*det.dims).values
        gap = np.nanmax(np.abs(np.r_[(below - cpt_below)[keep], (above - cpt_above)[keep]]))
        out[f"df={df}"] = round(float(gap), 4)
    out["cells compared"] = int(keep.sum())
    return out


# ---------------------------------------------------------------------------
# B1. CFSv2 targets, unit factor and missing values, every lead
# ---------------------------------------------------------------------------
import cptdl as dl
from pycpt import notebook as nbk

rows = []
for case, (root, _, target, first_month) in CASES.items():
    for lead in range(1, 7):
        data = root / f"lead-{lead}" / DOMAIN / "data"
        hc = xr.open_dataset(data / "CFSv2.PRCP.nc", decode_times=True).load()
        fc = xr.open_dataset(data / "CFSv2.PRCP_f2023.nc", decode_times=True).load()
        days = int((pd.Timestamp(hc["Tf"].values[0]) - pd.Timestamp(hc["Ti"].values[0])).days) + 1
        args = {"fdate": dt.datetime(2023, first_month - lead, 1), "target": target, "target_first_year": 1991,
                "target_final_year": 2020, "predictor_extent": {"west": 85, "east": 155, "south": -20, "north": 20},
                "predictand_extent": {"west": 94, "east": 142, "south": -12, "north": 7}}
        url = dl.evaluate_url(dl.hindcasts["CFSv2.PRCP"], **nbk._preprocess_download_args(args))
        factor = int(url.split("/mul")[0].rsplit("/", 1)[1])
        v = hc.prec
        rows.append({"case": case, "lead": lead, "target days": days, "url factor": factor,
                     "factor equals target days": factor == days,
                     "hindcast start month": int(pd.Timestamp(hc["S"].values[0]).month),
                     "forecast start": str(pd.Timestamp(fc["S"].values[0]).date()),
                     "missing or -999 in hindcasts": int((~np.isfinite(v) | (v <= -999)).sum()),
                     "missing or -999 in 2023": int((~np.isfinite(fc.prec) | (fc.prec <= -999)).sum())})
results["cfsv2_targets_units_missing"] = rows
log("B1", pd.DataFrame(rows).to_string())

# ---------------------------------------------------------------------------
# B2. CFSv2 ensemble size: hindcast years vs the 2023 forecast (one grid point)
# ---------------------------------------------------------------------------
tmp = OUT / "tmp"
tmp.mkdir(parents=True, exist_ok=True)
base = "https://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME/.NCEP-CFSv2/.HINDCAST/.PENTAD_SAMPLES_FULL/.prec"
members = []
for year, month, lead in [(2020, 10, 1.5), (2023, 10, 1.5), (2020, 9, 1.5), (2023, 9, 1.5), (2020, 4, 6.5), (2023, 4, 6.5)]:
    label = f"0000 1 {dt.date(year, month, 1):%b} {year}".replace(" ", "%20")
    url = f"{base}/S/({label})/VALUES/L/{lead}/VALUES/X/110/VALUES/Y/0/VALUES/data.nc"
    ds = open_nc(get(url), tmp / "cfsv2-members.nc")
    p = ds["prec"].values.ravel()
    members.append({"start": f"{year}-{month:02d}-01", "L": lead, "M slots": int(ds.sizes.get("M", 1)),
                    "finite members": int(np.isfinite(p).sum())})
results["cfsv2_members"] = members
by_year = {}
for month in ("Oct", "Sep"):
    url = f"{base}/S/(0000%201%20{month}%201991-2023)/VALUES/L/1.5/VALUES/X/110/VALUES/Y/0/VALUES/data.nc"
    ds = open_nc(get(url, timeout=300), tmp / "cfsv2-years.nc")
    counts = np.isfinite(ds["prec"].squeeze()).sum("M").values.astype(int).tolist()
    assert "months since 1960" in ds["S"].attrs.get("units", "")
    by_year[f"{month} starts"] = {int(1960 + v // 12): c for v, c in zip(ds["S"].values, counts)}
results["cfsv2_members_all_years"] = {"M slots": int(ds.sizes["M"]), **by_year}
log("B2", members, by_year)

# ---------------------------------------------------------------------------
# B4. GEFS dekad sums: our local computation vs IRI's own server-side sum
# ---------------------------------------------------------------------------
design = pd.read_csv(ROOT / "docs/data/dekad-leads-2023/lead-design.csv", parse_dates=["dekad", "start"])
gefs = xr.open_dataset(HOME / "indonesia-ond-2023-dekads/gefs-dekads-by-lead.nc").load()
gbase = "https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC"
checks = []
for kind, dekad, lead in [("hindcast", "2010-11-11", 1), ("hindcast", "2004-12-21", 3), ("forecast", "2023-11-01", 2)]:
    row = design[(design.dekad == pd.Timestamp(dekad)) & (design.lead == lead)].iloc[0]
    s = row.start
    label = f"0000 {s.day} {s:%b} {s.year}".replace(" ", "%20")
    branch = "/.hindcast/.weekly/.pr" if kind == "hindcast" else "/.forecast/.pr"
    l0, l1 = row.first_day + 0.5, row.first_day + row.days - 0.5
    url = (gbase + branch + f"/S/({label})/VALUES/X/110/VALUES/Y/0/VALUES/L/{l0}/{l1}/RANGE"
           "/[L]sum/[M]average/data.nc")
    ds = open_nc(get(url), tmp / "gefs-server-sum.nc")
    server = float(ds["pr"].values.ravel()[0]) * (86400.0 if kind == "forecast" else 1.0)
    local = float(gefs.precipitation.sel(lead=lead, T=pd.Timestamp(dekad), Y=0, X=110))
    checks.append({"kind": kind, "dekad": dekad, "lead": lead, "start": str(s.date()), "L slots": f"{l0}..{l1}",
                   "IRI server-side sum (mm)": round(server, 4), "local (mm)": round(local, 4),
                   "difference (mm)": round(local - server, 6)})
results["gefs_server_side_sums"] = checks
log("B4", checks)

# ---------------------------------------------------------------------------
# C1/C2. CPT probabilities and retained modes, November and OND, all leads
# ---------------------------------------------------------------------------
rows, modes, cv_gaps = [], [], []
for case, (root, yfile, *_ ) in CASES.items():
    y = xr.open_dataset(root / yfile).precipitation.load()
    n = y.sizes["T"]
    for lead in range(1, 7):
        out = root / f"lead-{lead}" / DOMAIN / "output"
        for method in ("cca", "pcr"):
            fc = xr.open_dataset(out / f"CFSv2.PRCP_realtime_{method}_forecasts.nc").load().isel(T=0)
            rows.append({"case": case, "lead": lead, "method": method, "N": n, **compare_probabilities(fc, y, n, positive_only=True)})
            hcv = xr.open_dataset(out / f"CFSv2.PRCP_crossvalidated_{method}_hindcasts.nc").load()
            det = hcv.deterministic.where(hcv.deterministic > -999).reindex(Y=y["Y"], X=y["X"], method="nearest", tolerance=1e-3)
            sk = xr.open_dataset(out / f"CFSv2.PRCP_skillscores_{method}.nc").load().pearson
            sk = sk.where(sk > -999).reindex(Y=y["Y"], X=y["X"], method="nearest", tolerance=1e-3)
            a_, b_ = det - det.mean("T"), y.transpose(*det.dims) - y.mean("T")
            mine = (a_ * b_).sum("T") / np.sqrt((a_ * a_).sum("T") * (b_ * b_).sum("T"))
            cv_gaps.append(float(np.nanmax(np.abs((mine - sk).values))))
            load = xr.open_dataset(out / f"CFSv2.PRCP_{method}_x_spatial_loadings.nc").load()
            entry = {"case": case, "lead": lead, "method": method}
            for var in load.data_vars:
                a = load[var]
                if "Mode" in a.dims:
                    entry[var] = int(sum(bool((a.sel(Mode=m) > -999).any() & a.sel(Mode=m).notnull().any()) for m in a["Mode"].values))
            modes.append(entry)
results["cpt_probability_reconstruction"] = rows
results["cv_correlation_recomputed_largest_gap_24_fits"] = round(max(cv_gaps), 6)
results["retained_modes"] = modes
log("C1", pd.DataFrame(rows).to_string())
log("C2", pd.DataFrame(modes).to_string())

# ---------------------------------------------------------------------------
# C3/D2. Dekad case: refit lead 1 CCA; reconstruct probabilities; 11 vs 31 GEFS members
# ---------------------------------------------------------------------------
from cptcore import canonical_correlation_analysis

obs = xr.open_dataset(HOME / "indonesia-ond-2023-dekads/obs-ond-dekads-0p25.nc").precipitation.load()
train = obs["T"].dt.year < 2019
key = obs["T"].dt.strftime("%m-%d")
cells = obs.where(train, drop=True).notnull().all("T")
y_clim = obs.where(train, drop=True).groupby(key.where(train, drop=True)).mean("T")
y_anom = (obs.groupby(key) - y_clim).where(obs.notnull())
x = gefs.precipitation.sel(lead=1, drop=True).sortby("Y", ascending=False)
x_clim = x.where(train, drop=True).groupby(key.where(train, drop=True)).mean("T")
x_anom = x.groupby(key) - x_clim

# 11-member version of the 2023 lead-1 forecasts, from the raw daily files
raw_dir = HOME / "indonesia-ond-2023-dekads/gefs"
eleven = []
for row in design[(design.kind == "forecast") & (design.lead == 1)].itertuples():
    slots = np.arange(row.first_day, row.first_day + row.days) + 0.5
    with xr.open_dataset(raw_dir / f"gefs-forecast-{row.start.date().isoformat()}.nc", decode_timedelta=False) as ds:
        daily = ds["pr"].isel(S=0, drop=True).sel(L=slots).isel(M=slice(0, 11)).load()
    eleven.append((daily * 86400.0).sum("L").mean("M").assign_coords(T=row.dekad))
x11 = xr.concat(eleven, dim="T").sortby("Y", ascending=False)
x11_anom = x11.groupby(x11["T"].dt.strftime("%m-%d")) - x_clim


def cpt_ready(a, times, first_year):
    years = first_year + np.arange(len(times))
    a = a.drop_vars([c for c in a.coords if c not in ("T", "Y", "X")]).sel(T=times)
    a = a.assign_coords(T=pd.to_datetime([f"{y}-10-05" for y in years]))
    a = a.assign_coords(Ti=("T", pd.to_datetime([f"{y}-10-01" for y in years])),
                        Tf=("T", pd.to_datetime([f"{y}-10-10" for y in years])))
    a = a.transpose("T", "Y", "X").rename("anomaly")
    a.attrs = {"units": "mm", "missing": -999.0}
    return a


trT, teT = obs["T"].values[train.values], obs["T"].values[~train.values]
Y = cpt_ready(y_anom, trT, 1801)
X = cpt_ready(x_anom, trT, 1801)
F = xr.concat([cpt_ready(x_anom, teT, 1990), cpt_ready(x11_anom.assign_coords(T=teT), teT, 1999)], dim="T")
folder = HOME / "indonesia-ond-2023-dekads/audit-lead1-cca"
shutil.rmtree(folder, ignore_errors=True)
folder.mkdir(parents=True)
log("fitting dekad lead 1 CCA for the audit")
hc, fc, skill, pxs, pys = canonical_correlation_analysis(
    X, Y, F=F, x_eof_modes=(3, 3), y_eof_modes=(3, 3), cca_modes=(2, 2), validation="CROSSVALIDATION",
    crossvalidation_window=17, synchronous_predictors=True, transform_predictand=None, tailoring=None,
    drymask_threshold=None, skillmask_threshold=None, cpt_kwargs={"outputdir": folder})
w = np.cos(np.deg2rad(Y["Y"])) * cells
cv = skill.pearson.where(skill.pearson > -999).reindex(Y=Y["Y"], X=Y["X"], method="nearest", tolerance=1e-3)
notebook_value = pd.read_csv(ROOT / "docs/data/dekad-leads-2023/skill-by-lead.csv").set_index(["lead", "method"]).loc[(1, "CCA"), "Pearson"]
dekad = {"cv_pearson_area_mean": round(float(cv.where(cells).weighted(w).mean()), 4), "notebook_value": float(notebook_value)}
dekad["probability_reconstruction_pooled_hazen"] = compare_probabilities(
    fc.isel(T=slice(0, 9)), Y.drop_vars(["Ti", "Tf"]), 171, positive_only=False)
dekad["retained_modes"] = {v: int(sum(bool((pxs[v].sel(Mode=m) > -999).any()) for m in pxs[v]["Mode"].values))
                           for v in pxs.data_vars if "loadings" in v}

# score 2023 with 31-member and 11-member forecasts (same fit)
def rps(p, cat):
    cum = p.cumsum("C") / 100
    o = xr.concat([(cat <= k).astype(float) for k in range(3)], dim="C").assign_coords(C=p["C"])
    return ((cum - o) ** 2).isel(C=slice(0, 2)).sum("C")


lower, upper = hazen_bounds(Y.drop_vars(["Ti", "Tf"]))
o23 = y_anom.sel(T=teT)
cat = xr.where(o23 < lower, 0, xr.where(o23 > upper, 2, 1)).where(o23.notnull())
ens = {}
for label, part in [("31 members", slice(0, 9)), ("11 members", slice(9, 18))]:
    p = fc.probabilistic.isel(T=part).where(fc.probabilistic > -999)
    p = p.reindex(Y=Y["Y"], X=Y["X"], method="nearest", tolerance=1e-3).drop_vars(
        [c for c in p.coords if c not in ("T", "C", "Y", "X")]).assign_coords(T=teT)
    ml = p.fillna(-1).argmax("C").where(p.notnull().all("C") & cat.notnull())
    ww = (w * cat.notnull()).where(ml.notnull(), 0)
    clim = xr.DataArray([33.0, 34.0, 33.0], dims="C", coords={"C": p["C"]}).broadcast_like(p)
    det = fc.deterministic.isel(T=part).where(fc.deterministic > -999).reindex(Y=Y["Y"], X=Y["X"], method="nearest", tolerance=1e-3)
    det = det.drop_vars([c for c in det.coords if c not in ("T", "Y", "X")]).assign_coords(T=teT)
    ens[label] = {"hit rate (%)": round(float(ww.where(ml == cat, 0).sum() / ww.sum() * 100), 2),
                  "RPSS 2023": round(float(1 - rps(p, cat).weighted(ww).mean() / rps(clim, cat).weighted(ww).mean()), 3),
                  "area-mean forecast anomaly by dekad (mm)": [round(float(v), 2) for v in det.where(cells).weighted(w).mean(("Y", "X")).values],
                  "raw input area-mean anomaly by dekad (mm)": None}
for label, a in [("31 members", x_anom.sel(T=teT)), ("11 members", x11_anom)]:
    box = a.sel(X=slice(94, 142)).where((a["Y"] >= -12) & (a["Y"] <= 7))
    ens[label]["raw input area-mean anomaly by dekad (mm)"] = [round(float(v), 2) for v in box.mean(("Y", "X")).values]
dekad["ensemble_size_2023"] = ens
results["dekad_lead1_refit"] = dekad
log("C3/D2", json.dumps(dekad, indent=1)[:3000])

# ---------------------------------------------------------------------------
# D1. Climatology leakage: raw GEFS anomaly correlation, in-sample vs leave-one-year-out
# ---------------------------------------------------------------------------
def pearson(a, b):
    a, b = a - a.mean("T"), b - b.mean("T")
    return (a * b).sum("T") / np.sqrt((a * a).sum("T") * (b * b).sum("T"))


ytr = obs.sel(T=trT)
years = ytr["T"].dt.year
leak = []
for lead in (1, 2, 3):
    xtr = gefs.precipitation.sel(lead=lead, drop=True).sel(T=trT).interp(Y=ytr["Y"], X=ytr["X"])
    def anomalies(field, loyo):
        parts = []
        for yr in np.unique(years):
            this = field.sel(T=field["T"].dt.year == yr)
            ref = field.sel(T=field["T"].dt.year != yr) if loyo else field
            clim = ref.groupby(ref["T"].dt.strftime("%m-%d")).mean("T")
            parts.append(this.groupby(this["T"].dt.strftime("%m-%d")) - clim)
        return xr.concat(parts, dim="T").drop_vars("strftime", errors="ignore")
    r_in = pearson(anomalies(xtr, False), anomalies(ytr, False)).where(cells)
    r_lo = pearson(anomalies(xtr, True), anomalies(ytr, True)).where(cells)
    wy = np.cos(np.deg2rad(ytr["Y"])) * cells
    leak.append({"lead": lead, "in-sample climatology": round(float(r_in.weighted(wy).mean()), 4),
                 "leave-one-year-out climatology": round(float(r_lo.weighted(wy).mean()), 4)})
results["dekad_climatology_leakage_raw"] = leak
log("D1", leak)

# ---------------------------------------------------------------------------
# E. Scoring formulas and design arithmetic
# ---------------------------------------------------------------------------
cat_m = xr.open_dataset(ROOT / "docs/data/monthly-2023/monthly-2023-maps.nc").observed_category_2023.load()
valid = cat_m.notnull()
perfect = xr.concat([(cat_m == k).astype(float) * 100 for k in range(3)], dim="C").assign_coords(C=[1, 2, 3]).where(valid)
climp = xr.DataArray([33.0, 34.0, 33.0], dims="C", coords={"C": [1, 2, 3]}).broadcast_like(perfect).where(valid)
r_perfect = float(1 - rps(perfect, cat_m).where(valid).mean() / rps(climp, cat_m).where(valid).mean())
# independent loop for one cell
iy, ix = [int(v[0]) for v in np.nonzero(valid.values)]
c0 = int(cat_m.values[iy, ix])
loop = sum((sum([33, 34, 33][:k + 1]) / 100 - (1.0 if c0 <= k else 0.0)) ** 2 for k in range(2))
vect = float(rps(climp, cat_m).values[iy, ix])
d = design[design.kind == "hindcast"].sort_values("dekad")
order = d.drop_duplicates("dekad").reset_index(drop=True)
same_season_within = all(
    (order.index[order.dekad.dt.year == yr].max() - order.index[order.dekad.dt.year == yr].min()) <= 8
    for yr in order.dekad.dt.year.unique())
results["scoring_and_design"] = {
    "RPSS of perfect probabilities (expect 1)": round(r_perfect, 6),
    "RPS climatology, vectorised vs loop, one cell": [round(vect, 6), round(loop, 6)],
    "dekad CV window 17 covers every same-season sample (max in-season gap <= 8)": bool(same_season_within),
    "dekad samples per year": int(order.groupby(order.dekad.dt.year).size().unique()[0]),
}
log("E", results["scoring_and_design"])

shutil.rmtree(tmp, ignore_errors=True)
(OUT / "audit-checks.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
log("written", OUT / "audit-checks.json")
