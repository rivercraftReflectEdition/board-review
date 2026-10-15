"""Load a review, write report.html, report_artifact.html, report.md, tickets, analysis.html; run verify-fixes."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from boardreview.report import analysis, html, markdown, plain
from boardreview.report import review as rv
from boardreview.report.verify import verify_fixes


@dataclass
class Ctx:
    header: dict
    board: str
    revision: str
    hash: str
    findings: list[dict]
    refuted: list[dict]
    facts: rv.Facts
    bench: list[rv.BenchStep]
    bench_given: bool
    findings_name: str
    known_good: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    checks_name: str = ""
    changes: rv.Changes | None = None
    status_items: dict[str, dict] = field(default_factory=dict)
    bench_numbers: dict[str, list[int]] = field(default_factory=dict)
    checks_of: dict[str, list[str]] = field(default_factory=dict)
    pointers: dict[str, list[dict]] = field(default_factory=dict)
    tickets: list[tuple[str, str]] = field(default_factory=list)
    analysis_href: str = ""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _with_findings(raw, findings: list[dict]):
    """The findings file in its original shape (a list, or a dict holding the list) with new findings."""
    if isinstance(raw, dict):
        out = dict(raw)
        out["findings"] = findings
        return out
    return findings


def load(args: argparse.Namespace) -> tuple[Ctx, object, list[dict]]:
    """Everything the outputs need; also returns the raw findings file and the findings with status merged."""
    raw = rv.read_json(args.findings)
    header, findings = rv.split_file(raw)
    status = rv.read_status(args.status)
    findings = rv.merge_status(findings, status)
    facts = rv.load_facts(args.facts, args.placement, args.pos_units)
    bench, given = rv.load_bench(args.bench, findings)
    _, known_good = rv.load_list(args.known_good)
    checks_path = Path(args.checks) if args.checks else Path(args.findings).with_name("checks.json")
    checks = rv.load_list(checks_path)[1] if checks_path.exists() else []
    active = rv.sort_findings([f for f in findings if not rv.refuted(f)])
    errs = rv.check_ids(findings, bench)
    cids = [c["id"] for c in checks]
    errs += [f"check id {c} is used twice" for c in sorted({c for c in cids if cids.count(c) > 1})]
    if errs:
        raise SystemExit("report: " + "; ".join(errs))
    board = str(header.get("board") or Path(args.facts).resolve().name)
    ctx = Ctx(header=header, board=board, revision=str(header.get("revision", "")), hash=rv.findings_hash(findings),
              findings=active, refuted=[f for f in findings if rv.refuted(f)], facts=facts, bench=bench,
              bench_given=given, findings_name=Path(args.findings).name, known_good=known_good, checks=checks,
              checks_name=checks_path.name if checks else "")
    if status.findings_hash and status.findings_hash != ctx.hash:
        print(f"warning: {Path(args.status).name} was exported for findings hash {status.findings_hash}, "
              f"these findings hash to {ctx.hash}; merged by id", file=sys.stderr)
    if args.previous:
        prev_header, prev = rv.split_file(rv.read_json(args.previous))
        ctx.changes = rv.changes(prev, findings, facts, str(prev_header.get("date", "")))
    ctx.status_items = {f["id"]: rv.status_item(f) for f in active}
    for b in bench:
        item = status.items.get(b.id)
        ctx.status_items[b.id] = {k: v for k, v in (item or {}).items() if k in ("done", "at", "by")}
    for n, b in enumerate(bench, 1):
        for fid in b.findings:
            ctx.bench_numbers.setdefault(fid, []).append(n)
    for c in checks:
        if c.get("finding"):
            ctx.checks_of.setdefault(c["finding"], []).append(c["id"])
    ctx.pointers = {f["id"]: html.pointers(f, facts) for f in active}
    ctx.analysis_href = "analysis.html" if args.detail == "full" else ""
    ctx.tickets = [(f"{f['id']}.md", markdown.ticket(f, ctx)) for f in active]
    return ctx, raw, findings


def run_report(args: argparse.Namespace) -> int:
    out = Path(args.out)
    ctx, raw, findings = load(args)
    status = {"board": ctx.board, "revision": ctx.revision, "findings_hash": ctx.hash, "exported_at": now(),
              "items": {k: v for k, v in ctx.status_items.items() if v}}
    files = {"report.html": html.render(ctx, artifact=False),
             "report_artifact.html": html.render(ctx, artifact=True),
             "report.md": markdown.report_md(ctx),
             "findings.json": json.dumps(_with_findings(raw, findings), indent=1, ensure_ascii=False) + "\n",
             "status.json": json.dumps(status, indent=1) + "\n"}
    if args.detail == "full":
        files["analysis.html"] = analysis.render(ctx)
    for name, text in files.items():
        write(out / name, text)
    for name, text in ctx.tickets:
        write(out / "tickets" / name, text)
    print(f"{len(ctx.findings)} findings, {len(ctx.refuted)} refuted, {len(ctx.bench)} bench steps, "
          f"{len(ctx.checks)} checks -> {out}")
    print("  " + ", ".join(files) + f", tickets/ ({len(ctx.tickets)} drafts)")
    for note in ctx.facts.notes:
        print(f"note: {note}")
    for c in ctx.checks:
        for problem in plain.check_problems(c):
            print(f"warning: {problem}", file=sys.stderr)
    return 0


def run_verify(args: argparse.Namespace) -> int:
    raw = rv.read_json(args.findings)
    header, findings = rv.split_file(raw)
    status = rv.read_status(args.status)
    findings = rv.merge_status(copy.deepcopy(findings), status)
    old = rv.load_facts(args.old_facts, with_placement=False)
    new = rv.load_facts(args.new_facts, with_placement=False)
    stamp = now()
    results = verify_fixes(findings, old, new, stamp)
    lines = ["| Finding | In the data | Note |", "|---|---|---|"]
    word = {True: "confirmed", False: "not found", None: "needs a reviewer"}
    lines += [f"| {fid} | {word[ok]} | {note.replace('|', '/')} |" for fid, ok, note in results]
    print("\n".join(lines) if results else "No finding is marked fixed; nothing to check.")
    tally = {w: sum(1 for _, ok, _ in results if word[ok] == w) for w in word.values()}
    print(", ".join(f"{n} {w}" for w, n in tally.items()))
    target = Path(args.out or args.findings)
    write(target, json.dumps(_with_findings(raw, findings), indent=1, ensure_ascii=False) + "\n")
    if args.status_out:
        items = dict(status.items) | {f["id"]: rv.status_item(f) for f in findings if f.get("status")}
        write(Path(args.status_out), json.dumps({"board": header.get("board", ""), "revision": header.get("revision", ""),
                                                 "findings_hash": rv.findings_hash(findings), "exported_at": stamp,
                                                 "items": items}, indent=1) + "\n")
    return 0


def add_parsers(sub) -> None:
    """The report and verify-fixes subcommands of python -m boardreview."""
    r = sub.add_parser("report", help="report.html, report_artifact.html, report.md and ticket drafts from findings")
    r.add_argument("--findings", required=True, help="findings.json: a list, or a dict with board, revision and findings")
    r.add_argument("--facts", required=True, help="facts folder written by prep")
    r.add_argument("--bench", help="bench plan JSON: a list of steps, or {steps: [...]}")
    r.add_argument("--known-good", help="known-good JSON: a list of {ref, note, source}")
    r.add_argument("--previous", help="findings.json of the previous review, for the what-changed fold")
    r.add_argument("--status", help="status.json exported from the page, merged into each finding's status")
    r.add_argument("--checks", help="checks.json from stage 4; default: checks.json next to --findings")
    r.add_argument("--placement", nargs="+", default=[], metavar="FILE",
                   help="a .kicad_pcb, IPC-D-356 or kicad-cli position files; prep's placement.json and the facts"
                        " folder are searched too")
    r.add_argument("--pos-units", choices=["mm", "in"], default="", help="units of a position CSV that does not say")
    r.add_argument("--detail", choices=["short", "full"], default="short",
                   help="full also writes analysis.html with every check")
    r.add_argument("--out", required=True)
    v = sub.add_parser("verify-fixes", help="mark verified_in_data on findings marked fixed, from two facts folders")
    v.add_argument("--findings", required=True)
    v.add_argument("--old-facts", required=True, help="facts folder the review was made on")
    v.add_argument("--new-facts", required=True, help="facts folder of the fixed design")
    v.add_argument("--status", help="status.json to merge before checking")
    v.add_argument("--out", help="findings file to write; default: overwrite --findings")
    v.add_argument("--status-out", help="status.json with the verified fields, one item per finding")
