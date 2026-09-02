from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .constants import (
    FORCE_PREDICTION_SOURCE_DIRECT_COEFFICIENTS,
    FORCE_PREDICTION_SOURCE_FIELD_INTEGRATED,
    FORCE_PREDICTION_SOURCES,
    PREDICTION_SCOPE_FULL,
    PREDICTION_SCOPE_SURFACE_ONLY,
    PREDICTION_SCOPES,
    SCORING_CONTRACT_SHA256,
    SURFACE_ONLY_UNAVAILABLE_COMPONENTS,
)
from .jsonio import read_json, sha256_file
from .profiles import r2_from_block_statistics
from .scores import (
    composite_component_group_scores,
    composite_overall_score,
    composite_transformed_component_scores,
)

RESULT_SCHEMA = "autocfd5-aiml-drivaerml-result-v2"
FORCE_TRUTH_SHA256 = "4e9e003da38ccdcacad359451079888361eae221d3c8dad7fd5682250d257865"
PRIMARY_FIELD_METRICS = (
    "surface_pressure_rel_l2",
    "surface_wall_shear_rel_l2",
    "volume_velocity_rel_l2",
    "volume_pressure_rel_l2",
)
_FORCE_COEFFICIENT_IDS = ("Cd", "Cl", "CmPitch", "Clf", "Clr")


class AggregateError(ValueError):
    """Raised when case results cannot form one exact split result."""


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise AggregateError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise AggregateError(f"{label} must be a finite number") from error
    if not math.isfinite(result):
        raise AggregateError(f"{label} must be a finite number")
    return result


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise AggregateError("mean requires at least one value")
    return math.fsum(values) / len(values)


def _rmse(errors: Sequence[float]) -> float:
    return math.sqrt(_mean([value * value for value in errors]))


def _r2(truth: Sequence[float], prediction: Sequence[float]) -> float:
    if len(truth) != len(prediction) or len(truth) < 2:
        raise AggregateError("R2 requires at least two aligned cases")
    truth_mean = _mean(list(truth))
    denominator = math.fsum((value - truth_mean) ** 2 for value in truth)
    if denominator <= 0.0:
        raise AggregateError("R2 truth values are constant")
    numerator = math.fsum(
        (actual - predicted) ** 2 for actual, predicted in zip(truth, prediction, strict=True)
    )
    return 1.0 - numerator / denominator


def load_force_truth(path: Path | str) -> dict[str, dict[str, float]]:
    source = Path(path)
    if sha256_file(source) != FORCE_TRUTH_SHA256:
        raise AggregateError("force truth table differs from its approved SHA-256")
    rows: dict[str, dict[str, float]] = {}
    with source.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["run", "cd", "cl", "clf", "clr", "cs"]:
            raise AggregateError("force truth table columns differ")
        for offset, row in enumerate(reader, start=2):
            try:
                run = int(row["run"])
            except (TypeError, ValueError) as error:
                raise AggregateError(f"force truth row {offset} has an invalid run") from error
            case_id = f"run_{run}"
            if case_id in rows:
                raise AggregateError(f"force truth repeats {case_id}")
            values = {
                key: _finite(row[key], f"force truth {case_id}.{key}")
                for key in ("cd", "cl", "clf", "clr", "cs")
            }
            values["c_pitch"] = (values["clf"] - values["clr"]) / 2.0
            rows[case_id] = values
    return rows


def _split(path: Path | str) -> tuple[dict[str, Any], tuple[str, ...], str]:
    document = read_json(path)
    if document.get("schema") != "autocfd5-aiml-drivaerml-split-v1":
        raise AggregateError("split schema differs")
    case_ids = document.get("test_case_ids")
    if (
        not isinstance(case_ids, list)
        or not case_ids
        or any(not isinstance(value, str) for value in case_ids)
        or len(case_ids) != len(set(case_ids))
        or document.get("test_case_count") != len(case_ids)
    ):
        raise AggregateError("split test cases are invalid")
    return document, tuple(case_ids), sha256_file(path)


def _force_coefficients(
    value: object, *, case_id: str, label: str
) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise AggregateError(f"{case_id} has no {label} force coefficients")
    return {
        coefficient: _finite(value.get(coefficient), f"{case_id}.{coefficient}")
        for coefficient in _FORCE_COEFFICIENT_IDS
    }


