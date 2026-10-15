"""CLI: build the board model, digests, lint and blocks, or compare two or three netlists."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from boardreview.model import compare, digest, loaders, serialize


def _build(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model, bom_check = loaders.load_with_bom(args.netlist, args.bom, args.format, args.variant)
    serialize.write_json(model, out / "board_model.json")
    if bom_check:
        (out / "bom_check.json").write_text(json.dumps(bom_check, indent=1) + "\n", encoding="utf-8")
    edges: list[str] = []
    if not args.model_only:
        from boardreview import blocks, lint

        found = blocks.find_all(model)
        edges = blocks.power_edges(found)
        (out / "blocks.json").write_text(json.dumps([b.to_dict() for b in found], indent=1) + "\n", encoding="utf-8")
        (out / "blocks.md").write_text(blocks.to_markdown(found), encoding="utf-8")
        report = lint.run_all(model)
        (out / "lint.json").write_text(json.dumps(report.to_dict(), indent=1) + "\n", encoding="utf-8")
        (out / "lint.md").write_text(report.to_markdown(), encoding="utf-8")
    digest.write_digests(model, out, edges)
    stats = serialize.to_dict(model)["stats"]
    print(f"{stats['components']} components, {stats['pins']} pins, {stats['nets']} nets -> {out}")
    for w in model.warnings[:20]:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def _compare(args: argparse.Namespace) -> int:
    labels = args.labels.split(",") if args.labels else ["schematic", "pcb", "fab"][: len(args.netlists)]
    if len(labels) != len(args.netlists):
        raise SystemExit("--labels needs one label per netlist")
    report = compare.compare([(lab, loaders.load(p)) for lab, p in zip(labels, args.netlists)])
    write_compare(report, Path(args.out))
    print(report.to_markdown(limit=10))
    return 0


def write_compare(report: compare.CompareReport, out: Path) -> None:
    """compare.md and compare.json in out."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare.md").write_text(report.to_markdown(), encoding="utf-8")
    (out / "compare.json").write_text(json.dumps(report.to_dict(), indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(prog="python -m boardreview.model")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="board_model.json, digests, lint and blocks from a netlist and BOM")
    b.add_argument("netlist")
    b.add_argument("--bom")
    b.add_argument("--format", default="", help="ipc356, kicad_xml, kicad_pcb, protel_net, eda_agent_json, board_model")
    b.add_argument("--variant", default="")
    b.add_argument("--out", required=True)
    b.add_argument("--model-only", action="store_true")
    c = sub.add_parser("compare", help="2- or 3-way connectivity compare")
    c.add_argument("netlists", nargs="+")
    c.add_argument("--labels", default="")
    c.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    return _build(args) if args.cmd == "build" else _compare(args)


if __name__ == "__main__":
    sys.exit(main())
