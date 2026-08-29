# AutoCFD5 AIML submission evaluator

This public repository is the participant route for evaluating predictions from the [DrivAerML dataset](https://huggingface.co/datasets/neashton/drivaerml) for the AutoCFD5 AIML workshop. Participants run the evaluator themselves, inspect their own results, and deliver one verified compact ZIP confidentially to the organisers.

For the complete participant procedure, use the [formatted submission instructions](output/pdf/AutoCFD5_AIML_Submission_Instructions.pdf).

> [!IMPORTANT]
> **Complete native-cell field coverage is required.** For every selected test case, the evaluator input must contain predictions for every cell of both the pinned surface VTP and the pinned volume VTU. The surface requires `pMeanTrim` and `wallShearStressMeanTrim`; the volume requires `pMeanTrim` and `UMeanTrim`. Inference may be performed in chunks or on another representation, but the final export must map back to every native `raw_cell_id` exactly once, with no missing or duplicate cells. Surface-only, volume-only, sampled, or profiles-only results are not accepted.

The scientific calculation is frozen:

- identical native DrivAerML field and force reductions;
- the approved nine-component score with 50% fields, 25% forces, and 25% profiles;
- 16 constant velocity profiles and four constant continuous Cp cuts in the score;
- 16 relative velocity profiles and four relative Cp cuts for reporting, with zero scoring weight;
- raw stair-stepped profile samples retained without smoothing;
- explicit unsupported intervals retained as separate segments and never joined;
- Cp scored using arc length, but displayed using physical streamwise `x`;

The metric IDs, numerical outputs, compact `result.json`, and 40-series profile output are compatible with the approved DrivAerML evaluator. Only repository-specific administrative envelopes and identities differ.

## Official splits

The AutoCFD organising committee asks every participant to use the official `full` split as the minimum common comparison. Participants are welcome to test the other official splits too.

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

The organisers strongly recommend these frozen splits. For an additional custom split, `entry.json` must include complete, non-overlapping `train_case_ids`, `validation_case_ids`, and `test_case_ids` arrays. See [split selection and custom splits](docs/SPLITS.md).

## Participant workflow

Use Linux, Python 3.12, NumPy 2.2.6, and VTK 9.5.2. A container is provided because the native-file protections rely on Linux descriptor semantics.

```bash
git clone https://github.com/neilashton/autocfd5-aiml-submission.git
cd autocfd5-aiml-submission
git checkout evaluator-v1.1.2
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
autocfd5-aiml fetch-support --destination support/native-v1
```

Prepare predictions using [the native chunk format](docs/PREDICTION_FORMAT.md), copy [the entry example](examples/entry/entry.json), then validate it:

```bash
autocfd5-aiml validate-entry examples/entry
```

Evaluate the complete selected test split:

```bash
autocfd5-aiml evaluate-entry my-entry \
  --dataset-root /data/drivaerml \
  --support-root support/native-v1 \
  --output output/my-entry \
  --resume
```

One case can be checked during development with `evaluate-case`. It provides field errors, forces, and profile losses, but an official R2 or overall score requires every case in the selected test split.

Inspect any evaluated case locally:

```bash
autocfd5-aiml report \
  --result-root output/my-entry \
  --support-root support/native-v1 \
  --case-id run_11 \
  --output output/run_11.html
```

Create and immediately verify the delivery package:

```bash
autocfd5-aiml package output/my-entry --output assigned-submission-id.zip
autocfd5-aiml verify-package assigned-submission-id.zip
```

Use the submission ID sent to you by the AutoCFD organising committee. Upload the ZIP through the [AutoCFD Dropbox File Request](https://www.dropbox.com/request/A6cJNTT9egFtYiFICjAi), then email the submission ID, filename, and SHA-256 from the generated `.sha256` file. Do not open a pull request containing an entry. See [confidential delivery](docs/CONFIDENTIAL_DELIVERY.md).

Questions can be sent to `neil@neilashton.co.uk` or `astridwalle@cfdsolutions.net`, the AutoCFD5 AI/ML TFG organisers.

## Immutable inputs

- Dataset: `neashton/drivaerml`
- Dataset revision: `7a5c0948ce27be709b1116a3a190f806e7a8f79f`
- Profile support release: `support-v1`
- Profile support ZIP SHA-256: `5ebcf744be53016bd158236d1f4af3290ff399b323c0e11a49c37ea9a6c686f6`
- Profile support index SHA-256: `f47f8c3ed7a56632b0c02a3aec793e4cd823d5d04d5264d00fcd419bf11c0f4f`

The native dataset is very large. `autocfd5-aiml fetch-data --split-id full --destination /data/drivaerml --dry-run` shows the exact pinned files before downloading them. For a custom split, use `autocfd5-aiml fetch-data --entry-root my-entry --destination /data/drivaerml --dry-run`.

Further detail is in [the scientific method](docs/SCIENTIFIC_METHOD.md) and [the organiser checklist](docs/ORGANISER_CHECKLIST.md).
