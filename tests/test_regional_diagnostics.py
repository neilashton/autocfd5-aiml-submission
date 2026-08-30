from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np
import pytest

from autocfd5_aiml.core.accumulators import StreamingFieldAccumulator
from autocfd5_aiml.core.regional_diagnostics import (
    REGION_DEFINITIONS,
    SURFACE_REGION_DEFINITION,
    VELOCITY_DIRECTION_MIN_SPEED_M_PER_S,
    VOLUME_REGION_DEFINITION,
    RegionalDiagnosticError,
    RegionalFieldAccumulator,
    RegionAssignmentHasher,
    build_regional_report,
    canonical_json_bytes,
    classify_surface_geometry,
    surface_region_codes,
    validate_reconstruction,
    validate_regional_field_report,
    validate_regional_report,
    volume_region_codes,
)


def _global_statistics(
    truth: np.ndarray,
    prediction: np.ndarray,
    weights: np.ndarray,
    chunks: tuple[tuple[int, int], ...],
):
    component_count = 1 if truth.ndim == 1 else truth.shape[1]
    accumulator = StreamingFieldAccumulator(
        len(truth), component_count=component_count
    )
    for start, stop in chunks:
        accumulator.add_chunk(
            np.arange(start, stop, dtype=np.int64),
            truth[start:stop],
            prediction[start:stop],
            weights[start:stop],
        )
    return accumulator.finalize()


def _scalar_report():
    codes = np.asarray([0, 1, 2, 3, 0, 1, 2, 3], dtype=np.uint8)
    truth = np.asarray([1.0, 2.0, 3.0, 4.0, 2.0, 3.0, 4.0, 5.0])
    prediction = truth + np.asarray([0.1, -0.2, 0.3, -0.4, 0.2, -0.3, 0.4, -0.5])
    weights = np.asarray([1.0, 2.0, 3.0, 4.0, 1.5, 2.5, 3.5, 4.5])
    chunks = ((0, 3), (3, 8))
    global_statistics = _global_statistics(truth, prediction, weights, chunks)
    accumulator = RegionalFieldAccumulator(
        SURFACE_REGION_DEFINITION,
        len(truth),
        ("p",),
    )
    for start, stop in chunks:
        accumulator.add_chunk(
            start,
            codes[start:stop],
            truth[start:stop],
            prediction[start:stop],
            weights[start:stop],
        )
    report = accumulator.finalize(
        expected_uniform=global_statistics.uniform,
        expected_physical=global_statistics.physical,
    )
    return report, global_statistics, codes


def _support(
    *,
    definition,
    assignment: dict[str, object],
    statistics: dict[str, object],
) -> dict[str, object]:
    return {
        "definition": definition.to_json(),
        "definition_sha256": definition.sha256,
        "assignment": assignment,
        "fields": {
            "surface_pressure": {
                "quantity": "pMeanTrim",
                "unit": "m2 s-2",
                "primary_weighting": "physical",
                "statistics": statistics,
            }
        },
    }


def test_release_definitions_are_closed_and_canonically_hashed() -> None:
    assert tuple(REGION_DEFINITIONS) == (
        "drivaerml-surface-four-geometric-regions-v1",
        "drivaerml-volume-four-geometric-regions-v1",
    )
    assert SURFACE_REGION_DEFINITION.region_ids == (
        "low_z_horizontal_normal",
        "low_z_other_normal",
        "high_z_horizontal_normal",
        "high_z_other_normal",
    )
    assert VOLUME_REGION_DEFINITION.region_ids == (
        "underbody_and_wheels",
        "near_body_upper",
        "near_wake",
        "upstream_and_outer",
    )
    for definition in REGION_DEFINITIONS.values():
        assert [rule.code for rule in definition.rules] == [0, 1, 2, 3]
        assert definition.sha256 == hashlib.sha256(
            canonical_json_bytes(definition.to_json())
        ).hexdigest()
        assert len(definition.sha256) == 64
        assert definition.to_json()["scoring_weight"] == 0.0


