"""CLI: python -m boardreview.blocks NETLIST_OR_BOARD_MODEL [--bom BOM] [--json OUT]."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from boardreview.blocks import find_all, to_markdown
from boardreview.model import loaders


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(prog="python -m boardreview.blocks")
    ap.add_argument("netlist", help="netlist file or board_model.json")
    ap.add_argument("--bom")
    ap.add_argument("--json", help="also write blocks with subgraphs as JSON here")
    args = ap.parse_args(argv)
    model, _ = loaders.load_with_bom(args.netlist, args.bom)
    blocks = find_all(model)
    if args.json:
        Path(args.json).write_text(json.dumps([b.to_dict() for b in blocks], indent=1) + "\n", encoding="utf-8")
    sys.stdout.write(to_markdown(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
