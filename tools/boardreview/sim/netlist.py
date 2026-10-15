"""Parse a SPICE netlist (LTspice dialect first) into elements, nodes, libraries and subcircuit pin lists."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

GROUND = {"0", "gnd"}
_SUFFIX = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
           "n": 1e-9, "p": 1e-12, "f": 1e-15, "mil": 25.4e-6}
_NUM = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)(meg|mil|[tgkmuµμnpf])?[a-zΩ]*$", re.I)
_TWO = set("RCLVIBD")
_EG_KEYWORDS = ("value", "table", "poly", "laplace", "freq")


def parse_value(text: str | None) -> float | None:
    """SPICE number with suffix (6.8u, 6.8µ, 10meg, 2.2uF); None for expressions or empty."""
    if not text:
        return None
    m = _NUM.match(text.strip())
    if not m:
        return None
    scale = _SUFFIX.get((m.group(2) or "").lower(), 1.0)
    return float(m.group(1)) * scale


def norm_name(name: str) -> str:
    """Element name without LTspice's hierarchy marker, upper case: 'X§U1' -> 'XU1'."""
    return name.replace("§", "").upper()


@dataclass(frozen=True)
class Element:
    name: str
    nodes: tuple[str, ...]
    model: str | None
    value: str | None
    params: dict[str, str]
    line_no: int
    text: str
    pin_names: tuple[str, ...] | None = None

    @property
    def kind(self) -> str:
        return self.name[0].upper()

    def pin_label(self, i: int) -> str:
        """1-based pin number plus its name when known: 'pin 5 (Rt)'."""
        name = self.pin_names[i] if self.pin_names and i < len(self.pin_names) and self.pin_names[i] else ""
        return f"pin {i + 1}" + (f" ({name})" if name else "")


@dataclass
class Subckt:
    name: str
    pins: tuple[str, ...]
    elements: list[Element] = field(default_factory=list)


@dataclass
class Netlist:
    path: Path | None
    elements: list[Element]
    subckts: dict[str, Subckt]
    directives: list[tuple[int, str]]
    libs: list[tuple[int, str]]
    models: set[str]
    globals: set[str]

    def node_map(self, elements: list[Element] | None = None) -> dict[str, list[tuple[Element, int]]]:
        """Node (lower case) -> list of (element, 0-based terminal index)."""
        out: dict[str, list[tuple[Element, int]]] = {}
        for el in self.elements if elements is None else elements:
            for i, n in enumerate(el.nodes):
                out.setdefault(n.lower(), []).append((el, i))
        return out

    def directive(self, name: str) -> list[str]:
        """All directives of one kind, e.g. directive('.tran')."""
        return [d for _, d in self.directives if d.lower().split()[0] == name.lower()]

    def is_ground(self, node: str) -> bool:
        return node.lower() in GROUND or node.lower() in self.globals


def read_netlist_text(path: str | Path) -> str:
    """Netlist file text; LTspice writes UTF-8 (24+), older files may be UTF-16 or Latin-1."""
    blob = Path(path).read_bytes()
    if blob[:2] == b"\xff\xfe" or blob[1:2] == b"\x00":
        return blob.decode("utf-16-le", errors="replace").lstrip("﻿")
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("latin-1")


def parse_netlist(source: str | Path) -> Netlist:
    """Parse netlist text or a file. Line 1 is the title, as in every SPICE."""
    path = None
    if isinstance(source, Path) or ("\n" not in str(source) and Path(str(source)).exists()):
        path = Path(source)
        text = read_netlist_text(path)
    else:
        text = str(source)
    lines = _logical_lines(text)
    top: list[Element] = []
    subckts: dict[str, Subckt] = {}
    directives: list[tuple[int, str]] = []
    libs: list[tuple[int, str]] = []
    models: set[str] = set()
    globals_: set[str] = set()
    stack: list[Subckt] = []
    for line_no, line, pnba in lines:
        low = line.lower()
        if low.startswith(".subckt"):
            toks = line.split()
            pins = tuple(t for t in _positional(toks[2:]))
            sub = Subckt(toks[1], pins)
            subckts[toks[1].lower()] = sub
            stack.append(sub)
            continue
        if low.startswith(".ends"):
            if stack:
                stack.pop()
            continue
        if low.startswith("."):
            word = low.split()[0]
            if word in (".lib", ".include", ".inc") and not stack:
                libs.append((line_no, _lib_name(line)))
            elif word == ".model":
                parts = line.split()
                if len(parts) > 1:
                    models.add(parts[1].lower())
            elif word == ".global":
                globals_.update(n.lower() for n in line.split()[1:])
            if not stack:
                directives.append((line_no, line))
            continue
        el = _parse_element(line, line_no, pnba, models)
        if el is None:
            continue
        (stack[-1].elements if stack else top).append(el)
    top = [_fix_model_nodes(e, models) for e in top]
    for sub in subckts.values():
        sub.elements = [_fix_model_nodes(e, models) for e in sub.elements]
    return Netlist(path, top, subckts, directives, libs, models, globals_)


