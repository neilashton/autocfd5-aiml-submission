from __future__ import annotations

import copy

import numpy as np
import pytest

from autocfd5_aiml.core.accumulators import field_chunk_statistics
from autocfd5_aiml.core.regional_diagnostics import (
    SURFACE_REGION_DEFINITION,
    VOLUME_REGION_DEFINITION,
    RegionalFieldAccumulator,
    RegionAssignmentHasher,
    build_regional_report,
)
from autocfd5_aiml.regional_aggregate import (
    RegionalAggregateError,
    aggregate_regional_diagnostics,
    build_case_regional_envelope,
    validate_aggregate_regional_diagnostics,
    validate_case_regional_envelope,
)


def _statistics(
    *,
    definition,
    labels: tuple[str, ...],
    truth: np.ndarray,
    prediction: np.ndarray,
    codes: np.ndarray,
    weights: np.ndarray,
    velocity: bool = False,
) -> dict:
    accumulator = RegionalFieldAccumulator(
        definition,
        len(codes),
        labels,
        velocity_diagnostics=velocity,
    )
    accumulator.add_chunk(0, codes, truth, prediction, weights)
    global_sums = field_chunk_statistics(
        np.arange(len(codes), dtype=np.int64), truth, prediction, weights
    )
    return accumulator.finalize(
        expected_uniform=global_sums.uniform,
        expected_physical=global_sums.physical,
    )


def _support(definition, fields: dict[str, dict], codes: np.ndarray) -> dict:
    hasher = RegionAssignmentHasher(definition, len(codes))
    hasher.add_chunk(0, codes)
    return {
        "definition": definition.to_json(),
        "definition_sha256": definition.sha256,
        "assignment": hasher.finalize(),
        "fields": fields,
    }


def _case(case_id: str, scale: float) -> dict:
    codes = np.asarray([0, 0, 1, 1, 2, 2, 3, 3], dtype=np.uint8)
    ids = np.arange(8, dtype=np.float64)
    surface_weights = np.asarray([1.0, 2.0, 1.5, 2.5, 1.2, 2.2, 1.7, 2.7])
    volume_weights = np.ones(8, dtype=np.float64)
    pressure_truth = ids + 1.0
    pressure_prediction = pressure_truth + scale * np.asarray(
        [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7, -0.8]
    )
    vector_truth = np.column_stack((ids + 2.0, ids + 3.0, ids + 4.0))
    vector_prediction = vector_truth + scale * np.asarray(
        [
            [0.1, -0.2, 0.3],
            [-0.2, 0.3, -0.4],
            [0.3, -0.4, 0.5],
            [-0.4, 0.5, -0.6],
            [0.5, -0.6, 0.7],
            [-0.6, 0.7, -0.8],
            [0.7, -0.8, 0.9],
            [-0.8, 0.9, -1.0],
        ]
    )
    surface = _support(
        SURFACE_REGION_DEFINITION,
        {
            "surface_pressure": {
                "quantity": "pMeanTrim",
                "unit": "m2 s-2",
                "primary_weighting": "physical",
                "statistics": _statistics(
                    definition=SURFACE_REGION_DEFINITION,
                    labels=("p",),
                    truth=pressure_truth,
                    prediction=pressure_prediction,
                    codes=codes,
                    weights=surface_weights,
                ),
            },
            "surface_wall_shear": {
                "quantity": "wallShearStressMeanTrim",
                "unit": "m2 s-2",
                "primary_weighting": "physical",
                "statistics": _statistics(
                    definition=SURFACE_REGION_DEFINITION,
                    labels=("x", "y", "z"),
                    truth=vector_truth,
                    prediction=vector_prediction,
                    codes=codes,
                    weights=surface_weights,
                ),
            },
        },
        codes,
    )
    volume = _support(
        VOLUME_REGION_DEFINITION,
        {
            "volume_pressure": {
                "quantity": "pMeanTrim",
                "unit": "m2 s-2",
                "primary_weighting": "equal_entity",
                "statistics": _statistics(
                    definition=VOLUME_REGION_DEFINITION,
                    labels=("p",),
                    truth=pressure_truth,
                    prediction=pressure_prediction,
                    codes=codes,
                    weights=volume_weights,
                ),
            },
            "volume_velocity": {
                "quantity": "UMeanTrim",
                "unit": "m s-1",
                "primary_weighting": "equal_entity",
                "statistics": _statistics(
                    definition=VOLUME_REGION_DEFINITION,
                    labels=("Ux", "Uy", "Uz"),
                    truth=vector_truth,
                    prediction=vector_prediction,
                    codes=codes,
                    weights=volume_weights,
                    velocity=True,
                ),
            },
        },
        codes,
    )
    case_report = build_regional_report(
        case_id=case_id,
        supports={
            SURFACE_REGION_DEFINITION.definition_id: surface,
            VOLUME_REGION_DEFINITION.definition_id: volume,
        },
    )
    additive_sums = {}
    for support in (surface, volume):
        for field_id, field in support["fields"].items():
            reconstruction = field["statistics"]["reconstruction"]
            additive_sums[field_id] = {
                "uniform": reconstruction["expected_uniform"]
            }
            if field_id.startswith("surface_"):
                additive_sums[field_id]["physical"] = reconstruction[
                    "expected_physical"
                ]
    metric_values = {}
    for field_id, sums in additive_sums.items():
        weighting = "physical" if field_id.startswith("surface_") else "uniform"
        values = sums[weighting]
        metric_values[f"{field_id}_rel_l2"] = 100.0 * np.sqrt(
            values["squared_error"] / values["squared_truth"]
        )
    envelope = build_case_regional_envelope(
        case_id=case_id,
        case_report=case_report,
        volume_geometry_audit={
            "method": "synthetic_test",
            "entity_count": len(codes),
            "region_labels": list(VOLUME_REGION_DEFINITION.region_ids),
            "region_entity_count": {
                region_id: 2 for region_id in VOLUME_REGION_DEFINITION.region_ids
            },
            "assignment_identity_sha256": volume["assignment"]["sha256"],
            "coordinate_identity_sha256": "a" * 64,
            "all_cells_assigned_exactly_once": True,
        },
        official_additive_sums=additive_sums,
    )
    return {
        "case_id": case_id,
        "core": {
            "additive_sums": additive_sums,
            "metric_values": metric_values,
            "report_only_regional_diagnostics": envelope,
        },
    }


