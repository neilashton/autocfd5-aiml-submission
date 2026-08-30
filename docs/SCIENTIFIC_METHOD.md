# Scientific method

## Immutable source

All native geometry and reference arrays are bound to the public DrivAerML dataset revision `7a5c0948ce27be709b1116a3a190f806e7a8f79f`. The evaluator checks exact file sizes and SHA-256 identities before using them. Surface pressure and wall shear use native polygon order and published polygon areas. Volume pressure and velocity use one equal weight per native volume cell.

## Field and force metrics

The four field errors are complete-case relative L2 percentages, macro-averaged equally across test cases:

| Component | Weight | Error cap |
|---|---:|---:|
| Surface pressure, area-weighted | 0.15 | 15% |
| Surface wall shear, area-weighted | 0.10 | 20% |
| Volume velocity, equal native cells | 0.15 | 12% |
| Volume pressure, equal native cells | 0.10 | 15% |

Forces are integrated from the predicted native surface fields. Drag R2 has weight 0.15, lift R2 has weight 0.05, and pitch-moment R2 has weight 0.05. Pitch truth is `(Clf - Clr) / 2`, matching the approved constant-reference force table.

## Regional field reports

The evaluator also partitions the same full-field predictions and native truth into four surface regions and four volume regions. These are report-only diagnostics with weight `0.0`: they require no new inference or prediction fields and do not alter any official metric, cap, weight, component score, or overall score.

Surface polygons are partitioned at face-centre `z = 0.75 m` and `|n_z| = 0.5`, producing low/high and horizontal/other regions. Volume cells use native `vtkCellCenters` parametric centres in raw-cell order. The volume regions are underbody-and-wheels, near-body-upper, near-wake, and the exhaustive upstream-and-outer complement. These are reproducible geometric bins, not audited OpenFOAM patch labels; in particular, “underbody-and-wheels” is a coarse envelope rather than an exclusive floor-boundary-layer mask. Exact coordinate definitions, half-open bounds, region order, and reconstruction requirements are frozen in [`contract/regional-diagnostics.json`](../contract/regional-diagnostics.json).

Each report retains regional additive sums and verifies that the mutually exclusive regions reconstruct the unchanged global field reduction. Relative L2, MAE, RMSE, support share, and squared-error share are reported; vector fields additionally retain component contributions, and volume velocity includes speed-magnitude and direction diagnostics. Complete-split summaries distinguish macro case means from pooled sufficient-statistic reductions and are written to `regional-diagnostics.json` alongside `result.json`.

## Profiles

Every case has 40 series:

- 16 constant-placement velocity profiles, scored with global weighted R2 at weight 0.15;
- 16 relative-placement velocity profiles, report only;
- four constant continuous native-surface Cp cuts, scored with global weighted R2 at weight 0.10;
- four relative Cp cuts, report only. Two are exact aliases of constant cuts and two use moving placement.

Within each velocity line or Cp cut, trapezoidal integration follows its scoring coordinate. Each case/profile block is normalized to unit supported length, giving cases and profiles equal weight in the global R2. Unsupported intervals are explicit segments. Integration stops at every segment boundary and therefore cannot bridge a gap.

Velocity is `magnitude(UMeanTrim) / 38.889`. Cp prediction is `2 * pMeanTrim / 38.889^2`.

Velocity truth is retained exactly as sampled from native cells. Repeated adjacent values are expected and are not smoothed. Cp scoring uses arc length. The HTML report uses the supplied physical streamwise `x` values for the horizontal axis without sorting or joining segments; display coordinates never enter scoring.

## Composite score

Each bounded field error `e` with cap `c` becomes `clip(100 * (1 - e/c), 0, 100)`. Each R2 becomes `100 * clip(R2, 0, 1)`. The nine transformed components are summed with their declared weights. Group scores are the normalized weighted means within fields, forces, and profiles.

R2 depends on variation across the complete test split. A single case therefore cannot produce an official force R2, profile R2, component score, or overall score. It can still produce its complete field errors, integrated forces, and profile losses.
