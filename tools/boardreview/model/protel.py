"""Altium / Protel .NET netlist importer (classic Protel and Protel 2.0 layouts)."""

from __future__ import annotations

from pathlib import Path

from boardreview.model import fields
from boardreview.model.board import BoardModel

_KEYWORDS = {"DESIGNATOR": "refdes", "FOOTPRINT": "footprint", "PARTTYPE": "comment", "COMMENT": "comment",
             "DESCRIPTION": "description", "VALUE": "value"}


def _lines(body: str) -> list[str]:
    return [ln.strip() for ln in body.splitlines() if ln.strip()]


def _component(body: str) -> dict[str, str]:
    raw = body.splitlines()
    lines = _lines(body)
    if lines and lines[0].upper() in _KEYWORDS:
        out: dict[str, str] = {}
        for i in range(0, len(lines) - 1):
            key = _KEYWORDS.get(lines[i].upper())
            if key and key not in out:
                out[key] = lines[i + 1]
        return out
    vals = [ln.strip() for ln in raw]
    while vals and not vals[0]:
        vals.pop(0)
    names = ["refdes", "footprint", "comment", "description"]
    return {k: v for k, v in zip(names, vals) if v}


def _net(body: str) -> tuple[str, list[tuple[str, str]]]:
    lines = _lines(body)
    if lines and lines[0].upper() in ("NET", "NETNAME"):
        lines = lines[1:]
    if not lines:
        return "", []
    nodes = []
    for ln in lines[1:]:
        token = ln.split()[0]
        ref, sep, pin = token.partition("-")
        if sep and ref and pin:
            nodes.append((ref, pin))
    return lines[0], nodes


def _blocks(text: str) -> list[tuple[str, str]]:
    """Split into ('[', body) and ('(', body); brackets open and close on their own lines."""
    out, opener, body = [], "", []
    for line in text.splitlines():
        s = line.strip()
        if not opener and s[:1] in ("[", "("):
            opener, body = s[0], [s[1:]]
        elif opener and s == {"[": "]", "(": ")"}[opener]:
            out.append((opener, "\n".join(body)))
            opener = ""
        elif opener:
            body.append(line)
    return out


def parse_protel(text: str, path: str = "") -> BoardModel:
    """Parse a Protel netlist: [component] blocks and (net) blocks with REF-PIN nodes."""
    model = BoardModel(pin_list_complete=False)
    for opener, body in _blocks(text):
        if opener == "[":
            info = _component(body)
            if not info.get("refdes"):
                continue
            c = model.component(info["refdes"])
            c.footprint = info.get("footprint", "")
            c.description = info.get("description", "")
            comment = info.get("value") or info.get("comment", "")
            c.value = comment
            c.fitted = not fields.value_says_dnp(comment)
            c.classify()
        else:
            name, nodes = _net(body)
            for ref, pin in nodes:
                model.add_pin(ref, pin, name)
    model.sources.append({"kind": "protel_net", "path": str(path)})
    return model.finalize()


def read_protel(path: str | Path) -> BoardModel:
    """Read an Altium/Protel .NET netlist file."""
    path = Path(path)
    return parse_protel(path.read_text(encoding="latin-1"), str(path))
