"""Crystals, oscillators, clock buffers and PLL candidates from part kinds and pin roles."""

from __future__ import annotations

import re

from boardreview.blocks.base import Block, describe, dnp_note, fitted_split, is_supply, make_block
from boardreview.model import naming
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph


def _series_to_ic(g: Graph, net: str) -> tuple[list[str], list[str]]:
    """Series resistors from a clock net to a net with IC pins, and those IC pins."""
    res, pins = [], []
    for r, far in g.resistors_to(net):
        if far is None or g.is_ground(far) or is_supply(g, far):
            continue
        hits = [p.key for p in _active_clock_loads(g, far)]
        if hits:
            res.append(r)
            pins += hits
    return res, pins


def _active_clock_loads(g: Graph, net: str):
    return [p for p in g.pins_on(net) if g.kind(p.refdes) in
            {"ic", "oscillator", "transistor", "clock_buffer", "pll", "jitter_cleaner", "clock_generator"}]


def _crystal(g: Graph, ref: str, signal: list[str]) -> Block:
    split = {n: fitted_split(g, g.caps_to_ground(n)) for n in signal}
    caps = {n: split[n][0] for n in signal}
    caps_dnp = [c for n in signal for c in split[n][1]]
    ic_pins = [p.key for n in signal for p in _active_clock_loads(g, n)]
    through, far_pins = [], []
    for n in signal:
        r, pins = _series_to_ic(g, n)
        through += r
        far_pins += pins
    series, series_dnp = fitted_split(g, through)
    named = [k for k in ic_pins + far_pins if naming.pin_is(g.model.pin(k).name, "xtal")]
    score = 1 + sum(1 for n in signal if caps[n]) + (1 if ic_pins or far_pins else 0) + (1 if named else 0)
    evidence = [f"{ref} has two signal nets {', '.join(signal)}"]
    evidence += [f"load cap {', '.join(caps[n])} on {n}" for n in signal if caps[n]]
    if ic_pins or far_pins:
        evidence.append(f"driver pins {', '.join(ic_pins + far_pins)}")
    if named:
        evidence.append(f"oscillator pin names on {', '.join(named)}")
    roles = {"crystal": [ref], "signal_nets": signal, "load_caps": [c for n in signal for c in caps[n]],
             "driver_pins": ic_pins + far_pins, "series_resistors": series, "load_caps_dnp": caps_dnp,
             "series_resistors_dnp": series_dnp}
    notes = ["values: " + ", ".join(describe(g, r) for r in [ref] + roles["load_caps"] + series),
             "load capacitance check needs the crystal CL and the pin and stray capacitance from datasheets"]
    bare = [n for n in signal if not caps[n]]
    if bare:
        notes.append(f"no fitted load cap on {', '.join(bare)}: internal load caps or a missing part")
    if series_dnp:
        notes.append(f"series {', '.join(series_dnp)} is DNP: that crystal pin may not reach the driver")
    if not g.fitted(ref):
        notes.append(f"{ref} is DNP: this crystal is not in the build")
    notes += dnp_note(g, caps_dnp + series_dnp)
    return make_block(g, "crystal", f"{ref} crystal", score, 4, 3, evidence, roles, notes)


def _oscillator(g: Graph, ref: str, supply: list[str], signal: list[str], unconnected: list[str]) -> Block:
    outputs, enables, series, loads = [], [], [], []
    for n in signal:
        direct = [p.key for p in _active_clock_loads(g, n) if p.refdes != ref]
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
    series, series_dnp = fitted_split(g, series)
    bypass, bypass_dnp = fitted_split(g, [c for n in supply for c in g.caps_to_ground(n)])
    roles = {"oscillator": [ref], "supply": supply, "output": outputs, "loads": loads, "series_resistors": series,
             "enable_nets": enables, "pins_on_supply": tied_high, "bypass_caps": bypass,
             "series_resistors_dnp": series_dnp, "bypass_caps_dnp": bypass_dnp}
    notes = []
    if not comp.fitted:
        notes.append(f"{ref} is DNP: this oscillator is not in the build")
    if series_dnp:
        notes.append(f"series {', '.join(series_dnp)} is DNP: that output may not reach its load")
    if unconnected:
        notes.append(f"pins with no net: {', '.join(unconnected)}; check OE/ST and NC pins against the datasheet")
    if len(tied_high) > 1:
        notes.append(f"more than one pin on the supply ({', '.join(tied_high)}): VDD plus OE/ST tied high, check")
    if not outputs:
        notes.append("no output net reaching an IC was found")
    return make_block(g, "oscillator", f"{ref} oscillator", score, 4, 3, evidence, roles, notes)


def _clock_pin_role(name: str) -> str:
    name = re.sub(r"[^A-Z0-9]", "", name.upper())
    for role, pattern in (
        ("feedback", r"(?:FB|FBIN|FBCLK|FBCLKIN|CLKFB|CLKFBIN)[0-9]*[PNB]?"),
        ("charge_pump", r"(?:CP|CPOUT|CHARGEPUMP)[0-9]*[PN]?"),
        ("tune", r"(?:VTUNE|VCTRL|VC|VCOIN|LF|FILT|LOOPFILTER)[0-9]*"),
        ("reference", r"(?:REF|REFIN|REFCLK|REFCLKIN|OSCIN|XIN|XA|XTALIN)[0-9]*[PNB]?"),
        ("input", r"(?:CLKIN|CLK|CLOCKIN|IN)[0-9]*[PNB]?"),
        ("output", r"(?:CLKOUT|CLOCKOUT|OUT|RFOUT|DCLKOUT|SDCLKOUT|Q|Y)[A-Z]?[0-9]*[PNB]?"),
        ("lock", r"(?:LOCK|LOCKED|LOCKDET|LD|LOL|LOS)[0-9]*[NB]?"),
        ("enable", r"(?:OE|EN|ENABLE|PDN|RESET)[0-9]*[NB]?"),
    ):
        if re.fullmatch(pattern, name):
            return role
    return ""


