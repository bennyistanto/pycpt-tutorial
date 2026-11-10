"""Derive candidate cohorts from saved coordinates only; never download or fit."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'research/audits/gefs-input-adapter'

def main():
    source=ROOT/'research/audits/subseasonal-readiness/coordinates.json'
    record=json.loads(source.read_text());epoch=dt.datetime(1960,1,1)
    dates={p['kind']:[(epoch+dt.timedelta(days=v)).date() for v in p['coordinates']['S']] for p in record['probes']}
    hc=[d for d in dates['hindcast'] if 2000<=d.year<=2018]
    fc=[d for d in dates['forecast'] if 2023<=d.year<=2025 and d.weekday()==2]
    assert len(hc)==len(set(hc)) and all(d.weekday()==2 for d in hc)
    folds=[]
    for year in range(2010,2019):
        cutoff=dt.date(year,1,1)
        candidates=[d for d in hc if d.year<year]
        training=[d for d in candidates if d+dt.timedelta(days=28)<=cutoff]
        validation=[d for d in hc if d.year==year]
        folds.append({'validation_initialization_year':year,'fit_label_cutoff_exclusive':str(cutoff),
            'candidate_training_initializations':len(candidates),'training_initializations_after_target_purge':len(training),
            'purged_initializations':[str(d) for d in candidates if d not in training],
            'last_training_initialization':str(training[-1]),
            'last_training_target_end_exclusive':str(training[-1]+dt.timedelta(days=28)),
            'validation_initializations':len(validation)})
    years={str(y):sum(d.year==y for d in hc) for y in range(2000,2019)}
    forecast_years={str(y):sum(d.year==y for d in fc) for y in range(2023,2026)}
    # Coordinate completeness does not establish complete fields or observations.
    for starts in [hc,fc]:
        assert all((b-a).days==7 for a,b in zip(starts,starts[1:]))
    required_days={d+dt.timedelta(days=k) for d in hc+fc for k in range(7,28)}
    preparation=json.loads((AUDIT/'preparation.json').read_text())
    mean_tiff_bytes=sum(r['source_bytes'] for r in preparation['daily_sources'])/len(preparation['daily_sources'])
    output={'date':'2026-11-02','status':'PROPOSED_NOT_SELECTED','fits_run':0,'network_requests':0,
        'coordinate_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'candidate_hindcast_period':'2000-2018','hindcast_initializations':len(hc),
        'hindcast_starts_per_year':years,'initial_candidate_training_period':'2000-2009',
        'initial_candidate_training_starts':sum(d.year<2010 for d in hc),
        'expanding_year_validation_period':'2010-2018','validation_starts_total':sum(f['validation_initializations'] for f in folds),
        'folds':folds,'candidate_final_training_period':'2000-2018',
        'candidate_archived_forecast_period':'2023-2025','forecast_initialization_day':'Wednesday',
        'forecast_starts_per_year':forecast_years,'forecast_initializations':len(fc),
        'first_forecast_initialization':str(fc[0]),'last_forecast_initialization':str(fc[-1]),
        'last_forecast_target_end_exclusive':str(fc[-1]+dt.timedelta(days=28)),
        'candidate_unique_daily_dates_both_cohorts':len(required_days),
        'candidate_daily_files_both_variants':2*len(required_days),
        'global_tiff_transfer_estimate_gb_from_pilot':round(2*len(required_days)*mean_tiff_bytes/1e9,1),
        'global_tiff_transfer_cap_bound_gb':round(2*len(required_days)*36_000_000/1e9,1),
        'full_cohort_field_or_pixel_qc_complete':False,
        'protocol':['All-year weekly starts; separate lead 2/3/4 models.',
            'At each January cutoff, remove training rows whose week-4 target ends after the cutoff; use the same retained starts at all leads.',
            'Training-only seasonal climatology, anomalies, missing-data masks, EOFs, scaling and model selection; no validation observations in preprocessing.',
            'Any mode/seasonal-window tuning requires inner time-block validation, purged for overlapping targets; freeze choices before outer-year scoring.',
            'Keep all 11 hindcast and all 31 forecast members; compare deterministic ensemble means; ensemble-size sensitivity must be predeclared.',
            'Compare raw, training-derived calendar-week climatology and calibration on identical observations/masks; also compare leads on matched target weeks.',
            'Use year/time-block uncertainty, not independent weekly-row uncertainty. No probability reliability claim from deterministic scores.',
            'CHIRPS3 Final is a retrospective reference; this is not an operational replay of the data vintages available at the historical issue time.'],
        'remaining_gates':['User agreement on cohort and validation design before fitting.',
            'Stage complete country-only source data with a reviewed download plan; verify every initialization, member, lead and daily observation.',
            'Check archive model/version provenance across 2023-2025, source consistency and train/forecast discontinuities.',
            'Freeze common support, regridding/baseline definitions and validation protocol before inspecting forecast skill.',
            'Resolve subseasonal fitter/calendar/PCR compatibility separately; input preparation does not repair the installed prototype.']}
    (AUDIT/'period-proposal.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:output[k] for k in ['status','hindcast_initializations','initial_candidate_training_starts','validation_starts_total','forecast_starts_per_year','forecast_initializations','last_forecast_target_end_exclusive','fits_run']},indent=2))

if __name__=='__main__':main()