def _logical_lines(text: str) -> list[tuple[int, str, str | None]]:
    out: list[tuple[int, str, str | None]] = []
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(raw[1:], start=2):
        pnba = None
        m = re.search(r";\s*§pnba\s*(.*)$", line)
        if m:
            pnba = m.group(1)
        body = line.split(";", 1)[0].rstrip()
        stripped = body.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+") and out:
            n, prev, prev_pnba = out[-1]
            out[-1] = (n, prev + " " + stripped[1:].strip(), prev_pnba or pnba)
            continue
        out.append((i, stripped, pnba))
    return out


def _lib_name(line: str) -> str:
    rest = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
    rest = rest.strip()
    if rest.startswith(('"', "'")):
        return rest[1:].split(rest[0], 1)[0]
    return rest.split()[0] if rest else ""


def _positional(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        if t.lower() in ("params:", "param:") or "=" in t:
            break
        out.append(t)
    return out


def _params(tokens: list[str]) -> dict[str, str]:
    joined = " ".join(tokens)
    return {k.lower(): v for k, v in re.findall(r"([\w.]+)\s*=\s*(\{[^}]*\}|\S+)", joined)}


def _parse_element(line: str, line_no: int, pnba: str | None, models: set[str]) -> Element | None:
    toks = line.split()
    name = toks[0]
    kind = name[0].upper()
    rest = toks[1:]
    params = _params(rest)
    if kind == "K":
        return Element(name, (), None, None, params, line_no, line)
    if kind == "X":
        pos = _positional(rest)
        if not pos:
            return None
        pins = _pnba_names(pnba) if pnba else None
        return Element(name, tuple(pos[:-1]), pos[-1], None, params, line_no, line, pins)
    if kind in _TWO:
        nodes = tuple(rest[:2])
        value = rest[2] if len(rest) > 2 and "=" not in rest[2] else None
        model = value if kind == "D" else None
        return Element(name, nodes, model, value, params, line_no, line)
    if kind in "EG":
        n = 2 if len(rest) > 2 and (rest[2].lower().startswith(_EG_KEYWORDS) or "=" in rest[2]) else 4
        return Element(name, tuple(rest[:n]), None, " ".join(rest[n:]) or None, params, line_no, line)
    if kind in "FH":
        return Element(name, tuple(rest[:2]), rest[2] if len(rest) > 2 else None, None, params, line_no, line)
    if kind == "W":
        return Element(name, tuple(rest[:2]), rest[3] if len(rest) > 3 else None, rest[2] if len(rest) > 2 else None,
                       params, line_no, line)
    if kind in "ST":
        model = rest[4] if kind == "S" and len(rest) > 4 else None
        return Element(name, tuple(rest[:4]), model, None, params, line_no, line)
    if kind == "A":
        return Element(name, tuple(rest[:8]), rest[8] if len(rest) > 8 else None, None, params, line_no, line)
    if kind in "OU":
        pos = _positional(rest)
        n = 4 if kind == "O" else 3
        return Element(name, tuple(pos[:n]), pos[n] if len(pos) > n else None, None, params, line_no, line)
    if kind in "QMJZ":
        return Element(name, tuple(_positional(rest)), None, None, params, line_no, line)
    return None


def _fix_model_nodes(el: Element, models: set[str]) -> Element:
    """Split Q/M/J/Z tokens into nodes and model once every .model name is known (4th node is optional)."""
    if el.kind not in "QMJZ":
        return el
    pos = _positional(el.text.split()[1:])
    idx = next((i for i in range(3, len(pos)) if pos[i].lower() in models), None)
    if idx is None:
        idx = 4 if el.kind in "QM" and len(pos) >= 5 and parse_value(pos[4]) is None else 3
    model = pos[idx] if idx < len(pos) else None
    return Element(el.name, tuple(pos[:idx]), model, None, el.params, el.line_no, el.text, el.pin_names)


def _pnba_names(text: str) -> tuple[str, ...]:
    names = text.strip().split(")")
    if names and names[-1] == "":
        names = names[:-1]
    out = []
    for n in names:
        out.append(n if n else (out[-1] if out else ""))
    return tuple(out)


def ltspice_lib_dirs() -> list[Path]:
    """LTspice library roots that exist on this machine (24+ per-user, XVII documents, macOS)."""
    home = Path.home()
    candidates = []
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "LTspice" / "lib")
    candidates += [home / "AppData" / "Local" / "LTspice" / "lib", home / "Documents" / "LTspiceXVII" / "lib",
                   home / "Documents" / "LTspice" / "lib", home / "Library" / "Application Support" / "LTspice" / "lib"]
    seen, out = set(), []
    for c in candidates:
        key = str(c).lower()
        if c.exists() and key not in seen:
            seen.add(key)
            out.append(c)
    return out