def test_surface_classifier_uses_exact_boundaries_and_absolute_normal() -> None:
    z = np.asarray([0.749, 0.749, 0.75, 0.75, -1.0, 10.0])
    signed_nz = np.asarray([0.5, 0.499, -0.5, -0.499, -1.0, 0.0])
    assert surface_region_codes(z, signed_nz).tolist() == [0, 1, 2, 3, 0, 3]

    centres = np.column_stack((np.zeros(6), np.zeros(6), z))
    areas = np.asarray([2.0] * 6)
    vectors = np.column_stack((np.zeros(6), np.zeros(6), signed_nz * areas))
    assert classify_surface_geometry(centres, vectors, areas).tolist() == [
        0,
        1,
        2,
        3,
        0,
        3,
    ]
    with pytest.raises(RegionalDiagnosticError, match="outside"):
        surface_region_codes([0.0], [1.01])
    with pytest.raises(RegionalDiagnosticError, match="positive"):
        classify_surface_geometry([[0, 0, 0]], [[0, 0, 0]], [0])


def test_volume_classifier_matches_validated_cartesian_partition() -> None:
    centres = np.asarray(
        [
            [-0.85, 0.0, 0.749],
            [3.649, -1.249, 0.75],
            [3.65, 1.999, 2.499],
            [3.65, 2.0, 0.0],
            [-0.851, 0.0, 0.0],
            [6.0, 0.0, 0.0],
            [0.0, 1.25, 1.0],
            [0.0, 0.0, 2.0],
        ],
        dtype=np.float64,
    )
    assert volume_region_codes(centres).tolist() == [0, 1, 2, 3, 3, 3, 3, 3]
    with pytest.raises(RegionalDiagnosticError, match="finite"):
        volume_region_codes([[math.nan, 0.0, 0.0]])


def test_assignment_identity_is_chunk_independent_and_fails_on_gaps() -> None:
    codes = np.asarray([0, 1, 2, 3, 3, 2, 1, 0], dtype=np.uint8)
    one = RegionAssignmentHasher(SURFACE_REGION_DEFINITION, len(codes))
    one.add_chunk(0, codes)
    identity_one = one.finalize()

    split = RegionAssignmentHasher(SURFACE_REGION_DEFINITION, len(codes))
    split.add_chunk(0, codes[:3])
    split.add_chunk(3, codes[3:])
    identity_split = split.finalize()
    assert identity_one == identity_split
    assert identity_one["sha256"] == (
        "6277490bb56cbab7c00affbb598680cb912c3c65738a2deb3a89b94344db0fe0"
    )

    incomplete = RegionAssignmentHasher(SURFACE_REGION_DEFINITION, len(codes))
    incomplete.add_chunk(0, codes[:3])
    with pytest.raises(RegionalDiagnosticError, match="cover"):
        incomplete.finalize()
    with pytest.raises(RegionalDiagnosticError, match="native order"):
        incomplete.add_chunk(4, codes[4:])
    with pytest.raises(RegionalDiagnosticError, match=r"\[0, 3\]"):
        RegionAssignmentHasher(SURFACE_REGION_DEFINITION, 1).add_chunk(0, [4])


