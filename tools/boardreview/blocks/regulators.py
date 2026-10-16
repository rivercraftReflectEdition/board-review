"""Switching regulators: an IC pin and an inductor on a switch node, output caps, bootstrap and feedback."""

from __future__ import annotations

import re

from boardreview.blocks.base import Block, describe, dnp_note, fitted_split, is_supply, make_block
from boardreview.model import naming
from boardreview.model.board import Pin, natural_key
from boardreview.model.graph import Graph


def _ic_pins(g: Graph, net: str) -> list[Pin]:
    return [p for p in g.net_pins.get(net, []) if g.kind(p.refdes) == "ic"]


def _fitted_caps_to_ground(g: Graph, net: str) -> list[str]:
    return [c for c in g.caps_to_ground(net) if g.fitted(c)]


def _private_boot(g: Graph, sw: str, ic: str) -> bool:
    """True when a cap joins the node to a net holding only it and one controller pin, directly or via one resistor."""
    for cap in g.refs_on(sw, {"capacitor"}):
        node = g.other_net(cap, sw)
        if node is None or g.is_ground(node) or is_supply(g, node):
            continue
        if len(g.pins_on(node, ic)) == 1 and set(g.refs_on(node)) == {cap, ic}:
            return True
        for res, far in g.resistors_to(node):
            if set(g.refs_on(node)) == {cap, res} and far and len(g.pins_on(far, ic)) == 1 \
                    and set(g.refs_on(far)) == {res, ic}:
                return True
    return False


def _converter_structure(g: Graph, sw: str, pins: list[Pin]) -> bool:
    """True when a node that is not a rail has a private bootstrap cap to a controller pin."""
    return not is_supply(g, sw) and any(_private_boot(g, sw, ic) for ic in {p.refdes for p in pins})


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
        caps_on_sw = bool(_fitted_caps_to_ground(g, sw))
        if named or (not caps_on_sw and g.caps_to_ground(out)):
            options.append((0 if named else 1, sw, out, pins, named))
        elif g.caps_to_ground(out) and _converter_structure(g, sw, pins):
            options.append((2, sw, out, pins, named))
    if not options:
        return None
    _, sw, out, pins, named = min(options, key=lambda o: o[0])
    return sw, out, pins, named


def _bootstrap_chains(g: Graph, sw: str, ic: str) -> list[tuple[list[str], list[str]]]:
    """Caps from the switch node to a net that reaches the controller, directly or through one resistor."""
    chains = []
    for cap in g.refs_on(sw, {"capacitor"}):
        other = g.other_net(cap, sw)
        if other is None or g.is_ground(other):
            continue
        direct = [p.key for p in g.pins_on(other, ic)]
        if direct:
            chains.append(([cap], direct))
            continue
        for res, far in g.resistors_to(other):
            pins = [p.key for p in g.pins_on(far, ic)] if far else []
            if pins:
                chains.append(([cap, res], pins))
    return chains


def _bootstrap(g: Graph, sw: str, ic: str) -> tuple[list[str], list[str], list[str]]:
    """(fitted bootstrap parts, controller pins, DNP bootstrap parts); a chain with a DNP part is not fitted."""
    chains = _bootstrap_chains(g, sw, ic)
    good = [c for c in chains if all(g.fitted(r) for r in c[0])]
    dnp = sorted({r for parts, _pins in chains for r in parts if not g.fitted(r)}, key=natural_key)
    parts, pins = good[0] if good else ([], [])
    return parts, pins, dnp


def _feedback(g: Graph, out: str, ic: str) -> dict[str, list[str]]:
    """Resistor divider from the output to a node on the controller, with the bottom leg to ground."""
    for top, mid in sorted(g.resistors_to(out), key=lambda t: not g.fitted(t[0])):
        if mid is None or mid == out or g.is_ground(mid) or is_supply(g, mid):
            continue
        fb_pins = [p.key for p in g.pins_on(mid, ic)]
        bottom = [r for r, far in g.resistors_to(mid) if r != top and g.is_ground(far)]
        if fb_pins and bottom:
            tops = [r for r, far in g.resistors_to(out) if far == mid]
            cff = [c for c in g.refs_on(mid, {"capacitor"}) if g.other_net(c, mid) == out]
            fit_top, dnp_top = fitted_split(g, tops)
            fit_bottom, dnp_bottom = fitted_split(g, bottom)
            fit_cff, dnp_cff = fitted_split(g, cff)
            zero = bool(fit_top) and not fit_bottom and all(g.model.components[r].value_si == 0 for r in fit_top)
            return {("feedback_direct" if zero else "feedback_top"): fit_top, "feedback_bottom": fit_bottom,
                    "feedback_node": [mid], "fb_pins": fb_pins, "feedforward_cap": fit_cff,
                    "feedback_top_dnp": dnp_top, "feedback_bottom_dnp": dnp_bottom, "feedforward_cap_dnp": dnp_cff}
    direct = [p.key for p in g.pins_on(out, ic) if naming.pin_is(p.name, "fb")]
    return {"fb_pins": direct} if direct else {}


_FIXED_MPN = re.compile(r"[-_](\d{1,2}\.\d{1,2})(?![\d.])|[-_](\d{1,2})V(\d{0,2})(?!\d)", re.I)


