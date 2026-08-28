#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PIN_SCHEMA = "autocfd5-aiml-drivaerml-native-source-pin-v1"
SPLIT_SCHEMA = "autocfd5-aiml-drivaerml-split-v1"
PROFILE_SCHEMA = "autocfd5-aiml-drivaerml-profile-definition-v1"
_DISALLOWED = ("fluid" + "sbench", "leader" + "board")


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"JSON document is not an object: {path}")
    return value


def write(path: Path, value: object) -> None:
    payload = canonical(value)
    lowered = payload.lower()
    for token in _DISALLOWED:
        if token.encode("ascii") in lowered:
            raise ValueError(f"disallowed legacy term in generated file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def clean_file(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in ("path", "size_bytes", "lfs_sha256")}


def transform_pin(source: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for case in source["cases"]:
        area = clean_file(case["surface_cell_area"])
        area.update(
            {
                key: case["surface_cell_area"][key]
                for key in ("dtype", "element_count", "source_boundary_sha256")
            }
        )
        volume = case["volume"]
        cases.append(
            {
                "case_id": case["case_id"],
                "run_number": case["run_number"],
                "boundary": clean_file(case["boundary"]),
                "surface_cell_area": area,
                "volume": {
                    "logical_path_after_assembly": volume["logical_path_after_assembly"],
                    "part_count": volume["part_count"],
                    "parts": [
                        {
                            **clean_file(part),
                            "part_index": part["part_index"],
                        }
                        for part in volume["parts"]
                    ],
                    "total_size_bytes": volume["total_size_bytes"],
                },
            }
        )
    repository = source["repository"]
    return {
        "schema": PIN_SCHEMA,
        "schema_version": 1,
        "repository": {
            "provider": repository["provider"],
            "repo_id": repository["repo_id"],
            "repo_type": repository["repo_type"],
            "revision": repository["revision"],
        },
        "case_scope": source["case_scope"],
        "totals": source["totals"],
        "cases": cases,
    }


def transform_split(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SPLIT_SCHEMA,
        "schema_version": 1,
        "dataset_id": "drivaerml",
        "split_id": source["split_id"],
        "split_label": source["split_label"],
        "case_set_id": source["case_set_id"],
        "train_case_count": source["training_case_count"],
        "validation_case_count": source["validation_case_count"],
        "test_case_count": source["case_count"],
        "train_case_ids": source["train_case_ids"],
        "validation_case_ids": source["validation_case_ids"],
        "test_case_ids": source["case_ids"],
    }


def transform_profiles(source: dict[str, Any]) -> dict[str, Any]:
    velocity = source["velocity_profiles"]
    pressure = source["pressure_cuts"]
    return {
        "schema": PROFILE_SCHEMA,
        "schema_version": 1,
        "dataset_id": "drivaerml",
        "velocity_profiles": {
            **{key: value for key, value in velocity.items() if key != "definition_authority"},
            "definition_authority": "AutoCFD5",
            "constant_series_per_case": 16,
            "relative_series_per_case": 16,
            "relative_scoring_weight": 0.0,
            "smoothing": "none",
            "unsupported_intervals": "explicit_segments_never_bridged",
        },
        "pressure_cuts": {
            **{
                key: value
                for key, value in pressure.items()
                if key not in {"definition_authority", "extraction_status"}
            },
            "definition_authority": "AutoCFD5",
            "constant_series_per_case": 4,
            "relative_series_per_case": 4,
            "relative_scoring_weight": 0.0,
            "scoring_coordinate": "arc_length_m",
            "display_coordinate": "streamwise_x_m",
            "display_coordinate_is_scoring_input": False,
            "segments_are_sorted_or_joined_for_display": False,
        },
        "excluded_diagnostics": {
            "discrete_cp_tap_count": 209,
            "included_in_score": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pin", type=Path, required=True)
    parser.add_argument("--source-splits", type=Path, required=True)
    parser.add_argument("--source-profiles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    pin_path = output / "native-source-pin.json"
    write(pin_path, transform_pin(load(args.source_pin)))
    split_count = 0
    for path in sorted(args.source_splits.glob("*.json")):
        write(output / "splits" / path.name, transform_split(load(path)))
        split_count += 1
    write(output / "profiles.json", transform_profiles(load(args.source_profiles)))
    print(
        json.dumps(
            {
                "native_source_pin_sha256": hashlib.sha256(pin_path.read_bytes()).hexdigest(),
                "split_count": split_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