def _loop_parts(g: Graph, seeds: list[str]) -> tuple[list[str], list[str]]:
    parts, seen = set(), set(seeds)
    frontier = list(seeds)
    for _ in range(3):
        next_nets = []
        for net in frontier:
            for ref in g.refs_on(net, {"resistor", "capacitor"}):
                far = g.other_net(ref, net)
                if far is None or is_supply(g, far):
                    continue
                parts.add(ref)
                if not g.is_ground(far) and far not in seen:
                    seen.add(far)
                    next_nets.append(far)
        frontier = next_nets
    return sorted(parts, key=natural_key), sorted(seen, key=natural_key)


def _clock_device(g: Graph, ref: str) -> Block | None:
    comp = g.model.components[ref]
    if comp.kind not in {"ic", "clock_buffer", "pll", "jitter_cleaner", "clock_generator", "oscillator", "crystal"}:
        return None
    pins = g.comp_pins.get(ref, [])
    roles = {}
    for pin in pins:
        role = _clock_pin_role(pin.name)
        if role and not naming.pin_is_supply(pin.name) and not g.is_ground(pin.net):
            roles.setdefault(role, []).append(pin)
    text = f"{comp.kind.replace('_', ' ')} {comp.description} {comp.value}"
    cleaner = bool(re.search(r"\bjitter[ -]*(?:cleaner|cleaning|attenuator)\b", text, re.I))
    pll = cleaner or bool(re.search(r"\bPLL\b|phase[ -]*locked|clock synthesizer|clock generator", text, re.I))
    buffer = bool(re.search(r"clock[ -]*(?:buffer|fanout)|fanout[ -]*(?:clock|buffer)", text, re.I))
    if not pll:
        pll = bool(roles.get("charge_pump") and (roles.get("reference") or roles.get("input"))
                   and (roles.get("output") or roles.get("tune")))
    if not buffer and not pll and comp.kind == "ic":
        clock_input = any(re.match(r"CLKIN|CLOCKIN", re.sub(r"[^A-Z0-9]", "", p.name.upper()))
                          for p in roles.get("input", []))
        clock_output = any(re.match(r"CLKOUT|CLOCKOUT", re.sub(r"[^A-Z0-9]", "", p.name.upper()))
                           for p in roles.get("output", []))
        buffer = clock_input and clock_output
    if not (pll or buffer):
        return None
    kind = "jitter_cleaner" if cleaner else "pll" if pll else "clock_buffer"
    block_roles = {"device": [ref]}
    for role, group in roles.items():
        block_roles[f"{role}_pins"] = [p.key for p in group]
    supply = sorted({p.net for p in pins if p.net and (naming.pin_is_supply(p.name) or p.type == "power_in")
                     and not g.is_ground(p.net)}, key=natural_key)
    inputs = sorted({p.net for role in ("input", "reference", "feedback") for p in roles.get(role, []) if p.net},
                    key=natural_key)
    outputs = sorted({p.net for p in roles.get("output", []) if p.net}, key=natural_key)
    block_roles.update(supply=supply, input=inputs, output=outputs, signal_nets=sorted(set(inputs + outputs), key=natural_key))
    bypass = [c for net in supply for c in g.caps_to_ground(net)]
    block_roles["bypass_caps"], block_roles["bypass_caps_dnp"] = fitted_split(g, bypass)
    series, loads = [], []
    for net in outputs:
        res, far = _series_to_ic(g, net)
        series += res
        loads += [p.key for p in _active_clock_loads(g, net) if p.refdes != ref] + [p for p in far if not p.startswith(ref + ".")]
    block_roles["series_resistors"], block_roles["series_resistors_dnp"] = fitted_split(g, sorted(set(series), key=natural_key))
    block_roles["loads"] = sorted(set(loads), key=natural_key)
    if pll:
        seeds = [p.net for role in ("charge_pump", "tune") for p in roles.get(role, []) if p.net]
        loop_parts, loop_nets = _loop_parts(g, seeds)
        block_roles["loop_filter_parts"], block_roles["loop_filter_parts_dnp"] = fitted_split(g, loop_parts)
        block_roles["loop_filter_nets"] = loop_nets
    evidence = [f"{ref} kind {comp.kind}; description {comp.description or '(not supplied)'}"]
    evidence += [f"{role.replace('_', ' ')} pins {', '.join(p.key + ' ' + p.name for p in group)}"
                 for role, group in roles.items()]
    notes = ["candidate from part kind and pin names; confirm clock format, programming and internal loops from the datasheet"]
    if not comp.fitted:
        notes.append(f"{ref} is DNP: this clock device is not in the build")
    if not outputs:
        notes.append("no connected output was identified; check missing pin names and unconnected outputs")
    if pll and not roles.get("charge_pump"):
        notes.append("no external charge-pump pin identified; the loop may be internal")
    notes += dnp_note(g, [r for role, refs in block_roles.items() if role.endswith("_dnp") for r in refs])
    score = int(bool(supply)) + int(bool(inputs)) + int(bool(outputs)) + int(pll or buffer)
    return make_block(g, kind, f"{ref} {kind.replace('_', ' ')}", score, 4, 2, evidence, block_roles, notes)


def find_clocks(g: Graph) -> list[Block]:
    """Clock devices by roles or kind, plus crystals and oscillators with eight pins or fewer."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        comp = g.model.components[ref]
        pins = g.comp_pins.get(ref, [])
        device = _clock_device(g, ref)
        if device is not None:
            found.append(device)
            continue
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
