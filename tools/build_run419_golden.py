#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


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
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"input is not a JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--support-chunk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = load(args.core)
    profile_document = load(args.profiles)
    support_document = load(args.support_chunk)
    cases = profile_document.get("cases")
    if not isinstance(cases, list) or len(cases) != 1 or cases[0].get("case_id") != "run_419":
        raise ValueError("profile input must contain only run_419")
    series = []
    for row in cases[0]["series"]:
        retained = {
            key: row[key]
            for key in (
                "family_id",
                "station_id",
                "quantity_id",
                "representation",
                "placement_mode",
                "scoring_role",
            )
        }
        if row["representation"] == "materialized":
            retained["coordinate"] = row["coordinate"]
            retained["prediction"] = row["prediction"]
        series.append(retained)
    support_cases = [
        case for case in support_document.get("cases", []) if case.get("case_id") == "run_419"
    ]
    if len(support_cases) != 1:
        raise ValueError("support input must contain run_419 exactly once")
    support_case = support_cases[0]
    result = {
        "schema": "autocfd5-aiml-run419-numerical-golden-v1",
        "schema_version": 1,
        "case_id": "run_419",
        "source_file_sha256": {
            "core": sha256(args.core),
            "profiles": sha256(args.profiles),
        },
        "core_projection": {
            "metric_values": core["metric_values"],
            "metric_sufficient_statistics": core["metric_sufficient_statistics"],
            "additive_sums": core["additive_sums"],
            "force_coefficients": core["force_coefficients"],
            "surface_entity_count": core["prediction_inputs"]["surface_native_cells"][
                "entity_count"
            ],
            "volume_entity_count": core["prediction_inputs"]["volume_native_cells"]["entity_count"],
        },
        "profile_prediction_series": series,
        "support_projection": {
            "native_support": support_case["native_support"],
            "series": support_case["series"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result))
    print(hashlib.sha256(args.output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
