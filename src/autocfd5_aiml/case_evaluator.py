from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from .constants import SUPPORT_INDEX_SHA256
from .core.evaluator import evaluate_candidate_case
from .core.native_surface import audit_fixed_surface_area_file, load_native_surface_vtp
from .core.source import (
    index_inline_binary_vtk_xml,
    load_native_source_pin,
    open_verified_monolithic,
    open_verified_multipart,
)
from .jsonio import sha256_file
from .profiles import evaluate_case_profiles, load_profile_support_case

CASE_RESULT_SCHEMA = "autocfd5-aiml-drivaerml-case-result-v1"


class CaseEvaluationError(ValueError):
    """Raised when a complete case cannot be evaluated."""


def evaluate_case(
    *,
    case_id: str,
    native_source_pin: Path | str,
    dataset_root: Path | str,
    support_root: Path | str,
    surface_prediction_manifest: Path | str,
    volume_prediction_manifest: Path | str,
    monolithic_volume: Path | str | None = None,
    maximum_prediction_chunk_rows: int = 1_000_000,
    io_chunk_bytes: int = 8 * 1024 * 1024,
) -> dict[str, Any]:
    pin = load_native_source_pin(native_source_pin)
    case = pin.case(case_id)
    resolved = pin.resolve(case_id, dataset_root)
    support_index = Path(support_root) / "index.json"
    if SUPPORT_INDEX_SHA256.startswith("__"):
        raise CaseEvaluationError("this evaluator build has no bound profile-support release")
    if sha256_file(support_index) != SUPPORT_INDEX_SHA256:
        raise CaseEvaluationError("profile-support index differs from this evaluator build")

    surface = load_native_surface_vtp(resolved.boundary_path)
    areas = audit_fixed_surface_area_file(
        surface,
        resolved.surface_cell_area_path,
        expected_area_sha256=case.surface_cell_area.sha256,
        source_boundary_sha256=case.surface_cell_area.source_boundary_sha256,
    )
    if monolithic_volume is None:
        volume_stream = open_verified_multipart(
            resolved,
            verification_chunk_size=io_chunk_bytes,
        )
    else:
        volume_stream = open_verified_monolithic(
            resolved,
            monolithic_volume,
            verification_chunk_size=io_chunk_bytes,
        )
    try:
        with closing(volume_stream) as stream:
            vtk_index = index_inline_binary_vtk_xml(stream, scan_chunk_size=io_chunk_bytes)
            core_result = evaluate_candidate_case(
                case_id=case_id,
                native_source_pin=pin,
                native_surface=surface,
                fixed_surface_areas=areas,
                volume_stream=stream,
                volume_vtk_index=vtk_index,
                surface_prediction_manifest=surface_prediction_manifest,
                volume_prediction_manifest=volume_prediction_manifest,
                maximum_prediction_chunk_rows=maximum_prediction_chunk_rows,
                hash_chunk_bytes=io_chunk_bytes,
                validation_block_rows=maximum_prediction_chunk_rows,
                encoded_chunk_bytes=io_chunk_bytes,
            ).to_json()
    finally:
        areas.close()

    profile_support = load_profile_support_case(support_root, case_id)
    profiles = evaluate_case_profiles(
        profile_support,
        surface_prediction_manifest=surface_prediction_manifest,
        volume_prediction_manifest=volume_prediction_manifest,
        maximum_chunk_rows=maximum_prediction_chunk_rows,
        hash_chunk_bytes=io_chunk_bytes,
        validation_block_rows=maximum_prediction_chunk_rows,
    )
    return {
        "schema": CASE_RESULT_SCHEMA,
        "schema_version": 1,
        "status": "complete",
        "case_id": case_id,
        "core": core_result,
        "profiles": profiles,
    }


__all__ = ["CASE_RESULT_SCHEMA", "CaseEvaluationError", "evaluate_case"]
