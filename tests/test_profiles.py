from __future__ import annotations

import pytest

from autocfd5_aiml.profiles import (
    CONSTANT_CP_FAMILY,
    CONSTANT_VELOCITY_FAMILY,
    EXPECTED_FAMILY_COUNTS,
    RELATIVE_CP_FAMILY,
    RELATIVE_VELOCITY_FAMILY,
    ProfileEvaluationError,
    _validate_series,
)


def _segment(start: int, stop: int) -> dict[str, object]:
    return {
        "coordinate_start": 0.0,
        "coordinate_stop": 1.0,
        "emitted_index_start": start,
        "emitted_index_stop": stop,
        "sample_index_start": start,
        "sample_index_stop": stop,
        "segment_id": "supported",
    }


def _valid_series() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for family, count in EXPECTED_FAMILY_COUNTS.items():
        for station_index in range(count):
            rows.append(
                {
                    "family_id": family,
                    "station_id": f"station_{station_index}",
                    "representation": "materialized",
                    "sample_index": [0, 1],
                    "raw_native_cell_id": [10, 11],
                    "coordinate": [0.0, 1.0],
                    "value": [0.0, 1.0],
                    "segments": [_segment(0, 2)],
                }
            )
    assert len(rows) == 40
    assert set(EXPECTED_FAMILY_COUNTS) == {
        CONSTANT_VELOCITY_FAMILY,
        RELATIVE_VELOCITY_FAMILY,
        CONSTANT_CP_FAMILY,
        RELATIVE_CP_FAMILY,
    }
    return rows


def test_profile_support_accepts_a_singleton_segment() -> None:
    rows = _valid_series()
    # These are the first coordinates and segment bounds retained by the
    # official run_26 constant autocfd5_r1 support.  The first point is a
    # complete supported segment, followed by a separate increasing segment.
    rows[0]["coordinate"] = [0.010000029204, 0.030000087611, 0.040000116814]
    rows[0]["sample_index"] = [1, 3, 4]
    rows[0]["raw_native_cell_id"] = [10, 11, 12]
    rows[0]["value"] = [0.0, 1.0, 2.0]
    rows[0]["segments"] = [
        {
            "coordinate_start": 0.010000029204,
            "coordinate_stop": 0.010000029204,
            "emitted_index_start": 0,
            "emitted_index_stop": 1,
            "sample_index_start": 1,
            "sample_index_stop": 2,
            "segment_id": "supported",
        },
        {
            "coordinate_start": 0.030000087611,
            "coordinate_stop": 0.040000116814,
            "emitted_index_start": 1,
            "emitted_index_stop": 3,
            "sample_index_start": 3,
            "sample_index_stop": 5,
            "segment_id": "supported",
        },
    ]

    assert len(_validate_series(rows, "run_26")) == 40


@pytest.mark.parametrize("coordinates", ([0.0, 0.0], [1.0, 0.0]))
def test_profile_support_rejects_non_increasing_multi_point_segment(
    coordinates: list[float],
) -> None:
    rows = _valid_series()
    rows[0]["coordinate"] = coordinates

    with pytest.raises(ProfileEvaluationError, match="segment is not increasing"):
        _validate_series(rows, "run_test")
