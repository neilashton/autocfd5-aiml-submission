from __future__ import annotations

from pathlib import Path

import pytest

from autocfd5_aiml.constants import (
    FORCE_PREDICTION_SOURCE_DIRECT_COEFFICIENTS,
    FORCE_PREDICTION_SOURCE_FIELD_INTEGRATED,
    PREDICTION_SCOPE_FULL,
    PREDICTION_SCOPE_SURFACE_ONLY,
)
from autocfd5_aiml.entry import (
    EntryError,
    entry_force_prediction_source,
    entry_prediction_scope,
    load_entry,
)
from autocfd5_aiml.jsonio import write_json
from autocfd5_aiml.training import (
    TRAINING_REGIME_FROM_SCRATCH,
    TRAINING_REGIME_PRETRAINED_OFFICIAL_TRAIN,
    TRAINING_REGIME_PRETRAINED_ZERO_SHOT,
)


def _custom_entry() -> dict[str, object]:
    return {
        "schema": "autocfd5-aiml-entry-v1",
        "schema_version": 1,
        "submission_id": "assigned-submission-id",
        "method_name": "Example method",
        "contact_email": "participant@example.org",
        "training_regime": TRAINING_REGIME_FROM_SCRATCH,
        "target_data_used": "official_train",
        "external_pretraining": False,
        "pretraining_data": [],
        "split_id": "custom-study",
        "train_case_ids": ["run_1", "run_2"],
        "validation_case_ids": ["run_3"],
        "test_case_ids": ["run_4", "run_5"],
    }


def test_official_example_uses_only_committee_submission_id() -> None:
    root = Path(__file__).resolve().parents[1]
    entry = load_entry(root / "examples" / "entry" / "entry.json")
    assert entry["submission_id"] == "assigned-submission-id"
    assert entry["split_id"] == "full"
    assert entry_prediction_scope(entry) == PREDICTION_SCOPE_FULL
    assert entry_force_prediction_source(entry) == FORCE_PREDICTION_SOURCE_FIELD_INTEGRATED
    assert entry["training_regime"] == TRAINING_REGIME_FROM_SCRATCH
    assert "train_case_ids" not in entry
    assert "validation_case_ids" not in entry


def test_legacy_entry_defaults_to_full_and_surface_only_is_explicit(
    tmp_path: Path,
) -> None:
    legacy = _custom_entry()
    legacy_path = tmp_path / "legacy" / "entry.json"
    write_json(legacy_path, legacy)
    assert entry_prediction_scope(load_entry(legacy_path)) == PREDICTION_SCOPE_FULL

    surface_only = _custom_entry()
    surface_only["prediction_scope"] = PREDICTION_SCOPE_SURFACE_ONLY
    surface_path = tmp_path / "surface" / "entry.json"
    write_json(surface_path, surface_only)
    assert (
        entry_prediction_scope(load_entry(surface_path))
        == PREDICTION_SCOPE_SURFACE_ONLY
    )

    invalid = _custom_entry()
    invalid["prediction_scope"] = "surface_maybe"
    invalid_path = tmp_path / "invalid" / "entry.json"
    write_json(invalid_path, invalid)
    with pytest.raises(EntryError, match="prediction_scope"):
        load_entry(invalid_path)


def test_direct_force_route_is_explicit_and_closed(tmp_path: Path) -> None:
    entry = _custom_entry()
    entry["force_prediction_source"] = FORCE_PREDICTION_SOURCE_DIRECT_COEFFICIENTS
    path = tmp_path / "direct" / "entry.json"
    write_json(path, entry)
    assert entry_force_prediction_source(load_entry(path)) == (
        FORCE_PREDICTION_SOURCE_DIRECT_COEFFICIENTS
    )

    invalid = _custom_entry()
    invalid["force_prediction_source"] = "direct_maybe"
    invalid_path = tmp_path / "invalid-direct" / "entry.json"
    write_json(invalid_path, invalid)
    with pytest.raises(EntryError, match="force_prediction_source"):
        load_entry(invalid_path)


@pytest.mark.parametrize(
    ("training_regime", "target_data_used"),
    [
        (TRAINING_REGIME_PRETRAINED_ZERO_SHOT, "none"),
        (TRAINING_REGIME_PRETRAINED_OFFICIAL_TRAIN, "official_train"),
    ],
)
def test_pretrained_training_regimes_are_accepted(
    tmp_path: Path, training_regime: str, target_data_used: str
) -> None:
    entry = _custom_entry()
    entry.update(
        {
            "training_regime": training_regime,
            "target_data_used": target_data_used,
            "external_pretraining": True,
            "pretraining_data": [
                {"name": "Example pretrained CFD model", "url": "https://example.org/model"}
            ],
        }
    )
    path = tmp_path / training_regime / "entry.json"
    write_json(path, entry)

    assert load_entry(path)["training_regime"] == training_regime


@pytest.mark.parametrize(
    "updates, message",
    [
        ({"training_regime": "pretrained_maybe"}, "training_regime"),
        (
            {
                "training_regime": TRAINING_REGIME_PRETRAINED_ZERO_SHOT,
                "target_data_used": "official_train",
                "external_pretraining": True,
                "pretraining_data": ["Example checkpoint"],
            },
            "target_data_used='none'",
        ),
        (
            {
                "training_regime": TRAINING_REGIME_PRETRAINED_OFFICIAL_TRAIN,
                "target_data_used": "official_train",
                "external_pretraining": True,
                "pretraining_data": [],
            },
            "named pretraining_data",
        ),
        ({"external_pretraining": True}, "from_scratch"),
    ],
)
def test_inconsistent_training_declarations_are_rejected(
    tmp_path: Path, updates: dict[str, object], message: str
) -> None:
    entry = _custom_entry()
    entry.update(updates)
    path = tmp_path / "entry.json"
    write_json(path, entry)

    with pytest.raises(EntryError, match=message):
        load_entry(path)


def test_training_declaration_is_required(tmp_path: Path) -> None:
    entry = _custom_entry()
    del entry["training_regime"]
    path = tmp_path / "entry.json"
    write_json(path, entry)

    with pytest.raises(EntryError, match="missing"):
        load_entry(path)


def test_custom_split_requires_complete_disjoint_membership(tmp_path: Path) -> None:
    entry = _custom_entry()
    path = tmp_path / "valid" / "entry.json"
    write_json(path, entry)
    assert load_entry(path) == entry

    missing = _custom_entry()
    del missing["validation_case_ids"]
    missing_path = tmp_path / "missing" / "entry.json"
    write_json(missing_path, missing)
    with pytest.raises(EntryError, match="must declare"):
        load_entry(missing_path)

    overlapping = _custom_entry()
    overlapping["validation_case_ids"] = ["run_1"]
    overlapping_path = tmp_path / "overlapping" / "entry.json"
    write_json(overlapping_path, overlapping)
    with pytest.raises(EntryError, match="disjoint"):
        load_entry(overlapping_path)


def test_custom_split_rejects_unknown_dataset_runs(tmp_path: Path) -> None:
    entry = _custom_entry()
    entry["test_case_ids"] = ["run_999999"]
    path = tmp_path / "entry.json"
    write_json(path, entry)
    with pytest.raises(EntryError, match="outside the pinned dataset"):
        load_entry(path)


def test_official_split_rejects_custom_membership_fields(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    entry = load_entry(root / "examples" / "entry" / "entry.json")
    entry["train_case_ids"] = ["run_1"]
    entry["validation_case_ids"] = ["run_4"]
    path = tmp_path / "entry.json"
    write_json(path, entry)
    with pytest.raises(EntryError, match="official splits"):
        load_entry(path)
