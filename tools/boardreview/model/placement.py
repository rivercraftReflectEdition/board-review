"""Part positions, board side and schematic sheet from IPC-D-356, a KiCad position file and KiCad XML."""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from boardreview.model.board import natural_key

INCH_MM = 25.4
IPC_SUFFIXES = (".ipc", ".d356", ".356", ".ipc356")
_UNITS = re.compile(r"^P\s+UNITS\s+(\S+)(?:\s+(\S+))?", re.I)
_COORD = re.compile(r"A(\d{2})X([+\- ]?\d+)Y([+\- ]?\d+)")
_RECORDS = ("317", "327", "367")
_SIDES = {"top": "top", "front": "top", "f": "top", "toplayer": "top", "t": "top",
          "bottom": "bottom", "back": "bottom", "b": "bottom", "bottomlayer": "bottom", "bot": "bottom"}
_COLS = {"ref": ("ref", "designator", "refdes", "reference"),
         "x": ("posx", "pos x", "x", "mid x", "center-x", "centerx"),
         "y": ("posy", "pos y", "y", "mid y", "center-y", "centery"),
         "rot": ("rot", "rotation"),
         "side": ("side", "layer")}


@dataclass
class Place:
    refdes: str
    x_mm: float
    y_mm: float
    side: str = ""
    rotation_deg: float | None = None
    pads: int = 0


@dataclass
class Placement:
    """Positions in mm seen from the top, Y up, with where the board extent came from."""

    kind: str
    source: str
    units: str
    parts: dict[str, Place] = field(default_factory=dict)
    extent_mm: tuple[float, float, float, float] | None = None
    extent_from: str = ""
    notes: list[str] = field(default_factory=list)

    def caption(self) -> str:
        """One line for the board map: what the extent and positions come from."""
        what = "pad positions" if self.extent_from == "pads" else "part positions"
        pos = "pad centres" if self.kind == "ipc356" else "part centroids"
        return f"Top view from {self.source}. Points are {pos}; extent from {what}, not the board outline."

    def to_dict(self) -> dict:
        """Compact form for the report page: [x, y, side code] per part."""
        code = {"top": "t", "bottom": "b", "through": "h", "inner": "i"}
        return {
            "kind": self.kind, "source": self.source, "units": self.units,
            "extent": [round(v, 3) for v in self.extent_mm] if self.extent_mm else None,
            "extent_from": self.extent_from, "caption": self.caption(), "notes": list(self.notes),
            "parts": {r: [round(p.x_mm, 3), round(p.y_mm, 3), code.get(p.side, "")]
                      for r, p in sorted(self.parts.items(), key=lambda kv: natural_key(kv[0]))},
        }


def ipc356_units(text: str) -> tuple[float, str, list[str]]:
    """Millimetres per coordinate count, a unit label and notes, from the UNITS record."""
    for line in text.splitlines():
        m = _UNITS.match(line)
        if not m:
            continue
        kind, arg = m.group(1).upper(), (m.group(2) or "").strip()
        if kind == "CUST" and arg in ("", "0", "2"):
            return 0.0001 * INCH_MM, "0.0001 in", []
        if kind == "CUST" and arg == "1":
            return 0.001, "0.001 mm", []
        if kind == "SI":
            return 0.001, "0.001 mm", ["UNITS SI is not an IPC-D-356A code; read as 0.001 mm. UNSURE until the map "
                                       "is checked against the board."]
        return 0.0001 * INCH_MM, "0.0001 in", [f"Unknown UNITS {kind} {arg}; read as 0.0001 inch. UNSURE."]
    return 0.0001 * INCH_MM, "0.0001 in", ["No UNITS record; read as 0.0001 inch (CUST 0)."]


def _count(text: str) -> int:
    return int(text.replace(" ", "") or "0")


def _side(codes: set[int], bottom: int) -> str:
    if codes == {1}:
        return "top"
    if bottom > 1 and codes == {bottom}:
        return "bottom"
    if codes and all(1 < c < bottom for c in codes):
        return "inner"
    return ""


