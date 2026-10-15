"""Importer for eda-agent Altium MCP JSON (proj_get_bom, connectivity, component info, pads, variants)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boardreview.model import fields, parts
from boardreview.model.board import BoardModel


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


def _apply_component(model: BoardModel, c: dict[str, Any]) -> None:
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
    comp.classify()


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


def _apply(model: BoardModel, payload: Any) -> None:
    if isinstance(payload, list):
        for item in payload:
            _apply(model, item)
        return
    if not isinstance(payload, dict):
        return
    payload = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    if isinstance(payload.get("variants"), list):
        return
    if isinstance(payload.get("components"), list):
        for c in payload["components"]:
            _apply_component(model, c)
    elif "designator" in payload and ("pins" in payload or "pads" in payload or "parameters" in payload):
        _apply_component(model, payload)
    elif isinstance(payload.get("pins"), list):
        for p in payload["pins"]:
            number, name, net = _pin_fields(p)
            model.add_pin(str(p.get("component", "")), number, net, name)
    elif isinstance(payload.get("unconnected_pins"), list):
        for p in payload["unconnected_pins"]:
            model.add_pin(str(p.get("designator", "")), str(p.get("pin_number", "")), None, str(p.get("pin_name", "")))
    else:
        for value in payload.values():
            if isinstance(value, (dict, list)):
                _apply(model, value)


def parse_eda_agent(payload: Any, path: str = "", variant: str = "") -> BoardModel:
    """Build a model from one payload, a list of payloads, or a snapshot dict of payloads."""
    # Upstream payloads are hand-built in DelphiScript with inconsistent keys, so shapes are sniffed.
    model = BoardModel(pin_list_complete=True)
    _apply(model, payload)
    if variant:
        _apply_variants_any(model, payload, variant)
    model.sources.append({"kind": "eda_agent_json", "path": str(path), "variant": variant})
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
