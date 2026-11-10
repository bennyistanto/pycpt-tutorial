"""Build the reviewable all-season report from verified saved results."""
from pathlib import Path
import datetime as dt
import json
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from prepare_indonesia_all_seasons import ROOT, SEASONS, read


def main(output_dir=None):
    case_directory=Path(__file__).resolve().parents[2]/"research/cases"/ROOT.name
    destination=Path(output_dir) if output_dir is not None else case_directory
    destination.mkdir(parents=True,exist_ok=True)
    metrics=json.loads((case_directory/"metrics.json").read_text())
    availability=json.loads((case_directory/"availability.json").read_text())
    verification=json.loads((case_directory/"verification.json").read_text())
    manifest=json.loads((case_directory/"case_manifest.json").read_text())
    fit_records={f"{season}_{method}_{period}":json.loads((ROOT/season/f"{method}_{period}_fit.json").read_text())
                 for season in SEASONS for method in ("cca","pcr") for period in ("1983_2010","1991_2020")}
    (destination/"fit_records.json").write_text(json.dumps(fit_records,indent=2)+"\n")
    scores=read(case_directory/"outputs/verification_scores.nc")
    gains=read(case_directory/"outputs/calibration_gains.nc")
    variants=list(scores.forecast_variant.values)
    names={"raw_cfsv2":"Raw","climatology_1983_2010":"Climatology 1983–2010","climatology_1991_2020":"Climatology 1991–2020",
           "cca_1983_2010":"CCA 1983–2010","cca_1991_2020":"CCA 1991–2020","pcr_1983_2010":"PCR 1983–2010","pcr_1991_2020":"PCR 1991–2020"}
    pooled=scores.pooled_rmse.sel(evaluation_set="all_four_years")
    def matrix(group):
        data=scores.pooled_rmse.sel(evaluation_set=group)
        result=[]
        for season in SEASONS:
            row=data.sel(season=season).values; best=int(np.argmin(row))
            cells=[f"**{value:.2f}**" if j==best else f"{value:.2f}" for j,value in enumerate(row)]
            result.append("| "+season+" | "+" | ".join(cells)+" |")
        return "\n".join(result)
    comparisons=[]; gain_rows=[]; audit_rows=[]
    for season in SEASONS:
        data=pooled.sel(season=season)
        cells=[]
        for method in ("cca","pcr"):
            old=float(data.sel(forecast_variant=method+"_1983_2010")); recent=float(data.sel(forecast_variant=method+"_1991_2020"))
            cells.append(f"{100*(old-recent)/old:+.2f}%")
        comparisons.append(f"| {season} | "+" | ".join(cells)+" |")
        gain=gains.mse_skill_vs_climatology.sel(season=season,evaluation_set="all_four_years")
        gain_rows.append(f"| {season} | "+" | ".join(f"{100*float(gain.sel(calibrated_variant=key)):+.1f}%" for key in gains.calibrated_variant.values)+" |")
        audit=availability["seasons"][season]
        low,high=audit["valid_member_count_range"]
        audit_rows.append(f"| {season} | {str(low) if low==high else str(low)+'–'+str(high)} | {audit['training_masks']['1983_2010']['included_cells']} | {audit['training_masks']['1991_2020']['included_cells']} |")
    counts={method:int((pooled.sel(forecast_variant=method+"_1991_2020")<pooled.sel(forecast_variant=method+"_1983_2010")).sum()) for method in ("cca","pcr")}
    beat_climo={key:int((pooled.sel(forecast_variant=key)<pooled.sel(forecast_variant="climatology_"+key.split("_",1)[1])).sum()) for key in names if key.startswith(("cca","pcr"))}
    beat_raw={key:int((pooled.sel(forecast_variant=key)<pooled.sel(forecast_variant="raw_cfsv2")).sum()) for key in beat_climo}
    tradeoffs=[]
    for method in ("cca","pcr"):
        old=pooled.sel(forecast_variant=method+"_1983_2010"); recent=pooled.sel(forecast_variant=method+"_1991_2020")
        bias=scores.pooled_bias.sel(evaluation_set="all_four_years")
        worse=abs(bias.sel(forecast_variant=method+"_1991_2020"))>abs(bias.sel(forecast_variant=method+"_1983_2010"))
        tradeoffs.append(f"{method.upper()}: "+", ".join(str(value) for value in scores.season.values[(recent<old).values&worse.values]))
    baselines="\n".join(f"| {names[key]} | {beat_climo[key]}/12 | {beat_raw[key]}/12 |" for key in beat_climo)
    control=[]
    for year in scores.season_year.values:
        cells=[]
        for method in ("cca","pcr"):
            row=metrics["ond_control"][method]["per_year_old82_old83_recent_rmse_mm"][str(year)]
            cells.append(" / ".join(f"{row[period]:.2f}" for period in ("1982_2010","1983_2010","1991_2020")))
        control.append(f"| {year} | "+" | ".join(cells)+" |")
    netcdf_count=sum(name.endswith(".nc") for name in manifest["outputs"])
    table_header="| Season | Raw | Clim83–10 | Clim91–20 | CCA83–10 | CCA91–20 | PCR83–10 | PCR91–20 |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    report=f'''# Indonesia: all twelve seasonal rainfall forecasts at 0.25°

