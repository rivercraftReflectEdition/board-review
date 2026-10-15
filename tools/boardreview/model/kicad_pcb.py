"""KiCad board importer (.kicad_pcb): footprints, pads with full net names, and placement."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Iterator

from boardreview.model import fields, kicad
from boardreview.model.board import BoardModel, natural_key

_SCAN = re.compile(r'"(?:[^"\\]|\\.)*"|[()]')
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([()])|([^\s()"]+)')
_HEAD = re.compile(r'\(\s*([^\s()"]+)')
_ESCAPE = re.compile(r"\\(.)")
FOOTPRINT_HEADS = ("footprint", "module")
SIDES = {"F.Cu": "top", "B.Cu": "bottom"}
NAME_ESCAPES = {"slash": "/", "backslash": "\\", "space": " ", "tab": "\t", "return": "\n", "dblquote": '"',
                "quote": "'", "comma": ",", "colon": ":", "lt": "<", "gt": ">", "dollar": "$"}
_NAME_ESCAPE = re.compile(r"\{(" + "|".join(NAME_ESCAPES) + r")\}")


def _blocks(text: str, heads: tuple[str, ...]) -> Iterator[str]:
    """Text of each child of the root whose head is in heads; strings may hold parentheses."""
    depth, start = 0, -1
    for m in _SCAN.finditer(text):
        tok = m.group()
        if tok == "(":
            depth += 1
            if depth == 2:
                head = _HEAD.match(text, m.start())
                start = m.start() if head and head.group(1) in heads else -1
        elif tok == ")":
            if depth == 2 and start >= 0:
                yield text[start:m.end()]
                start = -1
            depth -= 1


def parse_sexpr(text: str) -> list:
    """One s-expression as nested lists of strings."""
    stack: list[list] = [[]]
    for m in _TOKEN.finditer(text):
        quoted, paren, atom = m.groups()
        if paren == "(":
            stack.append([])
        elif paren == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(_ESCAPE.sub(r"\1", quoted) if quoted is not None else atom)
    return stack[0][0]


def _kids(node: list, head: str) -> list[list]:
    return [c for c in node if isinstance(c, list) and c and c[0] == head]


def _first(node: list, head: str) -> list:
    found = _kids(node, head)
    return found[0] if found else []


def _text_field(fp: list, name: str) -> str:
    for prop in _kids(fp, "property"):
        if len(prop) > 2 and prop[1] == name:
            return prop[2]
    for txt in _kids(fp, "fp_text"):
        if len(txt) > 2 and txt[1] == name.lower():
            return txt[2]
    return ""


def unescape(name: str) -> str:
    """Net name with KiCad's {slash}-style escapes undone, as the netlist export writes it."""
    return _NAME_ESCAPE.sub(lambda m: NAME_ESCAPES.get(m.group(1), m.group(0)), name)


def _pad_net(pad: list) -> str | None:
    net = _first(pad, "net")
    name = net[-1] if len(net) >= 2 and isinstance(net[-1], str) else ""
    return None if name.startswith("unconnected-(") else unescape(name) or None


def _add_footprint(model: BoardModel, fp: list, numbered: bool) -> None:
    ref = _text_field(fp, "Reference")
    c = model.component(ref)
    c.value = _text_field(fp, "Value")
    c.footprint = fp[1] if len(fp) > 1 and isinstance(fp[1], str) else ""
    props = {p[1]: p[2] for p in _kids(fp, "property") if len(p) > 2 and isinstance(p[2], str)}
    picked = fields.pick({k: v for k, v in props.items() if k not in ("Reference", "Value", "Footprint")})
    c.mpn, c.manufacturer = picked.get("mpn", ""), picked.get("manufacturer", "")
    c.description = picked.get("description", "") or (_first(fp, "descr") + ["", ""])[1]
    attr = set(_first(fp, "attr")[1:])
    c.fitted = "dnp" not in attr
    for flag in ("exclude_from_bom", "board_only"):
        if flag in attr:
            c.attrs[flag] = "yes"
    at = _first(fp, "at")
    c.attrs.update({"x_mm": at[1] if len(at) > 1 else "0", "y_mm": at[2] if len(at) > 2 else "0",
                    "rot_deg": at[3] if len(at) > 3 else "0",
                    "side": SIDES.get((_first(fp, "layer") + ["", ""])[1], "unknown")})
    for pad in _kids(fp, "pad"):
        num = pad[1] if len(pad) > 1 and isinstance(pad[1], str) else ""
        if not num:
            continue
        ptype = (_first(pad, "pintype") + ["", ""])[1]
        func = (_first(pad, "pinfunction") + [None, None])[1]
        model.add_pin(ref, num, _pad_net(pad), kicad.pin_function(func, num, numbered), ptype.split("+")[0],
                      no_connect="+no_connect" in ptype)
    c.classify()


