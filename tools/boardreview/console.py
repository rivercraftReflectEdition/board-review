"""Console encoding for the command-line entry points."""

from __future__ import annotations

import sys


def utf8_stdio() -> None:
    """Write stdout and stderr as UTF-8, so Ω, µ and ° never crash a cp1252 console or pipe on Windows."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "").replace("_", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
