"""report.md for pull requests and tickets/<id>.md drafts, from the same context as the HTML page."""

from __future__ import annotations

import hashlib
from pathlib import Path

from boardreview.calc.base import fmt
from boardreview.report import review as rv
from boardreview.report.html import (CONSEQUENCE, EVIDENCE_KIND, counts_line, question_lines, step_refs,
                                     unknown_summary, verdict_line)
from boardreview.report.plain import WORD


def cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def status_text(f: dict) -> str:
    st = f.get("status", {})
    bits = []
    if st.get("verified_in_data") is True:
        bits.append(f"confirmed in the data ({st.get('verify_note', '')})".replace(" ()", ""))
    elif st.get("verified_in_data") is False:
        bits.append(f"re-review did not find the fix ({st.get('verify_note', '')})".replace(" ()", ""))
    elif st.get("verify_note"):
        bits.append(st["verify_note"])
    if st.get("fixed"):
        bits.append("marked fixed in design" + (f" {st['fixed_at'][:10]}" if st.get("fixed_at") else ""))
    return "; ".join(bits) or "open"


def calc_md(c: dict) -> list[str]:
    """One calculation: verdict and summary first, key numbers, then the formula and the full table."""
    name = c.get("name") or c.get("calculator", "")
    lines = [f"**{name[:1].upper() + name[1:]}: {WORD.get(c.get('verdict', ''), c.get('verdict', ''))}.**"
             + (f" {c['summary']}" if c.get("summary") else (f" {c['reason']}" if c.get("reason") else "")), ""]
    keys = [f"{k['label']} {fmt(k.get('value'), k.get('unit', ''))}" + (f" (want {k['want']})" if k.get("want") else "")
            for k in c.get("key", [])]
    if keys:
        lines += [" · ".join(keys), ""]
    lines += [f"`{c.get('formula', '')}` ({c.get('calculator', '')})", "", "| | Quantity | Value | Note |",
              "|---|---|---|---|"]
    for side, rows in (("in", c.get("inputs", {})), ("out", c.get("outputs", {}))):
        lines += [f"| {side} | {cell(q.get('label') or k)} | {cell(fmt(q.get('value'), q.get('unit', '')))} | "
                  f"{cell(q.get('note'))} |" for k, q in rows.items()]
    lines.append("")
    lines += [f"- assumes {a}" for a in c.get("assumptions", [])]
    lines += [f"- ref {r}" for r in c.get("refs", [])]
    if c.get("plots"):
        lines.append("- plots: " + "; ".join(p.get("title", "") for p in c["plots"]) + " (in report.html)")
    return lines + [""]


def _sources(ctx) -> list[str]:
    rows = []
    for s in ctx.facts.sources:
        p = Path(s.get("path", ""))
        found = next((c for c in (p, ctx.facts.path / p, ctx.facts.path / p.name) if c.is_file()), None)
        digest = hashlib.sha256(found.read_bytes()).hexdigest()[:16] if found else "file not found"
        rows.append(f"{s.get('kind', '?')} {p.name} ({digest})")
    if ctx.facts.place is not None:
        rows.append(f"placement {ctx.facts.place.source} ({ctx.facts.place.kind}, {ctx.facts.place.units})")
    return rows


def finding_md(f: dict, ctx) -> list[str]:
    loc = []
    for key, label in (("parts", "parts"), ("nets", "nets"), ("pins", "pins"), ("pages", "pages")):
        if f.get(key):
            loc.append(f"{label} {', '.join(f[key])}")
    meta = [rv.SEV_NAME.get(f.get("severity"), f.get("severity", "")),
            f.get("area") or rv.AREA_OF_BLOCK.get(f.get("block", ""), ""),
            rv.CHANGE_LABEL.get(f.get("change_type", ""), "")]
    lines = [f"#### {f['id']} {f.get('title', '')}", "",
             f"- {' · '.join(m for m in meta if m)}; status: {status_text(f)}"]
    if ctx.changes and ctx.changes.tag(f["id"]):
        lines[-1] += f"; {ctx.changes.tag(f['id']).lower()}"
    if loc:
        lines.append(f"- Location: {'; '.join(loc)}")
    if f.get("symptom"):
        lines.append(f"- You'd see: {f['symptom']}")
    lines.append(f"- Claim: {f.get('claim', '')}")
    if f.get("mechanism"):
        lines.append(f"- How it fails: {f['mechanism']}")
    lines.append("- Evidence: " + "; ".join(
        f"{EVIDENCE_KIND.get(x.get('kind'), x.get('kind'))} {x.get('ref')}" + (f" ({x['detail']})" if x.get("detail") else "")
        for x in f.get("evidence", [])))
    for n in f.get("not_published", []):
        lines.append(f"- Not published: {n['item']}; became {CONSEQUENCE.get(n['consequence'], n['consequence'])}"
                     + (f": {n['action']}" if n.get("action") else ""))
    lines.append(f"- Fix: {f.get('fix', '')}")
    if f.get("bench_test"):
        lines.append(f"- Bench test: {f['bench_test']}")
    steps = step_refs(ctx.bench_numbers.get(f["id"], []))
    if steps:
        lines.append(f"- Verify: {steps}")
    v = f.get("verification", {})
    lines.append(f"- Verification: {v.get('status', 'PENDING')}" + (f" by {v['by']}" if v.get("by") else "")
                 + (f". {v['notes']}" if v.get("notes") else ""))
    lines.append("")
    if f.get("calculations"):
        lines += ["Math:", ""]
        for c in f["calculations"]:
            lines += calc_md(c)
    return lines