def _case_force_predictions(
    case: Mapping[str, Any], *, case_id: str
) -> tuple[str, dict[str, float], dict[str, float]]:
    """Return declared scoring values and the always-retained field reduction.

    Missing ``force_prediction`` is accepted only here for v1.1.4 compact
    results.  New evaluator output always carries the explicit envelope.
    """

    core = case.get("core")
    if not isinstance(core, Mapping):
        raise AggregateError(f"{case_id} has no core result")
    field_integrated = _force_coefficients(
        core.get("force_coefficients"), case_id=case_id, label="integrated"
    )
    prediction = case.get("force_prediction")
    if prediction is None:
        return FORCE_PREDICTION_SOURCE_FIELD_INTEGRATED, field_integrated, field_integrated
    if not isinstance(prediction, Mapping):
        raise AggregateError(f"{case_id} force prediction envelope differs")
    source = prediction.get("source")
    if source not in FORCE_PREDICTION_SOURCES:
        raise AggregateError(f"{case_id} force prediction source differs")
    retained_field = _force_coefficients(
        prediction.get("field_integrated_force_coefficients"),
        case_id=case_id,
        label="retained integrated",
    )
    if retained_field != field_integrated:
        raise AggregateError(f"{case_id} retained integrated force coefficients differ")
    selected = _force_coefficients(
        prediction.get("scoring_force_coefficients"),
        case_id=case_id,
        label="scoring",
    )
    if source == FORCE_PREDICTION_SOURCE_FIELD_INTEGRATED and selected != field_integrated:
        raise AggregateError(f"{case_id} field-integrated scoring coefficients differ")
    return str(source), selected, field_integrated


