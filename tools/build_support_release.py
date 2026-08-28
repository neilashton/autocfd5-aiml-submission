#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any

INDEX_SCHEMA = "autocfd5-aiml-native-profile-support-index-v1"
CHUNK_SCHEMA = "autocfd5-aiml-native-profile-support-chunk-v1"
CASE_SCHEMA = "autocfd5-aiml-native-profile-support-case-v1"
RELEASE_SCHEMA = "autocfd5-aiml-native-profile-support-release-v1"
DATASET_REVISION = "7a5c0948ce27be709b1116a3a190f806e7a8f79f"
DATASET_REPOSITORY = "neashton/drivaerml"
FAMILY_COUNTS = {
    "drivaerml-autocfd5-constant-v1": 16,
    "drivaerml-velocity-relative-v3": 16,
    "drivaerml_cp_constant_v1": 4,
    "drivaerml_cp_relative_v1": 4,
}
_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
_DISALLOWED = ("fluid" + "sbench", "leader" + "board")


class BuildError(ValueError):
    pass


def canonical(value: object, *, newline: bool = True) -> bytes:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            result.update(block)
    return result.hexdigest()


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise BuildError(f"JSON document is not an object: {path}")
    return value


def identity(document: dict[str, Any], field: str, scope: str) -> None:
    body = dict(document)
    body.pop(field, None)
    document[field] = {
        "algorithm": "sha256",
        "scope": scope,
        "sha256": digest(canonical(body)),
    }


def domain_identity(domain: str, value: object) -> str:
    return digest(domain.encode("ascii") + b"\0" + canonical(value, newline=False))


def scientific_projection(series: dict[str, Any]) -> dict[str, Any]:
    common = {
        "family_id": series["family_id"],
        "station_id": series["station_id"],
        "quantity_id": series["quantity_id"],
        "representation": series["representation"],
    }
    if series["representation"] == "shared_alias":
        reference = series["shared_support_ref"]
        return {
            **common,
            "canonical_family_id": reference["canonical_family_id"],
            "canonical_station_id": reference["canonical_station_id"],
        }
    result = {
        **common,
        "sample_index": series["sample_index"],
        "raw_native_cell_id": series["raw_native_cell_id"],
        "coordinate_id": series["coordinate_id"],
        "coordinate_unit": series["coordinate_unit"],
        "coordinate": series["coordinate"],
        "value": series["value"],
        "segments": series["segments"],
        "unsupported_samples": series.get("unsupported_samples", []),
    }
    for key in ("display_coordinate_id", "display_coordinate_unit", "display_coordinate"):
        if key in series:
            result[key] = series[key]
    return result


def placement_identity(source: dict[str, Any]) -> str:
    value = {
        "schema": "autocfd5-aiml-profile-placement-v1",
        "family_id": source["family_id"],
        "placement_mode": source["placement_mode"],
        "station_id": source["station_id"],
    }
    return domain_identity("autocfd5-aiml-profile-placement", value)


def materialized_series(source: dict[str, Any]) -> dict[str, Any]:
    result = {
        "panel_id": source["panel_id"],
        "family_id": source["family_id"],
        "placement_mode": source["placement_mode"],
        "station_id": source["station_id"],
        "quantity": source["quantity"],
        "quantity_id": source["quantity_id"],
        "units": source["units"],
        "scoring_role": ("scored" if source["placement_mode"] == "constant" else "report_only"),
        "representation": "materialized",
        "placement_receipt_identity_sha256": placement_identity(source),
        "sample_index": source["sample_index"],
        "raw_native_cell_id": source["raw_native_cell_id"],
        "coordinate_id": source["coordinate_id"],
        "coordinate_unit": source["coordinate_unit"],
        "coordinate": source["coordinate"],
        "segments": source["segments"],
        "unsupported_samples": source.get("unsupported_samples", []),
        "value": source["value"],
    }
    for key in ("display_coordinate_id", "display_coordinate_unit", "display_coordinate"):
        if key in source:
            result[key] = source[key]
    result["coordinate_identity_sha256"] = domain_identity(
        "autocfd5-aiml-coordinate-array-v1", result["coordinate"]
    )
    result["value_identity_sha256"] = domain_identity(
        "autocfd5-aiml-native-value-array-v1", result["value"]
    )
    result["native_id_identity_sha256"] = domain_identity(
        "autocfd5-aiml-native-id-array-v1", result["raw_native_cell_id"]
    )
    if "display_coordinate" in result:
        result["display_coordinate_identity_sha256"] = domain_identity(
            "autocfd5-aiml-display-coordinate-array-v1", result["display_coordinate"]
        )
    support_body = {
        key: result[key]
        for key in (
            "family_id",
            "station_id",
            "quantity_id",
            "sample_index",
            "raw_native_cell_id",
            "coordinate",
            "segments",
            "value",
        )
    }
    if "display_coordinate" in result:
        support_body["display_coordinate"] = result["display_coordinate"]
    result["support_identity_sha256"] = domain_identity(
        "autocfd5-aiml-native-series-support-v1", support_body
    )
    result["series_identity_sha256"] = domain_identity("autocfd5-aiml-native-series-v1", result)
    return result


