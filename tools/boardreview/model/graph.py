"""Structural queries over a BoardModel: two-pin neighbours, caps to ground, rails by evidence."""

from __future__ import annotations

from dataclasses import dataclass, field

from boardreview.model import naming
from boardreview.model.board import BoardModel, Pin, natural_key

PASSIVE_KINDS = {"resistor", "capacitor", "inductor", "ferrite", "fuse", "jumper"}
ACTIVE_KINDS = {"ic", "oscillator", "transistor"}
SIGNAL_PIN_ROLES = {"sda", "scl", "reset", "xtal", "sw", "boot", "pg"}


@dataclass
class Graph:
    model: BoardModel
    comp_pins: dict[str, list[Pin]] = field(default_factory=dict)
    net_pins: dict[str, list[Pin]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for pin in self.model.pins.values():
            self.comp_pins.setdefault(pin.refdes, []).append(pin)
            if pin.net is not None:
                self.net_pins.setdefault(pin.net, []).append(pin)
        for pins in self.comp_pins.values():
            pins.sort(key=lambda p: natural_key(p.number))

    def kind(self, refdes: str) -> str:
        comp = self.model.components.get(refdes)
        return comp.kind if comp else "other"

    def fitted(self, refdes: str) -> bool:
        comp = self.model.components.get(refdes)
        return comp.fitted if comp else True

    def nets_of(self, refdes: str) -> list[str | None]:
        """Net per pin of a component, in pin order."""
        return [p.net for p in self.comp_pins.get(refdes, [])]

    def is_two_pin(self, refdes: str) -> bool:
        return len(self.comp_pins.get(refdes, [])) == 2

    def other_net(self, refdes: str, net: str) -> str | None:
        """Net on the far side of a two-pin part from the given net."""
        nets = self.nets_of(refdes)
        if len(nets) != 2 or net not in nets:
            return None
        return nets[1] if nets[0] == net else nets[0]

    def refs_on(self, net: str, kinds: set[str] | None = None) -> list[str]:
        """Distinct refdes on a net, optionally filtered by kind."""
        seen = []
        for p in self.net_pins.get(net, []):
            if p.refdes not in seen and (kinds is None or self.kind(p.refdes) in kinds):
                seen.append(p.refdes)
        return sorted(seen, key=natural_key)

    def pins_on(self, net: str, refdes: str | None = None) -> list[Pin]:
        return [p for p in self.net_pins.get(net, []) if refdes is None or p.refdes == refdes]

    def is_ground(self, net: str | None) -> bool:
        return net is not None and naming.net_kind(net) == "ground"

    def caps_to_ground(self, net: str) -> list[str]:
        """Two-pin capacitors with one pin on the net and the other on a ground net."""
        return [r for r in self.refs_on(net, {"capacitor"}) if self.is_ground(self.other_net(r, net))]

    def resistors_to(self, net: str) -> list[tuple[str, str | None]]:
        """Two-pin resistors on the net with the net on their far side."""
        return [(r, self.other_net(r, net)) for r in self.refs_on(net, {"resistor"}) if self.is_two_pin(r)]

    def active_pins(self, net: str) -> list[Pin]:
        """Pins of ICs, oscillators and transistors on the net."""
        return [p for p in self.net_pins.get(net, []) if self.kind(p.refdes) in ACTIVE_KINDS]

    def rail_evidence(self, net: str) -> list[str]:
        """Why a net looks like a supply rail: its name, decoupling caps, or power-named pins."""
        if naming.net_kind(net) in ("ground", "chassis"):
            return []
        ev = []
        if naming.is_rail_name(net):
            ev.append("name")
        caps = self.caps_to_ground(net)
        pins = self.net_pins.get(net, [])
        power_pins = [p for p in pins if naming.pin_is_supply(p.name) or p.type == "power_in"]
        signal_pins = [p for p in pins if naming.pin_role(p.name) in SIGNAL_PIN_ROLES]
        if len(caps) >= 3 and not naming.is_reset_name(net) and not naming.i2c_role(net) and not signal_pins:
            ev.append(f"{len(caps)} caps to ground")
        if power_pins and caps:
            ev.append(f"{len(power_pins)} power-named pins")
        return ev

    def rails(self) -> dict[str, list[str]]:
        """Nets that look like rails, with the evidence for each."""
        out = {}
        for net in self.model.nets:
            ev = self.rail_evidence(net)
            if ev:
                out[net] = ev
        return out
