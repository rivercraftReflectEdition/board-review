"""BOM importer (CSV or XLSX) and merge of BOM attributes into a BoardModel."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from boardreview.model import fields, parts, xlsx
from boardreview.model.board import BoardModel, natural_key


@dataclass
class BomLine:
    refdes: list[str]
    mpn: str = ""
    manufacturer: str = ""
    value: str = ""
    comment: str = ""
    footprint: str = ""
    description: str = ""
    fitted: bool | None = None
    variant: str = ""
    datasheet: str = ""
    row: int = 0
    extra: dict[str, str] = field(default_factory=dict)


def _header_index(rows: list[list[str]]) -> int:
    for i, row in enumerate(rows[:40]):
        if any(fields.canonical(c) == "refdes" for c in row):
            return i
    raise ValueError("no designator column found in the first 40 rows")


def _population(got: dict[str, str], has_dnp_column: bool) -> bool | None:
    """Fitted state a BOM row states: True, False, or None when the row says nothing about it."""
    if fields.value_says_dnp(got.get("value", "")) or fields.value_says_dnp(got.get("comment", "")):
        return False
    if "dnp" in got and fields.is_dnp_flag(got["dnp"]):
        return False
    if "fitted" in got:
        return not fields.is_not_fitted(got["fitted"])
    return True if has_dnp_column else None


def parse_rows(rows: list[list[str]]) -> list[BomLine]:
    """BOM lines from a table whose header row has a designator column."""
    h = _header_index(rows)
    headers = [c.strip() for c in rows[h]]
    has_dnp_column = any(fields.canonical(c) == "dnp" for c in headers)
    out = []
    for n, raw in enumerate(rows[h + 1:], start=h + 2):
        row = {headers[i]: (raw[i] if i < len(raw) else "") for i in range(len(headers)) if headers[i]}
        got = fields.pick(row)
        refs = fields.expand_refdes(got.get("refdes", ""))
        if not refs:
            continue
        fitted = _population(got, has_dnp_column)
        known = {h for h in row if fields.canonical(h)}
        out.append(BomLine(
            refdes=refs, mpn=got.get("mpn", ""), manufacturer=got.get("manufacturer", ""),
            value=got.get("value", ""), comment=got.get("comment", ""), footprint=got.get("footprint", ""),
            description=got.get("description", ""), fitted=fitted, variant=got.get("variant", ""),
            datasheet=got.get("datasheet", ""), row=n,
            extra={k: v for k, v in row.items() if k not in known and v},
        ))
    return out


def read_bom(path: str | Path, sheet: str | int = 0) -> list[BomLine]:
    """Read a BOM from .csv/.tsv/.txt or .xlsx."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return parse_rows(xlsx.read_rows(path, sheet))
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return parse_rows([row for row in csv.reader(io.StringIO(text), dialect)])


def _value_for(line: BomLine, kind: str) -> tuple[str, str]:
    if line.value and not fields.value_says_dnp(line.value):
        return line.value, "bom value"
    if line.comment and parts.value_si(line.comment, kind) is not None:
        return line.comment, "bom comment"
    derived = parts.value_from_description(line.description, kind)
    return (derived, "bom description") if derived else ("", "")


_POPULATION_SOURCES = {"kicad_xml", "eda_agent_json"}


def _netlist_population(model: BoardModel) -> dict[str, bool]:
    """Fitted state per part where the netlist states one: any DNP mark, or every part for KiCad and eda-agent."""
    every = any(s.get("kind") in _POPULATION_SOURCES for s in model.sources)
    return {r: c.fitted for r, c in model.components.items() if every or not c.fitted}


def _apply_population(model: BoardModel, ref: str, line: BomLine, netlist: dict[str, bool]) -> None:
    """Take the BOM's fitted state when it states one; flag it when the netlist said otherwise."""
    if line.fitted is None:
        return
    c = model.components[ref]
    said = netlist.get(ref)
    if said is not None and said != line.fitted:
        was, now = ("fitted" if said else "DNP"), ("fitted" if line.fitted else "DNP")
        c.attrs["fitted_conflict"] = f"netlist {was}, BOM row {line.row} {now}; BOM kept"
        model.warnings.append(f"{ref} is {was} in the netlist but {now} in BOM row {line.row}; kept the BOM")
    c.fitted = line.fitted
    c.attrs["fitted_from"] = f"bom row {line.row}"


def apply_bom(model: BoardModel, lines: list[BomLine], path: str = "") -> dict[str, list[str]]:
    """Merge BOM attributes into components; return refdes only in the BOM and only in the netlist."""
    seen: set[str] = set()
    bom_only: list[str] = []
    netlist = _netlist_population(model)
    for line in lines:
        for ref in line.refdes:
            if ref in seen:
                model.warnings.append(f"{ref} appears on more than one BOM line; row {line.row} wins")
            seen.add(ref)
            if ref not in model.components:
                bom_only.append(ref)
            c = model.component(ref)
            c.mpn = line.mpn or c.mpn
            c.manufacturer = line.manufacturer or c.manufacturer
            c.description = line.description or c.description
            c.footprint = c.footprint or line.footprint
            _apply_population(model, ref, line, netlist)
            c.variant = line.variant or c.variant
            c.attrs["bom_row"] = str(line.row)
            if line.comment:
                c.attrs["comment"] = line.comment
            if line.datasheet and line.datasheet != "~":
                c.attrs["datasheet"] = line.datasheet
            if ref in bom_only:
                c.attrs["bom_only"] = "yes"
            c.classify()
            value, how = _value_for(line, c.kind)
            if value:
                c.value, c.attrs["value_from"] = value, how
    with_pins = {p.refdes for p in model.pins.values()}
    absent = sorted((r for r in with_pins if r not in seen), key=natural_key)
    excluded = [r for r in absent if model.components[r].attrs.get("exclude_from_bom")]
    netlist_only = [r for r in absent if r not in excluded]
    for ref in absent:
        model.components[ref].attrs["in_bom"] = "excluded" if ref in excluded else "no"
    model.sources.append({"kind": "bom", "path": str(path), "lines": str(len(lines))})
    model.invalidate()
    return {"bom_only": sorted(bom_only, key=natural_key), "netlist_only": netlist_only,
            "excluded_from_bom": excluded}
