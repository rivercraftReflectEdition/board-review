"""CLI: python -m boardreview prep | report | verify-fixes | validate (see --help of each)."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path
from xml.etree.ElementTree import ParseError

from boardreview import schema
from boardreview.lint import Finding, to_findings
from boardreview.model import compare, digest, loaders, placement, serialize
from boardreview.model.board import BoardModel
from boardreview.model.__main__ import main as model_main
from boardreview.model.__main__ import write_compare
from boardreview.report import build as report_build

DEFAULT_LABELS = ["schematic", "pcb", "fab"]
NOT_IN_PREP = [
    "NET-2 compiler messages and NET-3 project contents: from the CAD tool (workflow/10_extract.md).",
    "NET-5 floating inputs, NET-6 value outliers and NET-8 symbol pins against digests: no lint check yet; "
    "use nets_by_component.md and pinmaps/.",
    "Snapshot diff (NET-3, NET-4): python -m boardreview.model compare against the previous board_model.json.",
]
PAIR_COUNTS = [("only_a", "parts only in {a}"), ("only_b", "parts only in {b}"), ("pins_only_a", "pins only in {a}"),
               ("pins_only_b", "pins only in {b}"), ("renamed", "nets renamed"), ("merged", "nets merged"),
               ("split", "nets split"), ("moved", "pins on another net"), ("removed", "nets only in {a}"),
               ("added", "nets only in {b}"),
               ("truncated", "net names cut by the IPC-D-356 field (format limit, not renames)"),
               ("fitted_differs", "parts fitted in one source and DNP in the other"),
               ("cut_refs", "designators cut by the IPC-D-356 field (format limit)"),
               ("cut_pins", "pin numbers cut by the IPC-D-356 field (format limit)"),
               ("open_only_a", "pins with no net only in {a} (not a connectivity difference)"),
               ("open_only_b", "pins with no net only in {b} (not a connectivity difference)"),
               ("mech_only_a", "mechanical, test, pinless or board-excluded parts only in {a}"),
               ("mech_only_b", "mechanical, test, pinless or board-excluded parts only in {b}")]


def _quiet(argv: list[str]) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        model_main(argv)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _input_row(role: str, path: str, fmt: str = "") -> str:
    p = Path(path)
    if not fmt:
        try:
            fmt = loaders.sniff(p)
        except ValueError:
            fmt = p.suffix.lstrip(".") or "?"
    return f"| {role} | {p.name} | {fmt} | {hashlib.sha256(p.read_bytes()).hexdigest()} |"


def _pair_line(pair: dict) -> str:
    bits = [f"{len(pair[k])} {text.format(a=pair['a'], b=pair['b'])}" for k, text in PAIR_COUNTS if pair[k]]
    return f"{pair['a']} vs {pair['b']}: " + (", ".join(bits) if bits else "no differences")


def _written(out: Path, has_bom: bool, compared: bool, placed: tuple[str, int] | None) -> list[str]:
    model = _read(out / "board_model.json")
    st = model["stats"]
    lint = _read(out / "lint.json")
    sev = Counter(f["severity"] for f in lint["findings"])
    blocks = _read(out / "blocks.json")
    kinds = Counter(b["kind"] for b in blocks)
    low = sum(1 for b in blocks if b["confidence"] == "low")
    edges = sum(kinds[k] for k in ("switching_regulator", "ferrite_filter", "lc_filter"))
    pinmaps = digest.pin_map_refs(serialize.read_json(out / "board_model.json"))
    rows = [
        ("board_model.json", "parts, pins and nets (skill/schemas/board_model.schema.json)",
         f"{st['components']} components, {st['pins']} pins, {st['nets']} nets, "
         f"{st['unconnected_pins']} pins with no net; model warnings: {len(model['warnings'])}"),
        ("nets_by_net.md", "every net with its pins", f"{st['nets']} nets"),
        ("nets_by_component.md", "every part with the net on each pin", f"{st['components']} components"),
        ("power_tree.md", "rails with evidence, converters and filters, grounds", f"{edges} converters and filters"),
        ("pinmaps/", "one pin table per IC, connector and other multi-pin part",
         f"{len(pinmaps)} files"),
        ("lint.md, lint.json", "deterministic netlist and BOM checks",
         f"{sev['error']} errors, {sev['warning']} warnings, {sev['info']} info from {len(lint['ran'])} checks"),
        ("lint_findings.json", "lint results as candidate findings, verification PENDING",
         f"{len(lint['findings'])} findings"),
        ("blocks.md, blocks.json", "candidate blocks for stage 3",
         (", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(kinds.items())) or "none")
         + f"; {low} low confidence"),
    ]
    if has_bom:
        check = _read(out / "bom_check.json")
        excluded = check.get("excluded_from_bom", [])
        rows.insert(1, ("bom_check.json", "BOM against netlist", f"{len(check['bom_only'])} only in the BOM, "
                        f"{len(check['netlist_only'])} only in the netlist"
                        + (f", {len(excluded)} excluded from the BOM by the schematic" if excluded else "")))
    if compared:
        cmp = _read(out / "compare.json")
        text = "; ".join(_pair_line(p) for p in cmp["pairs"])
        if len(cmp["labels"]) == 3:
            text += f"; {len(cmp['disagreements'])} pins where the three disagree"
        rows.append(("compare.md, compare.json", f"connectivity compare, {' / '.join(cmp['labels'])}", text))
    if placed:
        rows.append(("placement.md, placement.json", f"part side, position and rotation from {placed[0]}",
                     f"{placed[1]} parts"))
    return [f"| {f} | {what} | {n} |" for f, what, n in rows]


def _facts(args: argparse.Namespace, out: Path, skipped: dict[str, str], compared: bool,
           placed: tuple[str, int] | None) -> str:
    labels = args.labels.split(",") if args.labels else DEFAULT_LABELS[: 1 + len(args.compare)]
    inputs = [_input_row("netlist" + (f" ({labels[0]})" if compared else ""), args.netlist, args.format)]
    if args.bom:
        inputs.append(_input_row("bom", args.bom, Path(args.bom).suffix.lstrip(".")))
    inputs += [_input_row(f"compare ({lab})", p) for lab, p in zip(labels[1:], args.compare)]
    lint = _read(out / "lint.json")
    skips = {f"lint {k}": v for k, v in lint["skipped"].items()} | skipped
    lines = ["# Facts", "", "Written by `python -m boardreview prep`. Read this first, then open the files it names.",
             "Files in this folder that are not listed here were not written by this run.", "",
             "## Inputs", "", "| Role | File | Format | SHA-256 |", "|---|---|---|---|", *inputs, "",
             "## Written", "", "| File | What | Counts |", "|---|---|---|",
             *_written(out, bool(args.bom), compared, placed), "",
             "## Skipped", ""]
    lines += [f"- {k}: {v}" for k, v in skips.items()] or ["Nothing skipped."]
    lines += ["", "## Not run by prep", ""] + [f"- {t}" for t in NOT_IN_PREP] + [""]
    return "\n".join(lines)


def _placement(out: Path, inputs: list[tuple[str, BoardModel]], own: BoardModel,
               skipped: dict[str, str]) -> tuple[str, int] | None:
    """placement.md and placement.json from a .kicad_pcb among the inputs, else from IPC-D-356."""
    places: list[tuple[placement.Placement, BoardModel]] = []
    for path, model in inputs:
        board = placement.from_board(model, Path(path).name)
        try:
            if board is None and placement.sniff(path) == "ipc356":
                board, model = placement.read_placement(path), own
        except (OSError, ValueError) as exc:
            skipped[f"placement from {Path(path).name}"] = str(exc)
        if board is not None:
            places.append((board, model))
    chosen, notes = placement.choose([p for p, _ in places])
    if chosen is None:
        skipped["placement"] = ("no .kicad_pcb or IPC-D-356 given; side, position and rotation come from the CAD"
                                " tool or the pick-and-place file, by hand")
        return None
    chosen.notes += notes
    model = next(m for p, m in places if p is chosen)
    (out / placement.SAVED).write_text(chosen.to_json(), encoding="utf-8", newline="\n")
    (out / "placement.md").write_text(placement.to_markdown(chosen, model), encoding="utf-8", newline="\n")
    return chosen.source, len(chosen.parts)


def _prep(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    skipped: dict[str, str] = {}
    compared = False
    # Compare first so a previous board_model.json named as an input is read before build replaces it.
    loaded: list[tuple[str, BoardModel]] = []
    if args.compare:
        labels = args.labels.split(",") if args.labels else DEFAULT_LABELS[: 1 + len(args.compare)]
        try:
            models = [(labels[0], loaders.load(args.netlist, args.format, args.variant))]
            models += [(lab, loaders.load(p)) for lab, p in zip(labels[1:], args.compare)]
            write_compare(compare.compare(models), out)
            compared = True
            loaded = list(zip([args.netlist, *args.compare], [m for _, m in models]))
        except (ValueError, OSError, ParseError) as exc:
            skipped["compare (NET-1)"] = f"could not load a netlist: {exc}"
        if len(args.compare) == 1:
            skipped["3-way compare (NET-1)"] = "two netlists given; the pin table where sources disagree needs three"
    else:
        skipped["compare (NET-1)"] = "no --compare netlist given; NET-1 needs the schematic, PCB and fab netlists"
    if not args.bom:
        skipped["BOM (NET-7)"] = "no --bom given; MPN, value and fitted state come from the netlist only"
    build = ["build", args.netlist, "--out", str(out)] + (["--bom", args.bom] if args.bom else [])
    build += (["--format", args.format] if args.format else []) + (["--variant", args.variant] if args.variant else [])
    try:
        _quiet(build)
    except (ValueError, OSError) as exc:
        raise SystemExit(f"prep: cannot build the board model: {exc}") from exc
    lint = _read(out / "lint.json")
    findings = to_findings([Finding(**f) for f in lint["findings"]])
    (out / "lint_findings.json").write_text(json.dumps(findings, indent=1) + "\n", encoding="utf-8", newline="\n")
    own = serialize.read_json(out / "board_model.json")
    placed = _placement(out, loaded or [(args.netlist, own)], own, skipped)
    text = _facts(args, out, skipped, compared, placed)
    (out / "facts.md").write_text(text, encoding="utf-8", newline="\n")
    sys.stdout.write(text)
    return 1 if args.compare and not compared else 0


def _validate(args: argparse.Namespace) -> int:
    errors = schema.check_file(args.file, args.schema)
    if args.schema == "finding" and not (errors and errors[0].startswith(("not valid JSON", "$:"))):
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        count = len(data.get("findings", []) if isinstance(data, dict) else data)
        print(f"{args.file}: {count} findings, {len(errors)} errors")
    else:
        print(f"{args.file}: {len(errors)} errors")
    for e in errors:
        print(e)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(prog="python -m boardreview")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep", help="board model, staging views, lint, blocks and compare, indexed in facts.md")
    p.add_argument("netlist", help="netlist or board_model.json; the naming reference for the compare")
    p.add_argument("--bom")
    p.add_argument("--compare", nargs="+", default=[], metavar="OTHER_NETLIST", help="one or two netlists to compare")
    p.add_argument("--labels", default="", help="comma list, one per netlist; default schematic,pcb,fab")
    p.add_argument("--format", default="", help="netlist format when the file sniff gets it wrong")
    p.add_argument("--variant", default="", help="variant name for eda-agent JSON")
    p.add_argument("--out", required=True)
    report_build.add_parsers(sub)
    v = sub.add_parser("validate", help="check findings.json, a datasheet digest or board_model.json against its schema")
    v.add_argument("file")
    v.add_argument("--schema", default="finding", choices=sorted(schema.NAMES))
    args = ap.parse_args(argv)
    if args.cmd == "report":
        return report_build.run_report(args)
    if args.cmd == "verify-fixes":
        return report_build.run_verify(args)
    if args.cmd == "validate":
        return _validate(args)
    if len(args.compare) > 2:
        ap.error("--compare takes one or two netlists")
    if args.labels and len(args.labels.split(",")) != 1 + len(args.compare):
        ap.error("--labels needs one label per netlist, NETLIST first")
    return _prep(args)


if __name__ == "__main__":
    sys.exit(main())
