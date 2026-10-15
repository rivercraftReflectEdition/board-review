"""Find kicad-cli and the KiCad demo projects, so KiCad tests can skip when either is absent."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path


def _version_key(path: Path) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", path.parent.parent.name)] or [0]


def kicad_cli() -> Path | None:
    """kicad-cli from KICAD_CLI, PATH, a per-user or Program Files install, macOS or Linux."""
    found = [os.environ.get("KICAD_CLI", ""), shutil.which("kicad-cli") or ""]
    roots = [(os.environ.get("LOCALAPPDATA", ""), "Programs/KiCad"), (os.environ.get("ProgramFiles", ""), "KiCad"),
             (os.environ.get("ProgramW6432", ""), "KiCad")]
    for base, sub in roots:
        if base:
            found += sorted((Path(base) / sub).glob("*/bin/kicad-cli.exe"), key=_version_key, reverse=True)
    found += ["/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli", "/usr/bin/kicad-cli", "/usr/local/bin/kicad-cli"]
    return next((Path(p) for p in found if p and Path(p).is_file()), None)


def demos_dir(cli: Path | None = None) -> Path | None:
    """The demos folder that ships with KiCad."""
    cli = cli or kicad_cli()
    roots = [cli.parent.parent / "share" / "kicad" / "demos", cli.parent.parent / "SharedSupport" / "demos"] if cli else []
    roots += [Path("/usr/share/kicad/demos"), Path("/usr/local/share/kicad/demos")]
    return next((r for r in roots if r.is_dir()), None)
