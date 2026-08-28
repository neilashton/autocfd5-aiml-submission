from __future__ import annotations

import html
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .jsonio import read_json
from .profiles import (
    CONSTANT_CP_FAMILY,
    CONSTANT_VELOCITY_FAMILY,
    RELATIVE_CP_FAMILY,
    RELATIVE_VELOCITY_FAMILY,
    load_profile_support_case,
)


class ReportError(ValueError):
    """Raised when an individual profile report cannot be rendered."""


_FAMILY_LABELS = {
    CONSTANT_VELOCITY_FAMILY: "Constant-placement velocity profiles",
    RELATIVE_VELOCITY_FAMILY: "Relative-placement velocity profiles (report only)",
    CONSTANT_CP_FAMILY: "Constant-placement continuous Cp cuts",
    RELATIVE_CP_FAMILY: "Relative-placement continuous Cp cuts (report only)",
}


def _prediction_series(result_root: Path, case_id: str) -> list[Mapping[str, Any]]:
    index = read_json(result_root / "profiles" / "index.json")
    chunks = index.get("chunks")
    if not isinstance(chunks, list):
        raise ReportError("profile prediction index has no chunks")
    matching = [row for row in chunks if case_id in row.get("case_ids", [])]
    if len(matching) != 1:
        raise ReportError(f"profile predictions do not locate {case_id}")
    chunk = read_json(result_root / matching[0]["path"])
    cases = [row for row in chunk.get("cases", []) if row.get("case_id") == case_id]
    if len(cases) != 1 or not isinstance(cases[0].get("series"), list):
        raise ReportError(f"profile prediction chunk does not contain {case_id}")
    return cases[0]["series"]


def _bounds(*arrays: Sequence[float]) -> tuple[float, float]:
    values = [float(value) for array in arrays for value in array]
    if not values or any(not math.isfinite(value) for value in values):
        raise ReportError("plot arrays contain no finite support")
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        padding = max(abs(low) * 0.05, 1.0e-6)
        return low - padding, high + padding
    padding = (high - low) * 0.06
    return low - padding, high + padding


def _polyline(
    x: Sequence[float],
    y: Sequence[float],
    *,
    x_bounds: tuple[float, float],
    y_bounds: tuple[float, float],
    color: str,
    segments: Sequence[Mapping[str, Any]],
) -> str:
    left, right = x_bounds
    bottom, top = y_bounds
    result = []
    for segment in segments:
        start = int(segment["emitted_index_start"])
        stop = int(segment["emitted_index_stop"])
        points = []
        for x_value, y_value in zip(x[start:stop], y[start:stop], strict=True):
            px = 54.0 + 706.0 * (float(x_value) - left) / (right - left)
            py = 18.0 + 252.0 * (top - float(y_value)) / (top - bottom)
            points.append(f"{px:.3f},{py:.3f}")
        result.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" '
            'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
        )
    return "".join(result)


def _chart(
    support: Mapping[str, Any],
    prediction: Sequence[float],
    *,
    title: str,
) -> str:
    score_coordinate = support["coordinate"]
    display_coordinate = support.get("display_coordinate", score_coordinate)
    truth = support["value"]
    segments = support["segments"]
    if not (len(display_coordinate) == len(truth) == len(prediction)):
        raise ReportError(f"plot arrays differ for {title}")
    x_bounds = _bounds(display_coordinate)
    y_bounds = _bounds(truth, prediction)
    truth_line = _polyline(
        display_coordinate,
        truth,
        x_bounds=x_bounds,
        y_bounds=y_bounds,
        color="#101828",
        segments=segments,
    )
    predicted_line = _polyline(
        display_coordinate,
        prediction,
        x_bounds=x_bounds,
        y_bounds=y_bounds,
        color="#d92d20",
        segments=segments,
    )
    axis_label = "Streamwise x (m)" if "display_coordinate" in support else "Distance (m)"
    return f"""
<article class="chart">
  <h3>{html.escape(title)}</h3>
  <svg viewBox="0 0 780 310" role="img" aria-label="{html.escape(title)}">
    <rect x="54" y="18" width="706" height="252" fill="#fff" stroke="#d0d5dd"/>
    {truth_line}{predicted_line}
    <text x="54" y="290">{x_bounds[0]:.3g}</text>
    <text x="760" y="290" text-anchor="end">{x_bounds[1]:.3g}</text>
    <text x="407" y="304" text-anchor="middle">{axis_label}</text>
    <text x="48" y="24" text-anchor="end">{y_bounds[1]:.3g}</text>
    <text x="48" y="270" text-anchor="end">{y_bounds[0]:.3g}</text>
  </svg>
</article>"""


def render_case_report(
    *,
    result_root: Path | str,
    support_root: Path | str,
    case_id: str,
    output: Path | str,
) -> Path:
    result_directory = Path(result_root).expanduser().resolve()
    destination = Path(output).expanduser().resolve()
    if destination.suffix.lower() != ".html" or destination.exists():
        raise ReportError("report output must be a new .html file")
    result = read_json(result_directory / "result.json")
    support_case = load_profile_support_case(support_root, case_id)
    predictions = _prediction_series(result_directory, case_id)
    support_by_key = {
        (str(row["family_id"]), str(row["station_id"])): row for row in support_case.series
    }
    prediction_by_key = {
        (str(row["family_id"]), str(row["station_id"])): row for row in predictions
    }
    sections = []
    for family in (
        CONSTANT_VELOCITY_FAMILY,
        RELATIVE_VELOCITY_FAMILY,
        CONSTANT_CP_FAMILY,
        RELATIVE_CP_FAMILY,
    ):
        charts = []
        for key, support in support_by_key.items():
            if key[0] != family:
                continue
            predicted = prediction_by_key.get(key)
            if predicted is None:
                raise ReportError(f"prediction series is missing: {key}")
            if support.get("representation") == "shared_alias":
                reference = support["shared_support_ref"]
                canonical = (
                    str(reference["canonical_family_id"]),
                    str(reference["canonical_station_id"]),
                )
                support = support_by_key[canonical]
                predicted = prediction_by_key[canonical]
            charts.append(
                _chart(
                    support,
                    predicted["prediction"],
                    title=key[1],
                )
            )
        sections.append(
            f"<section><h2>{html.escape(_FAMILY_LABELS[family])}</h2>"
            f'<div class="grid">{"".join(charts)}</div></section>'
        )
    method = result.get("submission", {}).get("method_name", "Submitted method")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(str(method))} — {html.escape(case_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:24px;color:#101828;background:#f9fafb}}
h1,h2,h3{{line-height:1.2}} h2{{margin-top:34px}} h3{{font-size:14px;margin:0 0 8px}}
.legend{{display:flex;gap:20px;margin:12px 0 24px}} .swatch{{display:inline-block;width:24px;border-top:3px solid;margin-right:6px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:16px}}
.chart{{background:white;border:1px solid #eaecf0;border-radius:8px;padding:14px}} svg{{width:100%;height:auto}}
svg text{{font-size:11px;fill:#475467}}
</style></head><body>
<h1>{html.escape(str(method))}: {html.escape(case_id)}</h1>
<p>Raw support samples are shown without smoothing. Each supported segment is drawn separately, so gaps are never joined.</p>
<div class="legend"><span><i class="swatch" style="border-color:#101828"></i>Ground truth</span><span><i class="swatch" style="border-color:#d92d20"></i>Prediction</span></div>
{"".join(sections)}
</body></html>"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return destination


__all__ = ["ReportError", "render_case_report"]
