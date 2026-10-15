"""Read SPICE .raw files (LTspice and ngspice, binary and ASCII) into numpy arrays."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

UNITS = {
    "time": "s",
    "frequency": "Hz",
    "voltage": "V",
    "current": "A",
    "device_current": "A",
    "subckt_current": "A",
    "power": "W",
    "impedance": "ohm",
}

_BINARY = "Binary:"
_VALUES = "Values:"


@dataclass(frozen=True)
class Variable:
    index: int
    name: str
    kind: str

    @property
    def unit(self) -> str:
        return UNITS.get(self.kind.lower(), "")


@dataclass
class RawFile:
    """One plot from a .raw file. data has shape (n_vars, n_points); complex for AC."""

    header: dict[str, str]
    variables: list[Variable]
    data: np.ndarray
    step_bounds: list[tuple[int, int]]
    step_params: list[dict[str, float]] = field(default_factory=list)
    path: Path | None = None

    @property
    def title(self) -> str:
        return self.header.get("title", "")

    @property
    def plotname(self) -> str:
        return self.header.get("plotname", "")

    @property
    def flags(self) -> set[str]:
        return set(self.header.get("flags", "").lower().split())

    @property
    def is_complex(self) -> bool:
        return np.iscomplexobj(self.data)

    @property
    def n_steps(self) -> int:
        return len(self.step_bounds)

    @property
    def names(self) -> list[str]:
        return [v.name for v in self.variables]

    def index(self, name: str) -> int:
        """Index of a variable by exact name, case-insensitive name, or bare node name."""
        names = [v.name for v in self.variables]
        if name in names:
            return names.index(name)
        low = [n.lower() for n in names]
        for candidate in (name.lower(), f"v({name.lower()})", f"i({name.lower()})"):
            if candidate in low:
                return low.index(candidate)
        raise KeyError(f"{name!r} not in raw file; have {', '.join(names)}")

    def unit(self, name: str) -> str:
        return self.variables[self.index(name)].unit

    def get(self, name: str, step: int | None = None) -> np.ndarray:
        """Values of one variable, for all points or one step."""
        row = self.data[self.index(name)]
        if step is None:
            return row
        a, b = self.step_bounds[step]
        return row[a:b]

    def axis(self, step: int | None = None) -> np.ndarray:
        """Sweep variable (time or frequency) as real floats."""
        row = self.data[0]
        if step is not None:
            a, b = self.step_bounds[step]
            row = row[a:b]
        return np.real(row)

    def __getitem__(self, name: str) -> np.ndarray:
        return self.get(name)


def read_raw(path: str | Path, log_path: str | Path | None = None, plot: int = -1) -> RawFile:
    """Read one plot (the last by default) and attach .step values from the sibling .log."""
    path = Path(path)
    plots = read_plots(path)
    raw = plots[plot]
    log = Path(log_path) if log_path else _sibling_log(path)
    if log is not None and log.exists():
        params = step_params_from_log(read_text_any(log.read_bytes()))
        if len(params) == raw.n_steps:
            raw.step_params = params
    return raw


def read_plots(path: str | Path) -> list[RawFile]:
    """Read every plot in a .raw file."""
    path = Path(path)
    blob = path.read_bytes()
    plots = []
    pos = 0
    while pos < len(blob):
        raw, pos = _read_one(blob, pos)
        raw.path = path
        plots.append(raw)
        while pos < len(blob) and blob[pos:pos + 1] in (b"\n", b"\r", b"\x00"):
            pos += 1
    if not plots:
        raise ValueError(f"{path}: no plots found")
    return plots


def read_text_any(blob: bytes) -> str:
    """Decode a log or header that may be UTF-16LE (LTspice XVII) or UTF-8."""
    if blob[:2] == b"\xff\xfe" or (len(blob) > 1 and blob[1:2] == b"\x00"):
        return blob.decode("utf-16-le", errors="replace").lstrip("﻿")
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("latin-1")


def step_params_from_log(text: str) -> list[dict[str, float]]:
    """Parameter values of each .step run as LTspice prints them in the log."""
    steps = []
    for line in text.splitlines():
        line = line.strip()
        if not line.lower().startswith(".step "):
            continue
        pairs = re.findall(r"([\w.]+)=(\S+)", line[6:])
        steps.append({k: _to_float(v) for k, v in pairs})
    return steps


def _sibling_log(path: Path) -> Path | None:
    name = path.name
    for suffix in (".op.raw", ".raw"):
        if name.lower().endswith(suffix):
            return path.with_name(name[: -len(suffix)] + ".log")
    return None


def _to_float(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _read_one(blob: bytes, pos: int) -> tuple[RawFile, int]:
    utf16 = blob[pos + 1:pos + 2] == b"\x00"
    enc = "utf-16-le" if utf16 else "latin-1"
    marker_pos, marker, line_end = _find_marker(blob, pos, enc)
    header_text = blob[pos:marker_pos].decode(enc)
    header, variables = _parse_header(header_text)
    data_pos = marker_pos + len(marker.encode(enc)) + len(line_end.encode(enc))
    n_vars = len(variables)
    n_points = int(header.get("no. points", "0"))
    flags = set(header.get("flags", "").lower().split())
    if marker == _VALUES:
        data, end = _parse_ascii(blob, data_pos, n_vars, n_points, "complex" in flags)
    else:
        data, end = _parse_binary(blob, data_pos, n_vars, n_points, flags, header.get("command", ""))
    if variables and variables[0].kind.lower() == "time":
        data[0] = np.abs(data[0])
    raw = RawFile(header=header, variables=variables, data=data, step_bounds=_split_steps(data[0], flags))
    return raw, end


def _find_marker(blob: bytes, pos: int, enc: str) -> tuple[int, str, str]:
    best = None
    for marker in (_BINARY, _VALUES):
        for line_end in ("\r\n", "\n"):
            needle = (marker + line_end).encode(enc)
            i = blob.find(needle, pos)
            if i >= 0 and (best is None or i < best[0]):
                best = (i, marker, line_end)
    if best is None:
        raise ValueError("raw file header has no 'Binary:' or 'Values:' line")
    return best


def _parse_header(text: str) -> tuple[dict[str, str], list[Variable]]:
    header: dict[str, str] = {}
    variables: list[Variable] = []
    in_vars = False
    for line in text.replace("\r", "").split("\n"):
        if not line.strip():
            continue
        if in_vars and (line.startswith("\t") or line.startswith(" ")):
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                variables.append(Variable(int(parts[0]), parts[1], parts[2]))
                continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        in_vars = key == "variables"
        if not in_vars:
            header[key] = value.strip()
    return header, variables


def _parse_ascii(blob: bytes, pos: int, n_vars: int, n_points: int, is_complex: bool) -> tuple[np.ndarray, int]:
    end = blob.find(b"Title:", pos)
    end = len(blob) if end < 0 else end
    tokens = blob[pos:end].decode("latin-1").split()
    per_point = n_vars + 1
    if n_points * per_point > len(tokens):
        n_points = len(tokens) // per_point
    tokens = tokens[: n_points * per_point]
    if is_complex:
        pairs = [t.split(",") for t in tokens]
        values = [complex(float(p[0]), float(p[1]) if len(p) > 1 else 0.0) for p in pairs]
        data = np.array(values, dtype=np.complex128).reshape(n_points, per_point)[:, 1:]
    else:
        data = np.array(tokens, dtype=np.float64).reshape(n_points, per_point)[:, 1:]
    return np.ascontiguousarray(data.T), end


def _parse_binary(
    blob: bytes, pos: int, n_vars: int, n_points: int, flags: set[str], command: str
) -> tuple[np.ndarray, int]:
    if "complex" in flags:
        size = n_points * n_vars * 16
        arr = np.frombuffer(blob, dtype="<c16", count=n_points * n_vars, offset=pos)
        return arr.reshape(n_points, n_vars).T.copy(), pos + size
    all_double = "double" in flags or "ngspice" in command.lower()
    if not all_double and not _fits_mixed(blob, pos, n_vars, n_points):
        all_double = len(blob) - pos >= n_points * n_vars * 8
    if all_double:
        size = n_points * n_vars * 8
        if "fastaccess" in flags:
            arr = np.frombuffer(blob, dtype="<f8", count=n_points * n_vars, offset=pos).reshape(n_vars, n_points)
            return arr.copy(), pos + size
        arr = np.frombuffer(blob, dtype="<f8", count=n_points * n_vars, offset=pos).reshape(n_points, n_vars)
        return arr.T.copy(), pos + size
    return _parse_mixed(blob, pos, n_vars, n_points, "fastaccess" in flags)


def _fits_mixed(blob: bytes, pos: int, n_vars: int, n_points: int) -> bool:
    return len(blob) - pos == n_points * (8 + 4 * (n_vars - 1))


def _parse_mixed(blob: bytes, pos: int, n_vars: int, n_points: int, fastaccess: bool) -> tuple[np.ndarray, int]:
    """LTspice default: sweep variable as float64, every other variable as float32."""
    size = n_points * (8 + 4 * (n_vars - 1))
    out = np.empty((n_vars, n_points), dtype=np.float64)
    if fastaccess:
        out[0] = np.frombuffer(blob, dtype="<f8", count=n_points, offset=pos)
        rest = np.frombuffer(blob, dtype="<f4", count=n_points * (n_vars - 1), offset=pos + 8 * n_points)
        out[1:] = rest.reshape(n_vars - 1, n_points)
        return out, pos + size
    rec = np.dtype([("axis", "<f8"), ("vals", "<f4", (n_vars - 1,))])
    arr = np.frombuffer(blob, dtype=rec, count=n_points, offset=pos)
    out[0] = arr["axis"]
    out[1:] = arr["vals"].T
    return out, pos + size


def _split_steps(axis: np.ndarray, flags: set[str]) -> list[tuple[int, int]]:
    n = len(axis)
    if n == 0:
        return []
    if "stepped" not in flags:
        return [(0, n)]
    x = np.real(axis)
    starts = [0] + [int(i) + 1 for i in np.nonzero(np.diff(x) < 0)[0]]
    ends = starts[1:] + [n]
    return list(zip(starts, ends))
