"""Document the executed provincial comparison from its saved numeric outputs."""
from pathlib import Path
import csv
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/assets/seasonal-2023'


def main():
    summary=json.loads((OUT/'regional-findings.json').read_text())
    audit=json.loads((ROOT/'research/audits/regional-2023/verification.json').read_text())
    counts=list(csv.DictReader((OUT/'province-improvement-counts.csv').open()))
    c=summary['province_counts']
    support=list(csv.DictReader((OUT/'province-support.csv').open()))
    province_names=json.loads((ROOT/'docs/data/regions/provenance.json').read_text())['province_names']
    small=min((r for r in support if r['Region'] in province_names),key=lambda r:int(r['Contributing coarse cells']))
    text=f'''# Province-weighted verification of the Indonesia seasonal case

Completed 2026-11-01 from frozen CFSv2/CHIRPS3 forecasts. No CPT refits,
model tuning, changes to national evaluation masks or new observation downloads.

## Design and footprint

All 38 supplied provinces are retained. Analysis uses the original unsimplified
`idn_bnd_adm1.shp`; the simplified GeoJSON remains a display layer. Native0.05°
country-pixel centres inherit the original cosine-latitude weights, partitioned
into each province within the existing0.25° cells. A shared coarse cell retains
the same forecast/observation error in every participating province. These are
province-weighted coarse-cell errors, not newly reconstructed province rainfall.

Of {audit['native_points']:,} native country pixels in the evaluation footprint,
{audit['unassigned_points']:,} are not contained in any province: **{audit['unassigned_country_weight_percent']:.4f}%**
of original country weight. They remain an explicit residual category. There
are {audit['overlap_points']} multiply assigned pixels. Region-plus-residual MSE,
MAE and bias recombine to national scores; RMSE follows the square root of MSE.

Main windows have midpoints in2023, so NDJ uses ending-year2024. The context uses
the original ending-year2021–2024 labels and includes2023; it is not an independent
confirmation set. Equal-year pooled errors average MSE before taking its square
root. All seven variants include raw CFSv2, both period climatologies and both
CCA/PCR fits (1983–2010 and1991–2020).

## Number of provinces beating1991–2020 climatology

These counts refer to recent-period CCA/PCR only. No significance or independence
claim follows from the counts; overlapping seasons and correlated regions are
not independent annual samples.

| Season |2023 CCA|2023 PCR|Four-year pooled CCA|Four-year pooled PCR|
| --- | ---: | ---: | ---: | ---: |
'''
    text+=''.join('| '+' | '.join(row.values())+' |\n' for row in counts)
    text+=f'''
OND 2023 improves over climatology in {c['2023 CCA']['OND']} provinces for CCA and {c['2023 PCR']['OND']} for PCR. In JJA 2023,
the counts are {c['2023 CCA']['JJA']} and {c['2023 PCR']['JJA']} provinces, whereas pooled context counts are {c['Four-year CCA']['JJA']} and {c['Four-year PCR']['JJA']}. A single
target year therefore gives a different regional picture from the four-year context.

![2023 province comparisons](../../docs/assets/seasonal-2023/province-gains-2023.png)

![Four-year province context](../../docs/assets/seasonal-2023/province-gains-context.png)

## Spatial and scientific limits

{small['Region']} has only {small['Contributing coarse cells']} contributing coarse cells; its largest cell carries {float(small['Largest single-cell share (%)']):.2f}% of
its province weight. Support counts and maximum single-cell fractions are
reported for every region. They are not independent sample sizes. Administrative
boundaries are the supplied snapshot, not certified current or historical limits.
No operational, probabilistic-reliability, drought, planting or onset claim is made.

## Outputs and audit

- [Executed notebook](../../docs/notebooks/indonesia-seasons-2023.ipynb)
- [2023 province scores NetCDF](../../docs/assets/seasonal-2023/province-verification-2023.nc)
- [All four methods: OND province table](../../docs/assets/seasonal-2023/province-ond-2023-rmse.csv)
- [Annual context NetCDF](../../docs/data/regions/province-context-annual.nc)
- [Pooled context NetCDF](../../docs/data/regions/province-context-pooled.nc)
- [Weights and support](../../docs/data/regions/province-weights.nc)
- [Assignment provenance](../../docs/data/regions/provenance.json)
- [Independent NumPy verification](../audits/regional-2023/verification.json)
- [Assignment methods and limits](../../docs/data/regions/README.md)

All {audit['annual_region_variant_season_comparisons']:,} region/year/variant/season combinations were checked independently.
Five original tutorial input NetCDFs remain byte-identical; the broader protected
research inventory is checked by scripts/verify_tutorial.py. Regression tests
cover shared-cell conservation, MSE pooling, missing support and grid mismatch.
'''
    # Numerical claims come from the executed notebook and independent audit.
    (ROOT/'research/reports/REGIONAL_VERIFICATION.md').write_text(text)
    print('Wrote research/reports/REGIONAL_VERIFICATION.md')


if __name__=='__main__': main()
