"""Deterministic netlist and BOM checks that return structured findings."""

from __future__ import annotations

from typing import Callable

from boardreview.lint.base import SEVERITY_ORDER, Finding, LintReport, Skip
from boardreview.lint.nets import dnp_only_link, near_duplicate_rails, single_pin_nets
from boardreview.lint.parts import bom_netlist_mismatch, fitted_without_mpn
from boardreview.lint.pins import ground_pin_off_ground, protection_ground_floating, unconnected_ic_pins
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph

CHECKS: dict[str, Callable[[BoardModel, Graph], list[Finding]]] = {
    "single_pin_net": single_pin_nets,
    "unconnected_ic_pin": unconnected_ic_pins,
    "ground_pin_off_ground": ground_pin_off_ground,
    "protection_ground_floating": protection_ground_floating,
    "near_duplicate_rails": near_duplicate_rails,
    "fitted_without_mpn": fitted_without_mpn,
    "dnp_only_link": dnp_only_link,
    "bom_netlist_mismatch": bom_netlist_mismatch,
}


def run_all(model: BoardModel, only: list[str] | None = None) -> LintReport:
    """Run every check (or the named ones); a check that cannot run is listed as skipped with the reason."""
    g = Graph(model)
    findings: list[Finding] = []
    ran: list[str] = []
    skipped: dict[str, str] = {}
    for name, fn in CHECKS.items():
        if only and name not in only:
            continue
        try:
            findings += fn(model, g)
            ran.append(name)
        except Skip as why:
            skipped[name] = str(why)
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.check))
    return LintReport(findings, ran, skipped)


__all__ = ["CHECKS", "Finding", "LintReport", "Skip", "run_all"]