def fixed_from_mpn(mpn: str) -> float | None:
    """Output voltage a fixed-output MPN spells out (LM3671MF-3.3/NOPB, AP2112K-1.8TRG1, LDO-3V3), else None."""
    m = _FIXED_MPN.search(mpn or "")
    if not m:
        return None
    v = float(m.group(1)) if m.group(1) else float(f"{m.group(2)}.{m.group(3) or '0'}")
    return v if 0.5 <= v <= 60 else None


def _direct_note(g: Graph, ic: str, fb: dict[str, list[str]], roles: dict[str, list[str]]) -> str:
    """Note for FB on the output with no divider: expected when the MPN says fixed, otherwise UNSURE."""
    via = fb.get("feedback_direct", [])
    path = f" through {', '.join(describe(g, r) for r in via)}" if via else ""
    pins = ", ".join(fb.get("fb_pins", []))
    mpn = g.model.components[ic].mpn
    volts = fixed_from_mpn(mpn)
    if volts is not None:
        roles["fixed_output"] = [f"{volts:g} V from MPN {mpn}"]
        return f"MPN {mpn} reads as a fixed {volts:g} V part, so FB {pins} on the output{path} is expected"
    return (f"FB {pins} senses the output directly{path}: a fixed-output part needs no divider, an adjustable one "
            "does; UNSURE until the MPN or the datasheet digest says the output is fixed")


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
        out_caps, out_caps_dnp = fitted_split(g, g.caps_to_ground(out))
        if out_caps:
            score += 1
            evidence.append(f"{len(out_caps)} caps from {out} to ground")
        sw_caps, sw_caps_dnp = fitted_split(g, g.caps_to_ground(sw))
        if not sw_caps:
            score += 1
            evidence.append(f"no caps to ground on {sw}, as a switch node should be")
        boot, boot_pins, boot_dnp = _bootstrap(g, sw, ic)
        if boot:
            score += 2
            evidence.append(f"bootstrap {' + '.join(boot)} from {sw} to {', '.join(boot_pins)}")
        fb = _feedback(g, out, ic)
        divider = bool(fb.get("feedback_top") and fb.get("feedback_bottom"))
        if divider:
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
        catch, catch_dnp = fitted_split(g, [d for d in g.refs_on(sw, {"diode"}) if g.is_ground(g.other_net(d, sw))])
        in_caps, in_caps_dnp = fitted_split(g, [c for n in inputs for c in g.caps_to_ground(n)])
        roles = {
            "controller": [ic], "inductor": [ind], "switch_node": [sw], "output": [out], "output_caps": out_caps,
            "bootstrap": boot, "bootstrap_pins": boot_pins, "catch_diode": catch, **fb,
            "input": inputs, "input_caps": in_caps,
            "supply_candidates": candidates,
            "controller_pins_on_output": on_out,
            "enable_pins": [p.key for p in g.comp_pins[ic] if naming.pin_is(p.name, "en")],
            "power_good_pins": [p.key for p in g.comp_pins[ic] if naming.pin_is(p.name, "pg")],
            "switch_node_caps": sw_caps,
            "output_caps_dnp": out_caps_dnp, "bootstrap_dnp": boot_dnp, "catch_diode_dnp": catch_dnp,
            "input_caps_dnp": in_caps_dnp, "switch_node_caps_dnp": sw_caps_dnp,
        }
        notes = ["topology assumed buck (caps on the far side of the inductor); boost and inverting parts need a look"]
        if sw_caps:
            notes.append(f"caps to ground on the switch node {sw}: {', '.join(describe(g, c) for c in sw_caps)}; "
                         "a switch node should carry none, so check for a snubber, a misplaced part or a wrong "
                         "orientation")
        for ref in (ind, ic):
            if not g.fitted(ref):
                notes.append(f"{ref} is DNP: this converter is not in the build")
        if boot_dnp and not boot:
            notes.append(f"bootstrap {', '.join(boot_dnp)} is DNP: no fitted bootstrap path from {sw} to {ic}")
        direct = bool(fb.get("feedback_direct")) or bool(fb.get("fb_pins") and not fb.get("feedback_node"))
        if direct:
            notes.append(_direct_note(g, ic, fb, roles))
        elif fb.get("feedback_node") and not divider:
            notes.append(f"feedback divider on {fb['feedback_node'][0]} has no fitted top or bottom leg: "
                         + ", ".join(fb.get("feedback_top_dnp", []) + fb.get("feedback_bottom_dnp", [])) + " DNP")
        if candidates:
            notes.append(f"input unknown: {ic} has no pin names and sits on {len(candidates)} rails")
        if on_out and not divider:
            notes.append(f"controller also has pins on the output ({', '.join(on_out)}): FB, VOS or BIAS by datasheet")
        notes.append("values: " + ", ".join(describe(g, r) for r in [ind] + out_caps))
        notes += dnp_note(g, out_caps_dnp + boot_dnp + catch_dnp + in_caps_dnp + fb.get("feedback_top_dnp", [])
                          + fb.get("feedback_bottom_dnp", []) + fb.get("feedforward_cap_dnp", []))
        found.append(make_block(g, "switching_regulator", f"{ic} via {ind} -> {out}", score, 5, 3, evidence, roles,
                                notes))
    return found
