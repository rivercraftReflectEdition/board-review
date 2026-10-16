"""RF candidates from port names, component kinds and passive topology."""

from __future__ import annotations

import re
from itertools import combinations

from boardreview.blocks.base import Block, describe, dnp_note, fitted_split, make_block
from boardreview.model import naming
from boardreview.model.board import Pin, natural_key
from boardreview.model.graph import Graph

_RF_PORT = re.compile(r"^(?:RF(?:IN|OUT|COM|C)?|ANT(?:ENNA)?|RX|TX)\d*[PN+-]?$")
_CONTROL = re.compile(r"^(?:(?:V?C(?:TRL|TL)?|CTRL|CTL|SEL|EN|ENABLE|SHDN|PD|LE|CLK|DATA|SDI|SCLK|CS|A|B)\d*|V\d+)$")
_SWITCH = re.compile(r"\b(?:rf\s+switch|sp[1-9]t|dp[1-9]t|soi\s+switch|antenna\s+switch)\b", re.I)
_AMP = re.compile(r"\b(?:lna|pa|mmic|rf\s+amplifier|low[ -]noise\s+amplifier|power\s+amplifier)\b", re.I)
_CONNECTOR = re.compile(r"\b(?:[rp-]*sma|smb|smc|u[.]?fl|i[ -]?pex|mmcx|mcx|coax(?:ial)?|antenna)\b", re.I)


def _core(p: Pin) -> str:
    return re.sub(r"[\s_/]", "", naming.pin_core(p.name))


def _text(g: Graph, ref: str) -> str:
    c = g.model.components[ref]
    return " ".join((c.kind, c.description, c.value, c.footprint)).replace("_", " ").replace(":", " ")


def _ground(g: Graph, net: str | None) -> bool:
    return net is not None and naming.net_kind(net) in ("ground", "chassis")


def _supply(g: Graph, net: str) -> bool:
    if _ground(g, net):
        return False
    return naming.is_rail_name(net) or any(naming.pin_is_supply(p.name) or p.type == "power_in"
                                           for p in g.pins_on(net) if not _RF_PORT.fullmatch(_core(p)))


def _signal(g: Graph, p: Pin) -> bool:
    return p.net is not None and not p.no_connect and not _ground(g, p.net) \
        and (_RF_PORT.fullmatch(_core(p)) is not None or not _supply(g, p.net)) \
        and not naming.pin_is(p.name, "nc") and _core(p) != "DONOTCONNECT"


def _nets(pins: list[Pin]) -> list[str]:
    return sorted({p.net for p in pins if p.net is not None}, key=natural_key)


def _notes(g: Graph, refs: list[str]) -> list[str]:
    return ["Candidate only; confirm port roles, band and bias in the datasheet."] \
        + dnp_note(g, [r for r in refs if not g.fitted(r)])


def _nearby(g: Graph, ports: list[str], supply: list[str]) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {}
    candidates = {
        "dc_blocks": [r for n in ports for r in g.refs_on(n, {"capacitor"})
                      if g.is_two_pin(r) and (far := g.other_net(r, n)) is not None
                      and not _ground(g, far) and not _supply(g, far)],
        "shunt_resistors": [r for n in ports for r, far in g.resistors_to(n) if _ground(g, far)],
        "shunt_caps": [r for n in ports for r in g.caps_to_ground(n)],
        "bias_chokes": [r for n in ports for r in g.refs_on(n, {"inductor", "ferrite"})
                        if g.is_two_pin(r) and (far := g.other_net(r, n)) is not None and _supply(g, far)],
        "bypass_caps": [r for n in supply for r in g.caps_to_ground(n)],
    }
    for role, refs in candidates.items():
        fitted, dnp = fitted_split(g, sorted(set(refs), key=natural_key))
        roles[role], roles[role + "_dnp"] = fitted, dnp
    return roles


