# Province analysis inputs

These inputs support province scores of the **0.05° pixel errors** of the
twelve-season case. Preparation fits no models.

- `province-context-annual.nc`: all seven forecast variants, all twelve seasons and
  the ending-year 2021-2024 labels, for the 38 provinces.
- `province-context-pooled.nc`: equal-year pooled scores; MSE is averaged before the
  square root.
- `provenance.json`: hashes, province names, and each province's pixel count and
  share of the scored area.

Each pixel's province is stored with the fields themselves, as `province_index` in
`../indonesia-seasons-2023.nc`.

`research/scripts/run_indonesia_all_seasons_005.py` keeps every native CHIRPS v3.0
pixel that overlaps the **unsimplified** supplied `idn_bnd_adm1.shp` (38 provinces;
its metadata credits BIG, modified by Benny Istanto), so coastal pixels and small
islands are included. A pixel belongs to the province that covers the largest part
of it. Because a pixel is kept only if it touches a province, every scored pixel
has one: there is no unassigned remainder. The rule is implemented in
`pycpt_tutorial.country_grid.touching_pixels`. No display simplification or
province-dependent model fitting is used.

Province scores are means of pixel errors within the province, with cosine-latitude
weights. They add no information to the forecasts, which come from a 1° model.
Tiny provinces have few pixels, and neighbouring pixels share weather, so pixel
counts are support measures, not independent sample sizes. The supplied
38-feature boundary snapshot is not certified as a current or historical official
boundary product.

Sum province MSE, MAE and bias with each province's share of the scored area to
recover the national errors. Take the square root only after combining MSE. Main
tutorial dates are centred on 2023; context dates keep their ending-year labels and
include 2023. Neither twelve overlapping seasons nor four years establishes general
operational or probabilistic forecast skill.

Source for the weighting: [Xarray cosine-latitude weighting example](https://docs.xarray.dev/en/stable/examples/area_weighted_temperature.html).
