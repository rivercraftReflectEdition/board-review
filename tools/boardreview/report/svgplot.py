"""Inline SVG of a Result plot: one panel per y unit on a shared x, marked points, colors from the report's tokens."""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

from boardreview.calc.base import Plot

W = 420.0
LEFT = 50.0
RIGHT = 14.0
TITLE_H = 24.0
HEAD_H = 18.0
PANEL_H = 128.0
GAP = 10.0
X_AXIS_H = 36.0
FONT = 12
SMALL = 11
SERIES = ("var(--accent,#1d4f91)", "var(--major,#9a5b00)", "var(--pass,#2a6b45)", "var(--fmt,#6a4a9c)")
MARK = "var(--blocker,#a8261d)"
INK = "var(--ink,#18201d)"
INK2 = "var(--ink-2,#4c5753)"
INK3 = "var(--ink-3,#75807b)"
RULE = "var(--rule,#d5dad6)"
RULE_STRONG = "var(--rule-strong,#9aa59f)"
SHEET = "var(--sheet,#ffffff)"
MONO = "var(--f-mono,ui-monospace,Consolas,monospace)"
BODY = "var(--f-body,Helvetica,Arial,sans-serif)"
PLAIN_UNITS = {"", "dB", "deg", "%", "count", "ppm"}
PREFIXES = ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"),
            (1e-15, "f"))
DEG_STEPS = (1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 45.0, 90.0, 180.0, 360.0)


@dataclass(frozen=True)
class Axis:
    """Data range [lo, hi] mapped onto pixels [p0, p1], linear or log10."""

    lo: float
    hi: float
    log: bool
    p0: float
    p1: float

    def __call__(self, v: float) -> float:
        a, b, t = (math.log10(self.lo), math.log10(self.hi), math.log10(v)) if self.log else (self.lo, self.hi, v)
        return (self.p0 + self.p1) / 2 if b == a else self.p0 + (t - a) / (b - a) * (self.p1 - self.p0)

    def inside(self, v: float | None) -> bool:
        return v is not None and math.isfinite(v) and (v > 0 or not self.log) and self.lo <= v <= self.hi


@dataclass(frozen=True)
class Panel:
    unit: str
    series: tuple[int, ...]
    y: Axis
    head: float
    top: float
    bottom: float


@dataclass(frozen=True)
class Layout:
    x: Axis
    panels: tuple[Panel, ...]
    height: float

    def panel_for(self, unit: str) -> Panel:
        """Panel whose unit matches; the first panel when none does."""
        return next((p for p in self.panels if p.unit == unit), self.panels[0])


def _e(text: object) -> str:
    return html.escape(str(text), quote=True)


def _f(v: float) -> str:
    return f"{v:.1f}"


def _finite(values, log: bool) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(v) and (v > 0 or not log)]


def unit_text(unit: str) -> str:
    """Unit as printed on an axis: ohm becomes the omega sign."""
    return {"ohm": "Ω", "Ohm": "Ω"}.get(unit, unit)


def fmt_num(v: float) -> str:
    """Up to four significant digits, no exponent, no trailing zeros."""
    if abs(v) < 1e-12:
        return "0"
    s = f"{v:.4g}"
    if "e" in s:
        s = f"{v:.12f}".rstrip("0").rstrip(".")
    return s


def si(v: float) -> str:
    """Value with an SI prefix: 10000 -> 10k, 2.2e6 -> 2.2M, 0.0005 -> 500m."""
    if v == 0:
        return "0"
    for factor, prefix in PREFIXES:
        if abs(v) >= factor * 0.9995:
            return fmt_num(v / factor) + prefix
    return fmt_num(v / PREFIXES[-1][0]) + PREFIXES[-1][1]


def _prefix(max_abs: float) -> tuple[float, str]:
    for factor, prefix in PREFIXES:
        if max_abs >= factor * 0.9995:
            return factor, prefix
    return PREFIXES[-1]


def nice_step(raw: float, unit: str = "") -> float:
    """Tick step of 1, 2 or 5 times a power of ten at or above raw; multiples of 15, 45 or 90 for degrees."""
    if raw <= 0 or not math.isfinite(raw):
        return 1.0
    if unit == "deg" and raw >= 1.0:
        return next((s for s in DEG_STEPS if s >= raw), 360.0 * math.ceil(raw / 360.0))
    e = math.floor(math.log10(raw))
    for m in (1.0, 2.0, 5.0, 10.0):
        if m * 10**e >= raw * (1 - 1e-9):
            return m * 10**e
    return 10.0 ** (e + 1)


def linear_ticks(lo: float, hi: float, step: float) -> list[float]:
    """Multiples of step inside [lo, hi]."""
    first = math.ceil(lo / step - 1e-9)
    last = math.floor(hi / step + 1e-9)
    return [round(k * step, 12) for k in range(first, last + 1)]