def resolve_lib(name: str, netlist_dir: Path | None, extra_dirs: list[Path] | None = None) -> Path | None:
    """Find a .lib/.include file the way LTspice does: absolute, next to the netlist, then lib/sub and lib/cmp."""
    p = Path(name)
    if p.is_absolute():
        return p if p.exists() else None
    dirs = []
    if netlist_dir is not None:
        dirs.append(netlist_dir)
    dirs += list(extra_dirs or [])
    for root in ltspice_lib_dirs():
        dirs += [root / "sub", root / "cmp", root]
    for d in dirs:
        q = d / name
        if q.exists():
            return q
    return None


def is_encrypted(path: Path) -> bool:
    """True for ADI's binary or encrypted model files, whose pins cannot be read."""
    head = path.read_bytes()[:4096]
    if head.startswith(b"<Binary File>") or b"\x00" in head:
        return True
    if b"begin encrypted" in head.lower() or b"encrypted" in head[:200].lower():
        return True
    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in head)
    return printable < 0.9 * len(head)


def subckt_pins_in_file(path: Path, name: str) -> tuple[str, ...] | None:
    """Pin list of .subckt name in a plain-text library, or None."""
    text = read_netlist_text(path)
    lines = text.replace("\r", "").split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if not s.lower().startswith(".subckt"):
            continue
        toks = s.split()
        if len(toks) < 2 or toks[1].lower() != name.lower():
            continue
        j = i + 1
        while j < len(lines) and lines[j].strip().startswith("+"):
            toks += lines[j].strip()[1:].split()
            j += 1
        return tuple(_positional(toks[2:]))
    return None


def symbol_pins(name: str, extra_dirs: list[Path] | None = None) -> tuple[Path, tuple[str | None, ...]] | None:
    """Pins of an LTspice symbol NAME.asy in SpiceOrder; None marks an internally tied duplicate pin."""
    roots = list(extra_dirs or []) + [r / "sym" for r in ltspice_lib_dirs()]
    target = f"{name.lower()}.asy"
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.asy"):
            if p.name.lower() == target:
                return p, _asy_pins(p)
    return None


def _asy_pins(path: Path) -> tuple[str | None, ...]:
    text = read_netlist_text(path)
    order: dict[int, str] = {}
    current = None
    for line in text.replace("\r", "").split("\n"):
        parts = line.split(None, 2)
        if len(parts) >= 3 and parts[0] == "PINATTR" and parts[1] == "PinName":
            current = parts[2].strip()
        elif len(parts) >= 3 and parts[0] == "PINATTR" and parts[1] == "SpiceOrder" and current is not None:
            order[int(parts[2])] = current
            current = None
    if not order:
        return ()
    names: list[str | None] = []
    for i in range(1, max(order) + 1):
        names.append(order.get(i) or (f"{names[-1]} dup" if names and names[-1] else None))
    return tuple(names)
