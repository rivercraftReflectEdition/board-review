"""CLI: python -m boardreview.lint NETLIST_OR_BOARD_MODEL [--bom BOM] [--json OUT]."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from boardreview.console import utf8_stdio
from boardreview.lint import run_all
from boardreview.model import loaders


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="python -m boardreview.lint")
    ap.add_argument("netlist", help="netlist file or board_model.json")
    ap.add_argument("--bom")
    ap.add_argument("--json", help="also write findings as JSON here")
    args = ap.parse_args(argv)
    model, _ = loaders.load_with_bom(args.netlist, args.bom)
    report = run_all(model)
    if args.json:
        Path(args.json).write_text(json.dumps(report.to_dict(), indent=1) + "\n", encoding="utf-8")
    sys.stdout.write(report.to_markdown())
    return 1 if any(f.severity == "error" for f in report.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
