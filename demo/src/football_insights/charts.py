"""Server-rendered SVG charts built only from tool data.

No JavaScript chart library and nothing loaded from a CDN. The palette is
Okabe-Ito (color-blind safe), and series also differ by dash pattern so color
is never the only cue. Every chart is paired with a text summary in the page.
"""

from __future__ import annotations

import math
from html import escape

from .schemas import Chart

PALETTE = ("#56B4E9", "#E69F00", "#009E73", "#F0E442", "#CC79A7", "#D55E00", "#0072B2")
DASHES = ("", "10 6", "3 5", "14 5 3 5", "2 3", "18 6", "6 3")
WIDTH, HEIGHT = 960, 460
LEFT, RIGHT, TOP, BOTTOM = 86, 24, 24, 92
FG, GRID, DIM = "#f2f5f8", "#3a4350", "#b9c2cc"


def _nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    if high <= low:
        high = low + 1
    raw = (high - low) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = math.floor(low / step) * step
    ticks = []
    value = start
    while value <= high + step * 0.001:
        ticks.append(round(value, 10))
        value += step
    return ticks


def _fmt(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 100 or value == int(value) else f"{value:,.1f}"


def _y_range(chart: Chart) -> tuple[float, float]:
    values = [v for s in chart.series for v in (*s.values, *(s.lower or ()), *(s.upper or ())) if v is not None]
    low = min(values) if values else 0.0
    high = max(values) if values else 1.0
    if chart.y_min is not None:
        low = float(chart.y_min)
    if chart.y_max is not None:
        high = float(chart.y_max)
    if high == low:
        high = low + 1
    pad = (high - low) * 0.05
    return (low if chart.y_min is not None else low - pad), (high if chart.y_max is not None else high + pad)


def _legend(chart: Chart) -> str:
    parts, x = [], LEFT
    for i, series in enumerate(chart.series):
        color, dash = PALETTE[i % len(PALETTE)], DASHES[i % len(DASHES)]
        parts.append(f'<line x1="{x}" y1="{HEIGHT - 22}" x2="{x + 34}" y2="{HEIGHT - 22}" stroke="{color}" '
                     f'stroke-width="5" stroke-dasharray="{dash}"/>')
        label = escape(series.name)
        parts.append(f'<text x="{x + 42}" y="{HEIGHT - 15}" fill="{FG}" font-size="20">{label}</text>')
        x += 60 + 11 * len(series.name)
    return "".join(parts)


def _frame(chart: Chart, low: float, high: float) -> tuple[list[str], float, float]:
    plot_w = WIDTH - LEFT - RIGHT
    plot_h = HEIGHT - TOP - BOTTOM
    out = []
    for tick in _nice_ticks(low, high):
        if tick < low or tick > high:
            continue
        y = TOP + plot_h * (1 - (tick - low) / (high - low))
        out.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{WIDTH - RIGHT}" y2="{y:.1f}" stroke="{GRID}" '
                   'stroke-width="1"/>')
        label = _fmt(tick) + ("%" if chart.y_unit == "%" else "")
        out.append(f'<text x="{LEFT - 10}" y="{y + 7:.1f}" fill="{DIM}" font-size="19" '
                   f'text-anchor="end">{label}</text>')
    if chart.y_label:
        out.append(f'<text transform="translate(20,{TOP + plot_h / 2:.0f}) rotate(-90)" fill="{DIM}" font-size="19" '
                   f'text-anchor="middle">{escape(chart.y_label)}</text>')
    return out, plot_w, plot_h


def _x_labels(labels: list[str], xs: list[float], plot_h: float) -> list[str]:
    step = max(1, math.ceil(len(labels) / 12))
    out = []
    for i, (label, x) in enumerate(zip(labels, xs, strict=True)):
        if i % step and i != len(labels) - 1:
            continue
        out.append(f'<text x="{x:.1f}" y="{TOP + plot_h + 30}" fill="{DIM}" font-size="19" '
                   f'text-anchor="middle">{escape(label)}</text>')
    return out