def test_two_case_regional_aggregate_is_complete_and_zero_weight() -> None:
    documents = [_case("run_1", 1.0), _case("run_2", 2.0)]
    report = aggregate_regional_diagnostics(
        documents, case_ids=("run_1", "run_2")
    )
    validate_aggregate_regional_diagnostics(
        report, expected_case_ids=("run_1", "run_2")
    )
    assert report["scoring"]["weight"] == 0.0
    velocity = report["supports"][VOLUME_REGION_DEFINITION.definition_id]["fields"][
        "volume_velocity"
    ]
    assert len(velocity["regions"]) == 4
    assert velocity["regions"][0]["velocity"]["speed_magnitude"]["rmse"] > 0.0
    assert velocity["validation"]["pooled_is_report_only_not_official_case_reduction"]


def test_case_and_aggregate_validation_reject_incomplete_or_scored_reports() -> None:
    document = _case("run_1", 1.0)
    envelope = document["core"]["report_only_regional_diagnostics"]
    changed = copy.deepcopy(envelope)
    changed["scoring"]["weight"] = 0.01
    with pytest.raises(RegionalAggregateError, match="identity"):
        validate_case_regional_envelope(changed, expected_case_id="run_1")

    report = aggregate_regional_diagnostics([document], case_ids=("run_1",))
    missing = copy.deepcopy(report)
    missing["supports"].pop(SURFACE_REGION_DEFINITION.definition_id)
    with pytest.raises(RegionalAggregateError, match="membership"):
        validate_aggregate_regional_diagnostics(missing, expected_case_ids=("run_1",))

    wrong_assignment = copy.deepcopy(envelope)
    wrong_assignment["volume_geometry_audit"]["assignment_identity_sha256"] = "f" * 64
    with pytest.raises(RegionalAggregateError, match="assignment identity"):
        validate_case_regional_envelope(
            wrong_assignment,
            expected_case_id="run_1",
            expected_additive_sums=document["core"]["additive_sums"],
        )

    wrong_count = copy.deepcopy(envelope)
    wrong_count["volume_geometry_audit"]["region_entity_count"][
        "underbody_and_wheels"
    ] += 1
    wrong_count["volume_geometry_audit"]["region_entity_count"][
        "upstream_and_outer"
    ] -= 1
    with pytest.raises(RegionalAggregateError, match="field counts"):
        validate_case_regional_envelope(
            wrong_count,
            expected_case_id="run_1",
            expected_additive_sums=document["core"]["additive_sums"],
        )

    wrong_official_sum = copy.deepcopy(document["core"]["additive_sums"])
    wrong_official_sum["volume_velocity"]["uniform"]["squared_error"] += 1.0
    with pytest.raises(RegionalAggregateError, match="official scored"):
        validate_case_regional_envelope(
            envelope,
            expected_case_id="run_1",
            expected_additive_sums=wrong_official_sum,
        )


def test_aggregate_rejects_case_order_or_membership_difference() -> None:
    documents = [_case("run_1", 1.0), _case("run_2", 2.0)]
    with pytest.raises(RegionalAggregateError, match="membership"):
        aggregate_regional_diagnostics(documents, case_ids=("run_1", "run_3"))
