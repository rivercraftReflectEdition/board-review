"""Part classification and value parsing from refdes, description, MPN and value text."""

from __future__ import annotations

import re

_PREFIX = re.compile(r"^([A-Za-z_]+)")

_KIND_BY_PREFIX = [
    ("FID", "mechanical"), ("MH", "mechanical"), ("NUT", "mechanical"), ("STO", "mechanical"),
    ("TP", "testpoint"), ("LED", "led"), ("FB", "ferrite"), ("RN", "resistor"), ("RA", "resistor"),
    ("CN", "connector"), ("CON", "connector"), ("JP", "jumper"), ("SW", "switch"), ("BT", "battery"),
    ("OSC", "oscillator"), ("XTAL", "crystal"), ("IC", "ic"), ("VR", "ic"), ("PS", "ic"), ("CR", "diode"),
    ("ZD", "diode"), ("TVS", "tvs"), ("ESD", "tvs"), ("TR", "transformer"),
    ("R", "resistor"), ("C", "capacitor"), ("L", "inductor"), ("D", "diode"), ("Q", "transistor"),
    ("M", "transistor"), ("U", "ic"), ("Y", "crystal"), ("X", "crystal"), ("J", "connector"), ("P", "connector"),
    ("F", "fuse"), ("K", "relay"), ("T", "transformer"), ("H", "mechanical"), ("S", "switch"),
    ("FL", "ferrite"), ("A", "ic"),
]

_DESC_KIND = [
    (re.compile(r"ferrite|\bbead", re.I), "ferrite"),
    (re.compile(r"\btvs\b|\besd\b|suppress|transient|clamp|rclamp", re.I), "tvs"),
    (re.compile(r"oscillator|\bxo\b|\btcxo\b|\bvcxo\b|mems clock", re.I), "oscillator"),
    (re.compile(r"crystal|\bxtal\b|resonator", re.I), "crystal"),
    (re.compile(r"transformer|magnetics", re.I), "transformer"),
    (re.compile(r"mounting hole|fiducial|\bnut\b|standoff", re.I), "mechanical"),
    (re.compile(r"test ?point", re.I), "testpoint"),
    (re.compile(r"\bled\b", re.I), "led"),
    (re.compile(r"current source|regulator|\bldo\b|converter|controller", re.I), "ic"),
]
_MPN_FERRITE = re.compile(r"^(?:BLM|BLE|BLA|MPZ|MMZ|HZ|KPZ|FBMH|BK\d|MI\d|742\d|7427|CIM|HI\d)", re.I)

_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3,
       "M": 1e6, "G": 1e9, "R": 1.0, "r": 1.0, "": 1.0}
_VALUE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(meg|[pnuµμmkKMGRr]?)(\d*)\s*(ohms?|Ω|F|H|Hz)?\s*$", re.I)
_UNIT_KINDS = {"ohm": {"resistor", "ferrite", "jumper"}, "f": {"capacitor"}, "h": {"inductor"},
               "hz": {"crystal", "oscillator"}}
_KINDS_WITH_UNITS = set().union(*_UNIT_KINDS.values())


def _unit_fits(unit: str | None, kind: str) -> bool:
    """False when the value names a unit that the part kind cannot have (1mF on a resistor)."""
    if not unit or kind not in _KINDS_WITH_UNITS:
        return True
    key = "ohm" if unit.lower().startswith("ohm") else unit.lower()
    return kind in _UNIT_KINDS.get(key, set())


def prefix(refdes: str) -> str:
    """Letter prefix of a reference designator (R12 -> R, LED3 -> LED)."""
    m = _PREFIX.match(refdes.strip())
    return m.group(1).upper() if m else ""


def kind_of(refdes: str, description: str = "", mpn: str = "", value: str = "") -> str:
    """Component kind from description and MPN first, then the refdes prefix."""
    text = " ".join(x for x in (description, value) if x)
    pre = prefix(refdes)
    for pat, kind in _DESC_KIND:
        if pat.search(text):
            if kind == "ic" and pre not in ("U", "IC", "Q", "VR", "PS", "A"):
                continue
            if kind == "led" and pre not in ("D", "LED", "CR"):
                continue
            return kind
    if mpn and _MPN_FERRITE.match(mpn) and pre in ("L", "FB", "FL", "E", "B"):
        return "ferrite"
    for p, kind in _KIND_BY_PREFIX:
        if pre == p:
            return kind
    return "other"