def _line(chart: Chart) -> str:
    low, high = _y_range(chart)
    parts, plot_w, plot_h = _frame(chart, low, high)
    n = len(chart.x)
    xs = [LEFT + (plot_w * (i + 0.5) / n) for i in range(n)]

    def y_of(v: float) -> float:
        return TOP + plot_h * (1 - (v - low) / (high - low))

    for i, series in enumerate(chart.series):
        color, dash = PALETTE[i % len(PALETTE)], DASHES[i % len(DASHES)]
        if series.lower and series.upper:
            upper = [(xs[j], y_of(v)) for j, v in enumerate(series.upper) if v is not None]
            lower = [(xs[j], y_of(v)) for j, v in enumerate(series.lower) if v is not None]
            if upper and lower:
                pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in upper + lower[::-1])
                parts.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.18" stroke="none"/>')
        segment: list[str] = []
        segments: list[list[str]] = []
        for j, v in enumerate(series.values):
            if v is None:
                if segment:
                    segments.append(segment)
                segment = []
                continue
            segment.append(f"{xs[j]:.1f},{y_of(float(v)):.1f}")
        if segment:
            segments.append(segment)
        for seg in segments:
            parts.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{color}" stroke-width="4" '
                         f'stroke-dasharray="{dash}" stroke-linejoin="round"/>')
        for j, v in enumerate(series.values):
            if v is not None:
                parts.append(f'<circle cx="{xs[j]:.1f}" cy="{y_of(float(v)):.1f}" r="4.5" fill="{color}"/>')
    parts += _x_labels(chart.x, xs, plot_h)
    return "".join(parts)


def _bars(chart: Chart) -> str:
    low, high = _y_range(chart)
    low = min(low, 0.0)
    parts, plot_w, plot_h = _frame(chart, low, high)
    n = len(chart.x)
    groups = len(chart.series)
    slot = plot_w / n
    bar_w = slot * 0.8 / groups
    xs = [LEFT + slot * (i + 0.5) for i in range(n)]
    zero = TOP + plot_h * (1 - (0 - low) / (high - low))
    for gi, series in enumerate(chart.series):
        color = PALETTE[gi % len(PALETTE)]
        for i, v in enumerate(series.values):
            if v is None:
                continue
            y = TOP + plot_h * (1 - (float(v) - low) / (high - low))
            x = xs[i] - slot * 0.4 + gi * bar_w
            parts.append(f'<rect x="{x:.1f}" y="{min(y, zero):.1f}" width="{bar_w - 2:.1f}" '
                         f'height="{abs(zero - y):.1f}" fill="{color}"/>')
    parts += _x_labels(chart.x, xs, plot_h)
    return "".join(parts)


def _hbars(chart: Chart) -> str:
    values = [float(v) for v in chart.series[0].values if v is not None]
    low = min([0.0, *values]) if chart.y_min is None else float(chart.y_min)
    high = (max(values) if values else 1.0) if chart.y_max is None else float(chart.y_max)
    label_w = 250
    plot_w = WIDTH - label_w - RIGHT - 70
    n = len(chart.x)
    row_h = (HEIGHT - TOP - 40) / max(n, 1)
    parts = []
    for i, (label, v) in enumerate(zip(chart.x, chart.series[0].values, strict=True)):
        y = TOP + i * row_h
        parts.append(f'<text x="{label_w - 12}" y="{y + row_h * 0.68:.1f}" fill="{FG}" font-size="20" '
                     f'text-anchor="end">{escape(label[:24])}</text>')
        if v is None:
            continue
        span = high - low if high != low else 1
        w = plot_w * (float(v) - low) / span
        parts.append(f'<rect x="{label_w}" y="{y + row_h * 0.15:.1f}" width="{max(w, 1):.1f}" '
                     f'height="{row_h * 0.7:.1f}" fill="{PALETTE[0]}"/>')
        text = _fmt(float(v)) + ("%" if chart.y_unit == "%" else "")
        parts.append(f'<text x="{label_w + max(w, 1) + 8:.1f}" y="{y + row_h * 0.68:.1f}" fill="{FG}" '
                     f'font-size="19">{text}</text>')
    return "".join(parts)


def render(chart: Chart) -> str:
    body = {"line": _line, "bar": _bars, "hbar": _hbars}[chart.kind](chart)
    legend = _legend(chart) if chart.kind != "hbar" and len(chart.series) > 0 else ""
    title = escape(chart.title)
    return (f'<svg class="chart" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{title}" '
            f'xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, system-ui, sans-serif">'
            f"<title>{title}</title>{body}{legend}</svg>")
