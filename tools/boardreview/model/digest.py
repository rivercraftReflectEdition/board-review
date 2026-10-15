"""LLM-readable markdown digests of a BoardModel: by net, by component, power tree, pin maps."""

from __future__ import annotations

from pathlib import Path

from boardreview.model import naming
from boardreview.model.board import BoardModel, Component, natural_key
from boardreview.model.graph import Graph


def _source_line(model: BoardModel) -> str:
    parts = [f"{s.get('kind', '?')} {Path(s.get('path', '')).name}".strip() for s in model.sources]
    return "Sources: " + ("; ".join(parts) if parts else "none")


def _comp_label(c: Component) -> str:
    bits = [c.kind]
    bits += [x for x in (c.value, c.mpn) if x]
    if not c.fitted:
        bits.append("DNP")
    return ", ".join(bits)


def nets_by_net(model: BoardModel) -> str:
    """Every net with its pin count and pins, then unconnected pins by component."""
    nets = model.nets
    unconnected = model.unconnected_pins()
    lines = ["# Nets by net", "", _source_line(model),
             f"{len(nets)} nets, {len(model.pins)} pins, {len(unconnected)} pins with no net.", ""]
    for net in nets.values():
        lines += [f"**{net.name}** ({len(net.pins)}): {', '.join(net.pins)}", ""]
    if unconnected:
        lines += [f"## Pins with no net ({len(unconnected)})", ""]
        by_ref: dict[str, list[str]] = {}
        for p in unconnected:
            by_ref.setdefault(p.refdes, []).append(p.number + (f" ({p.name})" if p.name else ""))
        lines += [f"- {ref}: {', '.join(nums)}" for ref, nums in sorted(by_ref.items(), key=lambda kv: natural_key(kv[0]))]
        lines.append("")
    return "\n".join(lines)


def nets_by_component(model: BoardModel) -> str:
    """Every component with its attributes and the net on each pin."""
    lines = ["# Nets by component", "", _source_line(model), ""]
    for ref in sorted(model.components, key=natural_key):
        c = model.components[ref]
        lines += [f"## {ref} ({_comp_label(c)})"]
        pins = model.pins_of(ref)
        if not pins:
            lines.append("- no pins in the netlist")
        for p in pins:
            name = f" ({p.name})" if p.name else ""
            lines.append(f"- {p.number}{name}: {p.net if p.net is not None else '(no net)'}")
        lines.append("")
    return "\n".join(lines)


def _series_links(g: Graph, net: str) -> list[str]:
    out = []
    for ref in g.refs_on(net, {"inductor", "ferrite", "fuse", "jumper", "resistor"}):
        other = g.other_net(ref, net)
        c = g.model.components[ref]
        if other is None or g.is_ground(other):
            continue
        if c.kind == "resistor" and not (c.value_si is not None and c.value_si <= 1.0):
            continue
        out.append(f"{ref} ({_comp_label(c)}) to {other}")
    return out


def power_tree(model: BoardModel, edges: list[str] | None = None) -> str:
    """Rails with evidence, series links, multi-rail ICs and every pin; grounds last."""
    g = Graph(model)
    rails = g.rails()
    lines = ["# Power tree", "", _source_line(model),
             "Rails are nets whose name reads as a supply or that carry capacitors to ground and power pins.",
             "Each rail lists the evidence, the parts that link it to other nets, and every pin.", ""]
    if edges:
        lines += ["## Converters and switches found by blocks", ""] + [f"- {e}" for e in edges] + [""]
    order = sorted(rails, key=lambda n: (-(naming.voltage_of(n) or 0.0), natural_key(n)))
    for net in order:
        v = naming.voltage_of(net)
        pins = model.nets[net].pins
        head = f"## {net}" + (f" ({v:g} V by name)" if v is not None else "")
        lines += [head, "", f"- evidence: {', '.join(rails[net])}", f"- pins: {len(pins)}"]
        caps = g.caps_to_ground(net)
        if caps:
            lines.append(f"- caps to ground ({len(caps)}): {', '.join(caps)}")
        links = _series_links(g, net)
        if links:
            lines.append(f"- series links: {'; '.join(links)}")
        multi = []
        for ref in g.refs_on(net, {"ic", "transistor"}):
            others = sorted({p.net for p in g.comp_pins[ref] if p.net in rails and p.net != net}, key=natural_key)
            if others:
                multi.append(f"{ref} also on {', '.join(others)}")
        if multi:
            lines.append(f"- parts on more than one rail: {'; '.join(multi)}")
        lines += [f"- all pins: {', '.join(pins)}", ""]
    grounds = [n for n in model.nets.values() if n.kind in ("ground", "chassis")]
    for net in grounds:
        lines += [f"## {net.name} ({net.kind})", "", f"- pins: {len(net.pins)}", f"- all pins: {', '.join(net.pins)}", ""]
    return "\n".join(lines)


def pin_map(model: BoardModel, refdes: str, g: Graph | None = None) -> str:
    """Pin table for one component: number, name, type, net and what else is on the net."""
    c = model.components[refdes]
    g = g or Graph(model)
    lines = [f"# {refdes} pin map", "", f"{_comp_label(c)}" + (f"; {c.description}" if c.description else ""), "",
             "| Pin | Name | Type | Net | Others on net |", "|---|---|---|---|---|"]
    for p in model.pins_of(refdes):
        if p.net is None:
            others = "-"
        else:
            refs = [r for r in g.refs_on(p.net) if r != refdes]
            others = f"{len(refs)} parts" if len(refs) > 8 else ", ".join(refs) or "only this pin"
        nc = " (NC flag)" if p.no_connect else ""
        lines.append(f"| {p.number} | {p.name or ''} | {p.type or ''} | {p.net or '(no net)'}{nc} | {others} |")
    return "\n".join(lines) + "\n"


def pin_map_refs(model: BoardModel, min_pins: int = 3) -> list[str]:
    """Components that get their own pin map: ICs, connectors, oscillators and anything with many pins."""
    keep = {"ic", "connector", "oscillator", "crystal", "transistor", "tvs", "transformer"}
    counts: dict[str, int] = {}
    for p in model.pins.values():
        counts[p.refdes] = counts.get(p.refdes, 0) + 1
    out = []
    for ref, c in model.components.items():
        n = counts.get(ref, 0)
        if n and (c.kind in keep or n >= min_pins):
            out.append(ref)
    return sorted(out, key=natural_key)


def write_digests(model: BoardModel, out_dir: str | Path, edges: list[str] | None = None) -> list[Path]:
    """Write nets_by_net.md, nets_by_component.md, power_tree.md and pinmaps/<REF>.md."""
    out = Path(out_dir)
    (out / "pinmaps").mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in (("nets_by_net.md", nets_by_net(model)), ("nets_by_component.md", nets_by_component(model)),
                       ("power_tree.md", power_tree(model, edges))):
        path = out / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    g = Graph(model)
    for ref in pin_map_refs(model):
        path = out / "pinmaps" / f"{ref}.md"
        path.write_text(pin_map(model, ref, g), encoding="utf-8")
        written.append(path)
    return written
