from __future__ import annotations

from pathlib import Path


def test_tracked_content_has_no_legacy_product_terms() -> None:
    root = Path(__file__).resolve().parents[1]
    blocked = (("fluid" + "sbench").encode(), ("leader" + "board").encode())
    ignored = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        payload = path.read_bytes().lower()
        for token in blocked:
            assert token not in payload, f"legacy term found in {path.relative_to(root)}"
