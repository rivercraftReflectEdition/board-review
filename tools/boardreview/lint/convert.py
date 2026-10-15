"""Lint results as candidate review findings (skill/schemas/finding.schema.json) with verification PENDING."""

from __future__ import annotations

import re

from boardreview.lint.base import Finding, LintReport

PIN = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_+-]+$")
# One step below blocker: lint cannot show how the board fails as built, which a blocker needs.
SEVERITY = {"error": "major", "warning": "minor", "info": "note"}
CHECKS: dict[str, tuple[str, str, str, str]] = {
    "single_pin_net": ("netlist_integrity", "NET-5", "open_net",
                       "Connect the net or correct the label; waive it with a reason if it is meant to be open."),
    "unconnected_ic_pin": ("netlist_integrity", "NET-5", "open_net",
                           "Check each pin against the datasheet; connect power, ground and inputs that must not "
                           "float, and mark the rest no-connect."),
    "ground_pin_off_ground": ("netlist_integrity", "NET-5", "net_short",
                              "Move the pin to the net the datasheet names, or record why this part wants it here."),
    "protection_ground_floating": ("protection_tvs", "PROT-4", "protection_gap",
                                   "Connect the ground pins, or note on the schematic that the datasheet "
                                   "configuration without ground is intended."),
    "near_duplicate_rails": ("netlist_integrity", "NET-4", "open_net",
                             "Use one name for the rail, or rename one so the separate rails cannot be confused."),
    "fitted_without_mpn": ("netlist_integrity", "NET-7", "other",
                           "Add the MPN, or mark the part DNP in the released variant."),
    "dnp_only_link": ("netlist_integrity", "NET-7", "open_net",
                      "Confirm the pin may float in this variant, or fit a part on the net."),
    "bom_netlist_mismatch": ("netlist_integrity", "NET-7", "other",
                             "Make the BOM and the netlist list the same parts for the released variant."),
}
DEFAULT = ("netlist_integrity", "NET-5", "other", "Fix it, or waive it with a reason.")


def _title(summary: str) -> str:
    head = summary.split("; ")[0].strip()
    head = head[:1].upper() + head[1:]
    if len(head) < 5:
        head = f"Lint: {head}"
    return head if len(head) <= 140 else head[:137].rstrip() + "..."


def to_finding(f: Finding, number: int = 1) -> dict:
    """One lint result as a finding dict; pins the schema cannot hold move to the evidence detail."""
    block, item, mode, fix = CHECKS.get(f.check, DEFAULT)
    pins = [p for p in f.pins if PIN.match(p)]
    detail = [f"{k}: {v}" for k, v in f.evidence.items()]
    if len(pins) < len(f.pins):
        detail.append("pins: " + ", ".join(f.pins))
    evidence = {"kind": "lint", "ref": f"lint {f.check} ({f.severity})"}
    if detail:
        evidence["detail"] = "; ".join(detail)
    claim = f.summary if len(f.summary) >= 10 else f"{f.check}: {f.summary}"
    out = {"id": f"lint.{f.check}.{number}", "title": _title(f.summary), "severity": SEVERITY.get(f.severity, "note"),
           "block": block, "check": f"{block}#{item}", "failure_mode": mode, "parts": list(f.components),
           "nets": list(f.nets), "pins": pins, "claim": claim, "evidence": [evidence], "fix": fix,
           "verification": {"status": "PENDING"}}
    return {k: v for k, v in out.items() if v != []}


def to_findings(report: LintReport | list[Finding]) -> list[dict]:
    """Every lint result as a finding, numbered per check in report order."""
    seen: dict[str, int] = {}
    out = []
    for f in report.findings if isinstance(report, LintReport) else report:
        seen[f.check] = seen.get(f.check, 0) + 1
        out.append(to_finding(f, seen[f.check]))
    return out
