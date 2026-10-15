"""BoardModel: components, pins and nets from any netlist source, in one shape."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from boardreview.model import naming, parts

SCHEMA_ID = "boardreview/board_model/1"


@dataclass
class Component:
    refdes: str
    value: str = ""
    mpn: str = ""
    manufacturer: str = ""
    footprint: str = ""
    description: str = ""
    fitted: bool = True
    variant: str = ""
    kind: str = ""
    attrs: dict[str, str] = field(default_factory=dict)

    def classify(self) -> None:
        """Set kind from description, MPN and refdes."""
        self.kind = parts.kind_of(self.refdes, self.description, self.mpn, self.value)

    @property
    def value_si(self) -> float | None:
        return parts.value_si(self.value, self.kind)


@dataclass
class Pin:
    refdes: str
    number: str
    name: str = ""
    type: str = ""
    net: str | None = None
    no_connect: bool = False

    @property
    def key(self) -> str:
        return f"{self.refdes}.{self.number}"


@dataclass
class Net:
    name: str
    pins: list[str]
    net_class: str = ""
    kind: str = "signal"
    auto_named: bool = False
    attrs: dict[str, object] = field(default_factory=dict)


def natural_key(text: str) -> list[object]:
    """Sort key that orders R2 before R10 and U1.A2 before U1.A10."""
    return [int(t) if t.isdigit() else t.upper() for t in re.split(r"(\d+)", text)]


@dataclass
class BoardModel:
    components: dict[str, Component] = field(default_factory=dict)
    pins: dict[tuple[str, str], Pin] = field(default_factory=dict)
    net_info: dict[str, dict[str, object]] = field(default_factory=dict)
    sources: list[dict[str, str]] = field(default_factory=list)
    pin_list_complete: bool = False
    warnings: list[str] = field(default_factory=list)
    _nets: dict[str, Net] | None = field(default=None, repr=False, compare=False)

    def component(self, refdes: str) -> Component:
        """Get or create a component by refdes."""
        comp = self.components.get(refdes)
        if comp is None:
            comp = Component(refdes=refdes, kind=parts.kind_of(refdes))
            self.components[refdes] = comp
        return comp

    def add_pin(self, refdes: str, number: str, net: str | None = None, name: str = "", type: str = "",
                no_connect: bool = False) -> Pin:
        """Add or merge a pin; a conflicting second net is kept out and logged as a warning."""
        self.component(refdes)
        net = None if naming.is_unconnected_name(net) else net.strip()
        key = (refdes, number)
        pin = self.pins.get(key)
        if pin is None:
            pin = Pin(refdes, number, name, type, net, no_connect)
            self.pins[key] = pin
        else:
            if net is not None and pin.net is not None and pin.net != net:
                self.warnings.append(f"{pin.key} seen on {pin.net} and {net}; kept {pin.net}")
            pin.net = pin.net if pin.net is not None else net
            pin.name = pin.name or name
            pin.type = pin.type or type
            pin.no_connect = pin.no_connect or no_connect
        self._nets = None
        return pin

    def set_net_info(self, net: str, **info: object) -> None:
        """Attach class or other attributes to a net name."""
        self.net_info.setdefault(net, {}).update({k: v for k, v in info.items() if v not in (None, "")})
        self._nets = None

    def invalidate(self) -> None:
        """Drop cached nets after pins were edited in place."""
        self._nets = None

    @property
    def nets(self) -> dict[str, Net]:
        if self._nets is None:
            self._nets = self._build_nets()
        return self._nets

    def _build_nets(self) -> dict[str, Net]:
        grouped: dict[str, list[str]] = {}
        for pin in self.pins.values():
            if pin.net is not None:
                grouped.setdefault(pin.net, []).append(pin.key)
        nets = {}
        for name in sorted(grouped, key=natural_key):
            info = dict(self.net_info.get(name, {}))
            nets[name] = Net(
                name=name,
                pins=sorted(grouped[name], key=natural_key),
                net_class=str(info.pop("class", "")),
                kind=naming.net_kind(name),
                auto_named=naming.is_auto_named(name),
                attrs=info,
            )
        return nets

    def pins_of(self, refdes: str) -> list[Pin]:
        """Pins of one component in natural order."""
        return sorted((p for p in self.pins.values() if p.refdes == refdes), key=lambda p: natural_key(p.number))

    def pin(self, key: str) -> Pin:
        """Pin by 'REF.PIN' key."""
        ref, _, num = key.partition(".")
        return self.pins[(ref, num)]

    def net_components(self, net: str) -> list[str]:
        """Distinct refdes on a net, natural order."""
        seen = {k.partition(".")[0] for k in self.nets[net].pins} if net in self.nets else set()
        return sorted(seen, key=natural_key)

    def unconnected_pins(self) -> list[Pin]:
        """Pins with no net."""
        return sorted((p for p in self.pins.values() if p.net is None), key=lambda p: natural_key(p.key))

    def finalize(self) -> "BoardModel":
        """Classify components and fold tool-named single-pin nets into unconnected pins."""
        for comp in self.components.values():
            if not comp.kind or comp.kind == "other":
                comp.classify()
        folded = 0
        for net in list(self.nets.values()):
            if net.auto_named and len(net.pins) == 1:
                self.pin(net.pins[0]).net = None
                folded += 1
        if folded:
            self.warnings.append(f"{folded} tool-named single-pin nets treated as unconnected pins")
        self._nets = None
        return self
