from __future__ import annotations

import platform
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .aggregate import aggregate_cases
from .case_evaluator import CASE_RESULT_SCHEMA, evaluate_case
from .constants import (
    DATASET_REVISION,
    EVALUATOR_VERSION,
    FORCE_PREDICTION_SOURCE_DIRECT_COEFFICIENTS,
    FORCE_PREDICTION_SOURCE_FIELD_INTEGRATED,
    FORCE_PREDICTION_SOURCES,
    PREDICTION_SCOPE_FULL,
    PREDICTION_SCOPE_SURFACE_ONLY,
    PREDICTION_SCOPES,
    REGIONAL_DIAGNOSTICS_CONTRACT_SHA256,
    SCORING_CONTRACT_SHA256,
    SUPPORT_INDEX_SHA256,
    contract_root,
)
from .direct_forces import (
    DIRECT_FORCE_FILE_NAME,
    DirectForceError,
    load_direct_force_coefficients,
)
from .jsonio import read_json, sha256_file, write_json
from .regional_aggregate import (
    RegionalAggregateError,
    aggregate_regional_diagnostics,
    validate_case_regional_envelope,
)

ENTRY_SCHEMA = "autocfd5-aiml-entry-v1"
PROFILE_CHUNK_SCHEMA = "autocfd5-aiml-profile-prediction-chunk-v1"
PROFILE_INDEX_SCHEMA = "autocfd5-aiml-profile-prediction-index-v1"
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}\Z")
_ENTRY_KEYS = {
    "schema",
    "schema_version",
    "submission_id",
    "method_name",
    "contact_email",
    "split_id",
    "prediction_scope",
    "force_prediction_source",
    "train_case_ids",
    "validation_case_ids",
    "test_case_ids",
    "prediction_artifact",
}


class EntryError(ValueError):
    """Raised when an entry or its exact output is invalid."""


def entry_prediction_scope(entry: Mapping[str, Any]) -> str:
    """Return the explicit scope, preserving full-field behavior for legacy entries."""

    value = entry.get("prediction_scope", PREDICTION_SCOPE_FULL)
    if value not in PREDICTION_SCOPES:
        raise EntryError(
            "prediction_scope must be 'surface_and_volume' or 'surface_only'"
        )
    return str(value)


def entry_force_prediction_source(entry: Mapping[str, Any]) -> str:
    """Return the declared force route, retaining pre-v1.1.5 field behavior."""

    value = entry.get(
        "force_prediction_source", FORCE_PREDICTION_SOURCE_FIELD_INTEGRATED
    )
    if value not in FORCE_PREDICTION_SOURCES:
        raise EntryError(
            "force_prediction_source must be 'field_integrated' or "
            "'direct_coefficients'"
        )
    return str(value)


def _clean_text(value: object, label: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise EntryError(f"{label} must be a non-empty string of at most {maximum} characters")
    return value.strip()


def _case_id_array(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(case_id, str) or re.fullmatch(r"run_[1-9][0-9]*", case_id) is None
            for case_id in value
        )
        or len(value) != len(set(value))
    ):
        raise EntryError(f"{label} must be a non-empty unique array of run_N IDs")
    return value


def _known_dataset_case_ids() -> set[str]:
    document = read_json(contract_root() / "native-source-pin.json")
    cases = document.get("cases")
    if not isinstance(cases, list):
        raise EntryError("native source pin has no case list")
    result = {
        case.get("case_id")
        for case in cases
        if isinstance(case, Mapping) and isinstance(case.get("case_id"), str)
    }
    if len(result) != len(cases):
        raise EntryError("native source pin case IDs are invalid")
    return result


