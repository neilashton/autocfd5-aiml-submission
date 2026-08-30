from __future__ import annotations

from pathlib import Path

import pytest
from test_regional_aggregate import _case as _regional_case

from autocfd5_aiml.aggregate import aggregate_cases, load_force_truth
from autocfd5_aiml.constants import (
    DATASET_REVISION,
    EVALUATOR_VERSION,
    REGIONAL_DIAGNOSTICS_CONTRACT_SHA256,
    SCORING_CONTRACT_SHA256,
    SUPPORT_INDEX_SHA256,
    contract_root,
)
from autocfd5_aiml.core.evaluator import OFFICIAL_NATIVE_SOURCE_PIN_SHA256
from autocfd5_aiml.jsonio import read_json, sha256_file, write_json
from autocfd5_aiml.packaging import PackageError, create_package, verify_package
from autocfd5_aiml.regional_aggregate import aggregate_regional_diagnostics
from autocfd5_aiml.scores import (
    composite_component_group_scores,
    composite_overall_score,
)


def _profile_statistics(case_index: int) -> dict[str, object]:
    def blocks(count: int, offset: float) -> list[list[float]]:
        result = []
        for station_index in range(count):
            truth_mean = offset + case_index / 100.0 + station_index / 10.0
            result.append([truth_mean, truth_mean**2 + 1.0, 0.0])
        return result

    return {
        "velocity_profile_r2_blocks": blocks(16, 1.0),
        "cp_cut_r2_blocks": blocks(4, -1.0),
    }


def _recompute_published_scores(result: dict[str, object]) -> None:
    scoring = read_json(contract_root() / "scoring.json")
    metrics = result["metric_values"]
    metrics.update(
        composite_component_group_scores(
            metrics,
            scoring["overall_score_composite"],
            scoring["component_score_groups"],
        )
    )
    metrics["overall_score"] = composite_overall_score(
        metrics, scoring["overall_score_composite"]
    )


def _result_tree(root: Path, *, custom: bool = False) -> None:
    split_path = contract_root() / "splits" / "medium.json"
    split = read_json(split_path)
    if custom:
        split = {
            "schema": "autocfd5-aiml-drivaerml-split-v1",
            "schema_version": 1,
            "dataset_id": "drivaerml",
            "split_id": "custom-study",
            "split_label": "Participant custom: custom-study",
            "case_set_id": "participant_custom",
            "official": False,
            "train_case_count": 2,
            "train_case_ids": ["run_1", "run_2"],
            "validation_case_count": 1,
            "validation_case_ids": ["run_3"],
            "test_case_count": split["test_case_count"],
            "test_case_ids": split["test_case_ids"],
        }
        split_path = root / "custom-split.json"
        write_json(split_path, split)
    regional_documents = [
        _regional_case(case_id, 1.0 + index / 100.0)
        for index, case_id in enumerate(split["test_case_ids"])
    ]
    force_truth = load_force_truth(contract_root() / "force_mom_constref_all.csv")
    for index, regional_document in enumerate(regional_documents):
        case_id = regional_document["case_id"]
        truth = force_truth[case_id]
        regional_document["core"]["force_coefficients"] = {
            "Cd": truth["cd"],
            "Cl": truth["cl"],
            "CmPitch": truth["c_pitch"],
            "Clf": truth["clf"],
            "Clr": truth["clr"],
        }
        regional_document["profiles"] = {
            "metric_statistics": _profile_statistics(index)
        }
        write_json(
            root / "cases" / f"{case_id}.json",
            {
                "schema": "autocfd5-aiml-drivaerml-case-result-v2",
                "schema_version": 2,
                "status": "complete",
                "case_id": case_id,
                "core": regional_document["core"],
                "profiles": regional_document["profiles"],
            },
        )
    chunk_path = root / "profiles" / "chunk-000.json"
    write_json(
        chunk_path,
        {
            "schema": "autocfd5-aiml-profile-prediction-chunk-v1",
            "schema_version": 1,
            "case_count": split["test_case_count"],
            "case_ids": split["test_case_ids"],
            "series_per_case": 40,
            "cases": [
                {"case_id": case_id, "series": [{} for _ in range(40)]}
                for case_id in split["test_case_ids"]
            ],
        },
    )
    profile_index_identity = write_json(
        root / "profiles" / "index.json",
        {
            "case_count": split["test_case_count"],
            "chunks": [
                {
                    "path": "profiles/chunk-000.json",
                    "case_ids": split["test_case_ids"],
                    "sha256": sha256_file(chunk_path),
                    "size_bytes": chunk_path.stat().st_size,
                }
            ],
        },
    )
    regional_identity = write_json(
        root / "regional-diagnostics.json",
        aggregate_regional_diagnostics(
            regional_documents,
            case_ids=split["test_case_ids"],
        ),
    )
    result = aggregate_cases(
        regional_documents,
        split_path=split_path,
        force_truth_path=contract_root() / "force_mom_constref_all.csv",
        scoring_path=contract_root() / "scoring.json",
    )
    result["submission"] = {"submission_id": "assigned-submission-id"}
    result["evaluator"] = {"version": EVALUATOR_VERSION}
    result["inputs"] = {
        "dataset_revision": DATASET_REVISION,
        "profile_support_index_sha256": SUPPORT_INDEX_SHA256,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "native_source_pin_sha256": OFFICIAL_NATIVE_SOURCE_PIN_SHA256,
        "profile_prediction_index_sha256": profile_index_identity["sha256"],
        "regional_diagnostics_contract_sha256": (
            REGIONAL_DIAGNOSTICS_CONTRACT_SHA256
        ),
        "regional_diagnostics_report_sha256": regional_identity["sha256"],
    }
    write_json(root / "result.json", result)
    write_json(root / ".work" / "cases" / "run_1.json", {"private": "resume"})


