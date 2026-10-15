"""Common result type for every calculator, so a review can print the math it relied on."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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

    def __str__(self) -> str:
        return f"{self.value:.6g} {self.unit}"

    def to_dict(self) -> dict:
        """JSON shape of the finding schema's quantity."""
        return {"value": self.value, "unit": self.unit} | ({"note": self.note} if self.note else {})


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

    def to_dict(self) -> dict:
        """JSON shape of the finding schema's plot."""
        return {
            "title": self.title,
            "x": {"label": self.x_label, "unit": self.x_unit, "log": self.x_log, "values": [_num(v) for v in self.x]},
            "y_log": self.y_log,
            "series": [s.to_dict() for s in self.series],
            "markers": [m.to_dict() for m in self.markers],
        }


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
) -> Plot:
    """Plot from arrays: series are (label, unit, y); long series are thinned keeping each bucket's min and max."""
    xs = np.asarray(x, dtype=float)
    ys = [np.asarray(y, dtype=float) for _, _, y in series]
    idx = keep_indices(ys, max_points)
    return Plot(
        title=title, x_label=x_label, x_unit=x_unit, x=tuple(float(v) for v in xs[idx]),
        series=tuple(Series(lab, unit, tuple(float(v) for v in y[idx])) for (lab, unit, _), y in zip(series, ys)),
        x_log=x_log, y_log=y_log, markers=tuple(markers),
    )


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

    def to_markdown(self) -> str:
        lines = [f"**{self.name}**: {self.verdict.value}" + (f" ({self.reason})" if self.reason else "")]
        lines.append(f"`{self.formula}`")
        lines += [f"- in  {k} = {q}" + (f" ({q.note})" if q.note else "") for k, q in self.inputs.items()]
        lines += [f"- out {k} = {q}" + (f" ({q.note})" if q.note else "") for k, q in self.outputs.items()]
        lines += [f"- assumes {a}" for a in self.assumptions]
        lines += [f"- ref {r}" for r in self.refs]
        return "\n".join(lines)

    def to_dict(self, calculator: str = "") -> dict:
        """The finding schema's calculation object; calculator is the module path, for example 'calc.loop.margins'."""
        out = {
            "calculator": calculator or self.name, "formula": self.formula,
            "inputs": {k: q.to_dict() for k, q in self.inputs.items()},
            "outputs": {k: q.to_dict() for k, q in self.outputs.items()},
            "verdict": self.verdict.value, "reason": self.reason,
            "assumptions": list(self.assumptions), "refs": list(self.refs),
        }
        if self.plots:
            out["plots"] = [p.to_dict() for p in self.plots]
        return out
