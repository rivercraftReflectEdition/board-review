"""Pick an importer from the file: IPC-D-356, KiCad XML or board, Protel .NET, eda-agent JSON or board_model.json."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree.ElementTree import ParseError

from boardreview.model import bom, eda_agent, ipc356, kicad, kicad_pcb, protel, serialize
from boardreview.model.board import SCHEMA_ID, BoardModel


def _json_kind(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return "board_model" if isinstance(data, dict) and data.get("schema") == SCHEMA_ID else "eda_agent_json"


def sniff(path: str | Path) -> str:
    """Netlist format name: ipc356, kicad_xml, kicad_pcb, protel_net, eda_agent_json or board_model."""
    path = Path(path)
    suffix = path.suffix.lower()
    head = path.read_bytes()[:4096].decode("latin-1", errors="replace").lstrip("﻿\xef\xbb\xbf \r\n\t")
    if suffix == ".json" or head.startswith("{"):
        return _json_kind(path)
    if head.startswith("(kicad_pcb"):
        return "kicad_pcb"
    if head.startswith("(export"):
        raise ValueError("KiCad s-expression netlist: export with --format kicadxml instead")
    if head.startswith("<"):
        return "kicad_xml"
    lines = head.splitlines()
    if suffix in (".ipc", ".d356", ".356", ".ipc356") or any(ln[:3] in ("317", "327", "367") for ln in lines):
        return "ipc356"
    if suffix == ".net" or head.startswith(("[", "(", "PROTEL")):
        return "protel_net"
    raise ValueError(f"cannot tell the netlist format of {path}")


def load(path: str | Path, fmt: str = "", variant: str = "") -> BoardModel:
    """Load a netlist or board_model.json into a BoardModel."""
    fmt = fmt or sniff(path)
    if fmt == "ipc356":
        return ipc356.read_ipc356(path)
    if fmt == "kicad_xml":
        return kicad.read_kicad_xml(path)
    if fmt == "kicad_pcb":
        return kicad_pcb.read_kicad_pcb(path)
    if fmt == "protel_net":
        return protel.read_protel(path)
    if fmt == "eda_agent_json":
        return eda_agent.read_eda_agent(path, variant)
    if fmt == "board_model":
        return serialize.read_json(path)
    raise ValueError(f"unknown format {fmt!r}")


def load_with_bom(netlist: str | Path, bom_path: str | Path | None = None, fmt: str = "",
                  variant: str = "") -> tuple[BoardModel, dict[str, list[str]]]:
    """Load a netlist and merge a BOM when given; errors name the file that failed."""
    try:
        model = load(netlist, fmt, variant)
    except (ValueError, OSError, ParseError) as exc:
        raise ValueError(f"netlist {netlist}: {exc}") from exc
    if not bom_path:
        return model, {}
    try:
        lines = bom.read_bom(bom_path)
    except (ValueError, OSError) as exc:
        raise ValueError(f"BOM {bom_path}: {exc}") from exc
    return model, bom.apply_bom(model, lines, str(bom_path))
