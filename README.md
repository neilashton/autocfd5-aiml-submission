# AutoCFD5 AIML submission evaluator

This public repository is the participant route for evaluating predictions from the [DrivAerML dataset](https://huggingface.co/datasets/neashton/drivaerml) for the AutoCFD5 AIML workshop. Participants run the evaluator themselves, inspect their own results, and deliver one verified compact ZIP confidentially to the organisers.

For the complete participant procedure, use the [formatted submission instructions](output/pdf/AutoCFD5_AIML_Submission_Instructions.pdf).

> [!IMPORTANT]
> **Every accepted entry must predict the complete native surface.** For every selected test case, export `pMeanTrim` and `wallShearStressMeanTrim` for every cell of the pinned surface VTP. Choose one `prediction_scope` in `entry.json`:
>
> - `surface_and_volume` (the legacy default): also export `pMeanTrim` and `UMeanTrim` for every cell of the pinned volume VTU. All nine score components are available and the maximum overall score is 100.
> - `surface_only`: omit the volume prediction directory. Volume pressure, volume velocity, and velocity-profile component scores are fixed at zero; their scientific metric values are not fabricated, weights are not renormalized, and the maximum overall score is 60.
>
> In either scope, inference may run in chunks or on another representation, but each supplied field must map back to every native `raw_cell_id` exactly once, with no missing or duplicate cells. Volume-only, sampled, partial-surface, or profiles-only results are not accepted.

The scientific calculation is frozen:

- identical native DrivAerML field and force reductions;
- the approved nine-component score with 50% fields, 25% forces, and 25% profiles;
- 16 constant velocity profiles and four constant continuous Cp cuts in the score;
- 16 relative velocity profiles and four relative Cp cuts for reporting, with zero scoring weight;
- raw stair-stepped profile samples retained without smoothing;
- explicit unsupported intervals retained as separate segments and never joined;
- Cp scored using arc length, but displayed using physical streamwise `x`;
- four-region surface reports for every entry and four-region volume reports for full-field entries, derived from submitted native-cell fields with zero scoring weight.

The regional reports reuse the predictions supplied in the selected scope, so they require no new inference or participant fields. They do not change official metric values, scoring caps, weights, component scores, or overall score. The exact report-only partitions are frozen in [`contract/regional-diagnostics.json`](contract/regional-diagnostics.json), and complete-split results retain their compact aggregate in `regional-diagnostics.json`.

The scored metric IDs, numerical outputs, compact `result.json`, and 40-series profile output remain compatible with the approved DrivAerML evaluator. Only repository-specific administrative envelopes, identities, and report-only diagnostics differ.

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
git checkout evaluator-v1.1.5
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

Set `prediction_scope` explicitly to `surface_and_volume` or `surface_only`. Existing entries that omit it retain the full-field `surface_and_volume` behavior. To fetch only the native inputs needed by a surface-only entry, set the scope first and use:

```bash
autocfd5-aiml fetch-data --entry-root my-entry \
  --destination /data/drivaerml --dry-run
```

### Optional direct force coefficients

The default `"force_prediction_source": "field_integrated"` scores force coefficients reduced from your submitted surface fields, exactly as in v1.1.4. If your method also predicts force coefficients directly, set `"force_prediction_source": "direct_coefficients"` in `entry.json` and add this small complete file for every test case:

```text
my-entry/cases/run_419/direct-force-coefficients.json
```

```json
{
  "schema": "autocfd5-aiml-drivaerml-direct-force-v1",
  "schema_version": 1,
  "case_id": "run_419",
  "coefficient_convention": "drivaerml-constant-reference-v1",
  "Cd": 0.21,
  "Clf": -0.061,
  "Clr": 0.046
}
```

Use the evaluator's fixed constant-reference convention. Supply only `Cd`, `Clf`, and `Clr`; it derives `Cl = Clf + Clr` and `CmPitch = (Clf - Clr) / 2`. The declared direct values are used only for the existing three force R2 components. The native-field force reduction is still calculated, packaged, and reported alongside it. All field, profile, and regional diagnostics continue to use the submitted native fields. Existing v1.1.4 ZIPs remain valid; moving to this route does not require repeating field inference.

Evaluate the complete selected test split:

```bash
autocfd5-aiml evaluate-entry my-entry \
  --dataset-root /data/drivaerml \
  --support-root support/native-v1 \
  --output output/my-entry \
  --resume
```

One case can be checked during development with `evaluate-case`. For a surface-only case, add `--prediction-scope surface_only` and omit `--volume-manifest`. It provides available field errors, forces, profile losses, explicit unavailable components, and zero-weight regional reports, but an official R2 or overall score requires every case in the selected test split.

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
- Retained force truth: pinned dataset `force_mom_constref_all.csv`, SHA-256 `4e9e003da38ccdcacad359451079888361eae221d3c8dad7fd5682250d257865`
- Profile support release: `support-v1`
- Profile support ZIP SHA-256: `5ebcf744be53016bd158236d1f4af3290ff399b323c0e11a49c37ea9a6c686f6`
- Profile support index SHA-256: `f47f8c3ed7a56632b0c02a3aec793e4cd823d5d04d5264d00fcd419bf11c0f4f`
- Report-only regional diagnostics contract SHA-256: `2bfd372817989112642056e4c76cfb418dbdcee445c57ee20ca37ee9ca158583`

The native dataset is very large. `autocfd5-aiml fetch-data --split-id full --prediction-scope surface_and_volume --destination /data/drivaerml --dry-run` shows the exact pinned files before downloading them. Use `--prediction-scope surface_only` to omit native volume parts, or use `--entry-root my-entry` to read both the case membership and scope from `entry.json`.

For `surface_and_volume`, the v1.1.5 volume-region pass uses temporary raw geometry spools and processes topology in blocks of at most one million cells. Allow roughly 9 GiB of local temporary space per concurrently evaluated case; set `TMPDIR` to suitable local scratch when `/tmp` is too small. Temporary files are removed on both success and failure. Surface-only evaluation never downloads or opens the native volume and does not need this volume scratch allowance.

Further detail is in [the scientific method](docs/SCIENTIFIC_METHOD.md) and [the organiser checklist](docs/ORGANISER_CHECKLIST.md).