def log_ticks(lo: float, hi: float) -> tuple[list[float], list[float]]:
    """Labeled and minor ticks of a log axis: decades, with 2 and 5 labeled when fewer than two decades show."""
    k0, k1 = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
    inside = [10.0**k for k in range(k0, k1 + 1) if lo * (1 - 1e-9) <= 10.0**k <= hi * (1 + 1e-9)]
    every = [m * 10.0**k for k in range(k0, k1 + 1) for m in range(1, 10)]
    every = [v for v in every if lo * (1 - 1e-9) <= v <= hi * (1 + 1e-9)]
    if len(inside) >= 2:
        minor = [v for v in every if v not in inside] if k1 - k0 <= 7 else []
        return inside, minor
    major = [v for v in every if round(v / 10.0 ** math.floor(math.log10(v) + 1e-9)) in (1, 2, 5)]
    return major, [v for v in every if v not in major]


def _domain(values: list[float], log: bool, unit: str, pad: bool) -> tuple[float, float]:
    if not values:
        return (1.0, 10.0) if log else (0.0, 1.0)
    lo, hi = min(values), max(values)
    if log:
        if lo == hi:
            return lo / 10.0, hi * 10.0
        if not pad:
            return lo, hi
        if hi / lo >= 10.0:
            return 10.0 ** math.floor(math.log10(lo) + 1e-9), 10.0 ** math.ceil(math.log10(hi) - 1e-9)
        return lo / 1.15, hi * 1.15
    if lo == hi:
        d = abs(lo) * 0.1 or 1.0
        lo, hi = lo - d, hi + d
    if not pad:
        return lo, hi
    span = hi - lo
    lo_p, hi_p = lo - 0.05 * span, hi + 0.05 * span
    step = nice_step((hi_p - lo_p) / 5.0, unit)
    lo_p, hi_p = math.floor(lo_p / step + 1e-9) * step, math.ceil(hi_p / step - 1e-9) * step
    return (0.0 if lo >= 0 > lo_p else lo_p), (0.0 if hi <= 0 < hi_p else hi_p)


def _as_dict(plot: dict | Plot) -> dict:
    return plot.to_dict() if isinstance(plot, Plot) else plot


def _units(p: dict) -> list[str]:
    out: list[str] = []
    for s in p["series"]:
        if s["unit"] not in out:
            out.append(s["unit"])
    return out


def layout(plot: dict | Plot) -> Layout:
    """Axes and panel positions that plot_svg draws with; use it to turn data values into pixels."""
    p = _as_dict(plot)
    x_log = bool(p["x"].get("log"))
    y_log = bool(p.get("y_log"))
    x_lo, x_hi = _domain(_finite(p["x"]["values"], x_log), x_log, p["x"]["unit"], pad=False)
    x = Axis(x_lo, x_hi, x_log, LEFT, W - RIGHT)
    units = _units(p)
    panels = []
    for i, unit in enumerate(units):
        idx = tuple(k for k, s in enumerate(p["series"]) if s["unit"] == unit)
        vals = [v for k in idx for v in _finite(p["series"][k]["values"], y_log)]
        for m in p.get("markers", []):
            if m.get("y") is not None and (m.get("unit", "") == unit or (i == 0 and m.get("unit", "") not in units)):
                vals += _finite([m["y"]], y_log)
        lo, hi = _domain(vals, y_log, unit, pad=True)
        head = TITLE_H + i * (HEAD_H + PANEL_H + GAP)
        top = head + HEAD_H
        panels.append(Panel(unit, idx, Axis(lo, hi, y_log, top + PANEL_H, top), head, top, top + PANEL_H))
    height = (panels[-1].bottom if panels else TITLE_H + HEAD_H + PANEL_H) + X_AXIS_H
    return Layout(x, tuple(panels), height)


def _text(x: float, y: float, s: str, size: int = FONT, fill: str = INK3, anchor: str = "start", font: str = MONO,
          weight: str = "") -> str:
    w = f' font-weight="{weight}"' if weight else ""
    return (f'<text x="{_f(x)}" y="{_f(y)}" font-size="{size}" text-anchor="{anchor}"{w} '
            f'style="fill:{fill};font-family:{font}">{_e(s)}</text>')


def _line(x1: float, y1: float, x2: float, y2: float, stroke: str, width: float = 1.0, dash: str = "",
          opacity: float = 1.0) -> str:
    d = f";stroke-dasharray:{dash}" if dash else ""
    o = f";opacity:{opacity}" if opacity < 1 else ""
    return (f'<line x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}" '
            f'style="stroke:{stroke};stroke-width:{width}{d}{o}"/>')


