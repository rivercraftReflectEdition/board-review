"""Common result type for every calculator, so a review can print the math it relied on."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Sequence

import numpy as np


class Verdict(str, Enum):
    PASS = "pass"
    MARGINAL = "marginal"
    FAIL = "fail"
    INFO = "info"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str
    note: str = ""
    label: str = ""

    def __str__(self) -> str:
        return f"{self.value:.6g} {self.unit}"

    def to_dict(self) -> dict:
        """JSON shape of the finding schema's quantity; infinity and NaN become null with a note, so the JSON is valid."""
        value, note = self.value, self.note
        if value is not None and not math.isfinite(float(value)):
            what = "not a number" if math.isnan(float(value)) else ("infinite" if value > 0 else "minus infinite")
            value, note = None, "; ".join(x for x in (note, f"{what} in the calculation, written as null") if x)
        out = {"value": value, "unit": self.unit}
        if note:
            out["note"] = note
        if self.label:
            out["label"] = self.label
        return out


@dataclass(frozen=True)
class Key:
    """A number for the key line: an output or input name, what we want it to be, and an optional label."""

    name: str
    want: str = ""
    label: str = ""


_UNIT_TEXT = {"ohm": "Ω", "ohms": "Ω", "deg": "°", "C": "°C", "degC": "°C", "C/W": "°C/W", "deg/s": "°/s",
              "coulomb": "C"}