**Methodology audit, 2026-11-01:** see the [reference-based audit](../../reports/METHODOLOGY_AUDIT.md).
CPT uses a cyclic five-sample CV window and automatically zero-bounds rainfall.
Native category climatologies are 1991–2010 / 1991–2020 for within-year seasons;
DJF/NDJ use ending years 1992–2010 / 1992–2020. They are not necessarily the
training periods. Empirical probability reliability has not been demonstrated.

Completed {dt.datetime.now().date()} with PyCPT 2.10.4, cptio 1.4.0 and packaged
CPT 17.8.3 in Debian. **192 calibrated forecasts** cover twelve rolling seasons,
four ending-year labels (2021–2024), two methods and two training periods.
Each of the **48 native CPT calls** forecasts four years together.

The result is a comparison of when calibration helps, including neutral and
negative outcomes. It is not a claim of year-round operational reliability.

## Calendar and training periods

The older period is **1983–2010 (28 seasons)** and the recent period is
**1991–2020 (30 seasons)** for every season. This differs from the original
1982–2010 OND pilot: the source starts in January1982, whereas DJF/JFM/NDJ1982
would require1981 initializations under the ending-year convention. The common
1983 start avoids silently changing sample availability between seasons.
The [calendar decision](calendar_decision.json) records the source evidence.

DJF2022 means December2021–February2022, initialized1 November2021. NDJ2022
means November2021–January2022, initialized1 October2021. JFM2022 is initialized
1 December2021. Other windows lie within their labelled calendar year. Every
forecast is issued on the first day of the month preceding its first target month,
with CFSv2 lead centres1.5/2.5/3.5. Real month lengths, including February29, are used.
Actual initialization/target dates and `season_year` are saved; `T.year` alone
does not label NDJ correctly because its midpoint is in the preceding December.

CCA uses three predictor EOFs, three predictand EOFs and two CCA modes. PCR uses
three predictor EOFs. Each season is fitted separately; settings are retained
without test-year tuning. Both methods use synchronous predictors and CV window5,
with no transformation, tailoring, dry mask or skill mask. Observational coverage
and constant-value exclusions are fitted from training data only.

## Data audit and shared footprint

Every season has42 annual predictor sets with three monthly rates on the same
2,911-cell predictor domain,85–155°E and20°S–20°N. All
**{verification['source_monthly_model_values_verified']:,} requested monthly mean values** are finite.
CHIRPS rolling endpoints were checked against exact start/end-exclusive bounds
for every training/evaluation season, then country-only native0.05° pixels were
averaged in5×5 blocks with cosine-latitude weights and99% valid-land coverage.

| Season | Valid members, min–max | Older training cells | Recent training cells |
| --- | ---: | ---: | ---: |
{chr(10).join(audit_rows)}

Mean fields are complete, but ensemble coverage varies by initialization month
and year. Counts were calculated before averaging and are retained at every
requested grid/month/year. Completeness does not imply unchanged ensemble
composition or statistical homogeneity. The source retains the previously audited
April2011 reforecast-to-operational append; no transition adjustment is applied.
That boundary refers to initialization dates, so its corresponding target-season
year differs between windows.

All primary scores use **{metrics['common_evaluation_cells']:,} shared0.25° cells** and identical weights across
all twelve seasons, both periods and four years. This retains
**{100*metrics['country_land_weight_retained']:.4f}%** of approximate native country land weight.
The common mask restricts scoring only; it never refits any model.

