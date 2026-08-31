from __future__ import annotations

import math
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .aggregate import RESULT_SCHEMA, AggregateError, aggregate_cases
from .constants import (
    DATASET_REVISION,
    EVALUATOR_VERSION,
    PREDICTION_SCOPE_FULL,
    PREDICTION_SCOPE_SURFACE_ONLY,
    PREDICTION_SCOPES,
    REGIONAL_DIAGNOSTICS_CONTRACT_SHA256,
    SCORING_CONTRACT_SHA256,
    SUPPORT_INDEX_SHA256,
    SURFACE_ONLY_UNAVAILABLE_COMPONENTS,
    contract_root,
)
from .core.evaluator import OFFICIAL_NATIVE_SOURCE_PIN_SHA256
from .jsonio import canonical_json_bytes, read_json, sha256_bytes, sha256_file
from .regional_aggregate import (
    RegionalAggregateError,
    aggregate_regional_diagnostics,
    validate_aggregate_regional_diagnostics,
    validate_case_regional_envelope,
)

PACKAGE_SCHEMA = "autocfd5-aiml-result-package-v1"
_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


class PackageError(ValueError):
    """Raised when a result package is incomplete or unsafe."""


def _files(root: Path) -> list[Path]:
    result: list[Path] = []
    for path in root.rglob("*"):
        if ".work" in path.relative_to(root).parts:
            continue
        if path.is_symlink():
            raise PackageError(f"symbolic links are not allowed: {path}")
        if path.is_file():
            result.append(path)
    return sorted(result, key=lambda path: path.relative_to(root).as_posix())


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, _ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o444) << 16
    return info


def create_package(result_directory: Path | str, output: Path | str) -> dict[str, Any]:
    root = Path(result_directory).expanduser().resolve()
    destination = Path(output).expanduser().resolve()
    if not root.is_dir():
        raise PackageError("result directory does not exist")
    if destination.suffix.lower() != ".zip":
        raise PackageError("package output must use the .zip suffix")
    if destination.exists() or destination.is_symlink():
        raise PackageError(f"refusing to overwrite {destination}")
    result = read_json(root / "result.json")
    entries = []
    files = _files(root)
    for path in files:
        relative = path.relative_to(root).as_posix()
        entries.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "schema": PACKAGE_SCHEMA,
        "schema_version": 1,
        "submission_id": result.get("submission", {}).get("submission_id"),
        "dataset_id": "drivaerml",
        "prediction_scope": result.get("prediction_scope"),
        "file_count": len(entries),
        "files": entries,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
    )
    temporary = Path(handle.name)
    handle.close()
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            archive.writestr(_zip_info("package-manifest.json"), manifest_bytes)
            for path in files:
                relative = path.relative_to(root).as_posix()
                archive.writestr(_zip_info(relative), path.read_bytes())
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    digest = sha256_file(destination)
    checksum_path = destination.with_suffix(destination.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {destination.name}\n", encoding="ascii")
    return {
        "file": destination.name,
        "size_bytes": destination.stat().st_size,
        "sha256": digest,
        "checksum_file": checksum_path.name,
        "entry_count": len(entries),
    }


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in name
    ):
        raise PackageError(f"unsafe package member path: {name!r}")
    return path


