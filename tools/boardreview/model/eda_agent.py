"""Importer for eda-agent Altium MCP JSON (proj_get_bom, connectivity, component info, pads, variants)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from boardreview.model import fields, parts
from boardreview.model.board import BoardModel, natural_key


@dataclass
class _Seen:
    """What the payload proves about the pin list: per-part inventories, pins with a net field, an open-pin list."""
    inventory: set[str] = field(default_factory=set)
    known: set[tuple[str, str]] = field(default_factory=set)
    open_list: bool = False


def _pin_fields(p: dict[str, Any]) -> tuple[str, str, str | None]:
    """Pin number, pin name and net from any of the pin shapes (pin/pin_number/pad name)."""
    if "pin_number" in p:
        number = p["pin_number"]
    elif "pin" in p:
        number = p["pin"]
    else:
        number = p.get("name", "")
    if "pin_name" in p:
        name = p["pin_name"]
    elif "pin" in p or "pin_number" in p:
        name = p.get("name", "")
    else:
        name = ""
    net = p.get("net")
    return str(number), str(name or ""), (None if net is None else str(net))


def _apply_component(model: BoardModel, c: dict[str, Any], seen: _Seen) -> None:
    ref = c.get("designator") or c.get("reference")
    if not ref:
        return
    comp = model.component(str(ref))
    comment = str(c.get("comment", c.get("value", "")) or "")
    if comment:
        comp.attrs["comment"] = comment
        if not comp.value and parts.value_si(comment, comp.kind) is not None:
            comp.value = comment
    comp.footprint = comp.footprint or str(c.get("footprint", "") or "")
    if c.get("sheet"):
        comp.attrs["sheet"] = str(c["sheet"])
    if c.get("lib_ref"):
        comp.attrs["lib_ref"] = str(c["lib_ref"])
    params = c.get("parameters")
    if isinstance(params, dict):
        got = fields.pick({str(k): str(v) for k, v in params.items()})
        comp.mpn = got.get("mpn", comp.mpn)
        comp.manufacturer = got.get("manufacturer", comp.manufacturer)
        comp.description = got.get("description", comp.description)
        if got.get("value"):
            comp.value = got["value"]
    if c.get("dnp") is True:
        comp.fitted = False
    pins = c.get("pins") if isinstance(c.get("pins"), list) else c.get("pads")
    for p in pins or []:
        number, name, net = _pin_fields(p)
        model.add_pin(comp.refdes, number, net, name)
        if "net" in p:
            seen.known.add((comp.refdes, number))
    if pins and all("net" in p for p in pins):
        seen.inventory.add(comp.refdes)
    comp.classify()


def _incomplete_reason(model: BoardModel, seen: _Seen) -> str:
    """Empty when the payload lists every pin with its net, else why it may not."""
    if not model.pins:
        return "the payload has no pins"
    unknown = sorted((f"{r}.{n}" for r, n in model.pins if (r, n) not in seen.known), key=natural_key)
    if unknown:
        return f"{len(unknown)} pins have no net field ({', '.join(unknown[:5])})"
    partial = sorted({r for r, _ in model.pins if r not in seen.inventory}, key=natural_key)
    if partial and not seen.open_list:
        return (f"pins of {len(partial)} parts ({', '.join(partial[:5])}) come only from net listings, "
                "which leave out open pins, and no unconnected-pin list was given")
    return ""


def _apply_variants(model: BoardModel, payload: dict[str, Any], variant: str) -> None:
    chosen = [v for v in payload.get("variants", []) if v.get("name") == variant]
    if variant and not chosen:
        raise ValueError(f"variant {variant!r} not in payload")
    for v in chosen:
        for var in v.get("variations", []):
            comp = model.component(str(var.get("designator", "")))
            kind = str(var.get("kind", ""))
            comp.variant = variant
            comp.fitted = kind != "Not Fitted"
            if kind == "Alternate" and var.get("alternate_part"):
                comp.attrs["alternate_part"] = str(var["alternate_part"])


def _apply(model: BoardModel, payload: Any, seen: _Seen) -> None:
    if isinstance(payload, list):
        for item in payload:
            _apply(model, item, seen)
        return
    if not isinstance(payload, dict):
        return
    payload = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    if isinstance(payload.get("variants"), list):
        return
    if isinstance(payload.get("components"), list):
        for c in payload["components"]:
            _apply_component(model, c, seen)
    elif "designator" in payload and ("pins" in payload or "pads" in payload or "parameters" in payload):
        _apply_component(model, payload, seen)
    elif isinstance(payload.get("pins"), list):
        for p in payload["pins"]:
            number, name, net = _pin_fields(p)
            pin = model.add_pin(str(p.get("component", "")), number, net, name)
            if "net" in p:
                seen.known.add((pin.refdes, pin.number))
    elif isinstance(payload.get("unconnected_pins"), list):
        seen.open_list = True
        for p in payload["unconnected_pins"]:
            pin = model.add_pin(str(p.get("designator", "")), str(p.get("pin_number", "")), None,
                                str(p.get("pin_name", "")))
            seen.known.add((pin.refdes, pin.number))
    else:
        for value in payload.values():
            if isinstance(value, (dict, list)):
                _apply(model, value, seen)


def parse_eda_agent(payload: Any, path: str = "", variant: str = "") -> BoardModel:
    """Build a model from one payload, a list of payloads, or a snapshot dict of payloads."""
    # Upstream payloads are hand-built in DelphiScript with inconsistent keys, so shapes are sniffed.
    model = BoardModel()
    seen = _Seen()
    _apply(model, payload, seen)
    if variant:
        _apply_variants_any(model, payload, variant)
    why = _incomplete_reason(model, seen)
    model.pin_list_complete = not why
    source = {"kind": "eda_agent_json", "path": str(path), "variant": variant}
    if why:
        source["pin_list"] = f"incomplete: {why}"
        model.warnings.append(f"pin list not complete: {why}; open-pin checks are skipped and a pin missing "
                              "from this source is not a difference in the compare")
    model.sources.append(source)
    return model.finalize()


def _apply_variants_any(model: BoardModel, payload: Any, variant: str) -> None:
    if isinstance(payload, dict) and isinstance(payload.get("variants"), list):
        _apply_variants(model, payload, variant)
    elif isinstance(payload, dict):
        for value in payload.values():
            _apply_variants_any(model, value, variant)
    elif isinstance(payload, list):
        for item in payload:
            _apply_variants_any(model, item, variant)


def read_eda_agent(path: str | Path, variant: str = "") -> BoardModel:
    """Read a JSON file saved from eda-agent tool output."""
    path = Path(path)
    return parse_eda_agent(json.loads(path.read_text(encoding="utf-8")), str(path), variant)
