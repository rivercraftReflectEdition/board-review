"""Field and column names that different tools use for the same component attribute."""

from __future__ import annotations

import re


def _norm(header: str) -> str:
    bare = re.sub(r"^\$\{(.*)\}$", r"\1", header.strip())
    return re.sub(r"\s+", " ", bare.strip().lower().replace("_", " "))


_ALIASES = {
    "refdes": ["designator", "designators", "reference", "references", "ref", "refs", "refdes", "ref des",
               "part reference",
               "reference designator", "reference designators", "ref designator", "parts", "position"],
    "mpn": ["mpn", "manufacturer part number", "manufacturer part number 1", "manufacturer part", "mfr part number",
            "mfr part #", "mfr. part #", "mfr pn", "mfg part number", "mfg pn", "manufacturer pn", "part number",
            "pn", "name"],
    "manufacturer": ["manufacturer", "manufacturer 1", "manufacturer name", "mfr", "mfr.", "mfg", "vendor", "make"],
    "value": ["value", "val"],
    "comment": ["comment"],
    "footprint": ["footprint", "package", "pcb footprint", "case", "case/package"],
    "description": ["description", "desc", "part description"],
    "fitted": ["fitted", "populate", "populated", "mount", "stuff", "assembly", "place"],
    "dnp": ["dnp", "dni", "do not populate", "do not place", "no pop", "nopop", "not fitted", "exclude"],
    "quantity": ["quantity", "qty", "count"],
    "variant": ["variant"],
}
_LOOKUP = {_norm(alias): key for key, names in _ALIASES.items() for alias in names}
_RANK = {_norm(alias): i for names in _ALIASES.values() for i, alias in enumerate(names)}
_DNP_TRUE = {"x", "yes", "y", "true", "1", "dnp", "dni", "nf", "np", "not fitted", "do not populate", "no pop"}
_NOT_FITTED = {"no", "n", "false", "0", "not fitted", "dnp", "dni", "nf", "np", "not populated", "no pop"}


def canonical(header: str) -> str:
    """Canonical attribute key for a column or field name, or '' when unknown."""
    return _LOOKUP.get(_norm(header), "")


def rank(header: str) -> int:
    """Preference among columns that map to the same key; lower wins."""
    return _RANK.get(_norm(header), 99)


def pick(row: dict[str, str]) -> dict[str, str]:
    """Map a header->value row to canonical keys, preferring the most specific header per key."""
    best: dict[str, tuple[int, str]] = {}
    for header, value in row.items():
        key = canonical(header)
        if key and (value or "").strip():
            r = rank(header)
            if key not in best or r < best[key][0]:
                best[key] = (r, value.strip())
    return {k: v for k, (_, v) in best.items()}


def is_dnp_flag(text: str) -> bool:
    """True when a DNP-style column value says the part is not placed."""
    return text.strip().lower() in _DNP_TRUE


def is_not_fitted(text: str) -> bool:
    """True when a Fitted-style column value says the part is not placed."""
    return text.strip().lower() in _NOT_FITTED


def value_says_dnp(text: str) -> bool:
    """True when the value or comment itself is a DNP marker."""
    return bool(re.fullmatch(r"\s*(?:DNP|DNI|NF|NP|N/?F|NO ?POP|DO NOT (?:POPULATE|PLACE))\s*", text or "", re.I))


def expand_refdes(text: str) -> list[str]:
    """Split a designator cell: 'C1, C2 C3;R1-R4' -> [C1, C2, C3, R1, R2, R3, R4]."""
    out: list[str] = []
    for item in re.split(r"[,;\s]+", text.strip()):
        if not item:
            continue
        m = re.fullmatch(r"([A-Za-z_]+)(\d+)-(?:([A-Za-z_]+))?(\d+)", item)
        if m and m.group(3) in (None, m.group(1)) and 0 <= int(m.group(4)) - int(m.group(2)) <= 500:
            out += [f"{m.group(1)}{i}" for i in range(int(m.group(2)), int(m.group(4)) + 1)]
        else:
            out.append(item)
    return out