def verify_package(path: Path | str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != ".zip":
        raise PackageError("package must be a regular ZIP file")
    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or "package-manifest.json" not in names:
            raise PackageError("package members are duplicated or the manifest is missing")
        for info in infos:
            _safe_member(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or info.is_dir():
                raise PackageError("package may contain regular files only")
        try:
            manifest = read_json_bytes(archive.read("package-manifest.json"))
        except (KeyError, OSError, zipfile.BadZipFile) as error:
            raise PackageError("cannot read package manifest") from error
        if manifest.get("schema") != PACKAGE_SCHEMA or manifest.get("schema_version") != 1:
            raise PackageError("package manifest schema differs")
        if manifest.get("prediction_scope") not in PREDICTION_SCOPES:
            raise PackageError("package manifest prediction scope differs")
        entries = manifest.get("files")
        if not isinstance(entries, list) or manifest.get("file_count") != len(entries):
            raise PackageError("package manifest file count differs")
        expected_names = {"package-manifest.json"}
        for entry in entries:
            if not isinstance(entry, dict):
                raise PackageError("package manifest entry is invalid")
            name = entry.get("path")
            if not isinstance(name, str):
                raise PackageError("package manifest path is invalid")
            _safe_member(name)
            expected_names.add(name)
            payload = archive.read(name)
            if len(payload) != entry.get("size_bytes") or sha256_bytes(payload) != entry.get(
                "sha256"
            ):
                raise PackageError(f"package member identity differs: {name}")
        if set(names) != expected_names:
            raise PackageError("package members differ from the closed manifest")
        result = read_json_bytes(archive.read("result.json"))
        if manifest.get("prediction_scope") != result.get("prediction_scope"):
            raise PackageError("package and result prediction scopes differ")
        _verify_result(result, archive)
    return {
        "file": source.name,
        "size_bytes": source.stat().st_size,
        "sha256": sha256_file(source),
        "entry_count": len(entries),
        "submission_id": result.get("submission", {}).get("submission_id"),
    }


def _verify_result(result: dict[str, Any], archive: zipfile.ZipFile) -> None:
    if (
        result.get("schema") != RESULT_SCHEMA
        or result.get("schema_version") != 2
        or result.get("status") != "complete"
        or result.get("dataset_id") != "drivaerml"
    ):
        raise PackageError("result.json contract differs")
    prediction_scope = result.get("prediction_scope")
    if prediction_scope not in PREDICTION_SCOPES:
        raise PackageError("result prediction scope differs")
    submission = result.get("submission")
    if (
        not isinstance(submission, dict)
        or submission.get("prediction_scope") != prediction_scope
    ):
        raise PackageError("submission prediction scope differs")
    split = result.get("split")
    if not isinstance(split, dict) or split.get("complete_exact_membership") is not True:
        raise PackageError("result split is incomplete")
    split_id = split.get("split_id")
    if (
        not isinstance(split_id, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", split_id) is None
    ):
        raise PackageError("result split ID is invalid")
    split_path = contract_root() / "splits" / f"{split_id}.json"
    if split_path.is_file():
        if "custom-split.json" in archive.namelist():
            raise PackageError("an official split package may not contain custom-split.json")
        expected_split = read_json(split_path)
        split_sha256 = sha256_file(split_path)
        official = True
    else:
        try:
            custom_split_payload = archive.read("custom-split.json")
        except KeyError as error:
            raise PackageError("custom split declaration is missing") from error
        expected_split = read_json_bytes(custom_split_payload)
        _verify_custom_split(expected_split, split_id)
        split_sha256 = sha256_bytes(custom_split_payload)
        official = False
    if (
        split.get("split_sha256") != split_sha256
        or split.get("official") is not official
        or split.get("case_set_id") != expected_split.get("case_set_id")
        or split.get("train_case_count") != expected_split.get("train_case_count")
        or split.get("validation_case_count") != expected_split.get("validation_case_count")
        or split.get("test_case_ids") != expected_split.get("test_case_ids")
        or split.get("test_case_count") != expected_split.get("test_case_count")
    ):
        raise PackageError("result split differs from this evaluator build")
    evaluator = result.get("evaluator")
    inputs = result.get("inputs")
    if not isinstance(evaluator, dict) or evaluator.get("version") != EVALUATOR_VERSION:
        raise PackageError("result evaluator version differs")
    if not isinstance(inputs, dict) or (
        inputs.get("dataset_revision") != DATASET_REVISION
        or inputs.get("profile_support_index_sha256") != SUPPORT_INDEX_SHA256
        or inputs.get("scoring_contract_sha256") != SCORING_CONTRACT_SHA256
        or inputs.get("native_source_pin_sha256") != OFFICIAL_NATIVE_SOURCE_PIN_SHA256
        or inputs.get("regional_diagnostics_contract_sha256")
        != REGIONAL_DIAGNOSTICS_CONTRACT_SHA256
    ):
        raise PackageError("result immutable inputs differ")
    try:
        regional_payload = archive.read("regional-diagnostics.json")
    except KeyError as error:
        raise PackageError("regional diagnostics report is missing") from error
    if sha256_bytes(regional_payload) != inputs.get(
        "regional_diagnostics_report_sha256"
    ):
        raise PackageError("regional diagnostics report identity differs")
    regional_report = read_json_bytes(regional_payload)
    try:
        validate_aggregate_regional_diagnostics(
            regional_report,
            expected_case_ids=expected_split["test_case_ids"],
        )
    except RegionalAggregateError as error:
        raise PackageError(f"regional diagnostics report is invalid: {error}") from error
    if regional_report.get("prediction_scope") != prediction_scope:
        raise PackageError("regional diagnostics prediction scope differs")
    try:
        profile_index_payload = archive.read("profiles/index.json")
    except KeyError as error:
        raise PackageError("profile prediction index is missing") from error
    if sha256_bytes(profile_index_payload) != inputs.get("profile_prediction_index_sha256"):
        raise PackageError("profile prediction index identity differs")
    profile_index = read_json_bytes(profile_index_payload)
    chunks = profile_index.get("chunks")
    if (
        not isinstance(chunks, list)
        or profile_index.get("case_count") != len(expected_split["test_case_ids"])
        or profile_index.get("prediction_scope") != prediction_scope
        or profile_index.get("velocity_series_availability")
        != (
            "not_submitted_surface_only"
            if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
            else "available"
        )
        or profile_index.get("cp_series_availability") != "available"
    ):
        raise PackageError("profile prediction index coverage differs")
    chunk_case_ids: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict) or not isinstance(chunk.get("path"), str):
            raise PackageError("profile prediction chunk declaration is invalid")
        try:
            payload = archive.read(chunk["path"])
        except KeyError as error:
            raise PackageError("profile prediction chunk is missing") from error
        if (
            sha256_bytes(payload) != chunk.get("sha256")
            or len(payload) != chunk.get("size_bytes")
        ):
            raise PackageError("profile prediction chunk identity differs")
        chunk_document = read_json_bytes(payload)
        declared_case_ids = chunk.get("case_ids", [])
        chunk_cases = chunk_document.get("cases")
        if (
            chunk_document.get("schema")
            != "autocfd5-aiml-profile-prediction-chunk-v1"
            or chunk_document.get("prediction_scope") != prediction_scope
            or chunk_document.get("case_ids") != declared_case_ids
            or chunk_document.get("case_count") != len(declared_case_ids)
            or chunk_document.get("series_per_case") != 40
            or not isinstance(chunk_cases, list)
            or len(chunk_cases) != len(declared_case_ids)
            or any(len(case.get("series", [])) != 40 for case in chunk_cases)
        ):
            raise PackageError("profile prediction chunk contract differs")
        for case in chunk_cases:
            series = case.get("series", [])
            for item in series:
                if not isinstance(item, dict):
                    raise PackageError("profile prediction series is invalid")
                is_velocity = item.get("quantity_id") == "velocity_ratio"
                expected_availability = (
                    "not_submitted_surface_only"
                    if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
                    and is_velocity
                    else "available"
                )
                if item.get("availability") != expected_availability:
                    raise PackageError("profile prediction availability differs")
                if expected_availability != "available" and "prediction" in item:
                    raise PackageError(
                        "surface-only velocity profiles contain fabricated values"
                    )
        chunk_case_ids.extend(declared_case_ids)
    if chunk_case_ids != expected_split["test_case_ids"]:
        raise PackageError("profile prediction case order or membership differs")
    compact_case_documents: list[dict[str, Any]] = []
    for case_id in expected_split["test_case_ids"]:
        case_path = f"cases/{case_id}.json"
        if case_path not in archive.namelist():
            raise PackageError(f"compact case result is missing: {case_id}")
        case_document = read_json_bytes(archive.read(case_path))
        if (
            case_document.get("schema") != "autocfd5-aiml-drivaerml-case-result-v3"
            or case_document.get("schema_version") != 3
            or case_document.get("case_id") != case_id
            or case_document.get("status") != "complete"
            or case_document.get("prediction_scope") != prediction_scope
        ):
            raise PackageError(f"compact case result contract differs: {case_id}")
        core = case_document.get("core")
        if not isinstance(core, dict):
            raise PackageError(f"compact case core result is missing: {case_id}")
        if (
            core.get("schema")
            != "autocfd5-aiml-drivaerml-case-evaluation-v4"
            or core.get("schema_version") != 4
            or core.get("prediction_scope") != prediction_scope
        ):
            raise PackageError(f"compact case core prediction scope differs: {case_id}")
        prediction_inputs = core.get("prediction_inputs")
        expected_prediction_supports = (
            {"surface_native_cells"}
            if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
            else {"surface_native_cells", "volume_native_cells"}
        )
        if (
            not isinstance(prediction_inputs, dict)
            or set(prediction_inputs) != expected_prediction_supports
        ):
            raise PackageError(f"compact case prediction inputs differ: {case_id}")
        try:
            validate_case_regional_envelope(
                core.get("report_only_regional_diagnostics", {}),
                expected_case_id=case_id,
                expected_additive_sums=core.get("additive_sums"),
            )
        except RegionalAggregateError as error:
            raise PackageError(
                f"compact case regional diagnostics are invalid: {case_id}: {error}"
            ) from error
        compact_case_documents.append(case_document)
    try:
        regenerated_regional_report = aggregate_regional_diagnostics(
            compact_case_documents,
            case_ids=expected_split["test_case_ids"],
        )
    except RegionalAggregateError as error:
        raise PackageError(
            f"regional diagnostics cannot be regenerated from cases: {error}"
        ) from error
    if canonical_json_bytes(regenerated_regional_report) != regional_payload:
        raise PackageError("regional diagnostics report differs from packaged cases")
    metrics = result.get("metric_values")
    required_metrics = {
        "overall_score",
        "field_score",
        "force_score",
        "diagnostic_score",
        "cd_r2",
        "cl_r2",
        "c_pitch_r2",
        "cp_cut_r2",
        "surface_pressure_rel_l2",
        "surface_wall_shear_rel_l2",
    }
    unavailable_metrics = (
        set(SURFACE_ONLY_UNAVAILABLE_COMPONENTS)
        if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
        else set()
    )
    if prediction_scope == PREDICTION_SCOPE_FULL:
        required_metrics.update(
            {
                "velocity_profile_r2",
                "volume_pressure_rel_l2",
                "volume_velocity_rel_l2",
            }
        )
    if (
        not isinstance(metrics, dict)
        or not required_metrics <= set(metrics)
        or any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            for value in metrics.values()
        )
    ):
        raise PackageError("result metrics are incomplete or non-finite")
    if unavailable_metrics & set(metrics):
        raise PackageError("unavailable scientific metric values were fabricated")
    component_scores = result.get("component_scores")
    component_availability = result.get("component_availability")
    expected_component_ids = {
        "surface_pressure_rel_l2",
        "surface_wall_shear_rel_l2",
        "volume_velocity_rel_l2",
        "volume_pressure_rel_l2",
        "cd_r2",
        "cl_r2",
        "c_pitch_r2",
        "velocity_profile_r2",
        "cp_cut_r2",
    }
    if (
        not isinstance(component_scores, dict)
        or set(component_scores) != expected_component_ids
        or any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            for value in component_scores.values()
        )
        or not isinstance(component_availability, dict)
        or set(component_availability) != expected_component_ids
        or component_availability
        != {
            metric_id: (
                "not_submitted_zero_score"
                if metric_id in unavailable_metrics
                else "available"
            )
            for metric_id in expected_component_ids
        }
        or any(component_scores[metric_id] != 0.0 for metric_id in unavailable_metrics)
    ):
        raise PackageError("result component availability or scores differ")
    scoring_summary = result.get("scoring")
    if (
        not isinstance(scoring_summary, dict)
        or scoring_summary.get("prediction_scope") != prediction_scope
        or scoring_summary.get("unavailable_component_metric_ids")
        != sorted(unavailable_metrics)
        or scoring_summary.get("unavailable_component_score") != 0.0
        or scoring_summary.get("component_weights_renormalized") is not False
        or scoring_summary.get("unavailable_metric_values_fabricated") is not False
        or scoring_summary.get("maximum_attainable_overall_score")
        != (60.0 if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY else 100.0)
    ):
        raise PackageError("result scoring summary differs")

    scoring_path = contract_root() / "scoring.json"
    force_truth_path = contract_root() / "force_mom_constref_all.csv"
    try:
        if official:
            regenerated = aggregate_cases(
                compact_case_documents,
                split_path=split_path,
                force_truth_path=force_truth_path,
                scoring_path=scoring_path,
            )
        else:
            with tempfile.NamedTemporaryFile(suffix=".json") as split_file:
                split_file.write(custom_split_payload)
                split_file.flush()
                regenerated = aggregate_cases(
                    compact_case_documents,
                    split_path=split_file.name,
                    force_truth_path=force_truth_path,
                    scoring_path=scoring_path,
                )
    except (AggregateError, OSError) as error:
        raise PackageError(
            f"official aggregate cannot be regenerated from compact cases: {error}"
        ) from error
    regenerated_metrics = regenerated.get("metric_values")
    if not isinstance(regenerated_metrics, dict) or metrics != regenerated_metrics:
        raise PackageError("result official aggregate metrics differ from compact cases")
    for key in (
        "prediction_scope",
        "component_scores",
        "component_availability",
        "scoring",
    ):
        if result.get(key) != regenerated.get(key):
            raise PackageError(
                f"result {key} differs from the frozen aggregate regeneration"
            )


