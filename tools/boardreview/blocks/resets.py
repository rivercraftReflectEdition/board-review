"""Reset nets with their pull-ups, RC delay, supervisors, diode-OR links and connectors."""

from __future__ import annotations

import re

from boardreview.blocks.base import Block, describe, is_supply, make_block
from boardreview.model import naming
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph

_SUPERVISOR = re.compile(r"supervis|watchdog|reset|voltage (?:detector|monitor)|\bmonitor\b|\bpor\b", re.I)


def _is_reset_net(g: Graph, net: str) -> tuple[bool, list[str]]:
    ev = []
    if naming.is_reset_name(net):
        ev.append(f"net name {net}")
    named = [p.key for p in g.net_pins.get(net, []) if naming.pin_is(p.name, "reset")]
    if named:
        ev.append(f"reset-named pins {', '.join(named)}")
    return bool(ev), ev


def _supervisor(g: Graph, ref: str) -> bool:
    c = g.model.components[ref]
    return bool(_SUPERVISOR.search(c.description)) or (len(g.comp_pins.get(ref, [])) <= 8 and any(
        naming.pin_is(p.name, "reset") and p.type in ("output", "open_collector", "open_emitter")
        for p in g.comp_pins[ref]))


def find_reset_nets(g: Graph) -> list[Block]:
    """Nets named like resets, or carrying reset-named pins, with every part's role on the net."""
    found = []
    for net in sorted(g.net_pins, key=natural_key):
        if g.is_ground(net) or is_supply(g, net):
            continue
        hit, evidence = _is_reset_net(g, net)
        if not hit:
            continue
        pullups, pulldowns, series = [], [], []
        for r, far in g.resistors_to(net):
            if is_supply(g, far):
                pullups.append(r)
            elif g.is_ground(far):
                pulldowns.append(r)
            elif far is not None:
                series.append(r)
        caps = g.caps_to_ground(net)
        actives = sorted({p.refdes for p in g.active_pins(net)}, key=natural_key)
        sups = [r for r in actives if _supervisor(g, r)]
        diodes = [d for d in g.refs_on(net, {"diode"}) if g.is_two_pin(d)]
        links = sorted({g.other_net(d, net) for d in diodes if g.other_net(d, net)}
                       | {g.other_net(r, net) for r in series if g.other_net(r, net)}, key=natural_key)
        score = 1 + (1 if pullups or pulldowns else 0) + (1 if sups else 0) + (1 if len(evidence) > 1 else 0)
        if pullups:
            evidence.append(f"pull-up {', '.join(pullups)}")
        if sups:
            evidence.append(f"supervisor or watchdog {', '.join(sups)}")
        roles = {
            "net": [net], "pullups": pullups, "pulldowns": pulldowns, "delay_caps": caps, "supervisors": sups,
            "receivers": [p.key for p in g.active_pins(net) if p.refdes not in sups],
            "driver_pins": [p.key for p in g.active_pins(net) if p.refdes in sups],
            "diodes": diodes, "series_resistors": series, "linked_nets": links,
            "connectors": [p.key for p in g.net_pins[net] if g.kind(p.refdes) in ("connector", "testpoint")],
            "transistors": [p.key for p in g.net_pins[net] if g.kind(p.refdes) == "transistor"],
        }
        notes = []
        if diodes:
            notes.append(f"diode-OR or isolation through {', '.join(diodes)} to {', '.join(links) or 'other nets'}")
        if not pullups and not sups:
            notes.append("no pull-up or supervisor found on this net; it may rely on an internal pull-up")
        parts_listed = pullups + pulldowns + caps
        if parts_listed:
            notes.append("values: " + ", ".join(describe(g, r) for r in parts_listed))
        found.append(make_block(g, "reset", f"reset {net}", score, 3, 2, evidence, roles, notes))
    return found