def load_entry(path: Path | str) -> dict[str, Any]:
    document = read_json(path)
    if document.get("schema") != ENTRY_SCHEMA or document.get("schema_version") != 1:
        raise EntryError("entry.json schema differs")
    required = _ENTRY_KEYS - {
        "prediction_artifact",
        "prediction_scope",
        "force_prediction_source",
        "train_case_ids",
        "validation_case_ids",
    }
    if set(document) - _ENTRY_KEYS or required - set(document):
        raise EntryError("entry.json contains missing or unknown keys")
    submission_id = document.get("submission_id")
    if not isinstance(submission_id, str) or _SAFE_ID.fullmatch(submission_id) is None:
        raise EntryError(
            "submission_id must use lowercase letters, digits, dots, dashes or underscores"
        )
    _clean_text(document.get("method_name"), "method_name")
    contact = _clean_text(document.get("contact_email"), "contact_email")
    if contact.count("@") != 1 or contact.startswith("@") or contact.endswith("@"):
        raise EntryError("contact_email is invalid")
    split_id = document.get("split_id")
    if not isinstance(split_id, str) or _SAFE_ID.fullmatch(split_id) is None:
        raise EntryError("split_id is invalid")
    entry_prediction_scope(document)
    entry_force_prediction_source(document)
    test_case_ids = _case_id_array(document.get("test_case_ids"), "test_case_ids")
    official_split_path = contract_root() / "splits" / f"{split_id}.json"
    custom_fields = {"train_case_ids", "validation_case_ids"} & set(document)
    if official_split_path.is_file():
        if custom_fields:
            raise EntryError("official splits must use the frozen train, validation and test membership")
        official_split = read_json(official_split_path)
        if test_case_ids != official_split.get("test_case_ids"):
            raise EntryError("entry test case order or membership differs from the official split")
    else:
        if custom_fields != {"train_case_ids", "validation_case_ids"}:
            raise EntryError(
                "a custom split must declare train_case_ids and validation_case_ids"
            )
        train_case_ids = _case_id_array(document.get("train_case_ids"), "train_case_ids")
        validation_case_ids = _case_id_array(
            document.get("validation_case_ids"), "validation_case_ids"
        )
        if (
            set(train_case_ids) & set(validation_case_ids)
            or set(train_case_ids) & set(test_case_ids)
            or set(validation_case_ids) & set(test_case_ids)
        ):
            raise EntryError("custom split train, validation and test case IDs must be disjoint")
        unknown = (
            set(train_case_ids) | set(validation_case_ids) | set(test_case_ids)
        ) - _known_dataset_case_ids()
        if unknown:
            raise EntryError(
                "custom split contains run IDs outside the pinned dataset: "
                + ", ".join(sorted(unknown))
            )
    artifact = document.get("prediction_artifact")
    if artifact is not None:
        if not isinstance(artifact, Mapping):
            raise EntryError("prediction_artifact must be an object")
        if set(artifact) != {"private_immutable_url", "size_bytes", "sha256"}:
            raise EntryError("prediction_artifact contains missing or unknown keys")
        digest = artifact.get("sha256")
        if (
            not isinstance(artifact.get("private_immutable_url"), str)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(artifact.get("size_bytes"), int)
            or artifact["size_bytes"] < 1
        ):
            raise EntryError("prediction_artifact requires a private URL, size and SHA-256")
    return document


def _field_force_coefficients(case_result: Mapping[str, Any], case_id: str) -> dict[str, Any]:
    core = case_result.get("core")
    if not isinstance(core, Mapping):
        raise EntryError(f"{case_id} has no core force reduction")
    coefficients = core.get("force_coefficients")
    if not isinstance(coefficients, Mapping):
        raise EntryError(f"{case_id} has no integrated force coefficients")
    required = ("Cd", "Cl", "CmPitch", "Clf", "Clr")
    if any(key not in coefficients for key in required):
        raise EntryError(f"{case_id} integrated force coefficients are incomplete")
    return {key: coefficients[key] for key in required}


def _direct_force_input_path(source: Path, case_id: str) -> Path:
    return source / "cases" / case_id / DIRECT_FORCE_FILE_NAME


def _copy_direct_force_input(
    *, source: Path, destination: Path, case_id: str
) -> tuple[dict[str, float], dict[str, str]]:
    input_path = _direct_force_input_path(source, case_id)
    try:
        coefficients = load_direct_force_coefficients(
            input_path, expected_case_id=case_id
        )
        digest = sha256_file(input_path)
    except (OSError, DirectForceError) as error:
        raise EntryError(f"{case_id} direct force input is invalid: {error}") from error
    target = destination / "direct-forces" / f"{case_id}.json"
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        if sha256_file(target) != digest:
            raise EntryError(f"retained direct force input differs for {case_id}")
    else:
        shutil.copyfile(input_path, target)
    return coefficients, {
        "path": f"direct-forces/{case_id}.json",
        "sha256": digest,
    }