_SI_UNITS = {"V", "A", "Hz", "F", "H", "Ω", "s", "W", "m", "A/V", "S", "J", "C"}
_STEPS = ((1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"),
          (1e-12, "p"), (1e-15, "f"))


def _sig(x: float, digits: int) -> str:
    if x == 0:
        return "0"
    s = f"{x:.{digits}g}"
    if "e" in s:
        s = f"{x:.{max(0, digits - 1 - int(math.floor(math.log10(abs(x)))))}f}"
        s = s.rstrip("0").rstrip(".") if "." in s else s
    return s


def fmt(value: float | None, unit: str = "", digits: int = 3) -> str:
    """A number as a person writes it: fmt(64150, 'Hz') is '64.2 kHz', fmt(30.19, 'deg') is '30.2°'."""
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    value = float(f"{float(value):.{digits}g}")
    u = _UNIT_TEXT.get(unit, unit)
    if u == "°":
        return f"{_sig(value, digits)}°"
    if u == "%":
        return f"{_sig(value, digits)}%"
    if u == "count":
        return f"{round(value):d}"
    if u == "A/s":
        return f"{_sig(value / 1e6, digits)} A/µs"
    if u in _SI_UNITS and value != 0:
        for factor, prefix in _STEPS:
            if abs(value) >= factor or factor == 1e-15:
                return f"{_sig(value / factor, digits)} {prefix}{u}"
    return f"{_sig(value, digits)} {u}".strip()


def _num(v: float | None) -> float | None:
    """Six significant digits; NaN and infinity become None so the JSON stays valid."""
    if v is None:
        return None
    v = float(v)
    return float(f"{v:.6g}") if math.isfinite(v) else None


@dataclass(frozen=True)
class Series:
    """One y series; series with the same unit share a panel."""

    label: str
    unit: str
    y: tuple[float, ...]

    def to_dict(self) -> dict:
        return {"label": self.label, "unit": self.unit, "values": [_num(v) for v in self.y]}


@dataclass(frozen=True)
class Marker:
    """A marked point (x and y), a vertical line (x only) or a horizontal limit line (y only)."""

    label: str
    x: float | None = None
    y: float | None = None
    unit: str = ""

    def to_dict(self) -> dict:
        out: dict = {"label": self.label}
        if self.x is not None:
            out["x"] = _num(self.x)
        if self.y is not None:
            out["y"] = _num(self.y)
        if self.unit:
            out["unit"] = self.unit
        return out


@dataclass(frozen=True)
class Band:
    """A shaded interval on the shared frequency axis."""

    label: str
    x_min: float
    x_max: float

    def to_dict(self) -> dict:
        return {"label": self.label, "x_min": _num(self.x_min), "x_max": _num(self.x_max)}


@dataclass(frozen=True)
class Plot:
    """A curve the verdict depends on: shared x, one or more y series, and the points that matter marked."""

    title: str
    x_label: str
    x_unit: str
    x: tuple[float, ...]
    series: tuple[Series, ...]
    x_log: bool = False
    y_log: bool = False
    markers: tuple[Marker, ...] = ()
    caption: str = ""
    bands: tuple[Band, ...] = ()

    def to_dict(self) -> dict:
        """JSON shape of the finding schema's plot."""
        out = {
            "title": self.title,
            "x": {"label": self.x_label, "unit": self.x_unit, "log": self.x_log, "values": [_num(v) for v in self.x]},
            "y_log": self.y_log,
            "series": [s.to_dict() for s in self.series],
            "markers": [m.to_dict() for m in self.markers],
        }
        if self.caption:
            out["caption"] = self.caption
        if self.bands:
            out["bands"] = [b.to_dict() for b in self.bands]
        return out


_PREFIXES = ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p"))


def si_text(value: float, unit: str, digits: int = 3) -> str:
    """Label text with an SI prefix: si_text(12300, 'Hz') is '12.3 kHz'."""
    if not math.isfinite(value) or value == 0:
        return f"{value:g} {unit}".strip()
    for factor, prefix in _PREFIXES:
        if abs(value) >= factor * 0.9995:
            return f"{value / factor:.{digits}g} {prefix}{unit}".strip()
    return f"{value / 1e-12:.{digits}g} p{unit}".strip()


def keep_indices(ys: Sequence[np.ndarray], n_max: int = 600) -> np.ndarray:
    """Indices that thin series to about n_max points while keeping each bucket's minimum and maximum, so peaks stay."""
    n = len(ys[0]) if ys else 0
    if n <= n_max:
        return np.arange(n)
    buckets = max(1, n_max // (2 * len(ys)))
    edges = np.linspace(0, n, buckets + 1).astype(int)
    keep = {0, n - 1}
    for y in ys:
        a = np.asarray(y, dtype=float)
        for lo, hi in zip(edges[:-1], edges[1:]):
            seg = a[lo:hi]
            if hi <= lo or np.all(np.isnan(seg)):
                continue
            keep.add(lo + int(np.nanargmin(seg)))
            keep.add(lo + int(np.nanargmax(seg)))
    return np.array(sorted(keep))


def plot_from_arrays(
    title: str,
    x_label: str,
    x_unit: str,
    x,
    series: Sequence[tuple[str, str, object]],
    x_log: bool = False,
    y_log: bool = False,
    markers: Sequence[Marker] = (),
    max_points: int = 600,
    caption: str = "",
    bands: Sequence[Band] = (),
) -> Plot:
    """Plot from arrays: series are (label, unit, y); long series are thinned keeping each bucket's min and max."""
    xs = np.asarray(x, dtype=float)
    ys = [np.asarray(y, dtype=float) for _, _, y in series]
    idx = keep_indices(ys, max_points)
    return Plot(
        title=title, x_label=x_label, x_unit=x_unit, x=tuple(float(v) for v in xs[idx]),
        series=tuple(Series(lab, unit, tuple(float(v) for v in y[idx])) for (lab, unit, _), y in zip(series, ys)),
        x_log=x_log, y_log=y_log, markers=tuple(markers), caption=caption, bands=tuple(bands),
    )


CONTEXTS = {"nominal": "nominal values", "worst_case": "worst-case values", "example": "a datasheet example's values",
            "ideal": "ideal values"}
_SOFTEN = ((re.compile(r"\bpasses\b"), "would pass"), (re.compile(r"\bmeets\b"), "would meet"),
           (re.compile(r"\b(?:is|are) enough\b"), "would be enough"), (re.compile(r"\b(?:is|are) fine\b"), "would be fine"),
           (re.compile(r"\bno problem\b"), "no problem at these values"), (re.compile(r"\bsafe\b"), "within the limit"))


def finite(obj):
    """Copy of a JSON-ready structure with infinity and NaN as None, so json.dumps(allow_nan=False) works."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [finite(v) for v in obj]
    return obj


@dataclass(frozen=True)
class Result:
    name: str
    formula: str
    inputs: dict[str, Quantity]
    outputs: dict[str, Quantity]
    verdict: Verdict = Verdict.INFO
    reason: str = ""
    refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = field(default=())
    plots: tuple[Plot, ...] = field(default=())
    summary: str = ""
    key: tuple[Key, ...] = field(default=())
    context: str = ""

    def in_context(self, context: str) -> "Result":
        """This result with its inputs marked nominal, worst_case, example or ideal; only worst-case inputs can pass."""
        if not context:
            return self
        if context not in CONTEXTS:
            raise ValueError(f"context {context!r} is not one of {', '.join(CONTEXTS)}")
        if context == "worst_case" or self.verdict is not Verdict.PASS:
            return replace(self, context=context)
        what = CONTEXTS[context]
        text = self.summary
        for pat, soft in _SOFTEN:
            text = pat.sub(soft, text)
        return replace(
            self, context=context, verdict=Verdict.UNKNOWN,
            reason=f"{self.reason}; from {what} only, not the worst case".lstrip("; "),
            summary=(f"Worked out from {what}, not the worst case: {text} That does not show it holds at the worst "
                     "case, so it stays unknown until the worst-case values run."),
            assumptions=self.assumptions + (f"inputs are {what}, not worst-case corners",))

    def quantity(self, name: str) -> Quantity | None:
        """An output, or else an input, by name."""
        return self.outputs.get(name) or self.inputs.get(name)

    def key_line(self) -> list[dict]:
        """Key numbers resolved for display: name, label, value, unit and what we want."""
        out = []
        for k in self.key:
            q = self.quantity(k.name)
            if q is not None:
                out.append({"name": k.name, "label": k.label or q.label or k.name, "value": _num(q.value),
                            "unit": q.unit, "want": k.want})
        return out

    def to_markdown(self) -> str:
        lines = [f"**{self.name}**: {self.verdict.value}" + (f" ({self.reason})" if self.reason else "")
                 + (f"; inputs are {CONTEXTS[self.context]}" if self.context else "")]
        lines.append(f"`{self.formula}`")
        lines += [f"- in  {k} = {q}" + (f" ({q.note})" if q.note else "") for k, q in self.inputs.items()]
        lines += [f"- out {k} = {q}" + (f" ({q.note})" if q.note else "") for k, q in self.outputs.items()]
        lines += [f"- assumes {a}" for a in self.assumptions]
        lines += [f"- ref {r}" for r in self.refs]
        return "\n".join(lines)

    def to_dict(self, calculator: str = "") -> dict:
        """The finding schema's calculation object; calculator is the module path, for example 'calc.loop.margins'."""
        out = {
            "calculator": calculator or self.name, "name": self.name, "formula": self.formula,
            "inputs": {k: q.to_dict() for k, q in self.inputs.items()},
            "outputs": {k: q.to_dict() for k, q in self.outputs.items()},
            "verdict": self.verdict.value, "reason": self.reason,
            "assumptions": list(self.assumptions), "refs": list(self.refs),
        }
        if self.summary:
            out["summary"] = self.summary
        if self.context:
            out["context"] = self.context
        if self.key:
            out["key"] = self.key_line()
        if self.plots:
            out["plots"] = [p.to_dict() for p in self.plots]
        return out


_FAIL_WORDS = re.compile(r"\b(?:fails?|failing|too (?:low|high|small|large|slow|fast|weak|close|thin|long|short|much|"
                         r"little)|not enough|short of|does not meet|do not meet)\b", re.I)
_PASS_WORDS = re.compile(r"\b(?:passes|meets|is enough|are enough|is fine|are fine|no problem|safe)\b", re.I)
_DASHES = re.compile("[\u2013\u2014]")


def plain_problems(r: Result) -> list[str]:
    """Why a Result does not read plainly: labels, summary, key numbers, variable names, or a contradicted verdict."""
    out = [f"{side} {k} has no label" for side, d in (("input", r.inputs), ("output", r.outputs))
           for k, q in d.items() if not q.label.strip()]
    out += [f"label {q.label!r} reads like a variable name" for q in [*r.inputs.values(), *r.outputs.values()]
            if "_" in q.label]
    text = r.summary.strip()
    if not text:
        return out + ["no summary"]
    if _DASHES.search(text):
        out.append("summary has a dash character")
    out += [f"summary uses the variable name {k}" for k in [*r.inputs, *r.outputs]
            if "_" in k and re.search(rf"\b{re.escape(k)}\b", text)]
    for k in r.key:
        q = r.quantity(k.name)
        if q is None:
            out.append(f"key {k.name} is not an input or output")
        elif fmt(q.value, q.unit) not in text:
            out.append(f"summary does not state key {k.name} as {fmt(q.value, q.unit)!r}")
    fail, ok = _FAIL_WORDS.search(text), _PASS_WORDS.search(text)
    if r.verdict is Verdict.PASS and fail:
        out.append(f"summary says {fail.group(0)!r} on a pass")
    if r.verdict in (Verdict.FAIL, Verdict.MARGINAL, Verdict.UNKNOWN) and ok:
        out.append(f"summary says {ok.group(0)!r} on a {r.verdict.value}")
    if r.verdict in (Verdict.UNKNOWN, Verdict.INFO, Verdict.MARGINAL) and re.search(r"\bfails\b", text, re.I):
        out.append(f"summary says 'fails' on a {r.verdict.value}")
    return out