def question_md(f: dict, ctx) -> list[str]:
    """An open question: what is missing, what settles it, the bench step or document, then the finding."""
    head = [f"#### {f['id']} {f.get('title', '')}", "", f"- Open question; status: {status_text(f)}"]
    head += [f"- {k}: {v}" if k else f"- {v}" for k, v in question_lines(f, ctx)]
    body = finding_md(f, ctx)[3:]
    return head + [line for line in body if not line.startswith(("- Bench test:", "- Verify:"))]


def report_md(ctx) -> str:
    """The full report as markdown, in the order workflow/60_report.md gives."""
    h = ctx.header
    title = f"{ctx.board} Rev {ctx.revision} review" if ctx.revision else f"{ctx.board} review"
    rows = [("Board", ctx.board), ("Revision", ctx.revision), ("Variant", h.get("variant", "")),
            ("Date", h.get("date", "")), ("Stage", h.get("stage", "")), ("Scope", h.get("scope", "")),
            ("Not reviewed", "; ".join(h["not_reviewed"]) if isinstance(h.get("not_reviewed"), list)
             else h.get("not_reviewed", "")),
            ("Sources", "; ".join(_sources(ctx))), ("Findings hash", ctx.hash)]
    lines = [f"# {title}", "", "| | |", "|---|---|"] + [f"| {k} | {cell(v)} |" for k, v in rows if v] + [""]
    if h.get("assumptions"):
        lines += ["Assumptions:", ""] + [f"- {a}" for a in h["assumptions"]] + [""]
    verdict, _ = verdict_line(ctx.findings, h)
    problems = [f for f in ctx.findings if not rv.is_question(f)]
    questions = [f for f in ctx.findings if rv.is_question(f)]
    lines += ["## Summary", "", f"**{verdict}**", "", counts_line(ctx.findings), "",
              "| Severity | Findings | Fixed in design | Confirmed in the data |", "|---|---|---|---|"]
    for s in rv.SEVERITIES:
        group = [f for f in problems if f.get("severity") == s]
        if group:
            fixed = sum(1 for f in group if f.get("status", {}).get("fixed"))
            ver = sum(1 for f in group if f.get("status", {}).get("verified_in_data") is True)
            lines.append(f"| {rv.SEV_NAME[s]} | {len(group)} | {fixed} | {ver} |")
    lines.append("")
    lines += [f"- **{f['id']}** ({f['severity']}) {f['title']}. Fix: {f.get('fix', '')}"
              for f in problems if f.get("severity") in ("blocker", "major")]
    if questions:
        lines += ["", f"Open questions, not confirmed problems: {', '.join(f['id'] for f in questions)}."]
    if ctx.checks:
        lines += ["", f"Checks: {unknown_summary(ctx.checks)}." if rv.unknown_groups(ctx.checks)
                  else f"Checks: {len(ctx.checks)}, none unknown."]
    lines.append("")
    if ctx.changes:
        c = ctx.changes
        lines += [f"## What changed since {('the ' + c.since + ' review') if c.since else 'the previous review'}", "",
                  c.summary(), ""]
        lines += [f"- Reopened: {n['id']} {n['title']} (marked fixed as {o['id']})" for o, n in c.reopened]
        lines += [f"- New: {f['id']} {f['title']}" for f in c.new]
        lines += [f"- Fixed: {o['id']} {o['title']}. {note}." for o, note in c.fixed]
        lines += [f"- Not found again, fix not confirmed in the data: {o['id']} {o['title']}. {note}."
                  for o, note in c.not_found]
        lines += [f"- Still open: {n['id']} {n['title']}" for _, n in c.still_open]
        lines.append("")
    lines += ["## Findings", ""]
    blocks = sorted({f.get("block", "other") for f in problems},
                    key=lambda b: rv.BLOCK_ORDER.index(b) if b in rv.BLOCK_ORDER else 99)
    for b in blocks:
        lines += [f"### {rv.BLOCK_NAME.get(b, b)}", ""]
        for f in problems:
            if f.get("block", "other") == b:
                lines += finding_md(f, ctx)
    if not problems:
        lines += ["No confirmed problems.", ""]
    if questions:
        lines += ["## Open questions", "", "Paper could not settle these. None is a confirmed problem.", ""]
        for f in questions:
            lines += question_md(f, ctx)
    feet = [(f, n) for f in ctx.findings for n in f.get("not_published", []) if n["consequence"] == "footprint"]
    lines += ["## Required footprints", ""]
    lines += [f"- {f['id']}: {n.get('action') or n['item']}" for f, n in feet] or ["None."]
    lines += ["", "## Firmware handoff", ""]
    fw = [f"- {i.get('item', '')}: {i.get('setting', '')}" + (" (never)" if i.get("never") else "")
          for i in h.get("firmware", [])]
    fw += [f"- {f['id']} {f['title']}: {f.get('fix', '')}" for f in ctx.findings if f.get("change_type") == "firmware"]
    lines += fw or ["None."]
    lines += ["", "## Accepted risks and deviations", ""]
    lines += [f"- {r.get('item', '')}: {r.get('reason', '')}" + (f" Accepted by {r['by']}." if r.get("by") else "")
              for r in h.get("accepted_risks", [])] or ["None recorded."]
    lines += ["", "## Bench test plan", ""]
    if ctx.bench:
        lines += ["| # | Phase | Step | Settles | Pass | Done |", "|---|---|---|---|---|---|"]
        for n, b in enumerate(ctx.bench, 1):
            done = "yes" if ctx.status_items.get(b.id, {}).get("done") else ""
            lines.append(f"| {n} | {cell(b.phase)} | {cell(b.title)} | {cell(', '.join(b.findings))} | {cell(b.rule)} | {done} |")
        for n, b in enumerate(ctx.bench, 1):
            if b.detail:
                lines += ["", f"Step {n} ({b.id}):"] + [f"- {k}: {v}" for k, v in b.detail]
    else:
        lines.append("None.")
    lines += ["", "## Known-good list", ""]
    lines += [f"- {k.get('ref') or ', '.join(k.get('parts', []))}: {k.get('note', '')}"
              + (f" {k['source']}." if k.get("source") else "") for k in ctx.known_good] or ["None."]
    lines += ["", "## Appendix", "", "### Refuted findings", ""]
    lines += [f"- {f['id']} {f['title']}: {f.get('verification', {}).get('notes', '')}" for f in ctx.refuted] or ["None."]
    lines += ["", "### Coverage", ""]
    if ctx.checks:
        lines += ["| Check | Block | Instance | Verdict | Finding |", "|---|---|---|---|---|"]
        lines += [f"| {c['id']} | {c['block']} | {cell(c['instance'])} | {c['verdict']} | {c.get('finding', '')} |"
                  for c in ctx.checks]
        groups = rv.unknown_groups(ctx.checks)
        if groups:
            lines += ["", "### Checks that could not run", "", unknown_summary(ctx.checks) + ".", "",
                      "| Why | Checks | Examples |", "|---|---|---|"]
            lines += [f"| {rv.UNKNOWN_REASONS[k]} | {len(cs)} | "
                      + cell("; ".join(f"{c['id']}: {c.get('reason', '')}" for c in cs[:6]))
                      + (f" and {len(cs) - 6} more" if len(cs) > 6 else "") + " |" for k, cs in groups.items()]
    else:
        lines.append("No checks.json given.")
    return "\n".join(lines) + "\n"


