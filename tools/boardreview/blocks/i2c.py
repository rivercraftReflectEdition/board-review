"""I2C buses: SDA and SCL nets paired, with pull-ups, devices and series parts."""

from __future__ import annotations

import re

from boardreview.blocks.base import Block, describe, is_supply, make_block
from boardreview.model import naming
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph


def _line_role(g: Graph, net: str) -> tuple[str, str]:
    role = naming.i2c_role(net)
    if role:
        return role, f"net name {net}"
    for want in ("sda", "scl"):
        named = [p.key for p in g.net_pins.get(net, []) if naming.pin_is(p.name, want)]
        if named:
            return want, f"{want.upper()}-named pins {', '.join(named)}"
    return "", ""


def _bus_key(net: str) -> str:
    return re.sub(r"SDA|SCL|SMBDAT(?:A)?|SMBCLK", "#", naming.leaf(net).upper())


def _line(g: Graph, net: str) -> dict[str, list[str]]:
    pullups, series = [], []
    for r, far in g.resistors_to(net):
        if is_supply(g, far):
            pullups.append(r)
        elif far is not None and not g.is_ground(far):
            series.append(r)
    return {"pullups": pullups, "pullup_rails": sorted({g.other_net(r, net) for r in pullups}),
            "series": series, "devices": sorted({p.refdes for p in g.net_pins[net]
                                                 if g.kind(p.refdes) in ("ic", "connector", "oscillator")},
                                                key=natural_key)}


def find_i2c_buses(g: Graph) -> list[Block]:
    """SDA/SCL pairs matched by name (I2C1_SDA with I2C1_SCL), else by shared devices; lone lines kept."""
    lines: dict[str, tuple[str, str]] = {}
    for net in g.net_pins:
        role, why = _line_role(g, net)
        if role and not g.is_ground(net) and not is_supply(g, net):
            lines[net] = (role, why)
    sdas = sorted((n for n, (r, _) in lines.items() if r == "sda"), key=natural_key)
    scls = [n for n, (r, _) in lines.items() if r == "scl"]
    pairs: list[tuple[str | None, str | None, str]] = []
    for sda in sdas:
        match = [s for s in scls if _bus_key(s) == _bus_key(sda)]
        how = "names match"
        if not match:
            devs = set(_line(g, sda)["devices"])
            match = [s for s in scls if devs and set(_line(g, s)["devices"]) == devs]
            how = "same devices on both lines"
        scl = match[0] if len(match) == 1 else None
        if scl:
            scls.remove(scl)
        pairs.append((sda, scl, how if scl else "no SCL partner found"))
    pairs += [(None, s, "no SDA partner found") for s in sorted(scls, key=natural_key)]
    found = []
    for sda, scl, how in pairs:
        nets = [n for n in (sda, scl) if n]
        info = {n: _line(g, n) for n in nets}
        evidence = [lines[n][1] for n in nets] + [f"pairing: {how}"]
        pulled = [n for n in nets if info[n]["pullups"]]
        if pulled:
            evidence.append("pull-ups " + "; ".join(f"{n}: {', '.join(info[n]['pullups'])}" for n in pulled))
        score = 1 + (1 if sda and scl else 0) + len(pulled)
        roles = {"sda": [sda] if sda else [], "scl": [scl] if scl else [],
                 "pullups": [r for n in nets for r in info[n]["pullups"]],
                 "pullup_rails": sorted({x for n in nets for x in info[n]["pullup_rails"]}),
                 "series_resistors": [r for n in nets for r in info[n]["series"]],
                 "devices": sorted({d for n in nets for d in info[n]["devices"]}, key=natural_key)}
        notes = [f"no pull-up found on {n}; it may be on another board or inside a device" for n in nets
                 if not info[n]["pullups"]]
        if len(roles["pullup_rails"]) > 1:
            notes.append(f"pull-ups go to different rails: {', '.join(roles['pullup_rails'])}")
        if roles["pullups"]:
            notes.append("values: " + ", ".join(describe(g, r) for r in roles["pullups"]))
        found.append(make_block(g, "i2c_bus", f"I2C {' / '.join(nets)}", score, 4, 2, evidence, roles, notes))
    return found
