from __future__ import annotations

import math
from pathlib import Path

import pytest

from autocfd5_aiml.aggregate import (
    FORCE_TRUTH_SHA256,
    AggregateError,
    aggregate_cases,
    load_force_truth,
)
from autocfd5_aiml.constants import (
    DATASET_REVISION,
    PREDICTION_SCOPE_SURFACE_ONLY,
    REGIONAL_DIAGNOSTICS_CONTRACT_SHA256,
    SCORING_CONTRACT_SHA256,
    SURFACE_ONLY_UNAVAILABLE_COMPONENTS,
    contract_root,
)
from autocfd5_aiml.core.evaluator import OFFICIAL_NATIVE_SOURCE_PIN_SHA256
from autocfd5_aiml.core.regional_diagnostics import regional_contract_projection
from autocfd5_aiml.core.source import load_native_source_pin
from autocfd5_aiml.jsonio import read_json, sha256_file, write_json
from autocfd5_aiml.scores import (
    composite_component_group_scores,
    composite_overall_score,
    composite_transformed_component_scores,
)


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
    scoring_path = contract_root() / "scoring.json"
    assert sha256_file(scoring_path) == SCORING_CONTRACT_SHA256
    scoring = read_json(scoring_path)
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


def test_surface_only_components_are_zero_without_weight_renormalization() -> None:
    scoring = read_json(contract_root() / "scoring.json")
    policy = scoring["prediction_scope_policy"][PREDICTION_SCOPE_SURFACE_ONLY]
    unavailable = tuple(sorted(SURFACE_ONLY_UNAVAILABLE_COMPONENTS))
    assert policy["unavailable_component_metric_ids"] == [
        "volume_velocity_rel_l2",
        "volume_pressure_rel_l2",
        "velocity_profile_r2",
    ]
    assert policy["component_weights_renormalized"] is False
    assert policy["maximum_overall_score"] == 60.0

    # Every submitted component is perfect. The unavailable 40% remains zero,
    # so the overall score reaches exactly 60 rather than being renormalized.
    values = {
        "surface_pressure_rel_l2": 0.0,
        "surface_wall_shear_rel_l2": 0.0,
        "cd_r2": 1.0,
        "cl_r2": 1.0,
        "c_pitch_r2": 1.0,
        "cp_cut_r2": 1.0,
    }
    components = composite_transformed_component_scores(
        values,
        scoring["overall_score_composite"],
        unavailable_metric_ids=unavailable,
    )
    assert all(components[metric_id] == 0.0 for metric_id in unavailable)
    assert (
        composite_overall_score(
            values,
            scoring["overall_score_composite"],
            unavailable_metric_ids=unavailable,
        )
        == 60.0
    )

    fabricated = {**values, "volume_pressure_rel_l2": 0.0}
    with pytest.raises(ValueError, match="must not have a fabricated metric value"):
        composite_overall_score(
            fabricated,
            scoring["overall_score_composite"],
            unavailable_metric_ids=unavailable,
        )


def test_force_truth_is_retained_for_offline_aggregate_verification() -> None:
    force_truth_path = contract_root() / "force_mom_constref_all.csv"
    assert force_truth_path.stat().st_size == 33_947
    assert sha256_file(force_truth_path) == FORCE_TRUTH_SHA256
    assert len(load_force_truth(force_truth_path)) == 484


def test_aggregate_rejects_modified_scoring_contract(tmp_path: Path) -> None:
    scoring = read_json(contract_root() / "scoring.json")
    scoring["overall_score_composite"]["components"][0]["weight"] = 0.16
    modified = tmp_path / "scoring.json"
    write_json(modified, scoring)
    with pytest.raises(AggregateError, match="scoring contract"):
        aggregate_cases(
            [],
            split_path=contract_root() / "splits" / "tiny.json",
            force_truth_path=tmp_path / "unused.csv",
            scoring_path=modified,
        )


def test_regional_diagnostics_contract_is_report_only() -> None:
    contract_path = contract_root() / "regional-diagnostics.json"
    assert sha256_file(contract_path) == REGIONAL_DIAGNOSTICS_CONTRACT_SHA256
    contract = read_json(contract_path)
    assert contract["status"] == "approved_report_only"
    assert contract["scoring"] == {
        "weight": 0.0,
        "affects_official_metric_values": False,
        "affects_component_or_overall_scores": False,
        "changes_prediction_format": False,
        "requires_new_inference": False,
    }
    assert len(contract["surface"]["region_order"]) == 4
    assert len(contract["volume"]["region_order"]) == 4
    assert contract["executable_projection"] == regional_contract_projection()


def test_repository_root_is_this_checkout() -> None:
    assert (contract_root().parent / "pyproject.toml").is_file()
    assert Path(__file__).resolve().parents[1] == contract_root().parent