def find_baluns(g: Graph) -> list[Block]:
    """Baluns by balanced and unbalanced pin roles, or transformer topology."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        c = g.model.components[ref]
        pins = [p for p in g.comp_pins.get(ref, []) if _signal(g, p)]
        named = c.kind == "balun" or bool(re.search(r"\bbalun\b", _text(g, ref), re.I))
        unbal = [p for p in pins if _core(p) in ("UNBAL", "UNBALANCED", "UB", "SE", "RF", "RFIN")]
        balanced = [p for p in pins if re.fullmatch(r"(?:BAL(?:ANCED)?|DIFF)(?:[12PN+-])", _core(p))
                    or _core(p) in ("OUT+", "OUT-", "RF+", "RF-")]
        tap = [p for p in g.comp_pins.get(ref, []) if _core(p) in ("CT", "CENTERTAP", "DCFEED", "BIAS")]
        signal = _nets([p for p in pins if p not in tap])
        by_roles = len(_nets(unbal)) == 1 and len(_nets(balanced)) == 2
        topology = c.kind == "transformer" and len(signal) == 3
        if not (named or by_roles or topology):
            continue
        evidence = [f"{ref} kind {c.kind}"]
        if named:
            evidence.append("part text identifies a balun")
        if by_roles:
            evidence.append("one unbalanced net and two balanced nets from pin names")
        elif topology:
            evidence.append("transformer has three signal nets; winding connections need confirmation")
        roles = {"device": [ref], "signal_nets": signal, "unbalanced": _nets(unbal),
                 "balanced": _nets(balanced), "dc_feed_pins": [p.key for p in tap], "dc_feed": _nets(tap)}
        roles.update(_nearby(g, signal, _nets(tap)))
        found.append(make_block(g, "balun", f"{ref} balun", 2 * named + 3 * by_roles + topology, 5, 2,
                                evidence, roles, _notes(g, [ref])
                                + ["DC continuity, impedance ratio and band require the datasheet."]))
    return found


def find_rf_switches(g: Graph) -> list[Block]:
    """RF switches with multiple RF ports and control pins or an explicit part kind."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        c = g.model.components[ref]
        if c.kind not in ("ic", "switch", "rf_switch", "other"):
            continue
        pins = [p for p in g.comp_pins.get(ref, []) if _signal(g, p)]
        ports = [p for p in pins if _RF_PORT.fullmatch(_core(p))]
        controls = [p for p in pins if _CONTROL.fullmatch(_core(p))]
        named = c.kind == "rf_switch" or bool(_SWITCH.search(_text(g, ref)))
        if not (named or len(_nets(ports)) >= 3 and controls):
            continue
        if named and not ports:
            ports = [p for p in pins if p not in controls and _core(p) not in ("VSS", "VEE", "VNEG")]
        supply = _nets([p for p in g.comp_pins.get(ref, []) if p.net and not _ground(g, p.net)
                        and (naming.pin_is_supply(p.name) or p.type == "power_in" or _supply(g, p.net))
                        and p not in ports and p not in controls])
        roles = {"device": [ref], "rf_ports": _nets(ports), "rf_pins": [p.key for p in ports],
                 "control_nets": _nets(controls), "control_pins": [p.key for p in controls], "supply": supply}
        roles.update(_nearby(g, _nets(ports), supply))
        evidence = [f"{ref} has {len(_nets(ports))} RF port nets and {len(controls)} control pins"]
        if named:
            evidence.append("part kind or text identifies an RF switch")
        found.append(make_block(g, "rf_switch", f"{ref} RF switch", 2 * named + bool(controls)
                                + 2 * (len(_nets(ports)) >= 3), 5, 3, evidence, roles, _notes(g, [ref])
                                + ["Check control domains, isolation and DC discharge paths in RF-8."]))
    return found