def parse_kicad_pcb(text: str, path: str = "") -> BoardModel:
    """Parse a .kicad_pcb file: one part per footprint, one pin per numbered pad, placement in attrs."""
    if not text.lstrip().startswith("(kicad_pcb"):
        raise ValueError("not a KiCad board file (no kicad_pcb root)")
    footprints = [parse_sexpr(b) for b in _blocks(text, FOOTPRINT_HEADS)]
    pairs = [(f[1], p[1]) for fp in footprints for p in _kids(fp, "pad") if len(p) > 1
             for f in _kids(p, "pinfunction") if len(f) > 1]
    numbered = kicad.numbered_functions(pairs)
    model = BoardModel(pin_list_complete=True)
    refs = Counter(_text_field(fp, "Reference") for fp in footprints)
    skipped = 0
    for fp in footprints:
        ref = _text_field(fp, "Reference")
        if not ref or "*" in ref:
            skipped += 1
            continue
        _add_footprint(model, fp, numbered)
    dup = sorted((r for r, n in refs.items() if n > 1 and r and "*" not in r), key=natural_key)
    if dup:
        model.warnings.append(f"designators used by more than one footprint: {', '.join(dup)}")
    if skipped:
        model.warnings.append(f"{skipped} footprints without a designator (REF** or empty) left out")
    head = text[:400]
    source = {"kind": "kicad_pcb", "path": str(path)}
    for key in ("version", "generator_version"):
        m = re.search(rf"\({key}\s+\"?([^\s\")]+)", head)
        if m:
            source[key] = m.group(1)
    model.sources.append(source)
    return model.finalize()


def read_kicad_pcb(path: str | Path) -> BoardModel:
    """Read a .kicad_pcb file."""
    path = Path(path)
    return parse_kicad_pcb(path.read_text(encoding="utf-8"), str(path))


def has_placement(model: BoardModel) -> bool:
    """True when the model carries footprint positions."""
    return any("x_mm" in c.attrs for c in model.components.values())


def placement_markdown(model: BoardModel, source: str) -> str:
    """Placement table: side, position and rotation of every footprint."""
    comps = sorted((c for c in model.components.values() if "x_mm" in c.attrs), key=lambda c: natural_key(c.refdes))
    sides = Counter(c.attrs.get("side", "unknown") for c in comps)
    lines = ["# Placement", "",
             f"From `{source}`: {len(comps)} footprints, "
             + ", ".join(f"{sides[s]} {s}" for s in ("top", "bottom", "unknown") if sides[s]) + ".",
             "KiCad board coordinates in mm (y grows downward), rotation in degrees.", "",
             "| Ref | Side | X mm | Y mm | Rot deg | Footprint | Value | Fitted |", "|---|---|---|---|---|---|---|---|"]
    for c in comps:
        a = c.attrs
        lines.append(f"| {c.refdes} | {a.get('side', '')} | {a['x_mm']} | {a.get('y_mm', '')} | {a.get('rot_deg', '')}"
                     f" | {c.footprint} | {c.value} | {'yes' if c.fitted else 'no'} |")
    return "\n".join(lines) + "\n"
