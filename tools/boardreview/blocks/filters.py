"""Series bead or inductor filters with caps to ground: candidates for the LC tank check."""

from __future__ import annotations

import re

from boardreview.blocks.base import Block, describe, dnp_note, fitted_split, make_block
from boardreview.model import naming, parts
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph

_DOWNSTREAM_WORDS = {"FILT", "FILTERED", "CLEAN", "QUIET", "A", "ANA", "AN", "ANALOG", "PLL", "REF", "F", "LF"}


_OUT_PIN = re.compile(r"^(?:V?OUT\d?|VO)$")


def _output_pins(g: Graph, net: str) -> list[str]:
    """IC pins on the net that drive it as a supply: power_out type, or named OUT or VOUT."""
    return [p.key for p in g.net_pins.get(net, []) if g.kind(p.refdes) == "ic"
            and (p.type == "power_out" or _OUT_PIN.match(naming.pin_core(p.name)))]


def _supply_pins(g: Graph, net: str) -> list[str]:
    """IC pins on the net that draw supply from it: power_in type, or a supply name (VIN, VCC, VDD)."""
    return [p.key for p in g.net_pins.get(net, []) if g.kind(p.refdes) in ("ic", "oscillator")
            and (p.type == "power_in" or naming.pin_is_supply(p.name))]


def _downstream(g: Graph, a: str, b: str, sources: dict[str, str] | None = None,
                loads: dict[str, str] | None = None) -> tuple[str, str, str]:
    """(upstream, downstream, reason): name hints, regulator outputs and inputs, IC pins, then fewer pins."""
    sources, loads = sources or {}, loads or {}
    for up, down in ((a, b), (b, a)):
        extra = set(naming.tokens(down)) - set(naming.tokens(up))
        if extra & _DOWNSTREAM_WORDS or naming.leaf(down).upper().endswith(("A", "_F", "-F", "FILT")) \
                and naming.leaf(down).upper().startswith(naming.leaf(up).upper()):
            return up, down, f"name {down} reads as the filtered side"
    for up, down in ((a, b), (b, a)):
        if up in sources and down not in sources:
            return up, down, f"{up} is the {sources[up]}"
    for up, down in ((a, b), (b, a)):
        if down in loads and up not in loads:
            return up, down, f"{down} feeds the {loads[down]}"
    for up, down in ((a, b), (b, a)):
        drive = _output_pins(g, up)
        if drive and not _output_pins(g, down):
            return up, down, f"{up} is driven by output pin {', '.join(drive[:3])}"
    for up, down in ((a, b), (b, a)):
        draw = _supply_pins(g, down)
        if draw and not _supply_pins(g, up):
            return up, down, f"{down} supplies IC pins {', '.join(draw[:3])}; {up} supplies none"
    na, nb = len(g.net_pins.get(a, [])), len(g.net_pins.get(b, []))
    if na != nb:
        up, down = (a, b) if na > nb else (b, a)
        return up, down, f"{down} has fewer pins ({min(na, nb)} vs {max(na, nb)})"
    return a, b, "no hint; order is arbitrary"


def _total_c(g: Graph, caps: list[str]) -> float | None:
    vals = [g.model.components[c].value_si for c in caps]
    return sum(v for v in vals if v is not None) if vals and all(v is not None for v in vals) else None


def find_series_filters(g: Graph, exclude: set[str] = frozenset(), sources: dict[str, str] | None = None,
                        loads: dict[str, str] | None = None) -> list[Block]:
    """Two-pin beads or inductors off ground and shield with caps on a side; sources and loads name regulator nets."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        kind = g.kind(ref)
        if kind not in ("ferrite", "inductor") or ref in exclude or not g.is_two_pin(ref):
            continue
        a, b = g.nets_of(ref)
        if a is None or b is None or a == b or any(naming.net_kind(n) in ("ground", "chassis") for n in (a, b)):
            continue
        up, down, why = _downstream(g, a, b, sources, loads)
        caps_up, dnp_up = fitted_split(g, g.caps_to_ground(up))
        caps_down, dnp_down = fitted_split(g, g.caps_to_ground(down))
        if not (caps_up or caps_down or dnp_up or dnp_down):
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
                 "caps_upstream": caps_up, "loads_downstream": loads, "caps_downstream_dnp": dnp_down,
                 "caps_upstream_dnp": dnp_up}
        total = _total_c(g, caps_down)
        notes = ["check as an LC tank: the element's inductance with the downstream capacitance resonates, and "
                 "the damping comes from the element's resistance and the caps' ESR"]
        if not comp.fitted:
            notes.append(f"{ref} is DNP: this filter is not in the build")
        if caps_up and caps_down:
            notes.append("caps on both sides: a pi filter")
        if not caps_up and not caps_down:
            notes.append("no fitted caps to ground on either side")
        notes.append("values: " + ", ".join(describe(g, r) for r in [ref] + caps_down)
                     + (f"; downstream C total {total:.3g} F" if total is not None else ""))
        notes += dnp_note(g, dnp_down + dnp_up)
        kind_name = "ferrite_filter" if kind == "ferrite" else "lc_filter"
        found.append(make_block(g, kind_name, f"{ref} {up} -> {down}", score, 4, 3, evidence, roles, notes))
    return found