def test_scalar_regions_reconstruct_both_official_weightings() -> None:
    report, global_statistics, _ = _scalar_report()
    assert report["entity_count"] == 8
    assert [row["entity_count"] for row in report["regions"]] == [2, 2, 2, 2]
    assert math.fsum(row["physical_weight_fraction"] for row in report["regions"]) == 1.0
    assert report["reconstruction"]["matches_expected_global_sums"] is True
    validate_reconstruction(
        report,
        expected_uniform=global_statistics.uniform,
        expected_physical=global_statistics.physical,
    )
    first = report["regions"][0]
    assert first["equal_entity"]["component_squared_error"]["p"] == pytest.approx(
        0.05
    )
    assert first["physical"]["rmse"] > 0.0
    assert first["physical"]["fraction_of_case_squared_error"] > 0.0
    validate_regional_field_report(report, SURFACE_REGION_DEFINITION)

    false_fraction = copy.deepcopy(report)
    false_fraction["regions"][0]["physical"][
        "fraction_of_case_squared_error"
    ] = 0.125
    with pytest.raises(RegionalDiagnosticError, match="fraction_of_case_squared_error"):
        validate_regional_field_report(false_fraction, SURFACE_REGION_DEFINITION)

    extra_inner_key = copy.deepcopy(report)
    extra_inner_key["regions"][0]["equal_entity"]["fabricated"] = 0.0
    with pytest.raises(RegionalDiagnosticError, match="equal_entity keys differ"):
        validate_regional_field_report(extra_inner_key, SURFACE_REGION_DEFINITION)

    negative_component_sum = copy.deepcopy(report)
    negative_component_sum["regions"][0]["equal_entity"][
        "component_squared_error"
    ]["p"] = -1.0
    with pytest.raises(RegionalDiagnosticError, match="component sums"):
        validate_regional_field_report(
            negative_component_sum,
            SURFACE_REGION_DEFINITION,
        )

    bad = copy.deepcopy(report)
    bad["reconstruction"]["reconstructed_physical"]["squared_error"] *= 2.0
    with pytest.raises(RegionalDiagnosticError, match="reconstruction differs"):
        validate_reconstruction(
            bad,
            expected_uniform=global_statistics.uniform,
            expected_physical=global_statistics.physical,
        )


def test_vector_components_reconstruct_region_vector_error() -> None:
    codes = np.asarray([0, 1, 2, 3], dtype=np.uint8)
    truth = np.asarray(
        [[2.0, 1.0, 0.5], [3.0, 0.0, 1.0], [4.0, 1.0, 2.0], [5.0, 2.0, 1.0]]
    )
    prediction = truth + np.asarray(
        [[1.0, 2.0, 3.0], [-1.0, 0.5, 0.25], [0.5, -0.5, 1.0], [2.0, 1.0, -1.0]]
    )
    weights = np.asarray([1.0, 2.0, 3.0, 4.0])
    global_statistics = _global_statistics(truth, prediction, weights, ((0, 4),))
    accumulator = RegionalFieldAccumulator(
        SURFACE_REGION_DEFINITION, 4, ("x", "y", "z")
    )
    accumulator.add_chunk(0, codes, truth, prediction, weights)
    report = accumulator.finalize(
        expected_uniform=global_statistics.uniform,
        expected_physical=global_statistics.physical,
    )
    for region in report["regions"]:
        values = region["physical"]
        assert math.fsum(values["component_squared_error"].values()) == pytest.approx(
            values["squared_error"]
        )
        assert math.fsum(
            value for value in values["component_fraction_of_region_squared_error"].values()
        ) == pytest.approx(1.0)


