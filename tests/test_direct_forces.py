from __future__ import annotations

import pytest

from autocfd5_aiml.direct_forces import (
    DIRECT_FORCE_CONVENTION,
    DIRECT_FORCE_SCHEMA,
    DirectForceError,
    validate_direct_force_document,
)


def _document() -> dict[str, object]:
    return {
        "schema": DIRECT_FORCE_SCHEMA,
        "schema_version": 1,
        "case_id": "run_419",
        "coefficient_convention": DIRECT_FORCE_CONVENTION,
        "Cd": 0.21,
        "Clf": -0.061,
        "Clr": 0.046,
    }


def test_direct_force_document_derives_lift_and_pitch() -> None:
    coefficients = validate_direct_force_document(_document(), expected_case_id="run_419")
    assert coefficients == {
        "Cd": 0.21,
        "Clf": -0.061,
        "Clr": 0.046,
        "Cl": -0.015,
        "CmPitch": -0.0535,
    }


@pytest.mark.parametrize("key", ["Cl", "CmPitch", "unexpected"])
def test_direct_force_document_rejects_derived_or_unknown_values(key: str) -> None:
    document = _document()
    document[key] = 0.0
    with pytest.raises(DirectForceError, match="unknown keys"):
        validate_direct_force_document(document, expected_case_id="run_419")