## Four-year pooled RMSE

Units are mm accumulated over each three-month window. Pooled RMSE is the square
root of mean annual spatial MSE, with equal year weights and shared spatial
weights. It is not an arithmetic mean of annual RMSE. Bold marks the lowest
national RMSE among the seven variants in each season; this is descriptive ranking.

{table_header}
{matrix('all_four_years')}

![Seasonal RMSE comparison](outputs/seasonal_rmse_matrix.png)

Recent training has lower pooled RMSE in **{counts['cca']} of12 seasons for CCA**
and **{counts['pcr']} of12 for PCR**. The table below reports matched-climatology
and raw-model comparisons, rather than interpreting low dry-season RMSE alone
as high forecast skill.

| Calibrated variant | Lower error than own-period climatology | Lower error than raw |
| --- | ---: | ---: |
{baselines}

**AMJ is the clearest failure against a simple baseline:**1991–2020 climatology
has the lowest pooled error among all seven variants. Both methods under both
training periods lose to their own climatology there. In DJF, recent-period CCA
and PCR also lose to their matched climatology, despite beating the raw model.
The older CCA fit has the lowest DJF error, with only a small margin over the
recent climatology. These exceptions matter when interpreting the11/12 result.

## Relative gains and bias tradeoffs

Positive reductions favour1991–2020; negative values favour1983–2010.

| Season | CCA RMSE reduction | PCR RMSE reduction |
| --- | ---: | ---: |
{chr(10).join(comparisons)}

![Period sensitivity](outputs/training_period_sensitivity.png)

The deterministic MSE skill score below is `1 − MSE(calibrated)/MSE(climatology)`
using each variant's own-period climatology. Positive means lower error than that
baseline; negative means calibration worsens it. These descriptive values do not
establish statistical significance or probabilistic skill.

| Season | CCA83–10 | CCA91–20 | PCR83–10 | PCR91–20 |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(gain_rows)}

Lower RMSE and smaller absolute bias need not coincide. Seasons where recent
training lowers pooled RMSE while increasing absolute pooled bias are:
**{'; '.join(tradeoffs)}**. Opposite annual biases can also cancel in a pooled mean.
Full annual RMSE/MAE/bias and both evaluation subsets are saved, so the pooled
summary should be read alongside year-specific errors.

![Seasonal bias](outputs/seasonal_bias.png)

## Additional-year sensitivity

This table excludes the motivating2023 case and pools2021,2022 and2024 only.
The same footprint and settings are retained. Three years provide limited
evidence, and the conclusions should not depend solely on the four-year table.

{table_header}
{matrix('additional_years')}

## Where the training-period change helps or hurts

The maps show older-minus-recent four-year temporal RMSE at each cell. Positive
blue values favour recent training; negative red values favour older training.
CCA/PCR maps share one colour scale. These are descriptive error differences,
not local significance or reliability assessments.

![CCA geographic differences](outputs/cca_period_gain_maps.png)

![PCR geographic differences](outputs/pcr_period_gain_maps.png)

## Bridge to the original OND experiment

Dropping1982 changes the older fit. This control separates that adjustment from
moving to other seasons. Entries below are RMSE for
**1982–2010 /1983–2010 /1991–2020**, all rescored on the new shared footprint.

| OND year | CCA, mm | PCR, mm |
| --- | ---: | ---: |
{chr(10).join(control)}

The recent-period OND model inputs reuse the exact cached predictor amounts;
every overlapping monthly binary-vs-text value passed a printed-precision bound.
The maximum seasonal difference is0.0045mm, within its derived0.0051mm bound. Its
batched forecasts reproduce the earlier recent-period forecasts within0.01mm.
All earlier output artifacts remain unchanged.

## Outputs and reproduction

**{netcdf_count} compressed NetCDF files** and five figures are saved in `outputs/`.
The [manifest](case_manifest.json) inventories every file and hash; the
[availability audit](availability.json), [metrics](metrics.json) and
[independent verification](verification.json) record the checks and configuration.
The [48 per-fit records](fit_records.json) include exact mode/validation settings,
input/output hashes, native-score checks and date-parsing provenance.