def ticket(f: dict, ctx) -> str:
    """A short ticket draft: what breaks, where, the fix and how to verify it."""
    sev = rv.SEV_NAME.get(f.get("severity"), "")
    meta = [f"Open question, {sev.lower()} if it holds" if rv.is_question(f) else sev,
            f.get("area") or rv.AREA_OF_BLOCK.get(f.get("block", ""), ""), rv.CHANGE_LABEL.get(f.get("change_type", ""), "")]
    where = []
    if f.get("parts"):
        where.append(f"Parts: {', '.join(f['parts'])}.")
    if f.get("nets"):
        where.append(f"Nets: {', '.join(f['nets'])}.")
    verify = step_refs(ctx.bench_numbers.get(f["id"], [])) or f.get("bench_test") or \
        "Re-review: the fix shows in the netlist or BOM."
    review = f"{ctx.board}" + (f" Rev {ctx.revision}" if ctx.revision else "") + (
        f", {ctx.header['date']}" if ctx.header.get("date") else "")
    body = [f"# {f['title']} ({f['id']})", "", f"{'. '.join(m for m in meta if m)}. {' '.join(where)}".strip(), ""]
    if f.get("symptom"):
        body.append(f["symptom"])
    body += [f.get("claim", ""), "", f"Fix: {f.get('fix', '')}", f"Verify: {verify}", "",
             f"Status: {status_text(f)}.", f"Review: {review}. Details: report.html#{f['id']}"]
    return "\n".join(body) + "\n"
