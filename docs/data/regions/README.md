# Province analysis inputs

These inputs support province-weighted verification of the **existing 0.25° cell
errors**, not a new province-only rainfall product. Preparation fits no models.

- `province-weights.nc`: weights and support diagnostics for every supplied province
  plus any unassigned/overlap residual categories.
- `native-membership.nc`: original country-native pixel coordinates, assignments,
  membership counts, cosine-latitude weights and coarse-cell indices for auditing.
- `province-context-annual.nc`: all seven variants, all twelve seasons and original
  ending-year2021–2024 labels, using identical region weights.
- `province-context-pooled.nc`: equal-year pooled scores; MSE precedes square root.
- `provenance.json`: hashes, source files, province names and assignment audit.

`scripts/prepare_regional_verification.py` reconstructs the original country mask
from its saved boundary and original CHIRPS coordinate grid, verifying that the
native 5×5 weight sums reproduce the frozen country weights. It assigns native
pixel centres with Shapely `contains_xy` to the **unsimplified** supplied
`idn_bnd_adm1.shp`, whose metadata credits BIG, modified by Benny Istanto.
Boundary points are not assigned by this containment predicate. Pixels in no
province or multiple provinces remain distinct categories. No nearest-province
assignment, display simplification or province-dependent model fitting is used.

Coarse cells crossing borders can contribute to several provinces. The same
coarse forecast/observation errors are partitioned by native weight shares; we
do not have province-only errors inside a mixed coarse cell. Tiny provinces and
islands may be represented by only a few cells. Inspect `contributing_cells` and
`largest_cell_weight_fraction`, which are support measures, not independent
sample sizes. The supplied38-feature boundary snapshot is not certified as a
current or historical official boundary product.

Sum region MSE, MAE and bias with each region's national weight fraction to
recover national errors, retaining the residual. Take the square root only after
combining MSE. Main tutorial dates are centred on2023; context dates retain their
original ending-year labels and include2023. Neither twelve overlapping seasons
nor four years establishes general operational or probabilistic forecast skill.

Sources for implementation semantics: [Shapely containment](https://shapely.readthedocs.io/en/stable/reference/shapely.contains_xy.html),
[Xarray cosine-latitude weighting example](https://docs.xarray.dev/en/stable/examples/area_weighted_temperature.html).
