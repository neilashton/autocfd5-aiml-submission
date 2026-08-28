# AutoCFD5 AIML submission evaluator

This private repository is the participant route for evaluating DrivAerML predictions for the AutoCFD5 AIML workshop. Participants run the evaluator themselves, inspect their own results, and deliver one verified compact ZIP to the organizers.

The scientific calculation is frozen:

- identical native DrivAerML field and force reductions;
- the approved nine-component score with 50% fields, 25% forces, and 25% profiles;
- 16 constant velocity profiles and four constant continuous Cp cuts in the score;
- 16 relative velocity profiles and four relative Cp cuts for reporting, with zero scoring weight;
- raw stair-stepped profile samples retained without smoothing;
- explicit unsupported intervals retained as separate segments and never joined;
- Cp scored using arc length, but displayed using physical streamwise `x`;
- the 209 discrete Cp taps excluded.

The metric IDs, numerical outputs, compact `result.json`, and 40-series profile output are compatible with the approved DrivAerML evaluator. Only repository-specific administrative envelopes and identities differ.

## Participant workflow

Use Linux, Python 3.12, NumPy 2.2.6, and VTK 9.5.2. A container is provided because the native-file protections rely on Linux descriptor semantics.

```bash
git clone git@github.com:neilashton/autocfd5-aiml-submission.git
cd autocfd5-aiml-submission
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
  --case-id run_419 \
  --output output/run_419.html
```

Create and immediately verify the delivery package:

```bash
autocfd5-aiml package output/my-entry --output team-method-v1.zip
autocfd5-aiml verify-package team-method-v1.zip
```

Upload the ZIP through the organizer-provided OneDrive or SharePoint File Request, then email the team ID, filename, and SHA-256 from the generated `.sha256` file. Do not open a pull request containing an entry. See [confidential delivery](docs/CONFIDENTIAL_DELIVERY.md).

## Immutable inputs

- Dataset: `neashton/drivaerml`
- Dataset revision: `7a5c0948ce27be709b1116a3a190f806e7a8f79f`
- Profile support release: `support-v1`
- Profile support ZIP SHA-256: `5ebcf744be53016bd158236d1f4af3290ff399b323c0e11a49c37ea9a6c686f6`
- Profile support index SHA-256: `f47f8c3ed7a56632b0c02a3aec793e4cd823d5d04d5264d00fcd419bf11c0f4f`

The native dataset is very large. `autocfd5-aiml fetch-data --split-id medium --destination /data/drivaerml --dry-run` shows the exact pinned files before downloading them.

Further detail is in [the scientific method](docs/SCIENTIFIC_METHOD.md) and [the organizer checklist](docs/ORGANISER_CHECKLIST.md).
