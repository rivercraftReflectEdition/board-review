"""Common result type for every calculator, so a review can print the math it relied on."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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

    def to_markdown(self) -> str:
        lines = [f"**{self.name}**: {self.verdict.value}" + (f" ({self.reason})" if self.reason else "")]
        lines.append(f"`{self.formula}`")
        lines += [f"- in  {k} = {q}" + (f" ({q.note})" if q.note else "") for k, q in self.inputs.items()]
        lines += [f"- out {k} = {q}" + (f" ({q.note})" if q.note else "") for k, q in self.outputs.items()]
        lines += [f"- assumes {a}" for a in self.assumptions]
        lines += [f"- ref {r}" for r in self.refs]
        return "\n".join(lines)
