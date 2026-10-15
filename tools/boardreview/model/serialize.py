"""board_model.json export and import (shape in skill/schemas/board_model.schema.json)."""

from __future__ import annotations

import json
from pathlib import Path

from boardreview.model.board import SCHEMA_ID, BoardModel, Component, natural_key


def to_dict(model: BoardModel) -> dict:
    """Plain JSON-ready dict of the model."""
    comps = sorted(model.components.values(), key=lambda c: natural_key(c.refdes))
    pins = sorted(model.pins.values(), key=lambda p: natural_key(p.key))
    return {
        "schema": SCHEMA_ID,
        "sources": list(model.sources),
        "pin_list_complete": model.pin_list_complete,
        "stats": {
            "components": len(comps),
            "pins": len(pins),
            "nets": len(model.nets),
            "unconnected_pins": sum(1 for p in pins if p.net is None),
        },
        "components": [
            {
                "refdes": c.refdes, "value": c.value, "value_si": c.value_si, "mpn": c.mpn,
                "manufacturer": c.manufacturer, "footprint": c.footprint, "description": c.description,
                "fitted": c.fitted, "variant": c.variant, "kind": c.kind, "attrs": dict(c.attrs),
            }
            for c in comps
        ],
        "pins": [
            {"refdes": p.refdes, "number": p.number, "name": p.name, "type": p.type, "net": p.net,
             "no_connect": p.no_connect}
            for p in pins
        ],
        "nets": [
            {"name": n.name, "class": n.net_class, "kind": n.kind, "auto_named": n.auto_named,
             "pins": list(n.pins), "attrs": dict(n.attrs)}
            for n in model.nets.values()
        ],
        "warnings": list(model.warnings),
    }


def from_dict(data: dict) -> BoardModel:
    """Rebuild a model from to_dict output."""
    if data.get("schema") != SCHEMA_ID:
        raise ValueError(f"not a board model: schema {data.get('schema')!r}")
    model = BoardModel(sources=list(data.get("sources", [])), pin_list_complete=bool(data.get("pin_list_complete")))
    for c in data.get("components", []):
        model.components[c["refdes"]] = Component(
            refdes=c["refdes"], value=c.get("value", ""), mpn=c.get("mpn", ""),
            manufacturer=c.get("manufacturer", ""), footprint=c.get("footprint", ""),
            description=c.get("description", ""), fitted=bool(c.get("fitted", True)),
            variant=c.get("variant", ""), kind=c.get("kind", ""), attrs=dict(c.get("attrs", {})),
        )
    for p in data.get("pins", []):
        model.add_pin(p["refdes"], p["number"], p.get("net"), p.get("name", ""), p.get("type", ""),
                      bool(p.get("no_connect")))
    for n in data.get("nets", []):
        model.set_net_info(n["name"], **{"class": n.get("class", "")}, **n.get("attrs", {}))
    model.warnings = list(data.get("warnings", []))
    return model


def write_json(model: BoardModel, path: str | Path) -> Path:
    """Write board_model.json."""
    path = Path(path)
    path.write_text(json.dumps(to_dict(model), indent=1) + "\n", encoding="utf-8")
    return path


def read_json(path: str | Path) -> BoardModel:
    """Read board_model.json."""
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