def alias_series(
    source: dict[str, Any],
    canonical_support: dict[tuple[str, str], str],
) -> dict[str, Any]:
    reference = source["shared_support_ref"]
    key = (reference["canonical_family_id"], reference["canonical_station_id"])
    if key not in canonical_support:
        raise BuildError(f"alias does not resolve: {key}")
    result = {
        "panel_id": source["panel_id"],
        "family_id": source["family_id"],
        "placement_mode": source["placement_mode"],
        "station_id": source["station_id"],
        "quantity": source["quantity"],
        "quantity_id": source["quantity_id"],
        "units": source["units"],
        "scoring_role": "report_only",
        "representation": "shared_alias",
        "placement_receipt_identity_sha256": placement_identity(source),
        "shared_support_ref": {
            "canonical_family_id": key[0],
            "canonical_station_id": key[1],
            "canonical_support_identity_sha256": canonical_support[key],
            "shared_support_id": f"{key[0]}:{key[1]}",
        },
    }
    result["series_identity_sha256"] = domain_identity(
        "autocfd5-aiml-native-series-alias-v1", result
    )
    return result


def native_support(source: dict[str, Any]) -> dict[str, Any]:
    boundary = source["native_boundary"]
    volume = source["native_volume"]
    return {
        "surface_native_cells": {
            "field_name": boundary["field_name"],
            "total_row_count": boundary["tuple_count"],
            "source_sha256": boundary["source_sha256"],
            "selected_unique_row_count": boundary["selected_unique_raw_polygon_id_count"],
            "selected_values_sha256": boundary["selected_values_sha256"],
        },
        "volume_native_cells": {
            "field_name": volume["field_name"],
            "total_row_count": volume["tuple_count"],
            "source_part_sha256": [part["sha256"] for part in volume["source_parts"]],
            "selected_unique_row_count": volume["selected_unique_raw_cell_id_count"],
            "selected_values_sha256": volume["selected_values_sha256"],
        },
    }


def transform_case(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_series = source.get("series")
    if not isinstance(source_series, list) or len(source_series) != 40:
        raise BuildError(f"{source.get('case_id')} does not contain 40 series")
    materialized = [
        materialized_series(row) for row in source_series if row["representation"] == "materialized"
    ]
    canonical_support = {
        (row["family_id"], row["station_id"]): row["support_identity_sha256"]
        for row in materialized
    }
    by_key = {(row["family_id"], row["station_id"]): row for row in materialized}
    transformed = []
    projections = []
    counts = {family: 0 for family in FAMILY_COUNTS}
    for source_row in source_series:
        key = (source_row["family_id"], source_row["station_id"])
        row = (
            by_key[key]
            if source_row["representation"] == "materialized"
            else alias_series(source_row, canonical_support)
        )
        transformed.append(row)
        projections.append(scientific_projection(source_row))
        counts[row["family_id"]] += 1
    if counts != FAMILY_COUNTS:
        raise BuildError(f"{source.get('case_id')} family coverage differs")
    output_projections = [scientific_projection(row) for row in transformed]
    if canonical(output_projections) != canonical(projections):
        raise BuildError(f"{source.get('case_id')} scientific arrays changed in transformation")
    result = {
        "schema": CASE_SCHEMA,
        "schema_version": 1,
        "case_id": source["case_id"],
        "dataset_revision": DATASET_REVISION,
        "series_count": 40,
        "native_support": native_support(source),
        "series": transformed,
    }
    identity(result, "case_identity", "case_without_case_identity")
    return result, projections


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, _ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o444) << 16
    return info


def assert_clean(path: Path) -> None:
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        lowered = file.read_bytes().lower()
        for token in _DISALLOWED:
            if token.encode("ascii") in lowered:
                raise BuildError(f"disallowed legacy term found in {file}")