def _tick_labels(ticks: list[float], log: bool, unit: str) -> tuple[list[str], str]:
    """Tick label strings and the unit text for the axis label (with the shared prefix on a linear axis)."""
    if unit in PLAIN_UNITS:
        return [fmt_num(v) for v in ticks], unit
    if log:
        return [si(v) for v in ticks], unit_text(unit)
    factor, prefix = _prefix(max((abs(v) for v in ticks), default=1.0) or 1.0)
    return [fmt_num(v / factor) for v in ticks], prefix + unit_text(unit)


def _axis_name(label: str, unit: str) -> str:
    return f"{label} ({unit})" if unit else label


def _segments(xs: list, ys: list, lay: Layout, y: Axis) -> list[list[tuple[float, float]]]:
    out: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for a, b in zip(xs, ys):
        if lay.x.inside(a) and y.inside(b):
            cur.append((lay.x(a), y(b)))
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _legend(p: dict, panel: Panel) -> list[str]:
    out = []
    x_end = W - RIGHT
    for k in reversed(panel.series):
        label = p["series"][k]["label"]
        width = 18 + len(label) * 6.2
        x0 = x_end - width
        out.append(_line(x0, panel.head + 8, x0 + 14, panel.head + 8, SERIES[k % len(SERIES)], 2))
        out.append(_text(x0 + 18, panel.head + 12, label, SMALL, INK2, font=BODY))
        x_end = x0 - 10
    return out


def _panel(p: dict, lay: Layout, panel: Panel, last: bool) -> list[str]:
    out = []
    y = panel.y
    if y.log:
        major, minor = log_ticks(y.lo, y.hi)
    else:
        major, minor = linear_ticks(y.lo, y.hi, nice_step((y.hi - y.lo) / 5.0, panel.unit)), []
    labels, unit_shown = _tick_labels(major, y.log, panel.unit)
    for v in minor:
        out.append(_line(LEFT, y(v), W - RIGHT, y(v), RULE, 0.6, opacity=0.6))
    for v, s in zip(major, labels):
        out.append(_line(LEFT, y(v), W - RIGHT, y(v), RULE, 1.0))
        out.append(_text(LEFT - 5, y(v) + 3.5, s, SMALL, INK3, "end"))
    xs = lay.x
    if xs.log:
        x_major, x_minor = log_ticks(xs.lo, xs.hi)
    else:
        x_major, x_minor = linear_ticks(xs.lo, xs.hi, nice_step((xs.hi - xs.lo) / 5.0, p["x"]["unit"])), []
    for v in x_minor:
        out.append(_line(xs(v), panel.top, xs(v), panel.bottom, RULE, 0.6, opacity=0.6))
    for v in x_major:
        out.append(_line(xs(v), panel.top, xs(v), panel.bottom, RULE, 1.0))
    out.append(_line(LEFT, panel.top, LEFT, panel.bottom, RULE_STRONG, 1.0))
    out.append(_line(LEFT, panel.bottom, W - RIGHT, panel.bottom, RULE_STRONG, 1.0))
    if len(panel.series) == 1:
        name = _axis_name(p["series"][panel.series[0]]["label"], unit_shown)
    else:
        name = unit_shown or "value"
        out += _legend(p, panel)
    out.append(_text(LEFT, panel.head + 12, name, FONT, INK2, font=BODY))
    for k in reversed(panel.series):
        s = p["series"][k]
        color = SERIES[k % len(SERIES)]
        for seg in _segments(p["x"]["values"], s["values"], lay, y):
            pts = " ".join(f"{_f(a)},{_f(b)}" for a, b in seg)
            out.append(f'<polyline class="pl-series" data-series="{_e(s["label"])}" points="{pts}" '
                       f'style="fill:none;stroke:{color};stroke-width:2;stroke-linejoin:round;stroke-linecap:round"/>')
    if last:
        x_labels, x_unit = _tick_labels(x_major, xs.log, p["x"]["unit"])
        for v, s in zip(x_major, x_labels):
            out.append(_text(xs(v), panel.bottom + 14, s, SMALL, INK3, "middle"))
        out.append(_text((LEFT + W - RIGHT) / 2, panel.bottom + 30, _axis_name(p["x"]["label"], x_unit), FONT, INK2,
                         "middle", BODY))
    return out


def _marker_attrs(m: dict, kind: str) -> str:
    bits = [f'class="pl-marker" data-kind="{kind}" data-label="{_e(m["label"])}"']
    if m.get("x") is not None:
        bits.append(f'data-x="{m["x"]:.6g}"')
    if m.get("y") is not None:
        bits.append(f'data-y="{m["y"]:.6g}"')
    if m.get("unit"):
        bits.append(f'data-unit="{_e(m["unit"])}"')
    return " ".join(bits)


