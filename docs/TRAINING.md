# Training and pretraining declaration

Pretrained models are accepted. Every v1.1.6 entry must declare exactly one training regime in `entry.json`; the declaration is preserved in the verified result package and does not change any score.

| Training regime | Meaning | Required accompanying values |
|---|---|---|
| `from_scratch` | Model parameters were learned using the official target training split without an externally pretrained model. | `target_data_used: "official_train"`, `external_pretraining: false`, empty `pretraining_data` |
| `pretrained_zero_shot` | A pretrained model predicts the selected AutoCFD test suite without parameter updates on the official target training split. | `target_data_used: "none"`, `external_pretraining: true`, non-empty `pretraining_data` |
| `pretrained_official_train` | An externally pretrained model is fine-tuned using the official target training split. | `target_data_used: "official_train"`, `external_pretraining: true`, non-empty `pretraining_data` |

Name every external pretrained model, checkpoint, or dataset used. A public URL is helpful but optional:

```json
"training_regime": "pretrained_official_train",
"target_data_used": "official_train",
"external_pretraining": true,
"pretraining_data": [
  {
    "name": "Example pretrained CFD model or corpus",
    "url": "https://example.org/model-or-dataset"
  }
]
```

The official validation split may be used for model selection in the normal way, but not for parameter updates. Solution fields, force coefficients, or profiles from the selected test cases must not be used during pretraining, fine-tuning, model selection, or post-processing calibration. Every submitted method must still predict every required native surface cell, and every required native volume cell for a `surface_and_volume` entry, across the complete selected test suite.

This is a participant declaration: the evaluator checks that the metadata is complete and internally consistent, then binds it into `result.json` and the deterministic ZIP. It cannot independently reconstruct how a model or checkpoint was trained.
