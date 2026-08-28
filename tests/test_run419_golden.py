from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from autocfd5_aiml.profiles import (
    ProfileSupportCase,
    profile_statistics_from_series,
    r2_from_block_statistics,
)

FIXTURE = Path(__file__).parent / "fixtures" / "run419-golden.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _support(document: dict) -> ProfileSupportCase:
    native = document["support_projection"]["native_support"]
    return ProfileSupportCase(
        root=FIXTURE.parent,
        index_sha256="0" * 64,
        chunk_sha256="1" * 64,
        case_id="run_419",
        surface_row_count=native["surface_native_cells"]["total_row_count"],
        volume_row_count=native["volume_native_cells"]["total_row_count"],
        series=tuple(document["support_projection"]["series"]),
    )


def test_existing_run419_core_projection_replays() -> None:
    document = _fixture()
    core = document["core_projection"]
    expected_source_hashes = {
        "core": "6aa349290049ad5498dd3a578865fc14aee5521be1ebc43208b43082a7a24bdf",
        "profiles": "3a5bca4c5f8730dcae4e29f69f415dc393050c6ebca6cf6e1303d307985bf262",
    }
    assert document["source_file_sha256"] == expected_source_hashes
    for metric_id, statistics in core["metric_sufficient_statistics"].items():
        expected = 100.0 * math.sqrt(statistics["numerator"] / statistics["denominator"])
        assert core["metric_values"][metric_id] == expected
    assert core["surface_entity_count"] == 7_284_102
    assert core["volume_entity_count"] == 121_635_947
    assert core["force_coefficients"]["Cd"] == 0.20997857570248848
    assert core["force_coefficients"]["CmPitch"] == -0.05397063567184078


def test_existing_run419_profiles_match_exact_native_support() -> None:
    document = _fixture()
    statistics = profile_statistics_from_series(
        _support(document), document["profile_prediction_series"]
    )
    encoded = json.dumps(
        statistics, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    assert hashlib.sha256(encoded).hexdigest() == (
        "9bcde20de2219acdf88bb9a4d8ffd6d5b43d4daba463053444402faa9806bd60"
    )
    assert statistics["velocity_profile_uinf_rmse"] == 0.012722685649733181
    assert statistics["cp_cut_rmse"] == 0.015373708203805573
    assert r2_from_block_statistics(statistics["velocity_profile_r2_blocks"]) == (
        0.9957833983449247
    )
    assert r2_from_block_statistics(statistics["cp_cut_r2_blocks"]) == 0.9955028959702529


def test_v2_gap_and_v1_stair_steps_are_retained() -> None:
    document = _fixture()
    rows = document["support_projection"]["series"]
    v1 = next(
        row
        for row in rows
        if row["family_id"] == "drivaerml-autocfd5-constant-v1"
        and row["station_id"] == "autocfd5_v1"
    )
    v2 = next(
        row
        for row in rows
        if row["family_id"] == "drivaerml-autocfd5-constant-v1"
        and row["station_id"] == "autocfd5_v2"
    )
    assert sum(left == right for left, right in zip(v1["value"], v1["value"][1:])) == 100
    assert [(row["coordinate_start"], row["coordinate_stop"]) for row in v2["segments"]] == [
        (0.01, 0.12),
        (0.77, 2.0),
    ]
    assert v2["coordinate"][11:13] == [0.12, 0.77]


def test_cp_display_coordinate_is_distinct_from_scoring_coordinate() -> None:
    rows = _fixture()["support_projection"]["series"]
    cp = next(
        row
        for row in rows
        if row["family_id"] == "drivaerml_cp_constant_v1"
        and row["station_id"] == "upperbody_centerline"
    )
    assert cp["coordinate_id"] == "arc_length_m"
    assert cp["display_coordinate_id"] == "streamwise_x_m"
    assert cp["coordinate"] != cp["display_coordinate"]
