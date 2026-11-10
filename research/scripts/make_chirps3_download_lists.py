"""Write exact, deduplicated daily CHIRPS3 URL lists; never download TIFF data.

Uses the saved proposed GEFS cohorts and checked CHC filename census. Optional
--check-links makes eight HEAD requests at the ends of the two date spans.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'research/audits/gefs-input-adapter'
READINESS = ROOT / 'research/audits/subseasonal-readiness'
BASE = 'https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_url(variant, day):
    return f'{BASE}/{variant}/{day.year}/chirps-v3.0.{variant}.{day:%Y.%m.%d}.tif'


def date_spans(days):
    spans = []
    for day in sorted(days):
        if not spans or day != spans[-1][1] + dt.timedelta(days=1):
            spans.append([day, day])
        else:
            spans[-1][1] = day
    return spans


def check_head(url):
    with urlopen(Request(url, method='HEAD'), timeout=30) as response:
        if response.status != 200:
            raise ValueError(f'Unexpected status {response.status}: {url}')
        return {'url': url, 'status': response.status,
                'content_length': response.headers.get('Content-Length')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=AUDIT / 'download-lists')
    parser.add_argument('--check-links', action='store_true', help='Check span endpoints using HEAD, without fetching TIFF bodies')
    args = parser.parse_args()
    coordinate_path = READINESS / 'coordinates.json'
    proposal_path = AUDIT / 'period-proposal.json'
    census_path = READINESS / 'daily-observations.json'
    coordinates = json.loads(coordinate_path.read_text())
    proposal = json.loads(proposal_path.read_text())
    census = json.loads(census_path.read_text())
    if sha(coordinate_path) != proposal['coordinate_source_sha256']:
        raise ValueError('Coordinate census differs from proposed cohort')
    epoch = dt.datetime(1960, 1, 1)
    starts = {p['kind']: [(epoch + dt.timedelta(days=v)).date()
                         for v in p['coordinates']['S']] for p in coordinates['probes']}
    hc = [d for d in starts['hindcast'] if 2000 <= d.year <= 2018]
    fc = [d for d in starts['forecast'] if 2023 <= d.year <= 2025 and d.weekday() == 2]
    if len(hc) != proposal['hindcast_initializations'] or len(fc) != proposal['forecast_initializations']:
        raise ValueError('Cohort counts differ from saved proposal')
    if not all(d.weekday() == 2 for d in hc + fc):
        raise ValueError('Expected Wednesday starts')
    # [7,14), [14,21), [21,28): all calendar dates at offsets 7 through 27.
    days = sorted({start + dt.timedelta(days=offset) for start in hc + fc for offset in range(7, 28)})
    if len(days) != proposal['candidate_unique_daily_dates_both_cohorts']:
        raise ValueError('Daily count differs from saved proposal')
    listings = {(r['variant'], r['year']): r for r in census['annual_listings']}
    spans = date_spans(days)
    files = {}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for variant in ['rnl', 'sat']:
        for day in days:
            listing = listings[(variant, day.year)]
            if (listing['status'] != 200 or str(day) in listing['missing_dates']
                    or not listing['first'] <= str(day) <= listing['last']):
                raise ValueError(f'Date not established by saved filename census: {variant} {day}')
        urls = [source_url(variant, day) for day in days]
        if len(set(urls)) != len(urls) or len({u.rsplit('/', 1)[1] for u in urls}) != len(urls):
            raise ValueError('Duplicate URLs or output filenames')
        path = args.output_dir / f'chirps3-{variant}.txt'
        path.write_text('\n'.join(urls) + '\n', encoding='ascii', newline='\n')
        files[path.name] = {'urls': len(urls), 'sha256': sha(path)}
    probes = []
    if args.check_links:
        endpoints = [source_url(v, d) for v in ['rnl', 'sat'] for span in spans for d in span]
        with ThreadPoolExecutor(max_workers=2) as pool:
            probes = list(pool.map(check_head, endpoints))
    manifest = {
        'date': '2026-11-02', 'scope': 'Download preparation for proposed cohorts; no fitting decision implied',
        'hindcast_initializations': len(hc), 'forecast_initializations': len(fc),
        'weeks': [2, 3, 4], 'daily_offsets_inclusive': [7, 27],
        'unique_dates_per_variant': len(days), 'total_tiffs': 2 * len(days),
        'date_spans_inclusive': [[str(a), str(b)] for a, b in spans],
        'files': files, 'source_sha256': {
            str(p.relative_to(ROOT)): sha(p) for p in [coordinate_path, proposal_path, census_path, Path(__file__)]},
        'filename_census_checked': census['date'], 'all_requested_dates_present_in_saved_census': True,
        'head_checks': probes, 'tiff_bodies_downloaded': 0, 'fits_run': 0,
        'estimated_total_global_tiff_gb': proposal['global_tiff_transfer_estimate_gb_from_pilot'],
        'limits': 'Filename availability only; download integrity and full-cohort pixel QC still required.'}
    (args.output_dir / 'download-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ['unique_dates_per_variant', 'total_tiffs', 'date_spans_inclusive', 'tiff_bodies_downloaded', 'fits_run']}, indent=2))


if __name__ == '__main__':
    main()