def find_rf_amplifiers(g: Graph) -> list[Block]:
    """RF amplifiers by input and output roles, supported by part text or RF pin names."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        c = g.model.components[ref]
        if c.kind not in ("ic", "transistor", "rf_amplifier", "amplifier", "other"):
            continue
        pins = [p for p in g.comp_pins.get(ref, []) if _signal(g, p)]
        inp = [p for p in pins if re.fullmatch(r"(?:RF)?IN(?:PUT)?[PN+-]?", _core(p))]
        out = [p for p in pins if re.fullmatch(r"(?:RF)?OUT(?:PUT)?[PN+-]?", _core(p))]
        named = c.kind == "rf_amplifier" or bool(_AMP.search(_text(g, ref)))
        if named and c.kind == "transistor":
            inp += [p for p in pins if _core(p) in ("G", "GATE", "B", "BASE")]
            out += [p for p in pins if _core(p) in ("D", "DRAIN", "C", "COLLECTOR")]
        rf_names = any(_core(p).startswith("RF") for p in inp) and any(_core(p).startswith("RF") for p in out)
        if not (named or rf_names):
            continue
        # Mixers and transceivers also have RF input and output pins.
        if not named and (len(_nets(inp)) != 1 or len(_nets(out)) != 1
                          or any(_CONTROL.fullmatch(_core(p)) or _core(p).startswith("LO") for p in pins)):
            continue
        supply = _nets([p for p in g.comp_pins.get(ref, []) if p.net and not _ground(g, p.net)
                        and p not in inp + out and (naming.pin_is_supply(p.name) or _supply(g, p.net))])
        roles = {"device": [ref], "input": _nets(inp), "output": _nets(out), "supply": supply,
                 "input_pins": [p.key for p in inp], "output_pins": [p.key for p in out],
                 "control_pins": [p.key for p in pins if _CONTROL.fullmatch(_core(p)) and p not in inp + out]}
        roles.update(_nearby(g, _nets(inp + out), supply))
        evidence = [f"{ref} input pins {', '.join(p.key for p in inp) or 'unknown'}; "
                    f"output pins {', '.join(p.key for p in out) or 'unknown'}"]
        if named:
            evidence.append("part kind or text identifies an RF amplifier")
        if rf_names:
            evidence.append("RF input and output pin names")
        found.append(make_block(g, "rf_amplifier", f"{ref} RF amplifier", 2 * named + 2 * rf_names
                                + bool(inp and out) + bool(supply), 5, 3, evidence, roles, _notes(g, [ref])
                                + ["Stability requires S-parameters at the fitted bias, including frequencies below the band."]))
    return found


def _rf_net(g: Graph, net: str) -> bool:
    return bool(re.search(r"(?:^|[/_])(?:RF|ANT|RX|TX)(?:[_/0-9]|$)", net, re.I)
                or re.search(r"rf|antenna", g.model.nets[net].net_class, re.I)
                or any(_RF_PORT.fullmatch(_core(p)) for p in g.pins_on(net)))


def find_attenuator_pads(g: Graph) -> list[Block]:
    """Three-resistor pi and T candidates, excluding supply and zero-ohm links."""
    resistors = {}
    for ref in sorted(g.model.components, key=natural_key):
        c = g.model.components[ref]
        nets = g.nets_of(ref)
        if c.kind == "resistor" and len(nets) == 2 and all(nets) and nets[0] != nets[1] \
                and (c.value_si is None or c.value_si > 0) and not any(_supply(g, n) for n in nets):
            resistors[ref] = nets
    shunts: dict[str, list[str]] = {}
    series = []
    for ref, nets in resistors.items():
        ground = [n for n in nets if _ground(g, n)]
        if len(ground) == 1:
            shunts.setdefault(next(n for n in nets if n not in ground), []).append(ref)
        elif not ground:
            series.append(ref)
    found, seen = [], set()

    def add(topology: str, arms: list[str], shunt: list[str], ports: list[str], middle: list[str]):
        refs = sorted(arms + shunt, key=natural_key)
        key = tuple(refs)
        if key in seen:
            return
        seen.add(key)
        known = all(g.model.components[r].value_si is not None for r in refs)
        anchored = any(_rf_net(g, n) for n in ports)
        roles = {"series_resistors": arms, "shunt_resistors": shunt, "ports": ports, "middle": middle,
                 "ground": sorted({n for r in shunt for n in resistors[r] if _ground(g, n)}, key=natural_key)}
        evidence = [f"three-resistor {topology} topology: {', '.join(describe(g, r) for r in refs)}"]
        if anchored:
            evidence.append("RF net class, net name or port pin on the pad")
        notes = _notes(g, refs) + [f"Topology {topology}; direction and attenuation require review.",
                                 "Compare fitted values and per-resistor dissipation with RF-12."]
        found.append(make_block(g, "attenuator_pad", f"{'/'.join(refs)} {topology} pad",
                                1 + known + 2 * anchored, 4, 2, evidence, roles, notes))

    for ref in series:
        a, b = sorted(resistors[ref], key=natural_key)
        for ra in shunts.get(a, []):
            for rb in shunts.get(b, []):
                add("pi", [ref], [ra, rb], [a, b], [])
    arms_at: dict[str, list[str]] = {}
    for ref in series:
        for net in resistors[ref]:
            arms_at.setdefault(net, []).append(ref)
    for center, arms in sorted(arms_at.items(), key=lambda item: natural_key(item[0])):
        if len(arms) != 2 or len(g.pins_on(center)) != 3:
            continue
        for ra, rb in combinations(arms, 2):
            ports = [g.other_net(r, center) for r in (ra, rb)]
            if ports[0] == ports[1]:
                continue
            for shunt in shunts.get(center, []):
                add("T", [ra, rb], [shunt], ports, [center])
    return found


def find_rf_connectors(g: Graph) -> list[Block]:
    """Coax connectors and antenna feeds; unnamed coax topology stays low confidence."""
    found = []
    for ref in sorted(g.model.components, key=natural_key):
        c = g.model.components[ref]
        named = bool(_CONNECTOR.search(_text(g, ref))) or c.kind in ("rf_connector", "antenna", "antenna_feed")
        if c.kind not in ("connector", "rf_connector", "antenna", "antenna_feed") and not (
                named and c.kind in ("other", "testpoint")):
            continue
        pins = g.comp_pins.get(ref, [])
        signal = [p for p in pins if _signal(g, p)]
        ground = [p for p in pins if _ground(g, p.net)]
        coax_topology = len(signal) == 1 and len(ground) >= 2 and len(signal) + len(ground) == len(pins)
        rf_role = len(signal) == 1 and ground and _rf_net(g, signal[0].net)
        if not signal or not named and not (coax_topology or rf_role):
            continue
        roles = {"connector": [ref], "rf_ports": _nets(signal), "signal_pins": [p.key for p in signal],
                 "shield": _nets(ground), "shield_pins": [p.key for p in ground]}
        roles.update(_nearby(g, _nets(signal), []))
        evidence = [f"{ref} has {len(signal)} signal pins and {len(ground)} ground or shield pins"]
        if named:
            evidence.append("part kind or text identifies a coax connector or antenna feed")
        notes = _notes(g, [ref])
        if not named:
            notes.append("An unnamed signal-plus-ground header has the same topology; confirm this is an RF port.")
        if not ground:
            notes.append("No connected shield pin found; confirm the antenna return path.")
        found.append(make_block(g, "rf_connector", f"{ref} RF port", 3 * named + bool(ground), 4, 3,
                                evidence, roles, notes))
    return found


def find_rf(g: Graph) -> list[Block]:
    """Run all RF finders without assigning a candidate a pass verdict."""
    return find_baluns(g) + find_rf_switches(g) + find_rf_amplifiers(g) \
        + find_attenuator_pads(g) + find_rf_connectors(g)
