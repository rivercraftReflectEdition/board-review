"""Candidate circuit blocks found in the netlist, each with its evidence, a confidence and its subgraph."""

from __future__ import annotations

from boardreview.blocks.base import Block
from boardreview.blocks.clocks import find_clocks
from boardreview.blocks.filters import find_series_filters
from boardreview.blocks.i2c import find_i2c_buses
from boardreview.blocks.linear import find_linear
from boardreview.blocks.regulators import find_switching_regulators
from boardreview.blocks.resets import find_reset_nets
from boardreview.blocks.straps import find_straps
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph

ORDER = ["switching_regulator", "ldo", "load_switch", "ferrite_filter", "lc_filter", "crystal", "oscillator",
         "clock_buffer", "pll", "jitter_cleaner", "reset",
         "i2c_bus", "strap"]


def _rail_roles(regs: list[Block], linear: list[Block]) -> tuple[dict[str, str], dict[str, str]]:
    """Nets driven by a regulator or switch output, and nets that feed a regulator or switch input."""
    sources: dict[str, str] = {}
    loads: dict[str, str] = {}
    for b in regs + linear:
        dev = (b.roles.get("controller") or b.roles.get("device"))[0]
        what = "regulator" if b.kind == "switching_regulator" else b.kind.replace("_", " ").replace("ldo", "LDO")
        for net in b.roles.get("output", []):
            sources.setdefault(net, f"{dev} {what} output")
        for net in b.roles.get("input", []):
            loads.setdefault(net, f"{dev} {what} input")
    return sources, loads


def find_all(model: BoardModel) -> list[Block]:
    """Run every finder; straps skip nets already explained as feedback, I2C, reset or clock nets."""
    g = Graph(model)
    regs = find_switching_regulators(g)
    linear = find_linear(g, exclude={b.roles["controller"][0] for b in regs})
    sources, loads = _rail_roles(regs, linear)
    filters = find_series_filters(g, exclude={b.roles["inductor"][0] for b in regs}, sources=sources, loads=loads)
    clocks = find_clocks(g)
    resets = find_reset_nets(g)
    buses = find_i2c_buses(g)
    taken: set[str] = set()
    for b in regs:
        taken.update(b.roles.get("feedback_node", []))
    for b in buses:
        taken.update(b.roles.get("sda", []) + b.roles.get("scl", []))
    for b in resets:
        taken.update(b.roles["net"])
    for b in clocks:
        taken.update(b.roles.get("signal_nets", []) + b.roles.get("output", []))
    return regs + linear + filters + clocks + resets + buses + find_straps(g, taken)


def power_edges(blocks: list[Block]) -> list[str]:
    """One line per converter or series filter, for power_tree.md."""
    out = []
    for b in blocks:
        if b.kind == "switching_regulator":
            src = ", ".join(b.roles.get("input", [])) or "input not found"
            out.append(f"{b.roles['controller'][0]} switching regulator ({b.confidence}): {src} -> "
                       f"{b.roles['output'][0]} via {b.roles['inductor'][0]}")
        elif b.kind in ("ldo", "load_switch"):
            src = ", ".join(b.roles.get("input", [])) or "input not found"
            out.append(f"{b.roles['device'][0]} {b.kind.replace('_', ' ')} ({b.confidence}): {src} -> "
                       f"{b.roles['output'][0]}")
        elif b.kind in ("ferrite_filter", "lc_filter"):
            out.append(f"{b.roles['element'][0]} {b.kind.replace('_', ' ')} ({b.confidence}): "
                       f"{b.roles['upstream'][0]} -> {b.roles['downstream'][0]}")
    return out


def to_markdown(blocks: list[Block]) -> str:
    """Blocks grouped by kind, each with confidence, evidence, roles and notes."""
    lines = ["# Circuit blocks", "",
             "Found by netlist structure first and names second. Confidence says how much evidence fired;",
             "a low-confidence block is a lead to check, not a fact.", ""]
    for kind in ORDER:
        group = [b for b in blocks if b.kind == kind]
        if not group:
            continue
        lines += [f"## {kind.replace('_', ' ')} ({len(group)})", ""]
        for b in group:
            lines += [f"### {b.name} ({b.confidence})", ""]
            lines += [f"- evidence: {e}" for e in b.evidence]
            lines += [f"- {role}: {', '.join(v)}" for role, v in b.roles.items()]
            lines += [f"- note: {n}" for n in b.notes]
            lines.append("")
    return "\n".join(lines)


__all__ = ["Block", "find_all", "power_edges", "to_markdown"]