def parse_ipc356_places(text: str, path: str = "") -> Placement:
    """Pad centres per part from test records; SMT access A01 is top, the highest layer number is bottom."""
    mm, label, notes = ipc356_units(text)
    pads: dict[str, list[tuple[float, float, int, str]]] = {}
    xs: list[float] = []
    ys: list[float] = []
    for line in text.splitlines():
        if line[:3] not in _RECORDS:
            continue
        m = _COORD.search(line, 32)
        if not m:
            continue
        x, y = _count(m.group(2)) * mm, _count(m.group(3)) * mm
        xs.append(x)
        ys.append(y)
        ref = line[20:26].strip()
        if not ref or ref.upper() == "VIA" or line[26:27] != "-" or line[31:32] == "M":
            continue
        pads.setdefault(ref, []).append((x, y, int(m.group(1)), line[:3]))
    smt_codes = [a for rows in pads.values() for _, _, a, rec in rows if rec == "327"]
    bottom = max(smt_codes, default=0)
    out = Placement("ipc356", Path(path).name or "IPC-D-356", label, notes=notes)
    for ref, rows in pads.items():
        px = [r[0] for r in rows]
        py = [r[1] for r in rows]
        smt = {a for _, _, a, rec in rows if rec == "327"}
        side = _side(smt, bottom) if smt else "through"
        out.parts[ref] = Place(ref, (min(px) + max(px)) / 2, (min(py) + max(py)) / 2, side, None, len(rows))
    if xs:
        out.extent_mm = (min(xs), min(ys), max(xs), max(ys))
        out.extent_from = "pads"
    if any(p.side == "through" for p in out.parts.values()):
        out.notes.append("Through-hole parts: IPC-D-356 does not say which side the body is on.")
    if bottom > 1:
        out.notes.append(f"SMT pads on layer {bottom}, the highest layer number in the file, are read as the bottom.")
    return out


def _num(text: str) -> float:
    return float(re.sub(r"[^0-9eE+\-.]", "", text))


def _norm_side(text: str) -> str:
    return _SIDES.get(text.strip().lower().replace(" ", ""), "")


def _pos_units(units: str, values: list[float], stated: str) -> tuple[float, str, list[str]]:
    if stated:
        return (1.0, "mm", []) if stated == "mm" else (INCH_MM, "in", [])
    if units:
        return (1.0, "mm", []) if units == "mm" else (INCH_MM, "in", [])
    if values and max(abs(v) for v in values) > 50:
        return 1.0, "mm", ["Units not stated in the file; coordinates above 50 read as mm."]
    return INCH_MM, "in", ["Units not stated in the file; read as inches, the kicad-cli default. UNSURE: pass the "
                           "units to settle it."]


def _column(headers: list[str], key: str) -> int:
    norm = [h.strip().lower() for h in headers]
    for name in _COLS[key]:
        if name in norm:
            return norm.index(name)
    return -1


def parse_kicad_pos(text: str, path: str = "", units: str = "") -> Placement:
    """Part centroids from kicad-cli pcb export pos, CSV or ASCII; units 'mm' or 'in' when the file does not say."""
    rows: list[tuple[str, float, float, float | None, str]] = []
    stated = ""
    m = re.search(r"##\s*Unit\s*=\s*(mm|in|inch|inches)", text, re.I)
    if m:
        stated = "mm" if m.group(1).lower() == "mm" else "in"
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and lines[0].lstrip().startswith("#"):
        for ln in lines:
            if ln.lstrip().startswith("#"):
                continue
            tok = ln.split()
            if len(tok) >= 5:
                rows.append((tok[0], _num(tok[-4]), _num(tok[-3]), _num(tok[-2]), _norm_side(tok[-1])))
    else:
        table = list(csv.reader(io.StringIO(text)))
        head = next((i for i, r in enumerate(table) if _column(r, "ref") >= 0 and _column(r, "x") >= 0), None)
        if head is None:
            raise ValueError(f"{path or 'position file'}: no Ref and PosX columns")
        cols = {k: _column(table[head], k) for k in _COLS}
        for r in table[head + 1:]:
            if len(r) <= max(cols["ref"], cols["x"], cols["y"]) or not r[cols["ref"]].strip():
                continue
            rot = _num(r[cols["rot"]]) if cols["rot"] >= 0 and r[cols["rot"]].strip() else None
            side = _norm_side(r[cols["side"]]) if cols["side"] >= 0 else ""
            rows.append((r[cols["ref"]].strip(), _num(r[cols["x"]]), _num(r[cols["y"]]), rot, side))
    scale, label, notes = _pos_units(units, [v for r in rows for v in (r[1], r[2])], stated)
    out = Placement("kicad_pos", Path(path).name or "position file", label, notes=notes)
    for ref, x, y, rot, side in rows:
        out.parts[ref] = Place(ref, x * scale, y * scale, side, rot)
    if out.parts:
        px = [p.x_mm for p in out.parts.values()]
        py = [p.y_mm for p in out.parts.values()]
        out.extent_mm = (min(px), min(py), max(px), max(py))
        out.extent_from = "parts"
    return out