def test_package_is_deterministic_and_verifiable(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _result_tree(root)
    first = create_package(root, tmp_path / "first.zip")
    second = create_package(root, tmp_path / "second.zip")
    assert first["sha256"] == second["sha256"]
    verified = verify_package(tmp_path / "first.zip")
    assert verified["submission_id"] == "assigned-submission-id"
    assert verified["entry_count"] == 54


def test_custom_split_is_packaged_and_verifiable(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _result_tree(root, custom=True)
    created = create_package(root, tmp_path / "custom.zip")
    verified = verify_package(tmp_path / "custom.zip")
    assert created["entry_count"] == 55
    assert verified["entry_count"] == 55


def test_package_refuses_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _result_tree(root)
    output = tmp_path / "result.zip"
    create_package(root, output)
    with pytest.raises(PackageError, match="overwrite"):
        create_package(root, output)


def test_package_rejects_score_not_reproduced_by_frozen_contract(
    tmp_path: Path,
) -> None:
    root = tmp_path / "result"
    _result_tree(root)
    result = read_json(root / "result.json")
    result["metric_values"]["overall_score"] += 1.0
    write_json(root / "result.json", result)
    package = tmp_path / "changed-score.zip"
    create_package(root, package)
    with pytest.raises(PackageError, match="official aggregate metrics"):
        verify_package(package)


@pytest.mark.parametrize("metric_id", ["cd_r2", "velocity_profile_r2"])
def test_package_rejects_aggregate_input_tampering_with_coherent_scores(
    tmp_path: Path,
    metric_id: str,
) -> None:
    root = tmp_path / "result"
    _result_tree(root)
    result = read_json(root / "result.json")
    result["metric_values"][metric_id] = 0.25
    _recompute_published_scores(result)
    write_json(root / "result.json", result)
    package = tmp_path / f"changed-{metric_id}.zip"
    create_package(root, package)
    with pytest.raises(PackageError, match="official aggregate metrics"):
        verify_package(package)


def test_package_rejects_aggregate_not_reproduced_by_packaged_cases(
    tmp_path: Path,
) -> None:
    root = tmp_path / "result"
    _result_tree(root)
    report_path = root / "regional-diagnostics.json"
    report = read_json(report_path)
    definition_id = "drivaerml-volume-four-geometric-regions-v1"
    report["supports"][definition_id]["assignments"][0]["sha256"] = "f" * 64
    identity = write_json(report_path, report)
    result = read_json(root / "result.json")
    result["inputs"]["regional_diagnostics_report_sha256"] = identity["sha256"]
    write_json(root / "result.json", result)
    package = tmp_path / "changed-regional-aggregate.zip"
    create_package(root, package)
    with pytest.raises(PackageError, match="differs from packaged cases"):
        verify_package(package)


def test_package_rejects_regional_sums_not_bound_to_official_case_sums(
    tmp_path: Path,
) -> None:
    root = tmp_path / "result"
    _result_tree(root)
    case_path = root / "cases" / "run_11.json"
    case = read_json(case_path)
    case["core"]["additive_sums"]["volume_velocity"]["uniform"][
        "squared_error"
    ] += 1.0
    write_json(case_path, case)
    package = tmp_path / "changed-case-sums.zip"
    create_package(root, package)
    with pytest.raises(PackageError, match="official scored"):
        verify_package(package)
