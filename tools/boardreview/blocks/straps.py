"""Strap pins: an IC pin set by resistors to rails or ground, with the level the fitted parts give."""

from __future__ import annotations

from boardreview.blocks.base import Block, describe, is_supply, make_block
from boardreview.model import naming
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph


def _level(g: Graph, ups: list[str], downs: list[str]) -> str:
    fu = [r for r in ups if g.fitted(r)]
    fd = [r for r in downs if g.fitted(r)]
    if fu and fd:
        return f"divider: {', '.join(fu)} up and {', '.join(fd)} down are both fitted"
    if fu:
        return f"high through {', '.join(fu)}" + (f" ({', '.join(downs)} not fitted)" if downs else "")
    if fd:
        return f"low through {', '.join(fd)}" + (f" ({', '.join(ups)} not fitted)" if ups else "")
    return "floating: no pull resistor is fitted"


def find_straps(g: Graph, exclude_nets: set[str] = frozenset()) -> list[Block]:
    """Nets where pulls to rails or ground set one IC pin, or a pull-up and pull-down pair sets a pin."""
    found = []
    for net in sorted(g.net_pins, key=natural_key):
        if net in exclude_nets or g.is_ground(net) or is_supply(g, net):
            continue
        ups, downs, series = [], [], []
        for r, far in g.resistors_to(net):
            if is_supply(g, far):
                ups.append(r)
            elif g.is_ground(far):
                downs.append(r)
            elif far is not None:
                series.append(r)
        if not ups and not downs:
            continue
        ic_pins = [p for p in g.net_pins[net] if g.kind(p.refdes) == "ic"]
        ics = sorted({p.refdes for p in ic_pins}, key=natural_key)
        others = [p.refdes for p in g.net_pins[net]
                  if p.refdes not in ups + downs + series and g.kind(p.refdes) not in ("ic", "capacitor")]
        pair = bool(ups and downs)
        if not ics or not (pair or (len(ics) == 1 and not others)):
            continue
        strap_named = [p.key for p in ic_pins if naming.pin_is(p.name, "strap")]
        tags = [t for t, role in (("enable", "en"), ("power good", "pg"), ("reset", "reset")) if any(
            naming.pin_is(p.name, role) for p in ic_pins)]
        score = 1 + (1 if pair else 0) + (1 if strap_named else 0) + (1 if len(ics) == 1 and not series else 0)
        evidence = [f"{', '.join(p.key for p in ic_pins)} pulled by {', '.join(ups + downs)}"]
        if pair:
            evidence.append("pull-up and pull-down pair (build option or divider)")
        if strap_named:
            evidence.append(f"strap-like pin names {', '.join(strap_named)}")
        if series:
            evidence.append(f"net also passes through {', '.join(series)} (strap shared with a signal)")
        roles = {"net": [net], "ic_pins": [p.key for p in ic_pins], "pullups": ups, "pulldowns": downs,
                 "series_resistors": series, "other_parts": sorted(set(others), key=natural_key)}
        notes = [f"level: {_level(g, ups, downs)}", "values: " + ", ".join(describe(g, r) for r in ups + downs)]
        if tags:
            notes.append(f"pin role by name: {', '.join(tags)}; a pull on this pin is a bias, not a boot strap")
        found.append(make_block(g, "strap", f"strap {net}", score, 3, 2, evidence, roles, notes))
    return found