- [verification_scores.nc](outputs/verification_scores.nc): annual and pooled national scores for all seasons/variants.
- [calibration_gains.nc](outputs/calibration_gains.nc): deterministic gains relative to matched climatology and raw model.
- [multiyear_error_fields.nc](outputs/multiyear_error_fields.nc): spatial RMSE/MAE/bias for four- and three-year sets.
- [evaluation_footprint.nc](outputs/evaluation_footprint.nc): shared scoring cells, country weights and seasonal masks.
- [OND_training_period_bridge.nc](outputs/OND_training_period_bridge.nc): original older, revised older and recent OND forecasts/baselines.
- Each `SEASON_METHOD_PERIOD_forecasts.nc` contains four years of rainfall, tercile probabilities and prediction-error variance.
- Corresponding `hindcasts.nc` and `native_skill.nc` files preserve deterministic CV diagnostics for that fit.
- Each season has `predictors.nc`, `observations.nc`, `monthly_audit.nc` and `footprint.nc` input/audit copies.
- Each `SEASON_forecast_comparison.nc` contains all seven variants, observations and errors.

For example, [DJF_cca_1991_2020_forecasts.nc](outputs/DJF_cca_1991_2020_forecasts.nc)
contains the recent-period DJF forecasts. Select an ending-year label explicitly:

```python
import xarray as xr
with xr.open_dataset("research/cases/{ROOT.name}/outputs/DJF_cca_1991_2020_forecasts.nc") as ds:
    rainfall = ds.deterministic.where(ds.season_year ==2023, drop=True).load()
```

From the repository root in Debian:

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate pycpt-tutorial
python scripts/prepare_indonesia_all_seasons.py
python scripts/run_indonesia_all_seasons.py
```

Caches and raw CPT files remain under `{ROOT}`. Completed preparations/fits are
retained and hash-checked, so interrupted runs can resume. Use `--refresh-figures`
on the runner to regenerate plots/derived comparisons from saved data.

## Verification and limits

All **{verification['prior_artifacts_unchanged']} earlier artifacts** remain unchanged. Independent NumPy checks cover raw
bilinear interpolation, climatologies, month integration, training masks,
actual dates, annual/pooled/grid errors and all192 calibrated forecasts.
Probability bounds/sums, finite counts and nonnegative variances pass. All20
calendar/parser/aggregation/export tests pass. NetCDF exports were reopened and
compared with their decoded originals; figures were inspected separately.

The cross-year pilot exposed a CPT17 date-only initialization output that cptio
rejects. A [scoped parser helper](../../../pycpt_tutorial/cpt_dates.py) adds midnight
only for independently audited initialization dates; raw text, parsing copies and
hashes are retained. No numerical forecast values or installed-library files are
changed. Full actual initialization/start/end arrays are checked after parsing.

Adjacent seasons share two months. Four years × twelve windows are **not48
independent annual samples**, and thousands of spatial cells do not solve that
sample-size limitation. Cross-year labels can also share an initialization
calendar year. This remains a retrospective current-vintage experiment with
28-versus30 training samples and a mixed reforecast/operational archive.
No test-year tuning, significance claim or probabilistic skill claim is made;
category thresholds use the effective CPT climatological periods recorded in the
methodology audit. Longer independent/blocked
validation and predefined regional diagnostics are needed before operational
recommendations.
'''
    # Improve prose spacing without rewriting file paths, URLs or code blocks.
    import re
    lines=[]; fenced=False
    for line in report.splitlines():
        if line.startswith("```"): fenced=not fenced
        if not fenced and "](" not in line and "`" not in line and "https://" not in line:
            line=re.sub(r"(?<=[A-Za-z])(?=\d)"," ",line)
            line=re.sub(r"(?<=\d)(?=[A-Za-z])"," ",line)
            line=line.replace("CFSv 2","CFSv2").replace("CHIRPS 3","CHIRPS3")
        lines.append(line)
    (destination/"README.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    import hashlib
    summary={"recent_period_lower_pooled_rmse_seasons":counts,"lower_error_than_matched_climatology_seasons":beat_climo,"lower_error_than_raw_seasons":beat_raw,"bias_tradeoff_seasons":tradeoffs,
             "fit_records_sha256":hashlib.sha256((destination/"fit_records.json").read_bytes()).hexdigest()}
    (destination/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("REPORT_WRITTEN",destination/"README.md"); print(json.dumps(summary,indent=2))


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,help="Write a preview elsewhere while reading the frozen case inputs.")
    main(parser.parse_args().output_dir)
