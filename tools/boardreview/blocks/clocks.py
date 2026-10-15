"""Crystals with load caps and oscillators with supply, enable and output loads."""

from __future__ import annotations

from boardreview.blocks.base import Block, describe, is_supply, make_block
from boardreview.model import naming
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph


def _series_to_ic(g: Graph, net: str) -> tuple[list[str], list[str]]:
    """Series resistors from a clock net to a net with IC pins, and those IC pins."""
    res, pins = [], []
    for r, far in g.resistors_to(net):
        if far is None or g.is_ground(far) or is_supply(g, far):
            continue
        hits = [p.key for p in g.active_pins(far)]
        if hits:
            res.append(r)
            pins += hits
    return res, pins


def _crystal(g: Graph, ref: str, signal: list[str]) -> Block:
    caps = {n: g.caps_to_ground(n) for n in signal}
    ic_pins = [p.key for n in signal for p in g.active_pins(n)]
    series, far_pins = [], []
    for n in signal:
        r, pins = _series_to_ic(g, n)
        series += r
        far_pins += pins
    named = [k for k in ic_pins + far_pins if naming.pin_is(g.model.pin(k).name, "xtal")]
    score = 1 + sum(1 for n in signal if caps[n]) + (1 if ic_pins or far_pins else 0) + (1 if named else 0)
    evidence = [f"{ref} has two signal nets {', '.join(signal)}"]
    evidence += [f"load cap {', '.join(caps[n])} on {n}" for n in signal if caps[n]]
    if ic_pins or far_pins:
        evidence.append(f"driver pins {', '.join(ic_pins + far_pins)}")
    if named:
        evidence.append(f"oscillator pin names on {', '.join(named)}")
    roles = {"crystal": [ref], "signal_nets": signal, "load_caps": [c for n in signal for c in caps[n]],
             "driver_pins": ic_pins + far_pins, "series_resistors": series}
    notes = ["values: " + ", ".join(describe(g, r) for r in [ref] + roles["load_caps"] + series),
             "load capacitance check needs the crystal CL and the pin and stray capacitance from datasheets"]
    if any(not caps[n] for n in signal):
        notes.append("a signal net has no load cap: internal load caps or a missing part")
    return make_block(g, "crystal", f"{ref} crystal", score, 4, 3, evidence, roles, notes)


def _oscillator(g: Graph, ref: str, supply: list[str], signal: list[str], unconnected: list[str]) -> Block:
    outputs, enables, series, loads = [], [], [], []
    for n in signal:
        direct = [p.key for p in g.active_pins(n) if p.refdes != ref]
        r, far = _series_to_ic(g, n)
        pulls = [x for x, far_net in g.resistors_to(n) if is_supply(g, far_net) or g.is_ground(far_net)]
        if direct or far:
            outputs.append(n)
            loads += direct + far
            series += r
        elif pulls:
            enables.append(n)
    tied_high = [p.key for p in g.comp_pins[ref] if p.net in supply]
    comp = g.model.components[ref]
    score = (1 if comp.kind == "oscillator" else 0) + (1 if supply else 0) + (1 if outputs else 0) + 1
    evidence = [f"{ref} kind {comp.kind}" + (" from description" if comp.description else " from refdes")]
    if supply:
        evidence.append(f"supply pins on {', '.join(supply)}")
    if outputs:
        evidence.append(f"output {', '.join(outputs)} reaches {', '.join(loads)}")
    roles = {"oscillator": [ref], "supply": supply, "output": outputs, "loads": loads, "series_resistors": series,
             "enable_nets": enables, "pins_on_supply": tied_high, "bypass_caps": [c for n in supply
                                                                                   for c in g.caps_to_ground(n)]}
    notes = []
    if unconnected:
        notes.append(f"pins with no net: {', '.join(unconnected)}; check OE/ST and NC pins against the datasheet")
    if len(tied_high) > 1:
        notes.append(f"more than one pin on the supply ({', '.join(tied_high)}): VDD plus OE/ST tied high, check")
    if not outputs:
        notes.append("no output net reaching an IC was found")
    return make_block(g, "oscillator", f"{ref} oscillator", score, 4, 3, evidence, roles, notes)


def find_clocks(g: Graph) -> list[Block]:
    """Crystals and oscillators with eight pins or fewer."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        comp = g.model.components[ref]
        pins = g.comp_pins.get(ref, [])
        if comp.kind not in ("crystal", "oscillator") or not pins or len(pins) > 8:
            continue
        supply = sorted({p.net for p in pins if is_supply(g, p.net)}, key=natural_key)
        signal = sorted({p.net for p in pins if p.net and not g.is_ground(p.net) and p.net not in supply},
                        key=natural_key)
        unconnected = [p.key for p in pins if p.net is None]
        if comp.kind == "crystal" and not supply and len(signal) == 2:
            found.append(_crystal(g, ref, signal))
        elif supply or comp.kind == "oscillator":
            found.append(_oscillator(g, ref, supply, signal, unconnected))
    return found
