from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from autocfd5_aiml.case_evaluator import CaseEvaluationError, evaluate_case
from autocfd5_aiml.constants import (
    PREDICTION_SCOPE_SURFACE_ONLY,
    REGIONAL_DIAGNOSTICS_CONTRACT_SHA256,
    SUPPORT_INDEX_SHA256,
)


class _Areas:
    closed = False

    def close(self) -> None:
        self.closed = True


class _Evaluation:
    def to_json(self) -> dict[str, object]:
        return {"prediction_scope": PREDICTION_SCOPE_SURFACE_ONLY}


def test_surface_only_case_never_opens_native_or_predicted_volume(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = SimpleNamespace(
        surface_cell_area=SimpleNamespace(
            sha256="a" * 64,
            source_boundary_sha256="b" * 64,
        )
    )
    resolved = SimpleNamespace(
        boundary_path=tmp_path / "boundary.vtp",
        surface_cell_area_path=tmp_path / "areas.npy",
    )
    pin = SimpleNamespace(
        case=lambda case_id: case,
        resolve=lambda case_id, dataset_root: resolved,
    )
    areas = _Areas()

    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.load_native_source_pin", lambda path: pin
    )
    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.sha256_file",
        lambda path: (
            SUPPORT_INDEX_SHA256
            if Path(path).name == "index.json"
            else REGIONAL_DIAGNOSTICS_CONTRACT_SHA256
        ),
    )
    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.load_native_surface_vtp",
        lambda path: object(),
    )
    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.audit_fixed_surface_area_file",
        lambda *args, **kwargs: areas,
    )
    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.evaluate_surface_only_candidate_case",
        lambda **kwargs: _Evaluation(),
    )
    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.load_profile_support_case",
        lambda *args: object(),
    )

    def profiles(_support: object, **kwargs: object) -> dict[str, object]:
        assert kwargs["volume_prediction_manifest"] is None
        assert kwargs["prediction_scope"] == PREDICTION_SCOPE_SURFACE_ONLY
        return {"prediction_scope": PREDICTION_SCOPE_SURFACE_ONLY}

    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.evaluate_case_profiles", profiles
    )

    def volume_was_opened(*args: object, **kwargs: object) -> None:
        raise AssertionError("surface-only evaluation opened volume data")

    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.open_verified_multipart", volume_was_opened
    )
    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.open_verified_monolithic", volume_was_opened
    )
    monkeypatch.setattr(
        "autocfd5_aiml.case_evaluator.evaluate_candidate_case", volume_was_opened
    )

    result = evaluate_case(
        case_id="run_1",
        native_source_pin=tmp_path / "pin.json",
        dataset_root=tmp_path / "data",
        support_root=tmp_path / "support",
        surface_prediction_manifest=tmp_path / "surface" / "manifest.json",
        prediction_scope=PREDICTION_SCOPE_SURFACE_ONLY,
    )
    assert result["prediction_scope"] == PREDICTION_SCOPE_SURFACE_ONLY
    assert areas.closed is True


def test_surface_only_case_rejects_any_volume_input(tmp_path: Path) -> None:
    with pytest.raises(CaseEvaluationError, match="must not receive a volume manifest"):
        evaluate_case(
            case_id="run_1",
            native_source_pin=tmp_path / "pin.json",
            dataset_root=tmp_path / "data",
            support_root=tmp_path / "support",
            surface_prediction_manifest=tmp_path / "surface" / "manifest.json",
            volume_prediction_manifest=tmp_path / "volume" / "manifest.json",
            prediction_scope=PREDICTION_SCOPE_SURFACE_ONLY,
        )