def _verify_custom_split(document: dict[str, Any], split_id: str) -> None:
    required = {
        "schema",
        "schema_version",
        "dataset_id",
        "split_id",
        "split_label",
        "case_set_id",
        "official",
        "train_case_count",
        "train_case_ids",
        "validation_case_count",
        "validation_case_ids",
        "test_case_count",
        "test_case_ids",
    }
    if (
        set(document) != required
        or document.get("schema") != "autocfd5-aiml-drivaerml-split-v1"
        or document.get("schema_version") != 1
        or document.get("dataset_id") != "drivaerml"
        or document.get("split_id") != split_id
        or not isinstance(document.get("split_label"), str)
        or not document["split_label"].strip()
        or document.get("case_set_id") != "participant_custom"
        or document.get("official") is not False
    ):
        raise PackageError("custom split declaration differs")
    arrays: list[list[str]] = []
    for prefix in ("train", "validation", "test"):
        case_ids = document.get(f"{prefix}_case_ids")
        if (
            not isinstance(case_ids, list)
            or not case_ids
            or any(
                not isinstance(case_id, str)
                or re.fullmatch(r"run_[1-9][0-9]*", case_id) is None
                for case_id in case_ids
            )
            or len(case_ids) != len(set(case_ids))
            or document.get(f"{prefix}_case_count") != len(case_ids)
        ):
            raise PackageError(f"custom split {prefix} case IDs are invalid")
        arrays.append(case_ids)
    if any(set(left) & set(right) for index, left in enumerate(arrays) for right in arrays[index + 1 :]):
        raise PackageError("custom split train, validation and test IDs overlap")
    native_pin = read_json(contract_root() / "native-source-pin.json")
    known_case_ids = {
        case.get("case_id")
        for case in native_pin.get("cases", [])
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    unknown = set().union(*(set(case_ids) for case_ids in arrays)) - known_case_ids
    if unknown:
        raise PackageError("custom split contains run IDs outside the pinned dataset")


def read_json_bytes(payload: bytes) -> dict[str, Any]:
    import json

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PackageError(f"package JSON repeats key {key!r}")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                PackageError(f"non-finite JSON token {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageError("package contains invalid JSON") from error
    if not isinstance(document, dict):
        raise PackageError("package JSON document must be an object")
    return document


__all__ = ["PackageError", "create_package", "verify_package"]