def test_velocity_magnitude_and_direction_are_separate_additive_diagnostics() -> None:
    codes = np.asarray([0, 0, 1, 1, 2, 2, 3, 3], dtype=np.uint8)
    truth = np.asarray(
        [
            [2.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 2.0, 0.0],
            [0.0, 0.0, 2.0],
            [2.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 2.0, 0.0],
            [0.0, 2.0, 0.0],
        ]
    )
    prediction = np.asarray(
        [
            [0.0, 2.0, 0.0],  # same speed, 90 degrees
            [2.0, 0.0, 0.0],  # truth below direction threshold
            [0.0, 2.0, 0.0],  # exact
            [0.0, 0.0, -2.0],  # opposite direction
            [3.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
            [0.0, 2.0, 0.0],
        ]
    )
    weights = np.ones(8)
    global_statistics = _global_statistics(truth, prediction, weights, ((0, 5), (5, 8)))
    accumulator = RegionalFieldAccumulator(
        VOLUME_REGION_DEFINITION,
        8,
        ("Ux", "Uy", "Uz"),
        velocity_diagnostics=True,
    )
    accumulator.add_chunk(0, codes[:5], truth[:5], prediction[:5])
    accumulator.add_chunk(5, codes[5:], truth[5:], prediction[5:])
    report = accumulator.finalize(
        expected_uniform=global_statistics.uniform,
        expected_physical=global_statistics.physical,
    )
    region_zero = report["regions"][0]
    assert region_zero["velocity"]["speed_magnitude"]["squared_error"] == 1.0
    assert region_zero["equal_entity"]["squared_error"] == 9.0
    direction = region_zero["velocity"]["direction"]
    assert direction["minimum_speed_m_per_s"] == VELOCITY_DIRECTION_MIN_SPEED_M_PER_S
    assert direction["defined_entity_count"] == 1
    assert direction["mean_cosine_similarity"] == pytest.approx(0.0)
    assert direction["mean_angular_error_degrees"] == pytest.approx(90.0)
    assert report["regions"][1]["velocity"]["direction"][
        "mean_angular_error_degrees"
    ] == pytest.approx(90.0)
    validate_regional_field_report(
        report,
        VOLUME_REGION_DEFINITION,
        field_id="volume_velocity",
    )

    false_threshold = copy.deepcopy(report)
    false_threshold["regions"][0]["velocity"]["direction"][
        "minimum_speed_m_per_s"
    ] = 2.0
    with pytest.raises(RegionalDiagnosticError, match="threshold differs"):
        validate_regional_field_report(
            false_threshold,
            VOLUME_REGION_DEFINITION,
            field_id="volume_velocity",
        )

    false_direction_definition = copy.deepcopy(report)
    false_direction_definition["regions"][0]["velocity"]["direction"][
        "definition"
    ] = "some fast cells"
    with pytest.raises(RegionalDiagnosticError, match="direction definition differs"):
        validate_regional_field_report(
            false_direction_definition,
            VOLUME_REGION_DEFINITION,
            field_id="volume_velocity",
        )

    missing_velocity = copy.deepcopy(report)
    missing_velocity["regions"][0].pop("velocity")
    with pytest.raises(RegionalDiagnosticError, match="row 0 keys differ"):
        validate_regional_field_report(
            missing_velocity,
            VOLUME_REGION_DEFINITION,
            field_id="volume_velocity",
        )

    extra_direction_key = copy.deepcopy(report)
    extra_direction_key["regions"][0]["velocity"]["direction"]["fabricated"] = 0
    with pytest.raises(RegionalDiagnosticError, match="direction diagnostic keys differ"):
        validate_regional_field_report(
            extra_direction_key,
            VOLUME_REGION_DEFINITION,
            field_id="volume_velocity",
        )

    extra_magnitude_key = copy.deepcopy(report)
    extra_magnitude_key["regions"][0]["velocity"]["speed_magnitude"][
        "fabricated"
    ] = 0.0
    with pytest.raises(RegionalDiagnosticError, match="magnitude diagnostic keys differ"):
        validate_regional_field_report(
            extra_magnitude_key,
            VOLUME_REGION_DEFINITION,
            field_id="volume_velocity",
        )

    negative_speed_sum = copy.deepcopy(report)
    negative_speed_sum["regions"][0]["velocity"]["speed_magnitude"][
        "absolute_error"
    ] = -1.0
    with pytest.raises(RegionalDiagnosticError, match="magnitude additive sums"):
        validate_regional_field_report(
            negative_speed_sum,
            VOLUME_REGION_DEFINITION,
            field_id="volume_velocity",
        )


def test_accumulator_rejects_gaps_bad_codes_and_incomplete_expected_sums() -> None:
    accumulator = RegionalFieldAccumulator(
        SURFACE_REGION_DEFINITION, 4, ("scalar",)
    )
    with pytest.raises(RegionalDiagnosticError, match="native order"):
        accumulator.add_chunk(1, [0], [1.0], [1.0], [1.0])
    with pytest.raises(RegionalDiagnosticError, match=r"\[0, 3\]"):
        accumulator.add_chunk(0, [4], [1.0], [1.0], [1.0])
    accumulator.add_chunk(0, [0], [1.0], [1.1], [1.0])
    with pytest.raises(RegionalDiagnosticError, match="cover"):
        accumulator.finalize()

    complete = RegionalFieldAccumulator(
        SURFACE_REGION_DEFINITION, 4, ("scalar",)
    )
    complete.add_chunk(0, [0, 1, 2, 3], [1, 2, 3, 4], [1, 2, 3, 4])
    with pytest.raises(RegionalDiagnosticError, match="supplied together"):
        complete.finalize(expected_uniform={})


def test_strict_case_report_binds_definition_assignment_and_zero_weight() -> None:
    statistics, _, codes = _scalar_report()
    hasher = RegionAssignmentHasher(SURFACE_REGION_DEFINITION, len(codes))
    hasher.add_chunk(0, codes)
    support = _support(
        definition=SURFACE_REGION_DEFINITION,
        assignment=hasher.finalize(),
        statistics=statistics,
    )
    report = build_regional_report(
        case_id="run_419",
        supports={SURFACE_REGION_DEFINITION.definition_id: support},
    )
    validate_regional_report(
        report,
        expected_case_id="run_419",
        required_definition_ids=[SURFACE_REGION_DEFINITION.definition_id],
    )
    encoded = canonical_json_bytes(report)
    assert json.loads(encoded)["scoring"]["weight"] == 0.0

    bad_weight = copy.deepcopy(report)
    bad_weight["scoring"]["weight"] = 0.01
    with pytest.raises(RegionalDiagnosticError, match="scoring boundary"):
        validate_regional_report(bad_weight)

    bad_definition = copy.deepcopy(report)
    key = SURFACE_REGION_DEFINITION.definition_id
    bad_definition["supports"][key]["definition_sha256"] = "0" * 64
    with pytest.raises(RegionalDiagnosticError, match="definition hash"):
        validate_regional_report(bad_definition)

    bad_assignment = copy.deepcopy(report)
    bad_assignment["supports"][key]["assignment"]["sha256"] = "not-a-hash"
    with pytest.raises(RegionalDiagnosticError, match="assignment identity"):
        validate_regional_report(bad_assignment)

    bad_assignment_encoding = copy.deepcopy(report)
    bad_assignment_encoding["supports"][key]["assignment"]["encoding"] = "uint8"
    with pytest.raises(RegionalDiagnosticError, match="assignment identity"):
        validate_regional_report(bad_assignment_encoding)

    fabricated_metadata = copy.deepcopy(report)
    fabricated_metadata["supports"][key]["fields"]["surface_pressure"][
        "quantity"
    ] = "CpMeanTrim"
    with pytest.raises(RegionalDiagnosticError, match="metadata differs"):
        validate_regional_report(fabricated_metadata)

    fabricated_components = copy.deepcopy(report)
    fabricated_components["supports"][key]["fields"]["surface_pressure"][
        "statistics"
    ]["component_labels"] = ["pressure"]
    with pytest.raises(RegionalDiagnosticError, match="component labels/order"):
        validate_regional_report(fabricated_components)

    wrong_support = copy.deepcopy(report)
    support = wrong_support["supports"].pop(key)
    support["definition"] = VOLUME_REGION_DEFINITION.to_json()
    support["definition_sha256"] = VOLUME_REGION_DEFINITION.sha256
    support["assignment"]["definition_sha256"] = VOLUME_REGION_DEFINITION.sha256
    wrong_support["supports"] = {VOLUME_REGION_DEFINITION.definition_id: support}
    with pytest.raises(RegionalDiagnosticError, match="different support definition"):
        validate_regional_report(wrong_support)

    missing_region = copy.deepcopy(report)
    missing_region["supports"][key]["fields"]["surface_pressure"]["statistics"][
        "regions"
    ].pop()
    with pytest.raises(RegionalDiagnosticError, match="exactly four"):
        validate_regional_report(missing_region)


def test_nonfinite_reports_fail_closed() -> None:
    statistics, _, _ = _scalar_report()
    statistics["regions"][0]["physical"]["rmse"] = math.nan
    with pytest.raises(RegionalDiagnosticError, match="finite JSON number"):
        validate_regional_field_report(statistics, SURFACE_REGION_DEFINITION)
    with pytest.raises(RegionalDiagnosticError, match="finite JSON"):
        canonical_json_bytes({"bad": math.inf})
