# Native prediction format

Every case has a `surface` directory containing `manifest.json` and one or more NPZ chunks. A `volume` directory is required only when `entry.json` declares `"prediction_scope": "surface_and_volume"`.

```text
my-entry/
  entry.json
  cases/
    run_419/
      surface/
        manifest.json
        chunks/chunk-00000.npz
      volume/
        manifest.json
        chunks/chunk-00000.npz
```

For `"prediction_scope": "surface_only"`, the case tree stops after the surface chunks; omit `volume/` entirely. Omitting `prediction_scope` preserves the legacy `surface_and_volume` behavior.

The surface NPZ fields are:

- `raw_cell_id`: signed int64, shape `(rows,)`;
- `pMeanTrim`: float32 or float64, shape `(rows,)`;
- `wallShearStressMeanTrim`: float32 or float64, shape `(rows, 3)`.

For `surface_and_volume`, the volume NPZ fields are:

- `raw_cell_id`: signed int64, shape `(rows,)`;
- `pMeanTrim`: float32 or float64, shape `(rows,)`;
- `UMeanTrim`: float32 or float64, shape `(rows, 3)`.

Evaluator v1.1.4 derives report-only regional diagnostics without adding prediction fields. It always reports surface regions and reports volume regions only for `surface_and_volume`. Participants do not run additional inference or submit region labels, coordinates, masks, or regional files.

Every supplied value must be finite. Raw IDs must exactly cover `[0, total_row_count)` in native order, without gaps or duplicates. Chunks normally contain at most 1,000,000 rows. Surface-only means a complete surface, not a sampled or partial surface. Do not create dummy volume chunks: absent volume fields are represented explicitly as unavailable and receive zero component points.

Example surface manifest:

```json
{
  "format": "drivaerml-native-prediction-chunks-candidate",
  "format_version": 1,
  "artifact_role": "local_evaluator_input_not_official_submission_artifact",
  "case_id": "run_419",
  "support_id": "surface_native_cells",
  "association": "CellData",
  "total_row_count": 7284102,
  "field_components": {
    "pMeanTrim": 1,
    "wallShearStressMeanTrim": 3
  },
  "chunks": [
    {
      "chunk_index": 0,
      "file": "chunks/chunk-00000.npz",
      "sha256": "64-lowercase-hex-characters",
      "row_count": 1000000,
      "raw_cell_id_start": 0,
      "raw_cell_id_stop": 1000000
    }
  ]
}
```

The manifest is closed: additional or missing keys fail validation. Each NPZ is hashed before its arrays are used, and file mutation during evaluation fails closed.
