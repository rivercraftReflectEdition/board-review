"""KiCad intermediate netlist importer (kicad-cli sch export netlist --format kicadxml)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from boardreview.model import fields
from boardreview.model.board import BoardModel


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _pin_name(name: str | None) -> str:
    return "" if name in (None, "~") else name.strip()


def numbered_functions(pairs: list[tuple[str, str]]) -> bool:
    """True when every pin function ends in _<pin number>, as KiCad 10 writes them."""
    return bool(pairs) and all(func.endswith(f"_{num}") for func, num in pairs)


def pin_function(func: str | None, num: str, numbered: bool) -> str:
    """Pin name from a KiCad pinfunction, without the pin number KiCad 10 appends."""
    name = _pin_name(func)
    return name[: -len(num) - 1] if numbered and name.endswith(f"_{num}") else name


def _flag(comp: ET.Element, name: str) -> bool:
    return any(p.get("name", "").lower() == name for p in comp.iter("property"))


def _comp_fields(comp: ET.Element) -> dict[str, str]:
    out = {f.get("name", ""): (f.text or "").strip() for f in comp.iter("field")}
    for prop in comp.iter("property"):
        out.setdefault(prop.get("name", ""), prop.get("value", "") or "")
    return out


def _is_dnp(comp: ET.Element, flds: dict[str, str], value: str) -> bool:
    for prop in comp.iter("property"):
        if prop.get("name", "").lower() == "dnp" and (prop.get("value") or "1").lower() not in ("0", "no", "false"):
            return True
    dnp_field = next((v for k, v in flds.items() if fields.canonical(k) == "dnp"), "")
    return fields.is_dnp_flag(dnp_field) or fields.value_says_dnp(value)


def parse_kicad_xml(text: str, path: str = "") -> BoardModel:
    """Parse a KiCad XML netlist: components with fields, pins with names and types, nets with classes."""
    root = ET.fromstring(text)
    if root.tag != "export":
        raise ValueError("not a KiCad XML netlist (root is not <export>)")
    model = BoardModel(pin_list_complete=True)
    libpins: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for lp in root.iter("libpart"):
        pins = [(p.get("num", ""), _pin_name(p.get("name")), p.get("type", "")) for p in lp.iter("pin")]
        libpins[(lp.get("lib", ""), lp.get("part", ""))] = pins
        for alias in lp.iter("alias"):
            libpins[(lp.get("lib", ""), _text(alias))] = pins
    comp_lib: dict[str, tuple[str, str]] = {}
    for comp in root.iter("comp"):
        ref = comp.get("ref", "")
        c = model.component(ref)
        flds = _comp_fields(comp)
        picked = fields.pick(flds)
        src = comp.find("libsource")
        c.value = _text(comp.find("value"))
        c.footprint = _text(comp.find("footprint"))
        c.description = _text(comp.find("description")) or picked.get("description", "") or (
            src.get("description", "") if src is not None else "")
        c.mpn = picked.get("mpn", "")
        c.manufacturer = picked.get("manufacturer", "")
        c.fitted = not _is_dnp(comp, flds, c.value)
        for flag in ("exclude_from_bom", "exclude_from_board"):
            if _flag(comp, flag):
                c.attrs[flag] = "yes"
        sheet = comp.find("sheetpath")
        if sheet is not None and sheet.get("names"):
            c.attrs["sheet"] = sheet.get("names", "")
        if src is not None:
            comp_lib[ref] = (src.get("lib", ""), src.get("part", ""))
        c.classify()
    numbered = numbered_functions([(n.get("pinfunction"), n.get("pin", "")) for n in root.iter("node")
                                   if n.get("pinfunction") is not None])
    for net in root.iter("net"):
        name = net.get("name", "")
        if net.get("class"):
            model.set_net_info(name, **{"class": net.get("class")})
        for node in net.iter("node"):
            ptype = node.get("pintype", "")
            num = node.get("pin", "")
            model.add_pin(node.get("ref", ""), num, name, pin_function(node.get("pinfunction"), num, numbered),
                          ptype.split("+")[0], no_connect="+no_connect" in ptype)
    for ref, key in comp_lib.items():
        for num, pname, ptype in libpins.get(key, []):
            model.add_pin(ref, num, None, pname, ptype)
    design = root.find("design")
    model.sources.append({"kind": "kicad_xml", "path": str(path), "tool": _text(design.find("tool"))
                          if design is not None else ""})
    return model.finalize()


def read_kicad_xml(path: str | Path) -> BoardModel:
    """Read a KiCad XML netlist file."""
    path = Path(path)
    return parse_kicad_xml(path.read_text(encoding="utf-8"), str(path))