def parse_value(text: str, kind: str = "") -> float | None:
    """SI value from component value text: 10k, 4k7, 4.7u, 100nF, 0R, 1R5, 240 ohm, 2.2n."""
    if not text:
        return None
    s = text.strip().replace("Ω", "ohm")
    m = _VALUE.match(s)
    if not m:
        return None
    num, mult, tail, unit = m.groups()
    if not _unit_fits(unit, kind):
        return None
    num = num.replace(",", ".")
    if tail and "." not in num:
        num = f"{num}.{tail}"
    elif tail:
        return None
    key = mult
    if mult.lower() == "meg":
        key = "M"
    elif kind == "capacitor" and mult in ("U", "N", "P"):
        key = mult.lower()
    elif kind in ("capacitor", "inductor") and mult == "M":
        key = "m"
    if key not in _SI:
        return None
    return float(num) * _SI[key]


_DESC_PATTERNS = {
    "capacitor": [re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*([pnuµμ])F?\b", re.I),
                  re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*()F\b")],
    "inductor": [re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*([pnuµμm])H\b", re.I),
                 re.compile(r"^(\d+(?:\.\d+)?)([nuµμ])\b")],
    "resistor": [re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*([kKmMG]?)\s*(?:ohms?|Ω)", re.I),
                 re.compile(r"(?<![\w.])(\d+[kKMR]\d+)\b"),
                 re.compile(r"(?<![\w.%])(\d+(?:\.\d+)?)([kKM]?)\s+\d+(?:\.\d+)?%")],
    "ferrite": [re.compile(r"(\d+(?:\.\d+)?)\s*(?:ohms?|Ω|R)\b[^,;]*?(?:@|at)?\s*100\s*MHz", re.I),
                re.compile(r"(\d+(?:\.\d+)?)\s*(?:ohms?|Ω)", re.I)],
}


def value_from_description(description: str, kind: str) -> str:
    """Value text pulled from a BOM description, or '' when none is found."""
    for pat in _DESC_PATTERNS.get(kind, []):
        m = pat.search(description or "")
        if not m:
            continue
        groups = [g for g in m.groups() if g is not None]
        if kind == "ferrite":
            return f"{groups[0]}R@100MHz" if "MHz" in m.group(0) else f"{groups[0]}R"
        text = "".join(groups)
        unit = {"capacitor": "F", "inductor": "H"}.get(kind, "")
        if kind == "resistor" and re.fullmatch(r"\d+(?:\.\d+)?", text):
            return text
        return text + (unit if text[-1:].isalpha() and unit else "")
    return ""


_LIB_KIND = {"C": {"capacitor"}, "CP": {"capacitor"}, "R": {"resistor"}, "L": {"inductor"},
             "FB": {"ferrite"}, "FL": {"ferrite"}}
_LIB_WORDS = re.compile(r"^(?:Pol|Polarized|Small|Elec|Tant|Tantalum|US|EU)$", re.I)
_LIB_VALUE = re.compile(r"^\d+(?:\.\d+)?[pnuµμmkKMGRr]\d*(?:F|H)?$|^\d+(?:\.\d+)?(?:F|H)$")


def library_value(text: str, kind: str) -> float | None:
    """SI value of a KiCad library-style value: C_10u_0603, R_52k3_0402, C_Pol_330u_6.3V, FB_120Z_3A_0603."""
    toks = [t for t in (text or "").strip().split("_") if t]
    if len(toks) < 2 or kind not in _LIB_KIND.get(toks[0].upper(), set()):
        return None
    i = 1
    while i < len(toks) - 1 and _LIB_WORDS.match(toks[i]):
        i += 1
    tok = toks[i]
    if kind == "ferrite":
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:R|Z|ohms?|Ω)", tok, re.I)
        return float(m.group(1)) if m else None
    return parse_value(tok, kind) if _LIB_VALUE.match(tok) else None


def value_si(value: str, kind: str) -> float | None:
    """SI value of a component, handling ferrite '120R@100MHz' as ohms and KiCad library-style values."""
    if kind == "ferrite":
        m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(?:R|ohms?|Ω)", value or "", re.I)
        return float(m.group(1)) if m else library_value(value, kind)
    got = parse_value(value, kind)
    return got if got is not None else library_value(value, kind)
