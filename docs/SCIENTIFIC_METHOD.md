# Scientific method

## Immutable source

All native geometry and reference arrays are bound to the public DrivAerML dataset revision `7a5c0948ce27be709b1116a3a190f806e7a8f79f`. The evaluator checks exact file sizes and SHA-256 identities before using them. Surface pressure and wall shear use native polygon order and published polygon areas. Volume pressure and velocity use one equal weight per native volume cell.

## Prediction scopes

The evaluator accepts two complete-split scopes. `surface_and_volume` requires all native surface and volume cells and preserves the original nine-component calculation. `surface_only` still requires every native surface cell, but never downloads, opens, or evaluates volume predictions.

For `surface_only`, the volume-velocity, volume-pressure, and velocity-profile scientific metric values are absent rather than filled with invented numbers. Their transformed component scores are exactly zero. The approved weights remain fixed, so they are not redistributed to the six available components; the maximum possible overall score is therefore 60/100.

## Field and force metrics

The four field errors are complete-case relative L2 percentages, macro-averaged equally across test cases:

| Component | Weight | Error cap |
|---|---:|---:|
| Surface pressure, area-weighted | 0.15 | 15% |
| Surface wall shear, area-weighted | 0.10 | 20% |
| Volume velocity, equal native cells | 0.15 | 12% |
| Volume pressure, equal native cells | 0.10 | 15% |

The default force route integrates coefficients from the predicted native surface fields. Alternatively, an entry may explicitly declare the `direct_coefficients` route and supply direct `Cd`, `Clf`, and `Clr` for every test case in the fixed constant-reference convention. The evaluator derives `Cl = Clf + Clr` and `CmPitch = (Clf - Clr) / 2`; it does not accept participant-supplied `Cl` or pitch values. In either route, drag R2 has weight 0.15, lift R2 has weight 0.05, and pitch-moment R2 has weight 0.05. Surface fields remain mandatory, and their integrated coefficients are retained as a report-only consistency diagnostic when direct coefficients are selected.

## Regional field reports

The evaluator partitions submitted predictions and native truth into four surface regions for both scopes and four volume regions for `surface_and_volume`. These are report-only diagnostics with weight `0.0`: they require no new inference or prediction fields and do not alter any official metric, cap, weight, component score, or overall score.

Surface polygons are partitioned at face-centre `z = 0.75 m` and `|n_z| = 0.5`, producing low/high and horizontal/other regions. Volume cells use native `vtkCellCenters` parametric centres in raw-cell order. The volume regions are underbody-and-wheels, near-body-upper, near-wake, and the exhaustive upstream-and-outer complement. These are reproducible geometric bins, not audited OpenFOAM patch labels; in particular, “underbody-and-wheels” is a coarse envelope rather than an exclusive floor-boundary-layer mask. Exact coordinate definitions, half-open bounds, region order, and reconstruction requirements are frozen in [`contract/regional-diagnostics.json`](../contract/regional-diagnostics.json).

Each report retains regional additive sums and verifies that the mutually exclusive regions reconstruct the unchanged global field reduction. Relative L2, MAE, RMSE, support share, and squared-error share are reported; vector fields additionally retain component contributions, and volume velocity includes speed-magnitude and direction diagnostics. Complete-split summaries distinguish macro case means from pooled sufficient-statistic reductions and are written to `regional-diagnostics.json` alongside `result.json`.

## Profiles

Every case retains 40 profile identities:

- 16 constant-placement velocity profiles, scored with global weighted R2 at weight 0.15 when volume is submitted;
- 16 relative-placement velocity profiles, report only when volume is submitted;
- four constant continuous native-surface Cp cuts, scored with global weighted R2 at weight 0.10;
- four relative Cp cuts, report only. Two are exact aliases of constant cuts and two use moving placement.

Within each velocity line or Cp cut, trapezoidal integration follows its scoring coordinate. Each case/profile block is normalized to unit supported length, giving cases and profiles equal weight in the global R2. Unsupported intervals are explicit segments. Integration stops at every segment boundary and therefore cannot bridge a gap.

For `surface_only`, all 32 velocity rows are explicitly marked `not_submitted_surface_only` and contain no prediction array; the constant velocity component receives zero points. Cp rows remain fully evaluated from surface pressure. For `surface_and_volume`, velocity is `magnitude(UMeanTrim) / 38.889`. Cp prediction is `2 * pMeanTrim / 38.889^2` in both scopes.

Velocity truth is retained exactly as sampled from native cells. Repeated adjacent values are expected and are not smoothed. Cp scoring uses arc length. The HTML report uses the supplied physical streamwise `x` values for the horizontal axis without sorting or joining segments; display coordinates never enter scoring.

## Composite score

Each bounded field error `e` with cap `c` becomes `clip(100 * (1 - e/c), 0, 100)`. Each available R2 becomes `100 * clip(R2, 0, 1)`. The nine transformed components are summed with their declared fixed weights. In `surface_only`, each unavailable component contributes zero to that unchanged sum. Group scores remain normalized within their original field, force, and profile group weights; unavailable components remain zero inside those groups.

R2 depends on variation across the complete test split. A single case therefore cannot produce an official force R2, profile R2, component score, or overall score. It can still produce its complete field errors, integrated forces, and profile losses.
