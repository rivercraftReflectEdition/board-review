"""Pin checks: IC pins with no net, ground pins off ground, protection devices with floating ground."""

from __future__ import annotations

from boardreview.lint.base import NEEDS, Finding, Skip, needs_datasheet
from boardreview.model import naming
from boardreview.model.board import BoardModel, Pin, natural_key
from boardreview.model.graph import Graph

IC_KINDS = {"ic", "oscillator"}


def _typed_power(p: Pin) -> bool:
    return p.type in ("power_in", "power_out")


def _is_power_pin(p: Pin) -> bool:
    """Supply or ground by type or name; a pin named NC or reserved is an option pin even when typed power."""
    if naming.pin_is(p.name, "nc"):
        return False
    return _typed_power(p) or naming.pin_is(p.name, "ground") or naming.pin_is_supply(p.name)


def _nc_by_name(p: Pin) -> bool:
    return p.type == "no_connect" or naming.pin_is(p.name, "nc")


def _marked_open(p: Pin) -> bool:
    return p.no_connect or _nc_by_name(p)


def _label(p: Pin) -> str:
    return p.number + (f" ({p.name})" if p.name else "")


def _keys(pins: list[Pin]) -> str:
    return ", ".join(p.key for p in pins)


def _marked_open_finding(ref: str, comp_mpn: str, marked: list[Pin]) -> Finding:
    by_name = [p for p in marked if _nc_by_name(p)]
    flag_only = [p for p in marked if not _nc_by_name(p)]
    why = [f"named NC or reserved: {_keys(by_name)}"] if by_name else []
    why += [f"no-connect flag only, so the symbol does not say NC: {_keys(flag_only)}"] if flag_only else []
    typed = [p for p in by_name if _typed_power(p)]
    why += [f"typed power in the symbol but named NC: {_keys(typed)}; the datasheet says whether it is a supply"
            ] if typed else []
    pg = [p for p in marked if naming.pin_is(p.name, "pg")]
    why += [f"unused power-good output: {_keys(pg)}"] if pg else []
    return Finding("unconnected_ic_pin", "warning" if by_name else "info",
                   f"{ref} has {len(marked)} open pins marked NC, reserved or no-connect: "
                   f"{', '.join(_label(p) for p in marked)}; {NEEDS}: each may float only if the datasheet says so, "
                   "since some parts require NC or reserved pins tied to ground",
                   components=[ref], pins=[p.key for p in marked],
                   evidence=needs_datasheet("; ".join(why), nc_by_name=[p.key for p in by_name],
                                            no_connect_flag=[p.key for p in marked if p.no_connect], mpn=comp_mpn))


def unconnected_ic_pins(model: BoardModel, g: Graph) -> list[Finding]:
    """IC pins with no net, grouped per part; power and ground pins with no net are errors even when marked NC."""
    if not model.pin_list_complete:
        raise Skip("the netlist format omits pins with no net (Protel .NET, or an eda-agent payload without every "
                   "pin; see the model warnings); use IPC-D-356, KiCad XML or an eda-agent payload with every pin")
    out = []
    for ref in sorted(model.components, key=natural_key):
        comp = model.components[ref]
        if comp.kind not in IC_KINDS or not comp.fitted:
            continue
        open_pins = [p for p in g.comp_pins.get(ref, []) if p.net is None]
        for p in [p for p in open_pins if _is_power_pin(p)]:
            out.append(Finding("unconnected_ic_pin", "error",
                               f"{p.key} ({p.name or p.type}) is a power or ground pin with no net",
                               components=[ref], pins=[p.key],
                               evidence={"pin_name": p.name, "pin_type": p.type, "marked_open": _marked_open(p)}))
        marked = [p for p in open_pins if not _is_power_pin(p) and _marked_open(p)]
        if marked:
            out.append(_marked_open_finding(ref, comp.mpn, marked))
        unmarked = [p for p in open_pins if not _is_power_pin(p) and not _marked_open(p)]
        pg = [p for p in unmarked if naming.pin_is(p.name, "pg")]
        if pg:
            out.append(Finding("unconnected_ic_pin", "info",
                               f"{ref} leaves its power-good output open: {', '.join(_label(p) for p in pg)}; {NEEDS}: "
                               "an unused open-drain power-good output can usually float",
                               components=[ref], pins=[p.key for p in pg],
                               evidence=needs_datasheet(f"unused power-good output: {_keys(pg)}", mpn=comp.mpn)))
        rest = [p for p in unmarked if p not in pg]
        if not rest:
            continue
        named = any(p.name for p in rest)
        labels = [_label(p) for p in rest]
        hint = ("each may be NC, reserved, unused I/O or must-connect" if not named
                else "unused I/O is often fine, but an input must not float")
        why = ("open pins with no names, so nothing says NC" if not named
               else f"open pins with no NC mark: {_keys(rest)}")
        out.append(Finding("unconnected_ic_pin", "warning" if named else "info",
                           f"{ref} has {len(rest)} pins with no net: {', '.join(labels)}; {NEEDS}: {hint}",
                           components=[ref], pins=[p.key for p in rest],
                           evidence=needs_datasheet(why, pin_names_known=named, mpn=comp.mpn)))
    return out


