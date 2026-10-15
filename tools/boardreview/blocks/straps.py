"""Strap pins: an IC pin set by resistors to rails or ground, with the pull topology and what is fitted."""

from __future__ import annotations

from boardreview.blocks.base import Block, describe, dnp_note, fitted_split, is_supply, make_block
from boardreview.model import naming
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph

LEVEL_NOTE = ("level: UNSURE; it depends on the pull values, the pin's internal pull and leakage, and its VIH and "
              "VIL; settle it with a calculation against the datasheet thresholds")


def _pulls(g: Graph, net: str, refs: list[str]) -> str:
    return ", ".join(f"{r} to {g.other_net(r, net)}" for r in refs)


def _topology(g: Graph, net: str, ups: list[str], downs: list[str], off: list[str]) -> str:
    """Which pulls are fitted and where they go; no logic level is claimed."""
    tail = f"; not fitted: {_pulls(g, net, off)}" if off else ""
    if ups and downs:
        return (f"{_pulls(g, net, ups)} and {_pulls(g, net, downs)} are both fitted: a divider, or both sides of a "
                f"build option fitted at once; confirm which is meant{tail}")
    if ups or downs:
        on = ups or downs
        rails = sorted({g.other_net(r, net) for r in on}, key=natural_key)
        return f"pulled toward {', '.join(rails)} by {', '.join(on)}{tail}"
    return f"no fitted pull resistor{tail}"


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
        fit_ups, dnp_ups = fitted_split(g, ups)
        fit_downs, dnp_downs = fitted_split(g, downs)
        fit_series, dnp_series = fitted_split(g, series)
        roles = {"net": [net], "ic_pins": [p.key for p in ic_pins], "pullups": fit_ups, "pulldowns": fit_downs,
                 "series_resistors": fit_series, "other_parts": sorted(set(others), key=natural_key),
                 "pullups_dnp": dnp_ups, "pulldowns_dnp": dnp_downs, "series_resistors_dnp": dnp_series}
        notes = [_topology(g, net, fit_ups, fit_downs, dnp_ups + dnp_downs), LEVEL_NOTE]
        if fit_ups or fit_downs:
            notes.append("values: " + ", ".join(describe(g, r) for r in fit_ups + fit_downs))
        notes += dnp_note(g, dnp_ups + dnp_downs + dnp_series)
        if tags:
            notes.append(f"pin role by name: {', '.join(tags)}; a pull on this pin is a bias, not a boot strap")
        found.append(make_block(g, "strap", f"strap {net}", score, 3, 2, evidence, roles, notes))
    return found
