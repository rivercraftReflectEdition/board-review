"""LDOs and load switches: a small IC with an IN pin on one net and an OUT pin on another net with caps to ground."""

from __future__ import annotations

import re

from boardreview.blocks.base import Block, describe, dnp_note, fitted_split, make_block
from boardreview.model import naming
from boardreview.model.board import Pin, natural_key
from boardreview.model.graph import Graph

MAX_PINS = 16
_IN = re.compile(r"^(?:V?IN|PVIN)(\d?)$")
_OUT = re.compile(r"^(?:V?OUT|VO)(\d?)$")
_SWITCH_TEXT = re.compile(r"load switch|power switch|power distribution|current.limit|e-?fuse|\bswitch\b", re.I)
_LDO_TEXT = re.compile(r"\bldo\b|linear|low.dropout|regulator", re.I)
_SWITCH_PINS = {"FLT", "FAULT", "OC", "OCB", "ILIM", "ISET", "QOD"}
_LDO_PINS = {"NR", "BYP", "BYPASS", "NR/SS", "NR_SS", "ADJ", "FB"}


def _usable(p: Pin) -> bool:
    return p.net is not None and naming.net_kind(p.net) not in ("ground", "chassis")


def _kind(g: Graph, ref: str, inp: str, out: str, pins: list[Pin]) -> tuple[str, str, bool]:
    """('ldo' or 'load_switch' or '', why, True when text or a pin name says so rather than rail names)."""
    c = g.model.components[ref]
    text = " ".join(x for x in (c.description, c.value, c.mpn) if x)
    cores = {naming.pin_core(p.name) for p in pins}
    if _SWITCH_TEXT.search(text):
        return "load_switch", f"description or value reads as a switch: {text}", True
    if _LDO_TEXT.search(text):
        return "ldo", f"description or value reads as a linear regulator: {text}", True
    if cores & _SWITCH_PINS:
        return "load_switch", f"pin {', '.join(sorted(cores & _SWITCH_PINS))} reads as a switch fault or limit pin", True
    if cores & _LDO_PINS:
        return "ldo", f"pin {', '.join(sorted(cores & _LDO_PINS))} reads as an LDO noise, bypass or feedback pin", True
    vin, vout = naming.voltage_of(inp), naming.voltage_of(out)
    if vin is not None and vout is not None and vout < vin - 0.05:
        return "ldo", f"output rail name says {vout:g} V, below the {vin:g} V input", False
    if vin is not None and vout is not None and abs(vout - vin) <= 0.05:
        return "load_switch", f"both rail names say {vin:g} V", False
    return "", "no description, MPN text, pin name or rail voltage says which", False


def _pairs(pins: list[Pin]) -> list[tuple[str, str]]:
    """(input net, output net) per channel, pairing IN1 with OUT1; a single IN serves every OUT."""
    ins: dict[str, set[str]] = {}
    outs: dict[str, set[str]] = {}
    for p in pins:
        core = naming.pin_core(p.name)
        for pat, into in ((_IN, ins), (_OUT, outs)):
            m = pat.match(core)
            if m:
                into.setdefault(m.group(1), set()).add(p.net)
    pairs = []
    for ch, out_nets in sorted(outs.items()):
        in_nets = ins.get(ch) or (next(iter(ins.values())) if len(ins) == 1 else set())
        if len(out_nets) == 1 and len(in_nets) == 1 and in_nets != out_nets:
            pairs.append((next(iter(in_nets)), next(iter(out_nets))))
    return pairs


def find_linear(g: Graph, exclude: set[str] = frozenset()) -> list[Block]:
    """LDOs and load switches by IN and OUT pin names; which of the two from text, pins or rail voltages."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        pins = g.comp_pins.get(ref, [])
        if g.kind(ref) != "ic" or ref in exclude or not pins or len(pins) > MAX_PINS \
                or any(naming.pin_is(p.name, "sw") for p in pins):
            continue
        for inp, out in _pairs([p for p in pins if _usable(p)]):
            out_caps, out_dnp = fitted_split(g, g.caps_to_ground(out))
            kind, why, named = _kind(g, ref, inp, out, pins)
            if not (out_caps or out_dnp or named):
                continue
            in_caps, in_dnp = fitted_split(g, g.caps_to_ground(inp))
            score = 2 + (2 if kind else 0)
            evidence = [f"{ref} pins IN on {inp} and OUT on {out}"]
            notes = [why] if kind else [f"LDO or load switch: {why}; recorded as an LDO, the datasheet decides"]
            if out_caps or out_dnp:
                evidence.append(f"{len(out_caps + out_dnp)} caps from {out} to ground")
            else:
                notes.append(f"no caps to ground on {out}; the output caps may sit past a series part")
            if kind:
                evidence.append(why)
            if not g.fitted(ref):
                notes.append(f"{ref} is DNP: this {'switch' if kind == 'load_switch' else 'regulator'} is not in the build")
            notes.append("values: " + ", ".join(describe(g, r) for r in [ref] + out_caps))
            notes += dnp_note(g, out_dnp + in_dnp)
            roles = {"device": [ref], "input": [inp], "output": [out], "output_caps": out_caps, "input_caps": in_caps,
                     "enable_pins": [p.key for p in pins if naming.pin_is(p.name, "en")],
                     "power_good_pins": [p.key for p in pins if naming.pin_is(p.name, "pg")],
                     "fb_pins": [p.key for p in pins if naming.pin_is(p.name, "fb")],
                     "output_caps_dnp": out_dnp, "input_caps_dnp": in_dnp}
            found.append(make_block(g, kind or "ldo", f"{ref} {inp} -> {out}", score, 4, 3, evidence, roles, notes))
    return found
