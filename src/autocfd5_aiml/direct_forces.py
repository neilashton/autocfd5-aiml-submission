"""Strict direct force-coefficient input for the optional v1.1.5 route."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .jsonio import read_json

DIRECT_FORCE_SCHEMA = "autocfd5-aiml-drivaerml-direct-force-v1"
DIRECT_FORCE_CONVENTION = "drivaerml-constant-reference-v1"
DIRECT_FORCE_FILE_NAME = "direct-force-coefficients.json"
_DIRECT_FORCE_KEYS = {
    "schema",
    "schema_version",
    "case_id",
    "coefficient_convention",
    "Cd",
    "Clf",
    "Clr",
}


class DirectForceError(ValueError):
    """Raised when a direct force-coefficient input is not exact and complete."""


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise DirectForceError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise DirectForceError(f"{label} must be a finite number") from error
    if not math.isfinite(result):
        raise DirectForceError(f"{label} must be a finite number")
    return result


def validate_direct_force_document(
    document: Mapping[str, Any], *, expected_case_id: str
) -> dict[str, float]:
    """Validate one source document and derive the two benchmark coefficients."""

    if set(document) != _DIRECT_FORCE_KEYS:
        raise DirectForceError("direct force file contains missing or unknown keys")
    if (
        document.get("schema") != DIRECT_FORCE_SCHEMA
        or document.get("schema_version") != 1
        or document.get("case_id") != expected_case_id
        or document.get("coefficient_convention") != DIRECT_FORCE_CONVENTION
    ):
        raise DirectForceError("direct force file contract differs")
    cd = _finite(document.get("Cd"), "Cd")
    clf = _finite(document.get("Clf"), "Clf")
    clr = _finite(document.get("Clr"), "Clr")
    return {
        "Cd": cd,
        "Clf": clf,
        "Clr": clr,
        "Cl": clf + clr,
        "CmPitch": (clf - clr) / 2.0,
    }


def load_direct_force_coefficients(
    path: Path | str, *, expected_case_id: str
) -> dict[str, float]:
    """Load and validate the fixed per-case direct-force file."""

    return validate_direct_force_document(
        read_json(path), expected_case_id=expected_case_id
    )


__all__ = [
    "DIRECT_FORCE_CONVENTION",
    "DIRECT_FORCE_FILE_NAME",
    "DIRECT_FORCE_SCHEMA",
    "DirectForceError",
    "load_direct_force_coefficients",
    "validate_direct_force_document",
]
