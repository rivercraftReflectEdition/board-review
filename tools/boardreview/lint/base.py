"""Finding and report types shared by the lint checks."""

from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


class Skip(Exception):
    """Raised by a check that cannot run on this model; the message says why."""


@dataclass
class Finding:
    check: str
    severity: str
    summary: str
    components: list[str] = field(default_factory=list)
    nets: list[str] = field(default_factory=list)
    pins: list[str] = field(default_factory=list)
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"check": self.check, "severity": self.severity, "summary": self.summary,
                "components": self.components, "nets": self.nets, "pins": self.pins, "evidence": self.evidence}


@dataclass
class LintReport:
    findings: list[Finding]
    ran: list[str]
    skipped: dict[str, str]

    def by_check(self, check: str) -> list[Finding]:
        return [f for f in self.findings if f.check == check]

    def to_dict(self) -> dict:
        return {"ran": self.ran, "skipped": self.skipped, "findings": [f.to_dict() for f in self.findings]}

    def to_markdown(self) -> str:
        counts = {s: sum(1 for f in self.findings if f.severity == s) for s in SEVERITY_ORDER}
        lines = ["# Lint", "", "Deterministic netlist checks. Each finding names the pins and nets it rests on.",
                 f"{counts['error']} errors, {counts['warning']} warnings, {counts['info']} info.", ""]
        if self.skipped:
            lines += ["Skipped:"] + [f"- {k}: {v}" for k, v in self.skipped.items()] + [""]
        for f in self.findings:
            lines.append(f"- **{f.severity}** `{f.check}`: {f.summary}")
        lines.append("")
        return "\n".join(lines)