def build(source_root: Path, output_root: Path, archive: Path) -> dict[str, Any]:
    if output_root.exists() or archive.exists():
        raise BuildError("output directory and archive must not already exist")
    source_index = load(source_root / "index.json")
    if source_index.get("dataset_revision") != DATASET_REVISION:
        raise BuildError("source support uses a different dataset revision")
    output_root.mkdir(parents=True)
    chunk_records = []
    case_locations = []
    case_ids = []
    projection_digest = hashlib.sha256()
    for chunk_offset, descriptor in enumerate(source_index["chunks"]):
        source_path = source_root / descriptor["path"]
        if file_digest(source_path) != descriptor["sha256"]:
            raise BuildError(f"source chunk identity differs: {source_path}")
        source_chunk = load(source_path)
        cases = []
        for case_offset, source_case in enumerate(source_chunk["cases"]):
            case, projections = transform_case(source_case)
            cases.append(case)
            case_id = case["case_id"]
            case_ids.append(case_id)
            projection_digest.update(canonical({"case_id": case_id, "series": projections}))
            case_locations.append(
                {
                    "case_id": case_id,
                    "chunk_id": f"chunk-{chunk_offset:03d}",
                    "chunk_path": f"chunks/chunk-{chunk_offset:03d}.json",
                    "case_offset": case_offset,
                }
            )
        chunk = {
            "schema": CHUNK_SCHEMA,
            "schema_version": 1,
            "dataset_revision": DATASET_REVISION,
            "chunk_id": f"chunk-{chunk_offset:03d}",
            "case_count": len(cases),
            "case_ids": [case["case_id"] for case in cases],
            "series_per_case": 40,
            "series_count": 40 * len(cases),
            "cases": cases,
        }
        identity(chunk, "chunk_identity", "chunk_without_chunk_identity")
        relative = Path("chunks") / f"chunk-{chunk_offset:03d}.json"
        destination = output_root / relative
        write(destination, chunk)
        sha = file_digest(destination)
        for location in case_locations[-len(cases) :]:
            location["chunk_sha256"] = sha
        chunk_records.append(
            {
                "chunk_id": chunk["chunk_id"],
                "path": relative.as_posix(),
                "sha256": sha,
                "size_bytes": destination.stat().st_size,
                "case_count": len(cases),
                "case_ids": chunk["case_ids"],
            }
        )
    if len(case_ids) != 484 or len(set(case_ids)) != 484:
        raise BuildError("support does not cover 484 unique cases")
    index = {
        "schema": INDEX_SCHEMA,
        "schema_version": 1,
        "dataset_id": "drivaerml",
        "dataset_repository": DATASET_REPOSITORY,
        "dataset_revision": DATASET_REVISION,
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "cases_per_chunk": 8,
        "series_per_case": 40,
        "series_count": len(case_ids) * 40,
        "profile_set": FAMILY_COUNTS,
        "constant_series_per_case": 20,
        "relative_series_per_case": 20,
        "scoring": {
            "constant_velocity_series": 16,
            "constant_cp_series": 4,
            "relative_profile_weight": 0.0,
            "cp_scoring_coordinate": "arc_length_m",
            "cp_display_coordinate": "streamwise_x_m",
            "explicit_segments_preserved": True,
            "smoothing_applied": False,
        },
        "scientific_projection_sha256": projection_digest.hexdigest(),
        "chunks": chunk_records,
        "case_locations": case_locations,
    }
    identity(index, "index_identity", "index_without_index_identity")
    write(output_root / "index.json", index)
    release = {
        "schema": RELEASE_SCHEMA,
        "schema_version": 1,
        "dataset_revision": DATASET_REVISION,
        "index_sha256": file_digest(output_root / "index.json"),
        "scientific_projection_sha256": projection_digest.hexdigest(),
        "case_count": len(case_ids),
        "series_count": len(case_ids) * 40,
        "source_arrays_transformed_without_numeric_changes": True,
    }
    write(output_root / "release.json", release)
    assert_clean(output_root)
    archive.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{archive.name}.", dir=archive.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as bundle:
            for file in sorted(output_root.rglob("*")):
                if file.is_file():
                    name = file.relative_to(output_root).as_posix()
                    bundle.writestr(zip_info(name), file.read_bytes())
        os.replace(temporary, archive)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "archive": str(archive),
        "archive_sha256": file_digest(archive),
        "archive_size_bytes": archive.stat().st_size,
        "index_sha256": release["index_sha256"],
        "scientific_projection_sha256": projection_digest.hexdigest(),
        "case_count": len(case_ids),
        "series_count": len(case_ids) * 40,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        args.source_root.expanduser().resolve(),
        args.output_root.expanduser().resolve(),
        args.archive.expanduser().resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
