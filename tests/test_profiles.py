from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from autocfd5_aiml.constants import PREDICTION_SCOPE_SURFACE_ONLY
from autocfd5_aiml.profiles import (
    CONSTANT_CP_FAMILY,
    CONSTANT_VELOCITY_FAMILY,
    EXPECTED_FAMILY_COUNTS,
    RELATIVE_CP_FAMILY,
    RELATIVE_VELOCITY_FAMILY,
    GatheredField,
    ProfileEvaluationError,
    ProfileSupportCase,
    _validate_series,
    evaluate_case_profiles,
    profile_statistics_from_series,
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


def _complete_support() -> ProfileSupportCase:
    rows = _valid_series()
    for row in rows:
        family = str(row["family_id"])
        is_velocity = family in {
            CONSTANT_VELOCITY_FAMILY,
            RELATIVE_VELOCITY_FAMILY,
        }
        row.update(
            {
                "panel_id": "panel",
                "placement_mode": "constant",
                "quantity_id": "velocity_ratio" if is_velocity else "cp",
                "scoring_role": "ranked" if family in {
                    CONSTANT_VELOCITY_FAMILY,
                    CONSTANT_CP_FAMILY,
                } else "report_only",
                "placement_receipt_identity_sha256": "a" * 64,
                "support_identity_sha256": "b" * 64,
                "coordinate_id": "z_m",
                "coordinate_unit": "m",
            }
        )
    return ProfileSupportCase(
        root=Path("."),
        index_sha256="c" * 64,
        chunk_sha256="d" * 64,
        case_id="run_1",
        surface_row_count=20,
        volume_row_count=20,
        series=tuple(rows),
    )


def test_surface_only_profiles_skip_volume_and_publish_no_dummy_velocity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def gather(_manifest: object, raw_ids: list[int], **kwargs: object) -> GatheredField:
        support_id = str(kwargs["support_id"])
        calls.append(support_id)
        assert support_id == "surface_native_cells"
        unique = np.unique(np.asarray(raw_ids, dtype=np.int64))
        values = np.zeros(len(unique), dtype=np.float64)
        return GatheredField(
            manifest_sha256="e" * 64,
            chunk_sha256=("f" * 64,),
            raw_cell_ids=unique,
            values=values,
        )

    monkeypatch.setattr("autocfd5_aiml.profiles._gather_field", gather)
    support = _complete_support()
    result = evaluate_case_profiles(
        support,
        surface_prediction_manifest=Path("surface/manifest.json"),
        volume_prediction_manifest=None,
        prediction_scope=PREDICTION_SCOPE_SURFACE_ONLY,
    )
    assert calls == ["surface_native_cells"]
    assert set(result["prediction_inputs"]) == {"surface_native_cells"}
    unavailable = [
        row for row in result["series"] if row["quantity_id"] == "velocity_ratio"
    ]
    assert len(unavailable) == 32
    assert all(row["availability"] == "not_submitted_surface_only" for row in unavailable)
    assert all("prediction" not in row for row in unavailable)
    assert "velocity_profile_r2_blocks" not in result["metric_statistics"]
    assert len(result["metric_statistics"]["cp_cut_r2_blocks"]) == 4

    fabricated = [dict(row) for row in result["series"]]
    fabricated[0]["prediction"] = [0.0, 0.0]
    with pytest.raises(ProfileEvaluationError, match="availability differs"):
        profile_statistics_from_series(
            support,
            fabricated,
            prediction_scope=PREDICTION_SCOPE_SURFACE_ONLY,
        )