def aggregate_cases(
    case_documents: Sequence[Mapping[str, Any]],
    *,
    split_path: Path | str,
    force_truth_path: Path | str,
    scoring_path: Path | str,
) -> dict[str, Any]:
    try:
        scoring_sha256 = sha256_file(scoring_path)
    except OSError as error:
        raise AggregateError("cannot read the approved scoring contract") from error
    if scoring_sha256 != SCORING_CONTRACT_SHA256:
        raise AggregateError("scoring contract differs from this evaluator build")
    split, case_ids, split_sha256 = _split(split_path)
    if len(case_documents) != len(case_ids):
        raise AggregateError("case result count differs from the selected test split")
    by_id: dict[str, Mapping[str, Any]] = {}
    for document in case_documents:
        case_id = document.get("case_id")
        if not isinstance(case_id, str) or case_id in by_id:
            raise AggregateError("case results must have unique case IDs")
        by_id[case_id] = document
    if set(by_id) != set(case_ids):
        raise AggregateError("case result membership differs from the selected test split")

    ordered = [by_id[case_id] for case_id in case_ids]
    prediction_scopes = {case.get("prediction_scope") for case in ordered}
    if len(prediction_scopes) != 1:
        raise AggregateError("case results use different prediction scopes")
    prediction_scope = prediction_scopes.pop()
    if prediction_scope not in PREDICTION_SCOPES:
        raise AggregateError("case result prediction scope differs")
    unavailable_metric_ids = (
        tuple(sorted(SURFACE_ONLY_UNAVAILABLE_COMPONENTS))
        if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
        else ()
    )

    field_values: dict[str, float] = {}
    field_metric_ids = (
        PRIMARY_FIELD_METRICS[:2]
        if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
        else PRIMARY_FIELD_METRICS
    )
    for metric_id in field_metric_ids:
        field_values[metric_id] = _mean(
            [
                _finite(
                    case.get("core", {}).get("metric_values", {}).get(metric_id),
                    f"{case_ids[index]}.{metric_id}",
                )
                for index, case in enumerate(ordered)
            ]
        )

    truth_table = load_force_truth(force_truth_path)
    force_truth: dict[str, list[float]] = {key: [] for key in _FORCE_COEFFICIENT_IDS}
    force_prediction: dict[str, list[float]] = {key: [] for key in force_truth}
    field_force_prediction: dict[str, list[float]] = {
        key: [] for key in force_truth
    }
    force_sources: set[str] = set()
    for case_id, case in zip(case_ids, ordered, strict=True):
        if case_id not in truth_table:
            raise AggregateError(f"force truth has no row for {case_id}")
        truth = truth_table[case_id]
        source, predicted, field_predicted = _case_force_predictions(case, case_id=case_id)
        force_sources.add(source)
        mapping = {"Cd": "cd", "Cl": "cl", "CmPitch": "c_pitch", "Clf": "clf", "Clr": "clr"}
        for target, column in mapping.items():
            force_truth[target].append(truth[column])
            force_prediction[target].append(predicted[target])
            field_force_prediction[target].append(field_predicted[target])
    if len(force_sources) != 1:
        raise AggregateError("case results use different force prediction sources")
    force_prediction_source = force_sources.pop()

    force_errors = {
        target: [
            predicted - truth
            for truth, predicted in zip(force_truth[target], force_prediction[target], strict=True)
        ]
        for target in force_truth
    }
    field_force_errors = {
        target: [
            predicted - truth
            for truth, predicted in zip(
                force_truth[target], field_force_prediction[target], strict=True
            )
        ]
        for target in force_truth
    }
    force_values = {
        "field_integrated_cd_rmse": _rmse(field_force_errors["Cd"]),
        "field_integrated_cl_rmse": _rmse(field_force_errors["Cl"]),
        "field_integrated_cmpitch_rmse": _rmse(field_force_errors["CmPitch"]),
        "field_integrated_clf_rmse": _rmse(field_force_errors["Clf"]),
        "field_integrated_clr_rmse": _rmse(field_force_errors["Clr"]),
        "field_integrated_lift_closure_max_abs": max(
            abs(cl - (clf + clr))
            for cl, clf, clr in zip(
                field_force_prediction["Cl"],
                field_force_prediction["Clf"],
                field_force_prediction["Clr"],
                strict=True,
            )
        ),
        "cd_r2": _r2(force_truth["Cd"], force_prediction["Cd"]),
        "cl_r2": _r2(force_truth["Cl"], force_prediction["Cl"]),
        "c_pitch_r2": _r2(force_truth["CmPitch"], force_prediction["CmPitch"]),
    }
    if force_prediction_source == FORCE_PREDICTION_SOURCE_DIRECT_COEFFICIENTS:
        force_values.update(
            {
                "direct_force_cd_rmse": _rmse(force_errors["Cd"]),
                "direct_force_cl_rmse": _rmse(force_errors["Cl"]),
                "direct_force_cmpitch_rmse": _rmse(force_errors["CmPitch"]),
                "direct_vs_field_cd_rmse": _rmse(
                    [
                        direct - field
                        for direct, field in zip(
                            force_prediction["Cd"],
                            field_force_prediction["Cd"],
                            strict=True,
                        )
                    ]
                ),
                "direct_vs_field_cl_rmse": _rmse(
                    [
                        direct - field
                        for direct, field in zip(
                            force_prediction["Cl"],
                            field_force_prediction["Cl"],
                            strict=True,
                        )
                    ]
                ),
                "direct_vs_field_cmpitch_rmse": _rmse(
                    [
                        direct - field
                        for direct, field in zip(
                            force_prediction["CmPitch"],
                            field_force_prediction["CmPitch"],
                            strict=True,
                        )
                    ]
                ),
            }
        )

    velocity_blocks: list[list[float]] = []
    cp_blocks: list[list[float]] = []
    relative_velocity_blocks: list[list[float]] = []
    relative_cp_blocks: list[list[float]] = []
    profile_means: dict[str, list[float]] = {
        "velocity_profile_uinf_rmse": [],
        "velocity_profile_experimental_subset_uinf_rmse": [],
        "cp_cut_rmse": [],
        "relative_velocity_profile_uinf_rmse": [],
        "relative_cp_cut_rmse": [],
    }
    for case_id, case in zip(case_ids, ordered, strict=True):
        statistics = case.get("profiles", {}).get("metric_statistics")
        if not isinstance(statistics, Mapping):
            raise AggregateError(f"{case_id} has no profile statistics")
        for block in statistics.get("velocity_profile_r2_blocks", []):
            velocity_blocks.append([_finite(value, f"{case_id} velocity block") for value in block])
        for block in statistics.get("cp_cut_r2_blocks", []):
            cp_blocks.append([_finite(value, f"{case_id} Cp block") for value in block])
        for block in statistics.get("relative_velocity_profile_r2_blocks", []):
            relative_velocity_blocks.append(
                [_finite(value, f"{case_id} relative velocity block") for value in block]
            )
        for block in statistics.get("relative_cp_cut_r2_blocks", []):
            relative_cp_blocks.append(
                [_finite(value, f"{case_id} relative Cp block") for value in block]
            )
        for metric_id in profile_means:
            if metric_id in statistics:
                profile_means[metric_id].append(
                    _finite(statistics[metric_id], f"{case_id}.{metric_id}")
                )
    expected_velocity_blocks = (
        0
        if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
        else 16 * len(case_ids)
    )
    if len(velocity_blocks) != expected_velocity_blocks or len(cp_blocks) != 4 * len(case_ids):
        raise AggregateError("constant profile block coverage differs")
    profile_values = {
        "cp_cut_r2": r2_from_block_statistics(cp_blocks),
        **{
            metric_id: _mean(values)
            for metric_id, values in profile_means.items()
            if len(values) == len(case_ids)
        },
    }
    if prediction_scope == PREDICTION_SCOPE_FULL:
        profile_values["velocity_profile_r2"] = r2_from_block_statistics(
            velocity_blocks
        )
    if len(relative_velocity_blocks) == 16 * len(case_ids):
        profile_values["relative_velocity_profile_r2"] = r2_from_block_statistics(
            relative_velocity_blocks
        )
    if len(relative_cp_blocks) == 4 * len(case_ids):
        profile_values["relative_cp_cut_r2"] = r2_from_block_statistics(relative_cp_blocks)

    values = {**field_values, **force_values, **profile_values}
    scoring = read_json(scoring_path)
    overall = scoring.get("overall_score_composite")
    groups = scoring.get("component_score_groups")
    if not isinstance(overall, Mapping) or not isinstance(groups, Mapping):
        raise AggregateError("scoring declaration is incomplete")
    component_scores = composite_transformed_component_scores(
        values,
        overall,
        unavailable_metric_ids=unavailable_metric_ids,
    )
    values.update(
        composite_component_group_scores(
            values,
            overall,
            groups,
            unavailable_metric_ids=unavailable_metric_ids,
        )
    )
    values["overall_score"] = composite_overall_score(
        values,
        overall,
        unavailable_metric_ids=unavailable_metric_ids,
    )
    published = {metric_id: round(value, 12) for metric_id, value in values.items()}
    published_component_scores = {
        metric_id: round(value, 12)
        for metric_id, value in component_scores.items()
    }
    return {
        "schema": RESULT_SCHEMA,
        "schema_version": 2,
        "status": "complete",
        "dataset_id": "drivaerml",
        "prediction_scope": prediction_scope,
        "force_prediction_source": force_prediction_source,
        "split": {
            "split_id": split["split_id"],
            "case_set_id": split["case_set_id"],
            "official": split.get("official") is not False,
            "train_case_count": split["train_case_count"],
            "validation_case_count": split["validation_case_count"],
            "test_case_count": len(case_ids),
            "test_case_ids": list(case_ids),
            "split_sha256": split_sha256,
            "complete_exact_membership": True,
        },
        "metric_values": published,
        "component_scores": published_component_scores,
        "component_availability": {
            metric_id: (
                "not_submitted_zero_score"
                if metric_id in unavailable_metric_ids
                else "available"
            )
            for metric_id in published_component_scores
        },
        "scoring": {
            "field_weight": 0.50,
            "force_weight": 0.25,
            "profile_weight": 0.25,
            "constant_profiles_scored": True,
            "relative_profiles_weight": 0.0,
            "prediction_scope": prediction_scope,
            "force_prediction_source": force_prediction_source,
            "unavailable_component_metric_ids": list(unavailable_metric_ids),
            "unavailable_component_score": 0.0,
            "component_weights_renormalized": False,
            "unavailable_metric_values_fabricated": False,
            "maximum_attainable_overall_score": (
                60.0
                if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
                else 100.0
            ),
        },
    }


__all__ = ["AggregateError", "aggregate_cases", "load_force_truth"]
