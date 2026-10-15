"""Switching regulators: an IC pin and an inductor on a switch node, output caps, bootstrap and feedback."""

from __future__ import annotations

import re

from boardreview.blocks.base import Block, describe, is_supply, make_block
from boardreview.model import naming
from boardreview.model.board import Pin, natural_key
from boardreview.model.graph import Graph


def _ic_pins(g: Graph, net: str) -> list[Pin]:
    return [p for p in g.net_pins.get(net, []) if g.kind(p.refdes) == "ic"]


def _orient(g: Graph, ind: str) -> tuple[str, str, list[Pin], bool] | None:
    """Pick (switch node, output, controller pins, named) for an inductor, or None if it is not a converter."""
    nets = g.nets_of(ind)
    if len(nets) != 2 or None in nets or any(g.is_ground(n) for n in nets) or nets[0] == nets[1]:
        return None
    options = []
    for sw, out in ((nets[0], nets[1]), (nets[1], nets[0])):
        pins = _ic_pins(g, sw)
        if not pins:
            continue
        named = any(naming.pin_is(p.name, "sw") for p in pins)
        caps_on_sw = bool(g.caps_to_ground(sw))
        if named or (not caps_on_sw and g.caps_to_ground(out)):
            options.append((0 if named else 1, sw, out, pins, named))
    if not options:
        return None
    _, sw, out, pins, named = min(options, key=lambda o: o[0])
    return sw, out, pins, named


def _bootstrap(g: Graph, sw: str, ic: str) -> tuple[list[str], list[str]]:
    """Caps from the switch node to a net that reaches the controller, directly or through one resistor."""
    for cap in g.refs_on(sw, {"capacitor"}):
        other = g.other_net(cap, sw)
        if other is None or g.is_ground(other):
            continue
        direct = [p.key for p in g.pins_on(other, ic)]
        if direct:
            return [cap], direct
        for res, far in g.resistors_to(other):
            pins = [p.key for p in g.pins_on(far, ic)] if far else []
            if pins:
                return [cap, res], pins
    return [], []


def _feedback(g: Graph, out: str, ic: str) -> dict[str, list[str]]:
    """Resistor divider from the output to a node on the controller, with the bottom leg to ground."""
    for top, mid in g.resistors_to(out):
        if mid is None or mid == out or g.is_ground(mid) or is_supply(g, mid):
            continue
        fb_pins = [p.key for p in g.pins_on(mid, ic)]
        bottom = [r for r, far in g.resistors_to(mid) if r != top and g.is_ground(far)]
        if fb_pins and bottom:
            cff = [c for c in g.refs_on(mid, {"capacitor"}) if g.other_net(c, mid) == out]
            return {"feedback_top": [top], "feedback_bottom": bottom, "feedback_node": [mid], "fb_pins": fb_pins,
                    "feedforward_cap": cff}
    direct = [p.key for p in g.pins_on(out, ic) if naming.pin_is(p.name, "fb")]
    return {"fb_pins": direct} if direct else {}


def _inputs(g: Graph, ic: str, exclude: set[str]) -> list[str]:
    pins = g.comp_pins.get(ic, [])
    usable = [p for p in pins if p.net and p.net not in exclude and not g.is_ground(p.net)]
    strict = sorted({p.net for p in usable if re.match(r"^(?:P?VIN\d?|IN\d?)$", naming.pin_core(p.name))})
    if strict:
        return strict
    named = sorted({p.net for p in usable if naming.pin_is(p.name, "vin")})
    if named:
        return named
    return sorted({p.net for p in pins if p.net and p.net not in exclude and is_supply(g, p.net)}, key=natural_key)


def _candidates(g: Graph) -> list[tuple[str, str, str, str, list[Pin], bool]]:
    """(inductor, controller, switch node, output, controller pins on the switch node, named) per converter."""
    out = []
    for ind in sorted(g.model.components, key=natural_key):
        if g.kind(ind) != "inductor" or not g.is_two_pin(ind):
            continue
        oriented = _orient(g, ind)
        if oriented is None:
            continue
        sw, net_out, pins, named = oriented
        ic = max(sorted({p.refdes for p in pins}, key=natural_key), key=lambda r: sum(p.refdes == r for p in pins))
        out.append((ind, ic, sw, net_out, [p for p in pins if p.refdes == ic], named))
    return out


def find_switching_regulators(g: Graph) -> list[Block]:
    """Inductors whose one side is an IC switch pin and whose other side has caps to ground."""
    cands = _candidates(g)
    outputs: dict[str, set[str]] = {}
    for _, ic, _, net_out, _, _ in cands:
        outputs.setdefault(ic, set()).add(net_out)
    found = []
    for ind, ic, sw, out, pins, named in cands:
        score, evidence = 1, [f"{ind} sits between {ic} pins {', '.join(p.number for p in pins)} on {sw} and {out}"]
        if named:
            score += 2
            evidence.append(f"switch pin name {', '.join(sorted({p.name for p in pins if naming.pin_is(p.name, 'sw')}))}")
        out_caps = g.caps_to_ground(out)
        if out_caps:
            score += 1
            evidence.append(f"{len(out_caps)} caps from {out} to ground")
        if not g.caps_to_ground(sw):
            score += 1
            evidence.append(f"no caps to ground on {sw}, as a switch node should be")
        boot, boot_pins = _bootstrap(g, sw, ic)
        if boot:
            score += 2
            evidence.append(f"bootstrap {' + '.join(boot)} from {sw} to {', '.join(boot_pins)}")
        fb = _feedback(g, out, ic)
        if fb.get("feedback_top"):
            score += 2
            evidence.append(f"divider {fb['feedback_top'][0]}/{fb['feedback_bottom'][0]} from {out} to "
                            f"{', '.join(fb['fb_pins'])}")
        elif fb.get("fb_pins"):
            score += 1
            evidence.append(f"FB-named pin on the output: {', '.join(fb['fb_pins'])}")
        on_out = [p.key for p in g.pins_on(out, ic)]
        inputs = _inputs(g, ic, {sw} | outputs[ic])
        candidates: list[str] = []
        if len(inputs) > 2 and not any(naming.pin_is(p.name, "vin") for p in g.comp_pins[ic]):
            inputs, candidates = [], inputs
        roles = {
            "controller": [ic], "inductor": [ind], "switch_node": [sw], "output": [out], "output_caps": out_caps,
            "bootstrap": boot, "bootstrap_pins": boot_pins,
            "catch_diode": [d for d in g.refs_on(sw, {"diode"}) if g.is_ground(g.other_net(d, sw))], **fb,
            "input": inputs, "input_caps": [c for n in inputs for c in g.caps_to_ground(n)],
            "supply_candidates": candidates,
            "controller_pins_on_output": on_out,
            "enable_pins": [p.key for p in g.comp_pins[ic] if naming.pin_is(p.name, "en")],
            "power_good_pins": [p.key for p in g.comp_pins[ic] if naming.pin_is(p.name, "pg")],
        }
        notes = ["topology assumed buck (caps on the far side of the inductor); boost and inverting parts need a look"]
        if candidates:
            notes.append(f"input unknown: {ic} has no pin names and sits on {len(candidates)} rails")
        if on_out and not fb.get("feedback_top"):
            notes.append(f"controller also has pins on the output ({', '.join(on_out)}): FB, VOS or BIAS by datasheet")
        notes.append("values: " + ", ".join(describe(g, r) for r in [ind] + out_caps))
        found.append(make_block(g, "switching_regulator", f"{ic} via {ind} -> {out}", score, 5, 3, evidence, roles,
                                notes))
    return found
