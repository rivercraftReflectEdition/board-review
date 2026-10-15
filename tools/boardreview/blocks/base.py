"""Block type, evidence scoring and the subgraph each block carries for the checklists."""

from __future__ import annotations

from dataclasses import dataclass, field

from boardreview.model import naming
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph


@dataclass
class Block:
    kind: str
    name: str
    confidence: str
    evidence: list[str]
    roles: dict[str, list[str]]
    components: list[str]
    nets: list[str]
    notes: list[str] = field(default_factory=list)
    subgraph: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "name": self.name, "confidence": self.confidence, "evidence": self.evidence,
                "roles": self.roles, "components": self.components, "nets": self.nets, "notes": self.notes,
                "subgraph": self.subgraph}


def confidence(score: int, high: int, medium: int) -> str:
    """Map an evidence score to high, medium or low."""
    return "high" if score >= high else "medium" if score >= medium else "low"


def is_supply(g: Graph, net: str | None) -> bool:
    """True for rails by name or by structure (caps to ground, power pins)."""
    if net is None or naming.net_kind(net) in ("ground", "chassis"):
        return False
    return naming.is_rail_name(net) or bool(g.rail_evidence(net))


def describe(g: Graph, ref: str) -> str:
    """Short label for a part: ref, value or MPN, DNP mark."""
    c = g.model.components.get(ref)
    if c is None:
        return ref
    label = c.value or c.mpn
    return f"{ref}" + (f" {label}" if label else "") + ("" if c.fitted else " (DNP)")


def fitted_split(g: Graph, refs: list[str]) -> tuple[list[str], list[str]]:
    """Refdes split into fitted parts and DNP parts, order kept."""
    return [r for r in refs if g.fitted(r)], [r for r in refs if not g.fitted(r)]


def dnp_note(g: Graph, refs: list[str]) -> list[str]:
    """A note naming DNP options, or nothing when there are none."""
    return [f"DNP options: {', '.join(describe(g, r) for r in refs)}"] if refs else []


def make_block(g: Graph, kind: str, name: str, score: int, high: int, medium: int, evidence: list[str],
               roles: dict[str, list[str]], notes: list[str] | None = None) -> Block:
    """Build a Block and its subgraph from the refdes and nets named in its roles."""
    comps: list[str] = []
    nets: list[str] = []
    for values in roles.values():
        for v in values:
            ref = v.partition(".")[0]
            if v in g.model.nets:
                if v not in nets:
                    nets.append(v)
            elif v in g.model.components or ref in g.model.components:
                key = v if v in g.model.components else ref
                if key not in comps:
                    comps.append(key)
    comps.sort(key=natural_key)
    nets.sort(key=natural_key)
    sub_nets = {}
    for net in nets:
        inside = [p.key for p in g.net_pins.get(net, []) if p.refdes in comps]
        sub_nets[net] = {"block_pins": sorted(inside, key=natural_key),
                         "other_pins": len(g.net_pins.get(net, [])) - len(inside)}
    sub_comps = {}
    for ref in comps:
        c = g.model.components[ref]
        pins = g.comp_pins.get(ref, [])
        shown = {p.number: {"name": p.name, "net": p.net} for p in pins if p.net in sub_nets or len(pins) <= 8}
        sub_comps[ref] = {"kind": c.kind, "value": c.value, "value_si": c.value_si, "mpn": c.mpn, "fitted": c.fitted,
                          "pins": shown, "other_pins": len(pins) - len(shown)}
    return Block(kind, name, confidence(score, high, medium), evidence, {k: list(v) for k, v in roles.items() if v},
                 comps, nets, notes or [], {"components": sub_comps, "nets": sub_nets})
