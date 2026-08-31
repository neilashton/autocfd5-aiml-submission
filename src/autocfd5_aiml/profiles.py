from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .constants import (
    DATASET_REVISION,
    PREDICTION_SCOPE_FULL,
    PREDICTION_SCOPE_SURFACE_ONLY,
    PREDICTION_SCOPES,
    U_INF_M_PER_S,
)
from .core.prediction_chunks import (
    DEFAULT_HASH_CHUNK_BYTES,
    DEFAULT_VALIDATION_BLOCK_ROWS,
    PredictionChunkError,
    PredictionChunkManifest,
    iter_prediction_chunks,
    load_prediction_chunk_manifest,
)
from .jsonio import canonical_json_bytes, read_json, sha256_bytes, sha256_file

SUPPORT_INDEX_SCHEMA = "autocfd5-aiml-native-profile-support-index-v1"
SUPPORT_CHUNK_SCHEMA = "autocfd5-aiml-native-profile-support-chunk-v1"
PROFILE_CASE_SCHEMA = "autocfd5-aiml-profile-case-result-v2"
CONSTANT_VELOCITY_FAMILY = "drivaerml-autocfd5-constant-v1"
RELATIVE_VELOCITY_FAMILY = "drivaerml-velocity-relative-v3"
CONSTANT_CP_FAMILY = "drivaerml_cp_constant_v1"
RELATIVE_CP_FAMILY = "drivaerml_cp_relative_v1"
MATERIALIZED_FAMILIES = {
    CONSTANT_VELOCITY_FAMILY,
    RELATIVE_VELOCITY_FAMILY,
    CONSTANT_CP_FAMILY,
    RELATIVE_CP_FAMILY,
}
EXPECTED_FAMILY_COUNTS = {
    CONSTANT_VELOCITY_FAMILY: 16,
    RELATIVE_VELOCITY_FAMILY: 16,
    CONSTANT_CP_FAMILY: 4,
    RELATIVE_CP_FAMILY: 4,
}
EXPERIMENTAL_VELOCITY_STATIONS = frozenset(
    {
        "autocfd5_v1",
        "autocfd5_v2",
        "autocfd5_v3",
        "autocfd5_v5",
        "autocfd5_u1",
        "autocfd5_u2",
        "autocfd5_u3",
        "autocfd5_u4",
        "autocfd5_u5",
        "autocfd5_u6",
        "autocfd5_l1",
    }
)


class ProfileEvaluationError(ValueError):
    """Raised when profile support or derived profile output is not exact."""


@dataclass(frozen=True)
class ProfileSupportCase:
    root: Path
    index_sha256: str
    chunk_sha256: str
    case_id: str
    surface_row_count: int
    volume_row_count: int
    series: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class GatheredField:
    manifest_sha256: str
    chunk_sha256: tuple[str, ...]
    raw_cell_ids: np.ndarray
    values: np.ndarray

    def values_for(self, raw_cell_ids: Sequence[int]) -> np.ndarray:
        requested = np.asarray(raw_cell_ids, dtype=np.int64)
        positions = np.searchsorted(self.raw_cell_ids, requested)
        if len(positions) and (
            np.any(positions >= len(self.raw_cell_ids))
            or np.any(self.raw_cell_ids[positions] != requested)
        ):
            raise ProfileEvaluationError("profile prediction gather omitted a requested raw ID")
        return np.take(self.values, positions, axis=0)


def _identity(document: Mapping[str, Any], field: str) -> str:
    identity = document.get(field)
    if not isinstance(identity, Mapping) or set(identity) != {"algorithm", "scope", "sha256"}:
        raise ProfileEvaluationError(f"{field} is not a closed identity object")
    if identity.get("algorithm") != "sha256":
        raise ProfileEvaluationError(f"{field} uses an unsupported algorithm")
    body = dict(document)
    body.pop(field)
    actual = sha256_bytes(canonical_json_bytes(body))
    if identity.get("sha256") != actual:
        raise ProfileEvaluationError(f"{field} does not replay")
    return actual


