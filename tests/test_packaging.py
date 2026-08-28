from __future__ import annotations

from pathlib import Path

import pytest

from autocfd5_aiml.constants import (
    DATASET_REVISION,
    EVALUATOR_VERSION,
    SUPPORT_INDEX_SHA256,
    contract_root,
)
from autocfd5_aiml.core.evaluator import OFFICIAL_NATIVE_SOURCE_PIN_SHA256
from autocfd5_aiml.jsonio import read_json, sha256_file, write_json
from autocfd5_aiml.packaging import PackageError, create_package, verify_package


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
    for case_id in split["test_case_ids"]:
        write_json(
            root / "cases" / f"{case_id}.json",
            {
                "schema": "autocfd5-aiml-drivaerml-case-result-v1",
                "schema_version": 1,
                "status": "complete",
                "case_id": case_id,
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
    write_json(
        root / "result.json",
        {
            "schema": "autocfd5-aiml-drivaerml-result-v1",
            "schema_version": 1,
            "status": "complete",
            "dataset_id": "drivaerml",
            "submission": {"submission_id": "assigned-submission-id"},
            "split": {
                "split_id": split["split_id"],
                "case_set_id": split["case_set_id"],
                "official": split.get("official") is not False,
                "train_case_count": split["train_case_count"],
                "validation_case_count": split["validation_case_count"],
                "test_case_count": split["test_case_count"],
                "test_case_ids": split["test_case_ids"],
                "split_sha256": sha256_file(split_path),
                "complete_exact_membership": True,
            },
            "evaluator": {"version": EVALUATOR_VERSION},
            "inputs": {
                "dataset_revision": DATASET_REVISION,
                "profile_support_index_sha256": SUPPORT_INDEX_SHA256,
                "native_source_pin_sha256": OFFICIAL_NATIVE_SOURCE_PIN_SHA256,
                "profile_prediction_index_sha256": profile_index_identity["sha256"],
            },
            "metric_values": {
                key: 1.0
                for key in (
                    "overall_score",
                    "field_score",
                    "force_score",
                    "diagnostic_score",
                    "cd_r2",
                    "cl_r2",
                    "c_pitch_r2",
                    "velocity_profile_r2",
                    "cp_cut_r2",
                )
            },
        },
    )
    write_json(root / ".work" / "cases" / "run_1.json", {"private": "resume"})


def test_package_is_deterministic_and_verifiable(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _result_tree(root)
    first = create_package(root, tmp_path / "first.zip")
    second = create_package(root, tmp_path / "second.zip")
    assert first["sha256"] == second["sha256"]
    verified = verify_package(tmp_path / "first.zip")
    assert verified["submission_id"] == "assigned-submission-id"
    assert verified["entry_count"] == 53


def test_custom_split_is_packaged_and_verifiable(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _result_tree(root, custom=True)
    created = create_package(root, tmp_path / "custom.zip")
    verified = verify_package(tmp_path / "custom.zip")
    assert created["entry_count"] == 54
    assert verified["entry_count"] == 54


def test_package_refuses_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _result_tree(root)
    output = tmp_path / "result.zip"
    create_package(root, output)
    with pytest.raises(PackageError, match="overwrite"):
        create_package(root, output)
