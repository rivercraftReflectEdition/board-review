"""Series bead or inductor filters with caps to ground: candidates for the LC tank check."""

from __future__ import annotations

from boardreview.blocks.base import Block, describe, make_block
from boardreview.model import naming, parts
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph

_DOWNSTREAM_WORDS = {"FILT", "FILTERED", "CLEAN", "QUIET", "A", "ANA", "AN", "ANALOG", "PLL", "REF", "F", "LF"}


def _downstream(g: Graph, a: str, b: str) -> tuple[str, str, str]:
    """(upstream, downstream, reason): name hints first, then the side with fewer pins."""
    for up, down in ((a, b), (b, a)):
        extra = set(naming.tokens(down)) - set(naming.tokens(up))
        if extra & _DOWNSTREAM_WORDS or naming.leaf(down).upper().endswith(("A", "_F", "-F", "FILT")) \
                and naming.leaf(down).upper().startswith(naming.leaf(up).upper()):
            return up, down, f"name {down} reads as the filtered side"
    na, nb = len(g.net_pins.get(a, [])), len(g.net_pins.get(b, []))
    if na != nb:
        up, down = (a, b) if na > nb else (b, a)
        return up, down, f"{down} has fewer pins ({min(na, nb)} vs {max(na, nb)})"
    return a, b, "no hint; order is arbitrary"


def _total_c(g: Graph, caps: list[str]) -> float | None:
    vals = [g.model.components[c].value_si for c in caps]
    return sum(v for v in vals if v is not None) if vals and all(v is not None for v in vals) else None


def find_series_filters(g: Graph, exclude: set[str] = frozenset()) -> list[Block]:
    """Two-pin beads or inductors between two non-ground nets where at least one side has caps to ground."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        kind = g.kind(ref)
        if kind not in ("ferrite", "inductor") or ref in exclude or not g.is_two_pin(ref):
            continue
        a, b = g.nets_of(ref)
        if a is None or b is None or a == b or g.is_ground(a) or g.is_ground(b):
            continue
        up, down, why = _downstream(g, a, b)
        caps_up, caps_down = g.caps_to_ground(up), g.caps_to_ground(down)
        if not caps_up and not caps_down:
            continue
        comp = g.model.components[ref]
        identified = bool(comp.description or comp.mpn) or parts.prefix(ref) == "FB"
        score = 1 + (1 if identified else 0) + (1 if caps_down else 0) + (1 if "name" in why else 0)
        evidence = [f"{ref} ({kind}{', from ' + ('description/MPN' if comp.description or comp.mpn else 'refdes')}) "
                    f"in series between {up} and {down}", f"downstream side: {why}"]
        if caps_down:
            evidence.append(f"{len(caps_down)} caps to ground on {down}")
        if caps_up:
            evidence.append(f"{len(caps_up)} caps to ground on {up}")
        loads = [p.key for p in g.active_pins(down)]
        roles = {"element": [ref], "upstream": [up], "downstream": [down], "caps_downstream": caps_down,
                 "caps_upstream": caps_up, "loads_downstream": loads}
        total = _total_c(g, caps_down)
        notes = ["check as an LC tank: the element's inductance with the downstream capacitance resonates, and "
                 "the damping comes from the element's resistance and the caps' ESR"]
        if caps_up and caps_down:
            notes.append("caps on both sides: a pi filter")
        notes.append("values: " + ", ".join(describe(g, r) for r in [ref] + caps_down)
                     + (f"; downstream C total {total:.3g} F" if total is not None else ""))
        kind_name = "ferrite_filter" if kind == "ferrite" else "lc_filter"
        found.append(make_block(g, kind_name, f"{ref} {up} -> {down}", score, 4, 3, evidence, roles, notes))
    return found