def ground_pin_off_ground(model: BoardModel, g: Graph) -> list[Finding]:
    """Pins named as ground that sit on a non-ground net, and power pins that sit on ground."""
    out = []
    for p in sorted(model.pins.values(), key=lambda p: natural_key(p.key)):
        if not p.name or p.net is None or not g.fitted(p.refdes):
            continue
        kind = naming.net_kind(p.net)
        if naming.pin_is(p.name, "ground") and kind not in ("ground", "chassis"):
            out.append(Finding("ground_pin_off_ground", "error", f"{p.key} is named {p.name} but is on {p.net}",
                               components=[p.refdes], nets=[p.net], pins=[p.key]))
        elif naming.pin_is(p.name, "pad") and kind not in ("ground", "chassis") and g.kind(p.refdes) in IC_KINDS:
            out.append(Finding("ground_pin_off_ground", "info",
                               f"{p.key} exposed pad is on {p.net}; most parts want it on ground, some on VIN or open",
                               components=[p.refdes], nets=[p.net], pins=[p.key]))
        elif naming.pin_is_supply(p.name) and kind == "ground" and g.kind(p.refdes) in IC_KINDS:
            out.append(Finding("ground_pin_off_ground", "warning", f"{p.key} is named {p.name} but is on {p.net}",
                               components=[p.refdes], nets=[p.net], pins=[p.key]))
    return out


def _sibling_ground_pins(model: BoardModel, g: Graph, ref: str) -> tuple[set[str], list[str]]:
    """Pin numbers that are on ground in another part with the same MPN, and those siblings."""
    comp = model.components[ref]
    if not comp.mpn:
        return set(), []
    sibs = [r for r, c in model.components.items() if r != ref and c.mpn == comp.mpn and r in g.comp_pins]
    pins = {p.number for r in sibs for p in g.comp_pins[r] if g.is_ground(p.net)}
    return pins, sorted(sibs, key=natural_key)


def protection_ground_floating(model: BoardModel, g: Graph) -> list[Finding]:
    """TVS/ESD parts whose ground pins (by name or by same-MPN siblings) are open or off ground."""
    out = []
    for ref in sorted(model.components, key=natural_key):
        comp = model.components[ref]
        pins = g.comp_pins.get(ref, [])
        if comp.kind != "tvs" or not comp.fitted or not pins:
            continue
        by_name = {p.number for p in pins if naming.pin_is(p.name, "ground")}
        # Two-pin TVS parts are often placed either way round, so siblings only count for arrays.
        by_sib, sibs = _sibling_ground_pins(model, g, ref) if len(pins) >= 3 else (set(), [])
        expected = by_name | by_sib
        bad = [p for p in pins if p.number in expected and not g.is_ground(p.net) and naming.net_kind(p.net or "") != "chassis"]
        if bad:
            why = []
            if by_name & {p.number for p in bad}:
                why.append("pin names say ground")
            if by_sib & {p.number for p in bad}:
                why.append(f"the same pins are on ground in {', '.join(sibs)}")
            nets = sorted({p.net or "(no net)" for p in bad})
            out.append(Finding("protection_ground_floating", "error",
                               f"{ref} ({comp.mpn or comp.value or comp.kind}) ground pins "
                               f"{', '.join(p.number for p in bad)} are on {', '.join(nets)}; {' and '.join(why)}. "
                               "Without ground the clamp does not work",
                               components=[ref] + sibs, nets=[n for n in nets if n != "(no net)"],
                               pins=[p.key for p in bad], evidence={"by_name": sorted(by_name), "by_sibling": sorted(by_sib)}))
        elif len(pins) >= 3 and not any(g.is_ground(p.net) or naming.net_kind(p.net or "") == "chassis" for p in pins):
            out.append(Finding("protection_ground_floating", "warning",
                               f"{ref} ({comp.mpn or comp.kind}) is a {len(pins)}-pin protection part with no pin on ground",
                               components=[ref], pins=[p.key for p in pins]))
    return out
