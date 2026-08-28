# Native prediction format

Each case has separate `surface` and `volume` directories. Each contains `manifest.json` and one or more NPZ chunks.

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

The surface NPZ fields are:

- `raw_cell_id`: signed int64, shape `(rows,)`;
- `pMeanTrim`: float32 or float64, shape `(rows,)`;
- `wallShearStressMeanTrim`: float32 or float64, shape `(rows, 3)`.

The volume NPZ fields are:

- `raw_cell_id`: signed int64, shape `(rows,)`;
- `pMeanTrim`: float32 or float64, shape `(rows,)`;
- `UMeanTrim`: float32 or float64, shape `(rows, 3)`.

Every value must be finite. Raw IDs must exactly cover `[0, total_row_count)` in native order, without gaps or duplicates. Chunks normally contain at most 1,000,000 rows.

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
