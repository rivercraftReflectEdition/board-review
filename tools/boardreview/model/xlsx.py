"""Minimal XLSX reader on zipfile and ElementTree: cell text of one worksheet, no styles or formulas."""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_CELL = re.compile(r"([A-Z]+)(\d+)")


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{_NS}t")) for si in root.iter(f"{_NS}si")]


def _sheet_paths(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target", "") for r in rels.iter(f"{_PKG_REL}Relationship")}
    out = []
    for sheet in wb.iter(f"{_NS}sheet"):
        t = target.get(sheet.get(f"{_REL_NS}id"), "")
        path = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join("xl", t))
        out.append((sheet.get("name", ""), path))
    return out


def sheet_names(path: str | Path) -> list[str]:
    """Worksheet names in workbook order."""
    with zipfile.ZipFile(path) as zf:
        return [name for name, _ in _sheet_paths(zf)]


def read_rows(path: str | Path, sheet: str | int = 0) -> list[list[str]]:
    """Rows of cell text for one worksheet, by name or index; missing cells are ''."""
    with zipfile.ZipFile(path) as zf:
        sheets = _sheet_paths(zf)
        name_to_path = dict(sheets)
        part = name_to_path[sheet] if isinstance(sheet, str) else sheets[sheet][1]
        strings = _shared_strings(zf)
        root = ET.fromstring(zf.read(part))
    rows: list[list[str]] = []
    for row in root.iter(f"{_NS}row"):
        cells: dict[int, str] = {}
        for i, c in enumerate(row.iter(f"{_NS}c")):
            m = _CELL.match(c.get("r", ""))
            col = _col_index(m.group(1)) if m else i
            kind = c.get("t", "")
            v = c.find(f"{_NS}v")
            if kind == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{_NS}t"))
            elif kind == "s" and v is not None:
                text = strings[int(v.text or 0)]
            else:
                text = v.text or "" if v is not None else ""
                if kind == "" and re.fullmatch(r"-?\d+\.0+", text):
                    text = text.split(".")[0]
            cells[col] = text
        width = max(cells) + 1 if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    return rows