def parse_kicad_sheets(text: str) -> dict[str, str]:
    """Schematic sheet per refdes from a KiCad XML netlist's sheetpath names; '/' is the root sheet."""
    root = ET.fromstring(text)
    out = {}
    for comp in root.iter("comp"):
        sp = comp.find("sheetpath")
        if sp is not None and sp.get("names") is not None:
            name = sp.get("names", "").strip("/")
            out[comp.get("ref", "")] = name or "/ (root sheet)"
    return out


def sniff(path: str | Path) -> str:
    """ipc356, kicad_pos or kicad_xml, or '' when the file is none of them."""
    path = Path(path)
    head = path.read_bytes()[:4096].decode("latin-1", errors="replace").lstrip("﻿\xef\xbb\xbf \r\n\t")
    if head.startswith("<"):
        return "kicad_xml" if "<export" in head else ""
    if path.suffix.lower() in IPC_SUFFIXES or any(ln[:3] in _RECORDS for ln in head.splitlines()):
        return "ipc356"
    low = head.lower()
    if "footprint positions" in low or ("ref" in low and "posx" in low.replace(" ", "")):
        return "kicad_pos"
    return ""


def read_placement(path: str | Path, units: str = "") -> Placement:
    """Read an IPC-D-356 file or a KiCad position file."""
    path = Path(path)
    kind = sniff(path)
    text = path.read_text(encoding="latin-1" if kind == "ipc356" else "utf-8-sig")
    if kind == "ipc356":
        return parse_ipc356_places(text, str(path))
    if kind == "kicad_pos":
        return parse_kicad_pos(text, str(path), units)
    raise ValueError(f"{path.name}: not an IPC-D-356 or KiCad position file")


def _candidates(facts: Path) -> list[Path]:
    """Placement and sheet files in the facts folder, then the sources board_model.json names that still exist."""
    found = [p for p in sorted(facts.iterdir()) if p.is_file() and (
        p.suffix.lower() in IPC_SUFFIXES + (".pos", ".xml") or (p.suffix.lower() == ".csv" and "pos" in p.stem.lower()))]
    model = facts / "board_model.json"
    if model.exists():
        for s in json.loads(model.read_text(encoding="utf-8")).get("sources", []):
            p = Path(s.get("path", ""))
            if s.get("kind") in ("ipc356", "kicad_xml") and p.is_file() and p not in found:
                found.append(p)
    return found


def for_facts(facts: str | Path, extra: list[str | Path] = (), units: str = "") -> tuple[Placement | None, dict[str, str], list[str]]:
    """Placement, sheets and notes for a review: a position file wins over IPC-D-356; sources are never mixed."""
    files = [Path(p) for p in extra] + (_candidates(Path(facts)) if Path(facts).is_dir() else [])
    pos: list[Placement] = []
    ipc: list[Placement] = []
    sheets: dict[str, str] = {}
    notes: list[str] = []
    for p in files:
        try:
            kind = sniff(p)
            if kind == "kicad_xml":
                for ref, name in parse_kicad_sheets(p.read_text(encoding="utf-8")).items():
                    sheets.setdefault(ref, name)
            elif kind == "kicad_pos":
                pos.append(read_placement(p, units))
            elif kind == "ipc356":
                ipc.append(read_placement(p, units))
        except (OSError, ValueError, ET.ParseError) as exc:
            notes.append(f"Skipped {p.name}: {exc}")
    chosen = (pos or ipc or [None])[0]
    if chosen is not None and len(pos) + len(ipc) > 1:
        notes.append(f"Positions from {chosen.source} only; other placement files use their own origin.")
    if chosen is None:
        notes.append("No IPC-D-356 or position file found: board side and X/Y are not shown.")
    return chosen, sheets, notes
