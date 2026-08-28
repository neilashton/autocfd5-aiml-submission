from __future__ import annotations

import math
from pathlib import Path

from autocfd5_aiml.constants import DATASET_REVISION, contract_root
from autocfd5_aiml.core.evaluator import OFFICIAL_NATIVE_SOURCE_PIN_SHA256
from autocfd5_aiml.core.source import load_native_source_pin
from autocfd5_aiml.jsonio import read_json, sha256_file
from autocfd5_aiml.scores import composite_component_group_scores, composite_overall_score


def test_native_source_pin_and_splits_are_closed() -> None:
    pin_path = contract_root() / "native-source-pin.json"
    pin = load_native_source_pin(pin_path)
    assert sha256_file(pin_path) == OFFICIAL_NATIVE_SOURCE_PIN_SHA256
    assert pin.repository_revision == DATASET_REVISION
    assert len(pin.cases) == 484
    split_paths = sorted((contract_root() / "splits").glob("*.json"))
    assert len(split_paths) == 8
    entry_schema = read_json(contract_root() / "entry.schema.json")
    declared_official = set(
        entry_schema["allOf"][0]["if"]["properties"]["split_id"]["enum"]
    )
    assert declared_official == {path.stem for path in split_paths}
    for path in split_paths:
        split = read_json(path)
        assert split["test_case_count"] == len(split["test_case_ids"])
        assert len(split["test_case_ids"]) == len(set(split["test_case_ids"]))


def test_approved_component_weights_and_groups() -> None:
    scoring = read_json(contract_root() / "scoring.json")
    overall = scoring["overall_score_composite"]
    assert [row["weight"] for row in overall["components"]] == [
        0.15,
        0.10,
        0.15,
        0.10,
        0.15,
        0.05,
        0.05,
        0.15,
        0.10,
    ]
    assert math.isclose(sum(row["weight"] for row in overall["components"]), 1.0)
    values = {
        "surface_pressure_rel_l2": 7.5,
        "surface_wall_shear_rel_l2": 10.0,
        "volume_velocity_rel_l2": 6.0,
        "volume_pressure_rel_l2": 7.5,
        "cd_r2": 0.5,
        "cl_r2": 0.5,
        "c_pitch_r2": 0.5,
        "velocity_profile_r2": 0.5,
        "cp_cut_r2": 0.5,
    }
    groups = composite_component_group_scores(values, overall, scoring["component_score_groups"])
    assert groups == {"field_score": 50.0, "force_score": 50.0, "diagnostic_score": 50.0}
    assert composite_overall_score(values, overall) == 50.0
    assert scoring["profile_rules"]["report_only"]["weight"] == 0.0


def test_repository_root_is_this_checkout() -> None:
    assert (contract_root().parent / "pyproject.toml").is_file()
    assert Path(__file__).resolve().parents[1] == contract_root().parent