def _location(index: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    locations = index.get("case_locations")
    if not isinstance(locations, list):
        raise ProfileEvaluationError("support index has no case_locations array")
    matches = [
        row for row in locations if isinstance(row, Mapping) and row.get("case_id") == case_id
    ]
    if len(matches) != 1:
        raise ProfileEvaluationError(f"support index has no unique location for {case_id}")
    return matches[0]


def _validate_series(series: object, case_id: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(series, list) or len(series) != 40:
        raise ProfileEvaluationError(f"{case_id} must contain exactly 40 profile series")
    counts = {family: 0 for family in EXPECTED_FAMILY_COUNTS}
    keys: set[tuple[str, str]] = set()
    validated: list[Mapping[str, Any]] = []
    for position, item in enumerate(series):
        if not isinstance(item, Mapping):
            raise ProfileEvaluationError(f"{case_id} series {position} must be an object")
        family = item.get("family_id")
        station = item.get("station_id")
        if family not in counts or not isinstance(station, str) or not station:
            raise ProfileEvaluationError(f"{case_id} series {position} identity is invalid")
        key = (str(family), station)
        if key in keys:
            raise ProfileEvaluationError(f"{case_id} repeats profile series {key}")
        keys.add(key)
        counts[str(family)] += 1
        representation = item.get("representation")
        if representation == "shared_alias":
            reference = item.get("shared_support_ref")
            if not isinstance(reference, Mapping):
                raise ProfileEvaluationError(f"{case_id} alias {key} has no support reference")
            validated.append(item)
            continue
        if representation != "materialized":
            raise ProfileEvaluationError(f"{case_id} series {key} has an invalid representation")
        arrays = [
            item.get("sample_index"),
            item.get("raw_native_cell_id"),
            item.get("coordinate"),
            item.get("value"),
        ]
        if any(not isinstance(value, list) for value in arrays):
            raise ProfileEvaluationError(f"{case_id} series {key} arrays are missing")
        count = len(arrays[0])
        if count < 2 or any(len(value) != count for value in arrays[1:]):
            raise ProfileEvaluationError(f"{case_id} series {key} arrays are not aligned")
        numeric = np.asarray(arrays[2], dtype=np.float64)
        truth = np.asarray(arrays[3], dtype=np.float64)
        if not np.all(np.isfinite(numeric)) or not np.all(np.isfinite(truth)):
            raise ProfileEvaluationError(f"{case_id} series {key} contains non-finite values")
        segments = item.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ProfileEvaluationError(f"{case_id} series {key} has no explicit segments")
        cursor = 0
        for segment in segments:
            if not isinstance(segment, Mapping):
                raise ProfileEvaluationError(f"{case_id} series {key} segment is invalid")
            start = segment.get("emitted_index_start")
            stop = segment.get("emitted_index_stop")
            if (
                not isinstance(start, int)
                or not isinstance(stop, int)
                or start != cursor
                or stop <= start
            ):
                raise ProfileEvaluationError(f"{case_id} series {key} segment coverage is invalid")
            coordinates = numeric[start:stop]
            # A supported singleton is a valid disconnected segment.  Strict
            # monotonicity is meaningful only when a segment has multiple points.
            if len(coordinates) > 1 and np.any(np.diff(coordinates) <= 0.0):
                raise ProfileEvaluationError(f"{case_id} series {key} segment is not increasing")
            cursor = stop
        if cursor != count:
            raise ProfileEvaluationError(f"{case_id} series {key} segments do not cover its arrays")
        validated.append(item)
    if counts != EXPECTED_FAMILY_COUNTS:
        raise ProfileEvaluationError(f"{case_id} profile family counts differ")
    return tuple(validated)


def load_profile_support_case(root: Path | str, case_id: str) -> ProfileSupportCase:
    support_root = Path(root).expanduser().resolve()
    index_path = support_root / "index.json"
    index = read_json(index_path)
    if (
        index.get("schema") != SUPPORT_INDEX_SCHEMA
        or index.get("schema_version") != 1
        or index.get("dataset_revision") != DATASET_REVISION
    ):
        raise ProfileEvaluationError("profile support index contract differs")
    _identity(index, "index_identity")
    location = _location(index, case_id)
    relative = location.get("chunk_path")
    expected_sha = location.get("chunk_sha256")
    offset = location.get("case_offset")
    if (
        not isinstance(relative, str)
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ProfileEvaluationError("profile support chunk path is unsafe")
    chunk_path = (support_root / relative).resolve()
    if not chunk_path.is_relative_to(support_root):
        raise ProfileEvaluationError("profile support chunk escapes its root")
    actual_sha = sha256_file(chunk_path)
    if actual_sha != expected_sha:
        raise ProfileEvaluationError("profile support chunk SHA-256 differs")
    chunk = read_json(chunk_path)
    if (
        chunk.get("schema") != SUPPORT_CHUNK_SCHEMA
        or chunk.get("schema_version") != 1
        or chunk.get("dataset_revision") != DATASET_REVISION
    ):
        raise ProfileEvaluationError("profile support chunk contract differs")
    _identity(chunk, "chunk_identity")
    cases = chunk.get("cases")
    if not isinstance(cases, list) or not isinstance(offset, int) or not 0 <= offset < len(cases):
        raise ProfileEvaluationError("profile support case offset is invalid")
    case = cases[offset]
    if not isinstance(case, Mapping) or case.get("case_id") != case_id:
        raise ProfileEvaluationError("profile support case location does not resolve")
    _identity(case, "case_identity")
    native = case.get("native_support")
    if not isinstance(native, Mapping):
        raise ProfileEvaluationError(f"{case_id} has no native support counts")
    surface = native.get("surface_native_cells")
    volume = native.get("volume_native_cells")
    if not isinstance(surface, Mapping) or not isinstance(volume, Mapping):
        raise ProfileEvaluationError(f"{case_id} native support declarations differ")
    surface_count = surface.get("total_row_count")
    volume_count = volume.get("total_row_count")
    if not isinstance(surface_count, int) or surface_count < 1:
        raise ProfileEvaluationError(f"{case_id} surface count is invalid")
    if not isinstance(volume_count, int) or volume_count < 1:
        raise ProfileEvaluationError(f"{case_id} volume count is invalid")
    return ProfileSupportCase(
        root=support_root,
        index_sha256=sha256_file(index_path),
        chunk_sha256=actual_sha,
        case_id=case_id,
        surface_row_count=surface_count,
        volume_row_count=volume_count,
        series=_validate_series(case.get("series"), case_id),
    )


def _gather_field(
    manifest: PredictionChunkManifest | Path | str,
    raw_cell_ids: Sequence[int],
    *,
    case_id: str,
    support_id: str,
    field_name: str,
    expected_total_row_count: int,
    maximum_chunk_rows: int,
    hash_chunk_bytes: int,
    validation_block_rows: int,
) -> GatheredField:
    parsed = (
        manifest
        if isinstance(manifest, PredictionChunkManifest)
        else load_prediction_chunk_manifest(manifest)
    )
    if (
        parsed.case_id != case_id
        or parsed.support_id != support_id
        or parsed.total_row_count != expected_total_row_count
        or field_name not in parsed.field_components
    ):
        raise ProfileEvaluationError(f"{support_id} prediction manifest binding differs")
    if any(chunk.row_count > maximum_chunk_rows for chunk in parsed.chunks):
        raise ProfileEvaluationError(f"{support_id} prediction chunk exceeds the row limit")
    requested = np.asarray(raw_cell_ids, dtype=np.int64)
    if requested.ndim != 1 or len(requested) < 1:
        raise ProfileEvaluationError(f"{support_id} profile support contains no raw IDs")
    if np.any(requested < 0) or np.any(requested >= expected_total_row_count):
        raise ProfileEvaluationError(f"{support_id} profile support raw ID is out of range")
    unique = np.unique(requested)
    components = parsed.field_components[field_name]
    selected = np.empty(
        (len(unique),) if components == 1 else (len(unique), components), dtype=np.float64
    )
    found = np.zeros(len(unique), dtype=bool)
    try:
        for chunk in iter_prediction_chunks(
            parsed,
            hash_chunk_bytes=hash_chunk_bytes,
            validation_block_rows=validation_block_rows,
        ):
            start = chunk.descriptor.raw_cell_id_start
            stop = chunk.descriptor.raw_cell_id_stop
            first = int(np.searchsorted(unique, start, side="left"))
            last = int(np.searchsorted(unique, stop, side="left"))
            if first < last:
                local = unique[first:last] - start
                selected[first:last] = np.asarray(chunk.field(field_name)[local], dtype=np.float64)
                found[first:last] = True
    except PredictionChunkError as error:
        raise ProfileEvaluationError(str(error)) from error
    if not np.all(found) or not np.all(np.isfinite(selected)):
        raise ProfileEvaluationError(f"{support_id} profile prediction gather is incomplete")
    if sha256_file(parsed.path, chunk_bytes=hash_chunk_bytes) != parsed.sha256:
        raise ProfileEvaluationError(f"{support_id} prediction manifest changed during gather")
    unique.setflags(write=False)
    selected.setflags(write=False)
    return GatheredField(
        manifest_sha256=parsed.sha256,
        chunk_sha256=tuple(chunk.sha256 for chunk in parsed.chunks),
        raw_cell_ids=unique,
        values=selected,
    )


def _block_statistics(
    coordinate: Sequence[float],
    truth: Sequence[float],
    prediction: Sequence[float],
    segments: Sequence[Mapping[str, Any]],
) -> tuple[float, float, float, float]:
    if not (len(coordinate) == len(truth) == len(prediction)) or len(coordinate) < 2:
        raise ProfileEvaluationError("profile arrays must align and contain two points")
    truth_integral = 0.0
    truth_squared_integral = 0.0
    squared_error_integral = 0.0
    supported_length = 0.0
    for segment in segments:
        start = int(segment["emitted_index_start"])
        stop = int(segment["emitted_index_stop"])
        for left in range(start, stop - 1):
            right = left + 1
            width = float(coordinate[right]) - float(coordinate[left])
            if not math.isfinite(width) or width <= 0.0:
                raise ProfileEvaluationError("profile segment coordinate is not increasing")
            truth_left = float(truth[left])
            truth_right = float(truth[right])
            error_left = float(prediction[left]) - truth_left
            error_right = float(prediction[right]) - truth_right
            truth_integral += width * (truth_left + truth_right) / 2.0
            truth_squared_integral += width * (truth_left**2 + truth_right**2) / 2.0
            squared_error_integral += width * (error_left**2 + error_right**2) / 2.0
            supported_length += width
    if not math.isfinite(supported_length) or supported_length <= 0.0:
        raise ProfileEvaluationError("profile series has no positive supported length")
    return (
        truth_integral / supported_length,
        truth_squared_integral / supported_length,
        squared_error_integral / supported_length,
        math.sqrt(squared_error_integral / supported_length),
    )


def r2_from_block_statistics(statistics: Sequence[Sequence[float]]) -> float:
    if not statistics:
        raise ProfileEvaluationError("profile R2 requires at least one block")
    truth_sum = math.fsum(float(item[0]) for item in statistics)
    truth_squared_sum = math.fsum(float(item[1]) for item in statistics)
    squared_error_sum = math.fsum(float(item[2]) for item in statistics)
    truth_sst = truth_squared_sum - truth_sum**2 / len(statistics)
    if not math.isfinite(truth_sst) or truth_sst <= 0.0:
        raise ProfileEvaluationError("profile R2 truth support is constant")
    return 1.0 - squared_error_sum / truth_sst


def profile_statistics_from_series(
    support: ProfileSupportCase,
    prediction_series: Sequence[Mapping[str, Any]],
    *,
    prediction_scope: str = PREDICTION_SCOPE_FULL,
) -> dict[str, Any]:
    """Reduce retained profile predictions against exact native support."""

    if len(prediction_series) != 40:
        raise ProfileEvaluationError("profile prediction output must contain 40 series")
    if prediction_scope not in PREDICTION_SCOPES:
        raise ProfileEvaluationError("profile prediction scope differs")
    predicted_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in prediction_series:
        key = (str(row.get("family_id")), str(row.get("station_id")))
        if key in predicted_by_key:
            raise ProfileEvaluationError(f"profile prediction repeats {key}")
        predicted_by_key[key] = row
    support_by_key = {
        (str(row["family_id"]), str(row["station_id"])): row for row in support.series
    }
    if set(predicted_by_key) != set(support_by_key):
        raise ProfileEvaluationError("profile prediction identity coverage differs")

    statistics_by_key: dict[tuple[str, str], tuple[float, float, float, float]] = {}
    for key, truth_row in support_by_key.items():
        if truth_row.get("representation") == "shared_alias":
            continue
        prediction_row = predicted_by_key[key]
        is_velocity = key[0] in {
            CONSTANT_VELOCITY_FAMILY,
            RELATIVE_VELOCITY_FAMILY,
        }
        if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY and is_velocity:
            if (
                prediction_row.get("availability")
                != "not_submitted_surface_only"
                or "prediction" in prediction_row
            ):
                raise ProfileEvaluationError(
                    f"surface-only velocity profile availability differs for {key}"
                )
            continue
        if prediction_row.get("availability", "available") != "available":
            raise ProfileEvaluationError(f"profile availability differs for {key}")
        prediction = prediction_row.get("prediction")
        if (
            not isinstance(prediction, list)
            or prediction_row.get("coordinate") != truth_row["coordinate"]
        ):
            raise ProfileEvaluationError(f"profile prediction support differs for {key}")
        numeric_prediction = np.asarray(prediction, dtype=np.float64)
        if len(numeric_prediction) != len(truth_row["value"]) or not np.all(
            np.isfinite(numeric_prediction)
        ):
            raise ProfileEvaluationError(f"profile prediction values differ for {key}")
        statistics_by_key[key] = _block_statistics(
            truth_row["coordinate"],
            truth_row["value"],
            prediction,
            truth_row["segments"],
        )
    for key, truth_row in support_by_key.items():
        if truth_row.get("representation") != "shared_alias":
            continue
        if predicted_by_key[key].get("availability", "available") != "available":
            raise ProfileEvaluationError(f"profile alias availability differs for {key}")
        reference = truth_row["shared_support_ref"]
        canonical = (
            str(reference["canonical_family_id"]),
            str(reference["canonical_station_id"]),
        )
        try:
            statistics_by_key[key] = statistics_by_key[canonical]
        except KeyError as error:
            raise ProfileEvaluationError(f"profile alias does not resolve for {key}") from error

    def family(family_id: str) -> list[tuple[float, float, float, float]]:
        return [
            statistics_by_key[(str(row["family_id"]), str(row["station_id"]))]
            for row in support.series
            if row["family_id"] == family_id
            and (str(row["family_id"]), str(row["station_id"]))
            in statistics_by_key
        ]

    constant_velocity = family(CONSTANT_VELOCITY_FAMILY)
    constant_cp = family(CONSTANT_CP_FAMILY)
    relative_velocity = family(RELATIVE_VELOCITY_FAMILY)
    relative_cp = family(RELATIVE_CP_FAMILY)
    experimental = [
        statistics_by_key[(str(row["family_id"]), str(row["station_id"]))][3]
        for row in support.series
        if row["family_id"] == CONSTANT_VELOCITY_FAMILY
        and row["station_id"] in EXPERIMENTAL_VELOCITY_STATIONS
        and (str(row["family_id"]), str(row["station_id"]))
        in statistics_by_key
    ]
    expected_lengths = (
        (0, 4, 0, 4)
        if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
        else (16, 4, 16, 4)
    )
    expected_experimental = 0 if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY else 11
    if (
        tuple(map(len, (constant_velocity, constant_cp, relative_velocity, relative_cp)))
        != expected_lengths
        or len(experimental) != expected_experimental
    ):
        raise ProfileEvaluationError("profile metric family coverage differs")
    result = {
        "cp_cut_r2_blocks": [list(row[:3]) for row in constant_cp],
        "cp_cut_rmse": math.fsum(row[3] for row in constant_cp) / 4.0,
        "relative_cp_cut_r2_blocks": [list(row[:3]) for row in relative_cp],
        "relative_cp_cut_rmse": math.fsum(row[3] for row in relative_cp) / 4.0,
    }
    if prediction_scope == PREDICTION_SCOPE_FULL:
        result.update(
            {
                "velocity_profile_r2_blocks": [
                    list(row[:3]) for row in constant_velocity
                ],
                "velocity_profile_uinf_rmse": (
                    math.fsum(row[3] for row in constant_velocity) / 16.0
                ),
                "velocity_profile_experimental_subset_uinf_rmse": (
                    math.fsum(experimental) / 11.0
                ),
                "relative_velocity_profile_r2_blocks": [
                    list(row[:3]) for row in relative_velocity
                ],
                "relative_velocity_profile_uinf_rmse": (
                    math.fsum(row[3] for row in relative_velocity) / 16.0
                ),
            }
        )
    return result


def evaluate_case_profiles(
    support: ProfileSupportCase,
    *,
    surface_prediction_manifest: PredictionChunkManifest | Path | str,
    volume_prediction_manifest: PredictionChunkManifest | Path | str | None,
    prediction_scope: str = PREDICTION_SCOPE_FULL,
    maximum_chunk_rows: int = 1_000_000,
    hash_chunk_bytes: int = DEFAULT_HASH_CHUNK_BYTES,
    validation_block_rows: int = DEFAULT_VALIDATION_BLOCK_ROWS,
) -> dict[str, Any]:
    if prediction_scope not in PREDICTION_SCOPES:
        raise ProfileEvaluationError("profile prediction scope differs")
    if prediction_scope == PREDICTION_SCOPE_FULL and volume_prediction_manifest is None:
        raise ProfileEvaluationError("full-field profile evaluation requires a volume manifest")
    if (
        prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
        and volume_prediction_manifest is not None
    ):
        raise ProfileEvaluationError(
            "surface-only profile evaluation must not receive a volume manifest"
        )
    materialized = [row for row in support.series if row.get("representation") == "materialized"]
    surface_ids = [
        int(raw_id)
        for row in materialized
        if row.get("quantity_id") == "cp"
        for raw_id in row["raw_native_cell_id"]
    ]
    volume_ids = [
        int(raw_id)
        for row in materialized
        if row.get("quantity_id") == "velocity_ratio"
        for raw_id in row["raw_native_cell_id"]
    ]
    surface = _gather_field(
        surface_prediction_manifest,
        surface_ids,
        case_id=support.case_id,
        support_id="surface_native_cells",
        field_name="pMeanTrim",
        expected_total_row_count=support.surface_row_count,
        maximum_chunk_rows=maximum_chunk_rows,
        hash_chunk_bytes=hash_chunk_bytes,
        validation_block_rows=validation_block_rows,
    )
    volume = (
        _gather_field(
            volume_prediction_manifest,
            volume_ids,
            case_id=support.case_id,
            support_id="volume_native_cells",
            field_name="UMeanTrim",
            expected_total_row_count=support.volume_row_count,
            maximum_chunk_rows=maximum_chunk_rows,
            hash_chunk_bytes=hash_chunk_bytes,
            validation_block_rows=validation_block_rows,
        )
        if volume_prediction_manifest is not None
        else None
    )
    output_series: list[dict[str, Any]] = []
    velocity_statistics: list[tuple[float, float, float, float]] = []
    cp_statistics: list[tuple[float, float, float, float]] = []
    relative_velocity_statistics: list[tuple[float, float, float, float]] = []
    relative_cp_statistics: list[tuple[float, float, float, float]] = []
    evaluated_by_key: dict[
        tuple[str, str], tuple[tuple[float, float, float, float], list[float]]
    ] = {}
    aliases: list[Mapping[str, Any]] = []
    experimental_velocity_rmse: list[float] = []
    all_velocity_rmse: list[float] = []
    all_cp_rmse: list[float] = []
    for row in support.series:
        common = {
            key: row[key]
            for key in (
                "panel_id",
                "family_id",
                "placement_mode",
                "station_id",
                "quantity_id",
                "scoring_role",
                "representation",
                "placement_receipt_identity_sha256",
            )
        }
        if row.get("representation") == "shared_alias":
            output_series.append(
                {
                    **common,
                    "availability": "available",
                    "shared_support_ref": dict(row["shared_support_ref"]),
                }
            )
            aliases.append(row)
            continue
        raw_ids = row["raw_native_cell_id"]
        if row.get("quantity_id") == "velocity_ratio":
            if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY:
                output_series.append(
                    {
                        **common,
                        "availability": "not_submitted_surface_only",
                    }
                )
                continue
            if volume is None:
                raise ProfileEvaluationError("volume profile input is absent")
            native_prediction = volume.values_for(raw_ids)
            prediction = np.linalg.norm(native_prediction, axis=-1) / U_INF_M_PER_S
        elif row.get("quantity_id") == "cp":
            native_prediction = surface.values_for(raw_ids)
            prediction = 2.0 * native_prediction / (U_INF_M_PER_S * U_INF_M_PER_S)
        else:
            raise ProfileEvaluationError("profile series has an unknown quantity")
        prediction_values = [float(value) for value in prediction]
        emitted = {
            **common,
            "availability": "available",
            "support_identity_sha256": row["support_identity_sha256"],
            "coordinate_id": row["coordinate_id"],
            "coordinate_unit": row["coordinate_unit"],
            "coordinate": list(row["coordinate"]),
            "segments": [dict(segment) for segment in row["segments"]],
            "prediction": prediction_values,
        }
        for optional in ("display_coordinate_id", "display_coordinate_unit", "display_coordinate"):
            if optional in row:
                emitted[optional] = row[optional]
        output_series.append(emitted)
        statistics = _block_statistics(
            row["coordinate"], row["value"], prediction_values, row["segments"]
        )
        evaluated_by_key[(str(row["family_id"]), str(row["station_id"]))] = (
            statistics,
            prediction_values,
        )
        if row.get("family_id") == CONSTANT_VELOCITY_FAMILY:
            velocity_statistics.append(statistics)
            all_velocity_rmse.append(statistics[3])
            if row.get("station_id") in EXPERIMENTAL_VELOCITY_STATIONS:
                experimental_velocity_rmse.append(statistics[3])
        elif row.get("family_id") == CONSTANT_CP_FAMILY:
            cp_statistics.append(statistics)
            all_cp_rmse.append(statistics[3])
        elif row.get("family_id") == RELATIVE_VELOCITY_FAMILY:
            relative_velocity_statistics.append(statistics)
        elif row.get("family_id") == RELATIVE_CP_FAMILY:
            relative_cp_statistics.append(statistics)
    for alias in aliases:
        reference = alias["shared_support_ref"]
        canonical_key = (
            str(reference["canonical_family_id"]),
            str(reference["canonical_station_id"]),
        )
        if canonical_key not in evaluated_by_key:
            raise ProfileEvaluationError("profile alias does not resolve to materialized support")
        if alias.get("family_id") != RELATIVE_CP_FAMILY:
            raise ProfileEvaluationError("only report-only Cp series may share support")
        relative_cp_statistics.append(evaluated_by_key[canonical_key][0])
    expected_velocity = 0 if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY else 16
    if len(velocity_statistics) != expected_velocity or len(cp_statistics) != 4:
        raise ProfileEvaluationError("ranked constant profile coverage differs")
    expected_experimental = (
        0
        if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
        else len(EXPERIMENTAL_VELOCITY_STATIONS)
    )
    if len(experimental_velocity_rmse) != expected_experimental:
        raise ProfileEvaluationError("experimental velocity subset coverage differs")
    if (
        len(relative_velocity_statistics) != expected_velocity
        or len(relative_cp_statistics) != 4
    ):
        raise ProfileEvaluationError("report-only relative profile coverage differs")
    prediction_inputs = {
        "surface_native_cells": {
            "manifest_sha256": surface.manifest_sha256,
            "chunk_sha256": list(surface.chunk_sha256),
        }
    }
    if volume is not None:
        prediction_inputs["volume_native_cells"] = {
            "manifest_sha256": volume.manifest_sha256,
            "chunk_sha256": list(volume.chunk_sha256),
        }
    return {
        "schema": PROFILE_CASE_SCHEMA,
        "schema_version": 2,
        "case_id": support.case_id,
        "prediction_scope": prediction_scope,
        "support": {
            "index_sha256": support.index_sha256,
            "chunk_sha256": support.chunk_sha256,
            "constant_series_count": 20,
            "relative_series_count": 20,
            "explicit_segments_preserved": True,
        },
        "family_availability": {
            CONSTANT_VELOCITY_FAMILY: (
                "not_submitted_surface_only"
                if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
                else "available"
            ),
            RELATIVE_VELOCITY_FAMILY: (
                "not_submitted_surface_only"
                if prediction_scope == PREDICTION_SCOPE_SURFACE_ONLY
                else "available"
            ),
            CONSTANT_CP_FAMILY: "available",
            RELATIVE_CP_FAMILY: "available",
        },
        "prediction_inputs": prediction_inputs,
        "metric_statistics": profile_statistics_from_series(
            support,
            output_series,
            prediction_scope=prediction_scope,
        ),
        "series": output_series,
    }


__all__ = [
    "CONSTANT_CP_FAMILY",
    "CONSTANT_VELOCITY_FAMILY",
    "ProfileEvaluationError",
    "ProfileSupportCase",
    "evaluate_case_profiles",
    "load_profile_support_case",
    "profile_statistics_from_series",
    "r2_from_block_statistics",
]
