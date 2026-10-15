"""IPC-D-356 / 356A netlist importer (the bare-board test netlist a fab package carries)."""

from __future__ import annotations

import re
from pathlib import Path

from boardreview.model.board import BoardModel

_RECORD_CODES = {"317", "327", "367"}
_ALIAS = re.compile(r"^P\s+NNAME(\d+)\s+(.+?)\s*$")
_PARAM = re.compile(r"^P\s+(JOB|TITLE|REV|VER|UNITS|NUM|IMAGE)\s*(.*?)\s*$")


def _pin_field(line: str) -> tuple[str, bool]:
    """Pin number and mid-point flag; tolerates pins that overflow the 4-column field."""
    if len(line) > 31 and line[31] not in " M":
        token = line[27:].split()[0]
        return token, False
    return line[27:31].strip(), line[31:32] == "M"


def parse_ipc356(text: str, path: str = "") -> BoardModel:
    """Parse IPC-D-356 text: pads with refdes become pins, VIA records become via counts per net."""
    model = BoardModel(pin_list_complete=True)
    aliases: dict[str, str] = {}
    params: dict[str, str] = {}
    vias: dict[str, int] = {}
    for line in text.splitlines():
        m = _ALIAS.match(line)
        if m:
            aliases[m.group(1)] = m.group(2)
            continue
        m = _PARAM.match(line)
        if m:
            params[m.group(1).lower()] = m.group(2)
            continue
        if line[:3] not in _RECORD_CODES:
            continue
        raw = line[3:17].strip()
        net = aliases.get(raw.removeprefix("NNAME"), raw) if raw.removeprefix("NNAME").isdigit() else raw
        refdes = line[20:26].strip()
        if not refdes or line[26:27] != "-":
            continue
        pin, midpoint = _pin_field(line)
        if refdes.upper() == "VIA" or midpoint:
            if net and net.upper() != "N/C":
                vias[net] = vias.get(net, 0) + 1
            continue
        model.add_pin(refdes, pin, net)
    for net, count in vias.items():
        model.set_net_info(net, vias=count)
    source = {"kind": "ipc356", "path": str(path)}
    source.update({k: v for k, v in params.items() if v})
    model.sources.append(source)
    return model.finalize()


def read_ipc356(path: str | Path) -> BoardModel:
    """Read an IPC-D-356 file."""
    path = Path(path)
    return parse_ipc356(path.read_text(encoding="latin-1"), str(path))