def _attach_force_prediction(
    case_result: dict[str, Any],
    *,
    force_prediction_source: str,
    source: Path,
    destination: Path,
    case_id: str,
) -> None:
    field_coefficients = _field_force_coefficients(case_result, case_id)
    prediction: dict[str, Any] = {
        "source": force_prediction_source,
        "field_integrated_force_coefficients": field_coefficients,
    }
    if force_prediction_source == FORCE_PREDICTION_SOURCE_DIRECT_COEFFICIENTS:
        direct_coefficients, direct_input = _copy_direct_force_input(
            source=source, destination=destination, case_id=case_id
        )
        prediction["scoring_force_coefficients"] = direct_coefficients
        prediction["direct_input"] = direct_input
    else:
        prediction["scoring_force_coefficients"] = field_coefficients
    case_result["force_prediction"] = prediction


def _validate_retained_force_prediction(
    case_result: Mapping[str, Any],
    *,
    force_prediction_source: str,
    source: Path,
    destination: Path,
    case_id: str,
) -> None:
    prediction = case_result.get("force_prediction")
    if not isinstance(prediction, Mapping) or prediction.get("source") != force_prediction_source:
        raise EntryError(f"retained work result force route differs for {case_id}")
    _field_force_coefficients(case_result, case_id)
    if force_prediction_source != FORCE_PREDICTION_SOURCE_DIRECT_COEFFICIENTS:
        return
    direct_input = prediction.get("direct_input")
    if (
        not isinstance(direct_input, Mapping)
        or direct_input.get("path") != f"direct-forces/{case_id}.json"
        or not isinstance(direct_input.get("sha256"), str)
    ):
        raise EntryError(f"retained direct force input differs for {case_id}")
    try:
        source_digest = sha256_file(_direct_force_input_path(source, case_id))
        target_digest = sha256_file(destination / str(direct_input["path"]))
    except OSError as error:
        raise EntryError(f"retained direct force input is missing for {case_id}") from error
    if source_digest != direct_input["sha256"] or target_digest != source_digest:
        raise EntryError(f"retained direct force input differs for {case_id}")
    try:
        expected = load_direct_force_coefficients(
            _direct_force_input_path(source, case_id), expected_case_id=case_id
        )
    except (OSError, DirectForceError) as error:
        raise EntryError(f"retained direct force input is invalid for {case_id}") from error
    if prediction.get("scoring_force_coefficients") != expected:
        raise EntryError(f"retained direct force coefficients differ for {case_id}")


def _custom_split_document(entry: dict[str, Any]) -> dict[str, Any]:
    train_case_ids = entry["train_case_ids"]
    validation_case_ids = entry["validation_case_ids"]
    test_case_ids = entry["test_case_ids"]
    return {
        "schema": "autocfd5-aiml-drivaerml-split-v1",
        "schema_version": 1,
        "dataset_id": "drivaerml",
        "split_id": entry["split_id"],
        "split_label": f"Participant custom: {entry['split_id']}",
        "case_set_id": "participant_custom",
        "official": False,
        "train_case_count": len(train_case_ids),
        "train_case_ids": train_case_ids,
        "validation_case_count": len(validation_case_ids),
        "validation_case_ids": validation_case_ids,
        "test_case_count": len(test_case_ids),
        "test_case_ids": test_case_ids,
    }


def _resolve_split_path(
    entry: dict[str, Any],
    destination: Path,
    requested: Path | str | None,
) -> Path:
    official = contract_root() / "splits" / f"{entry['split_id']}.json"
    if official.is_file():
        if requested is not None and Path(requested).expanduser().resolve() != official.resolve():
            raise EntryError("official splits must use the frozen evaluator declaration")
        return official
    if requested is not None:
        raise EntryError("a custom split must be declared completely in entry.json")
    document = _custom_split_document(entry)
    path = destination / "custom-split.json"
    if path.is_file():
        if read_json(path) != document:
            raise EntryError("retained custom-split.json differs from entry.json")
    else:
        write_json(path, document, exclusive=True)
    return path


def _profile_chunk(
    case_documents: list[dict[str, Any]],
    *,
    chunk_id: str,
    prediction_scope: str,
) -> dict[str, Any]:
    return {
        "schema": PROFILE_CHUNK_SCHEMA,
        "schema_version": 1,
        "chunk_id": chunk_id,
        "prediction_scope": prediction_scope,
        "case_count": len(case_documents),
        "case_ids": [case["case_id"] for case in case_documents],
        "series_per_case": 40,
        "cases": [
            {
                "case_id": case["case_id"],
                "series": case["profiles"]["series"],
            }
            for case in case_documents
        ],
    }


