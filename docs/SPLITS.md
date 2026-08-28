# Split selection

The AutoCFD organising committee asks every participant to evaluate the official `full` split as the minimum common comparison. Participants are welcome to test the other official splits too.

| Split ID | Train | Validation | Test | Case set |
|---|---:|---:|---:|---|
| `full` | 400 | 34 | 50 | Standard - requested baseline |
| `medium` | 133 | 34 | 50 | Standard |
| `scarce` | 67 | 34 | 50 | Standard |
| `super_scarce` | 11 | 34 | 50 | Standard |
| `geometry` | 339 | 48 | 97 | Geometry |
| `high_drag` | 339 | 48 | 97 | High drag |
| `low_drag` | 339 | 48 | 97 | Low drag |
| `rear_separation` | 339 | 48 | 97 | Rear separation |

Official membership and order are frozen in `contract/splits/`. For an official split, copy its ordered `test_case_ids` into `entry.json`; do not add training or validation arrays because the evaluator already has them.

## Custom splits

The organisers strongly recommend using the official splits. If you also use a split that is not listed above, give it a new safe `split_id` and include all three arrays in `entry.json`:

```json
{
  "split_id": "my-custom-study",
  "train_case_ids": ["run_1", "run_2"],
  "validation_case_ids": ["run_3"],
  "test_case_ids": ["run_4", "run_5"]
}
```

The arrays must be non-empty, unique, use `run_N` IDs from the pinned DrivAerML dataset, and be mutually disjoint. They are part of the entry identity. The evaluator writes the complete declaration to `custom-split.json`, includes it in the result ZIP, and verifies it when the package is checked.

Preview the native test files for a custom entry with:

```bash
autocfd5-aiml fetch-data \
  --entry-root my-entry \
  --destination /data/drivaerml \
  --dry-run
```