class _Labels:
    """Greedy label placement: the first candidate that stays in its panel and overlaps no placed label wins."""

    def __init__(self) -> None:
        self.boxes: list[tuple[float, float, float, float]] = []

    @staticmethod
    def box(x: float, y: float, anchor: str, text: str) -> tuple[float, float, float, float]:
        w = len(text) * 5.9 + 2
        x0 = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
        return x0, y - 9, x0 + w, y + 2

    def place(self, cands: list[tuple[float, float, str]], text: str, panel: Panel) -> tuple[float, float, str]:
        for c in cands:
            b = self.box(*c, text)
            inside = b[0] >= 0 and b[2] <= W and b[1] >= panel.top and b[3] <= panel.bottom
            if inside and all(b[2] <= o[0] or b[0] >= o[2] or b[3] <= o[1] or b[1] >= o[3] for o in self.boxes):
                self.boxes.append(b)
                return c
        self.boxes.append(self.box(*cands[0], text))
        return cands[0]


def _kind(m: dict) -> str:
    x, y = m.get("x"), m.get("y")
    return "point" if x is not None and y is not None else "vline" if x is not None else "hline" if y is not None else ""


def _markers(p: dict, lay: Layout) -> list[str]:
    out = []
    labels = _Labels()
    first = lay.panels[0]
    order = {"point": 0, "vline": 1, "hline": 2}
    for m in sorted(p.get("markers", []), key=lambda m: order.get(_kind(m), 3)):
        x, y, kind = m.get("x"), m.get("y"), _kind(m)
        panel = lay.panel_for(m.get("unit", ""))
        label = m["label"]
        if kind == "vline":
            if not lay.x.inside(x):
                continue
            px = lay.x(x)
            parts = [_line(px, pn.top, px, pn.bottom, MARK, 1.2, "4 3") for pn in lay.panels]
            cands = [c for k in range(8) for c in ((px + 3, first.top + 11 + 12 * k, "start"),
                                                   (px - 3, first.top + 11 + 12 * k, "end"))]
            tx, ty, anchor = labels.place(cands, label, first)
            parts.append(_text(tx, ty, label, SMALL, INK2, anchor, BODY))
        elif kind == "hline":
            if not panel.y.inside(y):
                continue
            py = panel.y(y)
            cands = [(W - RIGHT - 2, py - 4, "end"), (LEFT + 3, py - 4, "start"), (W - RIGHT - 2, py + 12, "end"),
                     (LEFT + 3, py + 12, "start"), ((LEFT + W - RIGHT) / 2, py - 4, "middle"),
                     ((LEFT + W - RIGHT) / 2, py + 12, "middle")]
            tx, ty, anchor = labels.place(cands, label, panel)
            parts = [_line(LEFT, py, W - RIGHT, py, MARK, 1.2, "6 3"), _text(tx, ty, label, SMALL, INK2, anchor, BODY)]
        elif kind == "point":
            if not (lay.x.inside(x) and panel.y.inside(y)):
                continue
            px, py = lay.x(x), panel.y(y)
            cands = [(px + 7, py - 7, "start"), (px - 7, py - 7, "end"), (px + 7, py + 15, "start"),
                     (px - 7, py + 15, "end"), (px, py - 10, "middle"), (px, py + 18, "middle")]
            tx, ty, anchor = labels.place(cands, label, panel)
            parts = [f'<circle cx="{_f(px)}" cy="{_f(py)}" r="4.5" '
                     f'style="fill:{MARK};stroke:{SHEET};stroke-width:2"/>',
                     _text(tx, ty, label, SMALL, INK, anchor, BODY)]
        else:
            continue
        out.append(f'<g {_marker_attrs(m, kind)}><title>{_e(label)}</title>{"".join(parts)}</g>')
    return out


def plot_svg(plot: dict | Plot, uid: str = "") -> str:
    """One inline SVG: title, a panel per y unit sharing x, series, gridlines, ticks and markers."""
    p = _as_dict(plot)
    title = p.get("title", "")
    lay = layout(p)
    ident = f' id="pl-{_e(uid)}"' if uid else ""
    head = (f'<svg xmlns="http://www.w3.org/2000/svg"{ident} class="pl" viewBox="0 0 {W:g} {_f(lay.height)}" '
            f'role="img" aria-label="{_e(title)}" '
            f'style="width:100%;height:auto;max-width:560px;display:block;overflow:visible">'
            f"<title>{_e(title)}</title>")
    body = [_text(LEFT, 15, title, 13, INK, font=BODY, weight="600")]
    if not p["series"] or not _finite(p["x"]["values"], bool(p["x"].get("log"))):
        body.append(_text(W / 2, TITLE_H + 40, "no data to plot", FONT, INK3, "middle", BODY))
        return head + "".join(body) + "</svg>"
    for i, panel in enumerate(lay.panels):
        body += _panel(p, lay, panel, i == len(lay.panels) - 1)
    body += _markers(p, lay)
    return head + "".join(body) + "</svg>"
