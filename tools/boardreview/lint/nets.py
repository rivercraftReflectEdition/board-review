"""Net checks: single-pin nets, near-duplicate rail names, DNP parts that are a net's only link."""

from __future__ import annotations

from boardreview.lint.base import Finding
from boardreview.model import naming
from boardreview.model.board import BoardModel, natural_key
from boardreview.model.graph import Graph


def single_pin_nets(model: BoardModel, g: Graph) -> list[Finding]:
    """Nets a person named that reach only one pin: usually a label typo or a missing wire."""
    out, flagged = [], []
    for net in model.nets.values():
        if len(net.pins) != 1 or net.auto_named:
            continue
        if model.pin(net.pins[0]).no_connect:
            flagged.append(net)
            continue
        out.append(Finding("single_pin_net", "warning",
                           f"net {net.name} reaches only {net.pins[0]}; check for a misspelled label or a missing wire",
                           components=[net.pins[0].partition(".")[0]], nets=[net.name], pins=list(net.pins)))
    if flagged:
        pins = sorted((n.pins[0] for n in flagged), key=natural_key)
        out.append(Finding("single_pin_net", "info",
                           f"{len(flagged)} labeled pins also carry a no-connect flag, so each label reaches only its "
                           f"own pin: {', '.join(pins)}; the flag says the pin is unused on purpose",
                           components=sorted({p.partition('.')[0] for p in pins}, key=natural_key),
                           nets=sorted((n.name for n in flagged), key=natural_key), pins=pins))
    return out


def _rail_like(g: Graph, name: str) -> bool:
    if naming.is_rail_name(name):
        return True
    return naming.voltage_of(name) is not None and bool(g.rail_evidence(name))


def near_duplicate_rails(model: BoardModel, g: Graph) -> list[Finding]:
    """Rail names that differ only in spelling (3V3, +3V3, 3.3V) or case, so they are separate nets."""
    out = []
    names = list(model.nets)
    rails = [n for n in names if _rail_like(g, n)]
    for level, index, severity in (("spelling", 0, "warning"), ("loose", 1, "info")):
        groups: dict[str, list[str]] = {}
        for n in rails:
            groups.setdefault(naming.rail_keys(n)[index], []).append(n)
        for key, group in groups.items():
            if len(group) < 2:
                continue
            if level == "loose" and len({naming.rail_keys(n)[0] for n in group}) < 2:
                continue
            group = sorted(group, key=natural_key)
            sizes = {n: len(model.nets[n].pins) for n in group}
            what = "spell the same rail differently" if level == "spelling" else "may be the same rail"
            out.append(Finding("near_duplicate_rails", severity,
                               f"nets {', '.join(group)} {what} and are not connected to each other (pins: "
                               + ", ".join(f"{n}={sizes[n]}" for n in group) + ")",
                               nets=group, evidence={"key": key, "pin_counts": sizes}))
    by_case: dict[str, list[str]] = {}
    for n in names:
        by_case.setdefault(n.upper(), []).append(n)
    for group in by_case.values():
        if len(group) > 1:
            out.append(Finding("near_duplicate_rails", "warning",
                               f"nets {', '.join(sorted(group))} differ only in case", nets=sorted(group)))
    return out


def dnp_only_link(model: BoardModel, g: Graph) -> list[Finding]:
    """Nets where removing DNP parts leaves one fitted pin alone (or none)."""
    out = []
    for net in model.nets.values():
        pins = [model.pin(k) for k in net.pins]
        dnp = [p.key for p in pins if not g.fitted(p.refdes)]
        if not dnp:
            continue
        fitted = [p.key for p in pins if g.fitted(p.refdes)]
        if len(fitted) == 1:
            out.append(Finding("dnp_only_link", "warning",
                               f"with {', '.join(sorted({k.partition('.')[0] for k in dnp}, key=natural_key))} not fitted, "
                               f"{fitted[0]} is alone on {net.name}; confirm the pin may float or is driven elsewhere",
                               components=sorted({k.partition(".")[0] for k in dnp + fitted}, key=natural_key),
                               nets=[net.name], pins=fitted + dnp, evidence={"dnp_pins": dnp, "fitted_pins": fitted}))
        elif not fitted:
            out.append(Finding("dnp_only_link", "info", f"net {net.name} has only DNP parts: {', '.join(dnp)}",
                               nets=[net.name], pins=dnp))
    return out