def _runtime() -> dict[str, str]:
    try:
        import vtk

        vtk_version = str(vtk.vtkVersion.GetVTKVersion())
    except ImportError:
        vtk_version = "unavailable"
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "vtk": vtk_version,
        "platform": platform.platform(),
    }


def evaluate_entry(
    *,
    entry_root: Path | str,
    output_root: Path | str,
    dataset_root: Path | str,
    support_root: Path | str,
    native_source_pin: Path | str,
    split_path: Path | str | None,
    scoring_path: Path | str,
    force_truth_path: Path | str,
    maximum_prediction_chunk_rows: int = 1_000_000,
    io_chunk_bytes: int = 8 * 1024 * 1024,
    resume: bool = False,
) -> dict[str, Any]:
    source = Path(entry_root).expanduser().resolve()
    destination = Path(output_root).expanduser().resolve()
    try:
        scoring_sha256 = sha256_file(scoring_path)
    except OSError as error:
        raise EntryError("cannot read the approved scoring contract") from error
    if scoring_sha256 != SCORING_CONTRACT_SHA256:
        raise EntryError("scoring contract differs from this evaluator build")
    entry_path = source / "entry.json"
    entry = load_entry(entry_path)
    prediction_scope = entry_prediction_scope(entry)
    force_prediction_source = entry_force_prediction_source(entry)
    if (destination / "result.json").exists():
        raise EntryError("result.json already exists; choose a new output directory")
    destination.mkdir(parents=True, exist_ok=True)
    resolved_split_path = _resolve_split_path(entry, destination, split_path)
    split = read_json(resolved_split_path)
    split_cases = split.get("test_case_ids")
    if (
        split.get("schema") != "autocfd5-aiml-drivaerml-split-v1"
        or entry["split_id"] != split.get("split_id")
        or entry["test_case_ids"] != split_cases
    ):
        raise EntryError("entry split ID, order or membership differs from the selected split")
    work_cases = destination / ".work" / "cases"
    final_cases = destination / "cases"
    work_cases.mkdir(parents=True, exist_ok=True)
    final_cases.mkdir(parents=True, exist_ok=True)

    documents: list[dict[str, Any]] = []
    for case_id in split_cases:
        work_path = work_cases / f"{case_id}.json"
        if resume and work_path.is_file():
            case_result = read_json(work_path)
            if (
                case_result.get("schema") != CASE_RESULT_SCHEMA
                or case_result.get("schema_version") != 3
                or case_result.get("case_id") != case_id
                or case_result.get("status") != "complete"
                or case_result.get("prediction_scope") != prediction_scope
            ):
                raise EntryError(f"retained work result is invalid for {case_id}")
            retained_core = case_result.get("core")
            if not isinstance(retained_core, Mapping):
                raise EntryError(f"retained work result has no core result for {case_id}")
            try:
                validate_case_regional_envelope(
                    retained_core.get("report_only_regional_diagnostics", {}),
                    expected_case_id=case_id,
                    expected_additive_sums=retained_core.get("additive_sums"),
                )
            except RegionalAggregateError as error:
                raise EntryError(
                    f"retained work result has invalid regional diagnostics for {case_id}: {error}"
                ) from error
            _validate_retained_force_prediction(
                case_result,
                force_prediction_source=force_prediction_source,
                source=source,
                destination=destination,
                case_id=case_id,
            )
        else:
            case_root = source / "cases" / case_id
            case_result = evaluate_case(
                case_id=case_id,
                native_source_pin=native_source_pin,
                dataset_root=dataset_root,
                support_root=support_root,
                surface_prediction_manifest=case_root / "surface" / "manifest.json",
                volume_prediction_manifest=(
                    case_root / "volume" / "manifest.json"
                    if prediction_scope == PREDICTION_SCOPE_FULL
                    else None
                ),
                prediction_scope=prediction_scope,
                maximum_prediction_chunk_rows=maximum_prediction_chunk_rows,
                io_chunk_bytes=io_chunk_bytes,
            )
            _attach_force_prediction(
                case_result,
                force_prediction_source=force_prediction_source,
                source=source,
                destination=destination,
                case_id=case_id,
            )
            write_json(work_path, case_result, exclusive=True)
        documents.append(case_result)
        compact = {
            **case_result,
            "profiles": {
                key: value for key, value in case_result["profiles"].items() if key != "series"
            },
        }
        final_path = final_cases / f"{case_id}.json"
        if final_path.exists():
            if read_json(final_path) != compact:
                raise EntryError(f"retained compact case result differs for {case_id}")
        else:
            write_json(final_path, compact, exclusive=True)

    profile_directory = destination / "profiles"
    profile_directory.mkdir(exist_ok=True)
    chunk_rows = []
    for offset in range(0, len(documents), 8):
        chunk_id = f"chunk-{offset // 8:03d}"
        chunk_path = profile_directory / f"{chunk_id}.json"
        identity = write_json(
            chunk_path,
            _profile_chunk(
                documents[offset : offset + 8],
                chunk_id=chunk_id,
                prediction_scope=prediction_scope,
            ),
            # Profile identity coverage remains 40 rows per case; unavailable
            # velocity rows in surface-only entries carry no fabricated values.
            exclusive=True,
        )
        chunk_rows.append(
            {
                "chunk_id": chunk_id,
                "path": f"profiles/{chunk_path.name}",
                "sha256": identity["sha256"],
                "size_bytes": identity["size_bytes"],
                "case_ids": [case["case_id"] for case in documents[offset : offset + 8]],
            }
        )
    profile_index = {
        "schema": PROFILE_INDEX_SCHEMA,
        "schema_version": 1,
        "submission_id": entry["submission_id"],
        "prediction_scope": prediction_scope,
        "case_count": len(documents),
        "series_per_case": 40,
        "constant_series_per_case": 20,
        "relative_series_per_case": 20,
        "velocity_series_availability": (
            "not_submitted_surface_only"
            if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
            else "available"
        ),
        "cp_series_availability": "available",
        "chunks": chunk_rows,
    }
    profile_index_identity = write_json(
        profile_directory / "index.json", profile_index, exclusive=True
    )

    try:
        regional_report = aggregate_regional_diagnostics(
            documents,
            case_ids=split_cases,
        )
    except RegionalAggregateError as error:
        raise EntryError(f"regional diagnostic aggregation failed: {error}") from error
    regional_report_identity = write_json(
        destination / "regional-diagnostics.json",
        regional_report,
        exclusive=True,
    )

    result = aggregate_cases(
        documents,
        split_path=resolved_split_path,
        force_truth_path=force_truth_path,
        scoring_path=scoring_path,
    )
    result["submission"] = {
        key: entry[key] for key in ("submission_id", "method_name", "contact_email")
    }
    result["submission"]["prediction_scope"] = prediction_scope
    result["submission"]["force_prediction_source"] = force_prediction_source
    if "prediction_artifact" in entry:
        result["submission"]["prediction_artifact"] = entry["prediction_artifact"]
    result["inputs"] = {
        "entry_sha256": sha256_file(entry_path),
        "native_source_pin_sha256": sha256_file(native_source_pin),
        "dataset_revision": DATASET_REVISION,
        "profile_support_index_sha256": SUPPORT_INDEX_SHA256,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "profile_prediction_index_sha256": profile_index_identity["sha256"],
        "regional_diagnostics_contract_sha256": (
            REGIONAL_DIAGNOSTICS_CONTRACT_SHA256
        ),
        "regional_diagnostics_report_sha256": regional_report_identity["sha256"],
    }
    result["evaluator"] = {"version": EVALUATOR_VERSION, "runtime": _runtime()}
    write_json(destination / "result.json", result, exclusive=True)
    write_json(
        destination / "provenance.json",
        {
            "schema": "autocfd5-aiml-evaluation-provenance-v1",
            "schema_version": 1,
            "evaluator_version": EVALUATOR_VERSION,
            "dataset_revision": DATASET_REVISION,
            "runtime": _runtime(),
            "case_count": len(documents),
            "prediction_scope": prediction_scope,
            "force_prediction_source": force_prediction_source,
            "all_supplied_native_and_prediction_hashes_verified": True,
            "unavailable_metric_values_fabricated": False,
            "component_weights_renormalized": False,
            "profile_gaps_preserved": True,
            "profile_smoothing_applied": False,
            "regional_diagnostics_report_only": True,
            "regional_diagnostics_scoring_weight": 0.0,
            "official_component_weights_changed": False,
            "surface_only_policy_added": True,
        },
        exclusive=True,
    )
    return result


__all__ = [
    "ENTRY_SCHEMA",
    "EntryError",
    "entry_prediction_scope",
    "entry_force_prediction_source",
    "evaluate_entry",
    "load_entry",
]
