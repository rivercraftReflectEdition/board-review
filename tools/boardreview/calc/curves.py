"""Parse vendor curve exports (CSV text) into numeric columns; the caller reads the file."""

from __future__ import annotations

import re

import numpy as np

_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "M": 1e6, "G": 1e9}


def _delimiter(lines: list[str]) -> str:
    counts = {d: sum(ln.count(d) for ln in lines[-10:]) for d in ("\t", ";", ",")}
    return max(counts, key=counts.get)


def _num(field: str, decimal_comma: bool) -> float | None:
    s = field.strip().strip('"').replace(" ", "")
    if decimal_comma:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_csv_table(text: str) -> tuple[list[str], np.ndarray]:
    """Header names and numeric rows from CSV text with ',', ';' or tab delimiters."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty curve text")
    delim = _delimiter(lines)
    decimal_comma = delim == ";" and any("," in ln for ln in lines[-5:])
    header: list[str] = []
    rows: list[list[float]] = []
    for ln in lines:
        fields = ln.split(delim)
        vals = [_num(f, decimal_comma) for f in fields]
        if len(fields) >= 2 and all(v is not None for v in vals):
            rows.append(vals)
        elif not rows:
            header = [f.strip().strip('"') for f in fields]
    if not rows:
        raise ValueError("no numeric rows found")
    width = min(len(r) for r in rows)
    data = np.array([r[:width] for r in rows], dtype=float)
    return header[:width] if len(header) >= width else [f"col{i}" for i in range(width)], data


def find_column(headers: list[str], *keys: str) -> int:
    """Index of the first header containing any key, case-insensitive."""
    for i, h in enumerate(headers):
        if any(k.lower() in h.lower() for k in keys):
            return i
    raise ValueError(f"no column matching {keys} in {headers}")


def unit_scale(header: str, base: str) -> float:
    """SI scale for a header like 'Capacitance [uF]' or 'Frequency(MHz)' given the base unit."""
    m = re.search(r"[\[(]\s*([pnuµμmkMG]?)" + re.escape(base) + r"\s*[\])]", header)
    if m:
        return _PREFIX[m.group(1)]
    m = re.search(r"(?<![A-Za-z])([pnuµμmkMG]?)" + re.escape(base) + r"(?![A-Za-z])", header)
    return _PREFIX[m.group(1)] if m else 1.0
