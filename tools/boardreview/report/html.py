"""report.html and report_artifact.html: one self-contained page, rows first, everything else folded."""

from __future__ import annotations

import html
import json
from pathlib import Path

from boardreview.model.board import natural_key
from boardreview.report import plain
from boardreview.report import review as rv

HERE = Path(__file__).parent
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700'
         '&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">')
_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
CONSEQUENCE = {"footprint": "Footprint", "bench_test": "Bench test", "vendor_question": "Vendor question",
               "model": "Model"}
EVIDENCE_KIND = {"netlist": "Netlist", "bom": "BOM", "variant": "Variant", "pcb": "PCB", "datasheet": "Datasheet",
                 "errata": "Errata", "app_note": "App note", "calculator": "Calculator", "simulation": "Simulation",
                 "bench": "Bench", "lint": "Lint", "compare": "Compare", "design_notes": "Notes"}


def fonts(ctx) -> str:
    """The Google Fonts links when asked for (--google-fonts); otherwise nothing, and the CSS falls back to system fonts."""
    return FONTS + "\n" if getattr(ctx, "fonts", False) else ""


def e(text) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def asset(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def words(n: int, cap: bool = False) -> str:
    w = _WORDS[n] if 0 <= n < len(_WORDS) else str(n)
    return w[:1].upper() + w[1:] if cap else w


def plural(n: int, word: str) -> str:
    return word if n == 1 else word + "s"


def _open(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("status", {}).get("verified_in_data") is not True]


def verdict_line(findings: list[dict], header: dict) -> tuple[str, str]:
    """Headline and its severity class, from the open problems; open questions never raise or lower it."""
    open_ = _open(findings)
    problems = [f for f in open_ if not rv.is_question(f)]
    count = {s: sum(1 for f in problems if f.get("severity") == s) for s in rv.SEVERITIES}
    questions = len(open_) - len(problems)
    cls = next((f"v-{s}" for s in ("blocker", "major", "minor") if count[s]), "v-minor" if questions else "v-pass")
    if header.get("verdict"):
        return str(header["verdict"]), cls
    if count["blocker"]:
        return f"Not ready to build. {words(count['blocker'], True)} {plural(count['blocker'], 'blocker')}.", cls
    if count["major"]:
        return (f"Builds, with {words(count['major'])} major {plural(count['major'], 'finding')} to fix or "
                "accept.", cls)
    if questions:
        return "Not signed off. Open questions need a bench test or a document first.", cls
    if problems:
        return f"Ready to build. {words(len(problems), True)} minor {plural(len(problems), 'item')} open.", cls
    return "Ready to build. No open findings.", cls


def counts_line(findings: list[dict]) -> str:
    """'1 confirmed problem, 11 open questions.': problems and open questions counted apart."""
    open_ = _open(findings)
    problems = [f for f in open_ if not rv.is_question(f)]
    confirmed = sum(1 for f in problems if f.get("verification", {}).get("status") == "CONFIRMED")
    pending = len(problems) - confirmed
    questions = len(open_) - len(problems)
    bits = [f"{confirmed} confirmed {plural(confirmed, 'problem')}"]
    if pending:
        bits.append(f"{pending} not challenged yet")
    bits.append(f"{questions} open {plural(questions, 'question')}" if questions else "no open questions")
    return ", ".join(bits) + "."


def step_refs(numbers: list[int]) -> str:
    if not numbers:
        return ""
    if len(numbers) == 1:
        return f"Bench step {numbers[0]}."
    if numbers == list(range(numbers[0], numbers[-1] + 1)):
        return f"Bench steps {numbers[0]} to {numbers[-1]}."
    return "Bench steps " + ", ".join(map(str, numbers[:-1])) + f" and {numbers[-1]}."


def flink(fid: str) -> str:
    return f'<a href="#{e(fid)}">{e(fid)}</a>'


def _pins_line(ref: str, f: dict, facts: rv.Facts) -> list[str]:
    nets = {n.upper() for n in f.get("nets", [])}
    named = set(f.get("pins", []))
    out = []
    for p in facts.pins_of(ref):
        key = f"{ref}.{p['number']}"
        if key in named or (p.get("net") or "").upper() in nets:
            out.append(f"{key}" + (f" ({p['name']})" if p.get("name") else "") + f" on {p.get('net') or 'no net'}")
    for key in sorted(named, key=natural_key):
        if key.partition(".")[0] == ref and not any(line.startswith(key + " ") for line in out):
            out.append(f"{key} (not in the netlist)")
    return out


def _part_text(ref: str, facts: rv.Facts) -> str:
    c = facts.components.get(ref)
    if c is None:
        return f'<span class="mono">{e(ref)}</span> not in the facts'
    bits = [b for b in (c.get("value"), c.get("mpn") if c.get("mpn") != c.get("value") else "") if b]
    text = f'<span class="mono">{e(ref)}</span> ' + e(", ".join(bits) or c.get("description", ""))
    return text + (" · DNP" if not c.get("fitted", True) else "")


def _where(refs: list[str], facts: rv.Facts) -> str:
    if facts.place is None:
        return "Not in the facts: add an IPC-D-356 or position file."
    side_name = {"top": "Top", "bottom": "Bottom", "through": "Through-hole", "inner": "Inner layer", "": "Side unknown"}
    found = [facts.place.parts[r] for r in refs if r in facts.place.parts]
    if not found:
        return f"Not in {facts.place.source}."
    if len(found) == 1:
        p = found[0]
        return f"{side_name[p.side]}, X {p.x_mm:.2f} Y {p.y_mm:.2f} mm"
    sides = sorted({side_name[p.side] for p in found})
    return f"{', '.join(sides)}; {len(found)} of {len(refs)} parts placed"


def pointers(f: dict, facts: rv.Facts) -> list[dict]:
    """One pointer per part chip: part, sheet, side and X/Y, the pins and nets in this finding."""
    chips = list(f.get("parts", []))
    covered = set(rv.expand(chips))
    for pin in f.get("pins", []):
        ref = pin.partition(".")[0]
        if ref not in covered:
            chips.append(ref)
            covered.add(ref)
    out = []
    for chip in chips:
        refs = rv.expand([chip])
        if len(refs) == 1:
            part = _part_text(refs[0], facts)
        else:
            values = sorted({facts.components.get(r, {}).get("value", "") for r in refs} - {""})
            part = f'<span class="mono">{e(chip)}</span> {len(refs)} parts' + (f", {e(', '.join(values))}" if values else "")
        sheets = sorted({facts.sheet(r) for r in refs} - {""})
        lines = [line for r in refs for line in _pins_line(r, f, facts)]
        shown = lines[:8] + ([f"and {len(lines) - 8} more"] if len(lines) > 8 else [])
        dl = [["Part", part], ["Sheet", e(", ".join(sheets)) or "Not in the facts"],
              ["On the PCB", e(_where(refs, facts))],
              ["In this finding", "<br>".join(e(x) for x in shown) or "Named in this finding; no pins or nets on it."]]
        out.append({"label": chip, "refs": refs, "dl": dl})
    return out


def _challenge(f: dict) -> str:
    v = f.get("verification", {})
    st = v.get("status", "PENDING")
    verdict = {"CONFIRMED": '<span class="held">Held.</span>',
               "UNVERIFIABLE": '<span class="unsettled">Paper cannot settle it; the bench test decides.</span>',
               "PENDING": '<span class="unsettled">Not challenged yet.</span>'}.get(st, e(st))
    who = f" ({e(v['by'])})" if v.get("by") else ""
    srcs = (f'<p class="small">Read: {e("; ".join(v["sources_checked"]))}</p>' if v.get("sources_checked") else "")
    return (f'<details><summary>Challenge</summary><p class="small"><b>Verifier{who}:</b> {verdict} '
            f'{e(v.get("notes", ""))}</p>{srcs}</details>')


def _history(f: dict, ctx) -> str:
    bits = []
    old = ctx.changes.previous_of(f["id"]) if ctx.changes else None
    if old is not None:
        since = f" of {ctx.changes.since}" if ctx.changes.since else ""
        bits.append(f"In the previous review{since} as {old['id']}.")
        ost = old.get("status", {})
        if ost.get("fixed"):
            when = f" {ost['fixed_at'][:10]}" if ost.get("fixed_at") else ""
            bits.append(f"Marked fixed{when}; it is still in the data.")
    st = f.get("status", {})
    if st.get("verified_at"):
        bits.append(f"Re-reviewed {st['verified_at'][:10]}: {st.get('verify_note', '')}".rstrip(": "))
    return f'<details><summary>History</summary><p class="small">{e(" ".join(bits))}</p></details>' if bits else ""


def _chips(f: dict, ctx) -> str:
    fid = f["id"]
    chips = "".join(f'<button class="part" type="button" aria-expanded="false" data-f="{e(fid)}" data-p="{i}">'
                    f'{e(p["label"])}</button>' for i, p in enumerate(ctx.pointers[fid]))
    pins = f.get("pins", [])
    pin_html = f'<span class="fid">{plural(len(pins), "pin")} {e(", ".join(pins))}</span>' if 0 < len(pins) <= 3 else ""
    return chips + pin_html


def question_lines(f: dict, ctx) -> list[tuple[str, str]]:
    """(label, text) for an open question: what is missing, what settles it, the bench step or document."""
    nps = f.get("not_published", [])
    missing = "; ".join(n["item"] + (f" (looked in {n['searched']})" if n.get("searched") else "") for n in nps)
    settle = f.get("bench_test") or "; ".join(n["action"] for n in nps if n.get("action")) or "Not stated."
    lines = [("Missing", missing or "Not listed: the finding names no missing value."), ("Settles it", settle)]
    steps = step_refs(ctx.bench_numbers.get(f["id"], []))
    docs = [n.get("action") or n["item"] for n in nps if n.get("consequence") in ("vendor_question", "model")]
    if steps:
        lines.append(("", steps))
    for d in docs:
        lines.append(("Document", d))
    if not steps and not docs:
        lines.append(("", "Not in the bench plan yet."))
    lines.append(("If it holds", rv.SEV_NAME.get(f.get("severity", ""), f.get("severity", "")).lower()))
    return lines


def question_row(f: dict, ctx) -> str:
    """An UNVERIFIABLE finding: no severity chip and no fix checkbox; what is missing and what settles it."""
    fid = f["id"]
    area = f.get("area") or rv.AREA_OF_BLOCK.get(f.get("block", ""), "Other")
    lines = "".join(f'<p class="qline">' + (f"<b>{e(k)}:</b> " if k else "") + f"{e(plain.sentence(v))}</p>"
                    for k, v in question_lines(f, ctx))
    facts = (f'<dl class="facts"><dt>Why it may fail</dt><dd>{e(f.get("claim", ""))}</dd>'
             f'<dt>Fix if it holds</dt><dd>{e(f.get("fix", ""))}</dd></dl>')
    return (f'<article class="item sev-question" id="{e(fid)}">\n'
            f'  <div class="row">\n    <div class="row-main">\n'
            f'      <div class="row-top"><span class="chip question">Open question</span>'
            f'<span class="fid">{e(fid)} · {e(area)}</span></div>\n'
            f'      <span class="row-title">{e(f.get("title", ""))}</span>\n'
            f'      <div class="parts">{_chips(f, ctx)}</div>\n      {lines}\n    </div>\n'
            f'    <button class="more" type="button" aria-expanded="false" aria-controls="d-{e(fid)}" '
            f'data-more="{e(fid)}">More</button>\n  </div>\n'
            f'  <div class="pointer" id="p-{e(fid)}" hidden></div>\n'
            f'  <div class="detail" id="d-{e(fid)}" hidden>\n    {facts}\n    {_folds(f, ctx)}\n  </div>\n'
            f'</article>')


def questions_section(ctx) -> str:
    qs = [f for f in ctx.findings if rv.is_question(f)]
    if not qs:
        return ""
    return (f'<section class="list questions" id="br-questions" aria-labelledby="br-qh">\n'
            f'<h2 id="br-qh" class="qhead">Open questions</h2>\n'
            f'<p class="small">Paper could not settle {words(len(qs))} {plural(len(qs), "finding")}. None is a '
            "confirmed problem; each needs the bench step or the document named.</p>\n"
            + "\n".join(question_row(f, ctx) for f in qs) + "\n</section>")


def _folds(f: dict, ctx) -> str:
    """Math, evidence, challenge, history, bench test and check links of a finding, each folded."""
    fid = f["id"]
    steps = ctx.bench_numbers.get(fid, [])
    folds = []
    calcs = f.get("calculations", [])
    if calcs:
        folds.append('<details><summary>Math</summary><div class="stack">'
                     + "".join(plain.calc_block(c, f"{fid}-c{i}") for i, c in enumerate(calcs)) + "</div></details>")
    ev = [f'<li><span class="ek">{e(EVIDENCE_KIND.get(x.get("kind"), x.get("kind")))}</span>{e(x.get("ref"))}'
          + (f": {e(x['detail'])}" if x.get("detail") else "") + "</li>" for x in f.get("evidence", [])]
    ev += [f'<li><span class="ek">Not published</span>{e(n["item"])}: {e(CONSEQUENCE.get(n["consequence"], ""))}'
           + (f", {e(n['action'])}" if n.get("action") else "") + "</li>" for n in f.get("not_published", [])]
    if f.get("mechanism"):
        ev.insert(0, f'<li><span class="ek">How it fails</span>{e(f["mechanism"])}</li>')
    if ev:
        folds.append(f'<details><summary>Evidence</summary><ul class="ev">{"".join(ev)}</ul></details>')
    folds.append(_challenge(f))
    folds.append(_history(f, ctx))
    if steps and f.get("bench_test"):
        folds.append(f'<details><summary>Bench test</summary><p class="small">{e(f["bench_test"])}</p></details>')
    checks = ctx.checks_of.get(fid, [])
    if checks and ctx.analysis_href:
        links = ", ".join(f'<a href="{e(ctx.analysis_href)}#chk-{e(c)}">{e(c)}</a>' for c in checks)
        folds.append(f'<p class="small">Checks: {links}</p>')
    return "".join(x for x in folds if x)


def finding_row(f: dict, ctx) -> str:
    fid = f["id"]
    sev = f.get("severity", "note")
    area = f.get("area") or rv.AREA_OF_BLOCK.get(f.get("block", ""), "Other")
    change = rv.CHANGE_LABEL.get(f.get("change_type", ""), "")
    tag = ctx.changes.tag(fid) if ctx.changes else ""
    tag_html = f'<span class="chip {"blocker" if tag == "Reopened" else "outline"}">{e(tag)}</span>' if tag else ""
    chips = _chips(f, ctx)
    steps = ctx.bench_numbers.get(fid, [])
    verify = step_refs(steps) or f.get("bench_test") or "Re-review: the fix shows in the netlist or BOM."
    facts = (f'<dl class="facts"><dt>You\'d see</dt><dd>{e(f.get("symptom") or "Not stated.")}</dd>'
             f'<dt>Why</dt><dd>{e(f.get("claim", ""))}</dd><dt>Fix</dt><dd>{e(f.get("fix", ""))}</dd>'
             f'<dt>Verify</dt><dd>{e(verify)}</dd></dl>')
    done = f.get("status", {}).get("fixed")
    return (f'<article class="item sev-{e(sev)}{" is-done" if done else ""}" id="{e(fid)}">\n'
            f'  <div class="row">\n'
            f'    <input class="check" type="checkbox" id="chk-{e(fid)}" data-id="{e(fid)}"{" checked" if done else ""}'
            f' aria-label="Mark {e(fid)} fixed in the design">\n'
            f'    <div class="row-main">\n'
            f'      <div class="row-top"><span class="chip {e(sev)}">{rv.SEV_NAME.get(sev, sev)}</span>{tag_html}'
            f'<span class="fid">{e(fid)} · {e(area)}</span>' + (f'<span class="effort">{e(change)}</span>' if change else "")
            + '</div>\n'
            f'      <label class="row-title" for="chk-{e(fid)}">{e(f.get("title", ""))}</label>\n'
            f'      <div class="parts">{chips}</div>\n'
            f'      <div class="status-line" id="st-{e(fid)}"></div>\n'
            f'    </div>\n'
            f'    <button class="more" type="button" aria-expanded="false" aria-controls="d-{e(fid)}" '
            f'data-more="{e(fid)}">More</button>\n'
            f'  </div>\n'
            f'  <div class="pointer" id="p-{e(fid)}" hidden></div>\n'
            f'  <div class="detail" id="d-{e(fid)}" hidden>\n    {facts}\n    {_folds(f, ctx)}\n  </div>\n'
            f'</article>')


def fold(title: str, summary: str, body: str, fid: str = "") -> str:
    ident = f' id="{e(fid)}"' if fid else ""
    sid = f' id="{e(fid)}-sum"' if fid else ""
    return (f'<details class="fold"{ident}>\n  <summary>{e(title)} <span class="sum"{sid}>{e(summary)}</span></summary>\n'
            f'  {body}\n</details>')


def table(rows: list[list[str]], head: list[str] | None = None) -> str:
    th = "<thead><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr></thead>" if head else ""
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="scroll"><table>{th}<tbody>{body}</tbody></table></div>'


def bench_fold(ctx) -> str:
    items = []
    phase = None
    for n, b in enumerate(ctx.bench, 1):
        if b.phase and b.phase != phase:
            items.append(f'<li class="phase">{e(b.phase)}</li>')
            phase = b.phase
        rule = ", ".join(b.findings) + ("." if b.findings else "") + (f" Pass: {b.rule}" if b.rule else "")
        more = ""
        if b.detail:
            more = ('<details><summary>Setup and procedure</summary><dl>'
                    + "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in b.detail) + "</dl></details>")
        done = ctx.status_items.get(b.id, {}).get("done")
        items.append(f'<li class="step{" is-done" if done else ""}" id="bench-{e(b.id)}"><input class="check" '
                     f'type="checkbox" id="chk-{e(b.id)}" data-id="{e(b.id)}"{" checked" if done else ""} '
                     f'aria-label="Mark bench step {n} done"><span class="n">{n}</span><span><span class="t">'
                     f'{e(b.title)}</span><br><span class="rule">{e(rule.strip())}</span>{more}</span></li>')
    body = f'<ol class="bench" id="br-benchlist">{"".join(items)}</ol>' if items else '<p class="small">No bench steps.</p>'
    if not ctx.bench_given and items:
        body += '<p class="small">No bench plan file was given: one step per finding bench test, in severity order.</p>'
    total = len(ctx.bench)
    return fold("Bench plan", f"{total} {plural(total, 'step')} in bring-up order" if ctx.bench_given else
                f"{total} {plural(total, 'step')} from the findings", body, "br-bench")


def changes_fold(ctx) -> str:
    c = ctx.changes
    rows = []
    for old, new in c.reopened:
        rows.append(['<span class="chip blocker">Reopened</span>', f"{flink(new['id'])} {e(new['title'])}. "
                     f"Marked fixed as {e(old['id'])}; still in the data."])
    for f in c.new:
        rows.append(['<span class="chip major">New</span>', f"{flink(f['id'])} {e(f['title'])}"])
    for old, note in c.fixed:
        rows.append(['<span class="chip passc">Fixed</span>', f"{e(old['id'])} {e(old['title'])}. {e(note)}."])
    for old, note in c.not_found:
        why = ("A reviewer has to confirm the fix." if note.startswith("needs a reviewer")
               else f"The data does not show the fix: {note}.")
        rows.append(['<span class="chip outline">Not found again</span>', f"{e(old['id'])} {e(old['title'])}. "
                     f"Not in this review, but not confirmed in the data. {e(why)}"])
    for old, new in c.still_open:
        rows.append(['<span class="chip note">Still open</span>', f"{flink(new['id'])} {e(new['title'])}"])
    since = f"the {c.since} review" if c.since else "the previous review"
    body = table(rows) if rows else '<p class="small">No differences.</p>'
    return fold(f"What changed since {since}", c.summary(), body, "br-changes")


def power_tree_fold(ctx) -> str:
    edges = rv.power_edges(ctx.tree)
    where = ctx.tree_source or "prep's blocks.json"
    if not edges:
        return fold("Power tree", f"No converters, switches or filters in {where}",
                    f'<p class="small">{e(where)} lists no regulators, load switches or series filters.</p>',
                    "br-power")
    refs_of = {f["id"]: set(rv.expand(f.get("parts"))) | {p.partition(".")[0] for p in f.get("pins", [])}
               for f in ctx.findings}
    flags: dict[int, list[dict]] = {}
    for i, (_, out, _, parts) in enumerate(edges):
        flags[i] = [f for f in ctx.findings if refs_of[f["id"]] & set(parts) or out in f.get("nets", [])]

    def flag_html(found: list[dict]) -> str:
        return "".join(f'<a class="flag {e(f.get("severity", "note"))}" href="#{e(f["id"])}">{e(f["id"])}</a>'
                       for f in found)
    children: dict[str, list[int]] = {}
    for i, (src, _, _, _) in enumerate(edges):
        children.setdefault(src, []).append(i)
    outputs = {out for _, out, _, _ in edges}
    roots = sorted({src for src, _, _, _ in edges if src not in outputs}, key=natural_key) or [edges[0][0]]

    def node(rail: str, seen: set[str]) -> str:
        kids = []
        for i in children.get(rail, []):
            src, out, label, _ = edges[i]
            if out in seen:
                continue
            sub = node(out, seen | {out})
            kids.append(f'<li><span class="node"><span class="via">{e(label)}</span><span class="rail">{e(out)}'
                        f'</span>{flag_html(flags[i])}</span>{sub}</li>')
        return f"<ul>{''.join(kids)}</ul>" if kids else ""

    root_flags = {r: [f for f in ctx.findings if r in f.get("nets", [])] for r in roots}
    body = '<ul class="tree">' + "".join(f'<li><span class="node"><span class="rail">{e(r)}</span>'
                                          f'{flag_html(root_flags[r])}</span>{node(r, {r})}</li>' for r in roots) + "</ul>"
    if ctx.tree_source:
        body += (f'<p class="small">Regulators, switches and filters from the {e(ctx.tree_source)}. Flags are findings '
                 "on the part or the rail.</p>")
    else:
        body += ('<p class="small">Regulators, switches and filters from prep\'s blocks.json. Their directions are a '
                 "heuristic from names and pins; give the reviewed tree with --power-tree. Flags are findings on the "
                 "part or the rail.</p>")
    busiest = max(flags, key=lambda i: len(flags[i]))
    n = len(flags[busiest])
    flagged = {f["id"] for v in list(flags.values()) + list(root_flags.values()) for f in v}
    summary = (f"{edges[busiest][2].split(' ')[0]} carries {words(n)} findings" if n >= 2 else
               f"{len(edges)} regulators, switches and filters, {len(flagged)} {plural(len(flagged), 'finding')} on them")
    return fold("Power tree", summary, body, "br-power")


def not_published_fold(ctx) -> str:
    rows = []
    for f in ctx.findings:
        for n in f.get("not_published", []):
            became = CONSEQUENCE.get(n["consequence"], n["consequence"]) + (f": {n['action']}" if n.get("action") else "")
            rows.append([e(n["item"]), f"{e(became)} ({flink(f['id'])})"])
    if not rows:
        return ""
    return fold("Could not settle on paper", f"{len(rows)} {plural(len(rows), 'value')} not published",
                table(rows, ["Missing value", "Became"]), "br-unpublished")


def firmware_fold(ctx) -> str:
    rows = []
    never = 0
    for item in ctx.header.get("firmware", []):
        setting = e(item.get("setting", ""))
        if item.get("never"):
            never += 1
            setting = f'<span class="chip blocker">{setting or "Never"}</span>'
        rows.append([e(item.get("item", "")), setting])
    for f in ctx.findings:
        if f.get("change_type") == "firmware":
            rows.append([f"{e(f['title'])} ({flink(f['id'])})", e(f.get("fix", ""))])
    if not rows:
        return ""
    summary = f"{len(rows)} {plural(len(rows), 'setting')}" + (f", {never} never-do" if never else "")
    return fold("Firmware handoff", summary, table(rows), "br-firmware")


def known_good_fold(ctx) -> str:
    if not ctx.known_good:
        return ""
    rows = []
    for k in ctx.known_good:
        refs = k.get("ref") or ", ".join(k.get("parts", []))
        note = k.get("note", "") + (f" {k['source']}." if k.get("source") else "") + (
            f" Decided {k['decided']}." if k.get("decided") else "")
        rows.append([f'<span class="mono">{e(refs)}</span>', e(note.strip())])
    n = len(rows)
    return fold("Looked wrong, are right", f"{n} {plural(n, 'decision')} on record", table(rows), "br-known-good")


def coverage_fold(ctx) -> str:
    if ctx.checks:
        by: dict[str, dict] = {}
        for c in ctx.checks:
            row = by.setdefault(c["block"], {"inst": [], "run": 0, "total": 0, "unknown": 0, "na": 0})
            if c["instance"] not in row["inst"]:
                row["inst"].append(c["instance"])
            row["total"] += 1
            row["run"] += c["verdict"] in ("pass", "marginal", "fail")
            row["unknown"] += c["verdict"] == "unknown"
            row["na"] += c["verdict"] == "not_applicable"
        order = sorted(by, key=lambda b: rv.BLOCK_ORDER.index(b) if b in rv.BLOCK_ORDER else 99)
        rows = [[e(rv.BLOCK_NAME.get(b, b)), e("; ".join(by[b]["inst"])),
                 f'{by[b]["run"]}/{by[b]["total"] - by[b]["na"]}', str(by[b]["unknown"])] for b in order]
        total = len(ctx.checks)
        unknown = sum(r["unknown"] for r in by.values())
        body = table(rows, ["Block", "Found", "Run", "Could not run"])
        if ctx.analysis_href:
            body += f'<p class="small">Every check with its numbers and plots: <a href="{e(ctx.analysis_href)}">' \
                    f'{e(ctx.analysis_href)}</a>.</p>'
        return fold("Coverage", f"{total} {plural(total, 'check')} · {unknown} could not run", body, "br-coverage")
    kinds: dict[str, list[str]] = {}
    for b in ctx.facts.blocks:
        kind = str(b.get("kind") or b.get("checklist") or "?")
        kinds.setdefault(rv.BLOCK_NAME.get(kind) or kind.replace("_", " ").capitalize(), []).append(str(b.get("name", "")))
    rows = [[e(k), e("; ".join(v))] for k, v in kinds.items()]
    body = (table(rows, ["Block", "Found"]) if rows else "") + \
        '<p class="small">No checks.json was given, so the checks run per block are not listed.</p>'
    return fold("Coverage", f"{len(ctx.facts.blocks)} blocks found · checks not listed", body, "br-coverage")


def unknown_summary(checks: list[dict]) -> str:
    """'609 of 644 could not run: 400 no datasheet, 150 no model, 59 needs bench'."""
    groups = rv.unknown_groups(checks)
    n = sum(len(v) for v in groups.values())
    return f"{n} of {len(checks)} could not run: " + ", ".join(
        f"{len(v)} {rv.UNKNOWN_REASONS[k].lower()}" for k, v in groups.items())


def unknown_fold(ctx, examples: int = 6) -> str:
    """Unknown checks counted by why they could not run, with a few examples of each."""
    groups = rv.unknown_groups(ctx.checks)
    if not groups:
        return ""
    rows = []
    for k, cs in groups.items():
        shown = "; ".join(f'<span class="mono">{e(c["id"])}</span> {e(c.get("reason", ""))}' for c in cs[:examples])
        more = f"; and {len(cs) - examples} more" if len(cs) > examples else ""
        rows.append([e(rv.UNKNOWN_REASONS[k]), str(len(cs)), shown + e(more)])
    body = table(rows, ["Why", "Checks", "Examples"])
    body += ('<p class="small">An unknown check is not a pass. No datasheet: the document was not supplied or '
             "does not exist. No model: a curve or model is missing. Needs bench: only a measurement settles it."
             "</p>")
    if ctx.analysis_href:
        body += f'<p class="small">Each one with its reason: <a href="{e(ctx.analysis_href)}">{e(ctx.analysis_href)}' \
                "</a>.</p>"
    return fold("Checks that could not run", unknown_summary(ctx.checks), body, "br-unknown")


def refuted_fold(ctx) -> str:
    if not ctx.refuted:
        return ""
    rows = [[f'<span class="mono">{e(f["id"])}</span>', f"{e(f['title'])}. {e(f.get('verification', {}).get('notes', ''))}"]
            for f in ctx.refuted]
    return fold("Refuted", f"{len(rows)} {plural(len(rows), 'finding')} dropped by the challenge", table(rows),
                "br-refuted")


def supporting_fold(ctx, artifact: bool = False) -> str:
    """Links to the verification, source availability, feedback and review files found beside findings.json."""
    if not ctx.supporting:
        return ""
    groups: dict[str, list[str]] = {}
    for group, name, href in ctx.supporting:
        link = f'<span class="mono">{e(name)}</span>' if artifact else f'<a href="{e(href)}">{e(name)}</a>'
        groups.setdefault(group, []).append(link)
    rows = [[e(g), ", ".join(links)] for g, links in groups.items()]
    note = ("These files stay in the review folder; the published page names them without links." if artifact
            else "Links are relative to this page, so keep the review folder together.")
    n = len(ctx.supporting)
    return fold("Supporting files", f"{n} {plural(n, 'file')}: " + ", ".join(g.lower() for g in groups),
                table(rows, ["What", "Files"]) + f'<p class="small">{note}</p>', "br-supporting")


def outputs_fold(ctx) -> str:
    files = ["report.md", "findings.json", f"tickets/ ({len(ctx.tickets)} drafts)"]
    if ctx.analysis_href:
        files.append(ctx.analysis_href)
    sample = ctx.tickets[0][1] if ctx.tickets else ""
    body = (f'<p class="small">{e(", ".join(files))}. Export status saves status.json for the next run.</p>'
            + (f"<pre>{e(sample)}</pre>" if sample else ""))
    return fold("Other outputs", f"report.md, findings.json, {len(ctx.tickets)} ticket drafts", body, "br-outputs")


def page_data(ctx) -> dict:
    return {
        "key": f"{ctx.board}-{ctx.revision}-{ctx.hash}", "board": ctx.board, "revision": ctx.revision,
        "hash": ctx.hash, "findings": [f["id"] for f in ctx.findings if not rv.is_question(f)],
        "bench": [b.id for b in ctx.bench],
        "status": ctx.status_items, "pointers": ctx.pointers,
        "place": ctx.facts.place.to_dict() if ctx.facts.place else None,
        "placeNote": " ".join(ctx.facts.notes),
    }


def render(ctx, artifact: bool = False) -> str:
    """The page; artifact=True keeps checkbox state in the artifact's shared database."""
    head = ctx.header
    title_text = f"{ctx.board} Rev {ctx.revision} Review" if ctx.revision else f"{ctx.board} Review"
    h1 = f"{ctx.board} · Rev {ctx.revision}" if ctx.revision else ctx.board
    first = ", ".join(x for x in (head.get("stage", "Review"), head.get("date", "")) if x)
    meta = " · ".join(x for x in (first, head.get("variant", ""), head.get("scope", "")) if x)
    verdict, vcls = verdict_line(ctx.findings, head)
    problems = [f for f in ctx.findings if not rv.is_question(f)]
    nf = len(problems)
    analysis = (f'<a href="{e(ctx.analysis_href)}">Full analysis</a>' if ctx.analysis_href else "")
    save = ("Checkmarks load from this page's shared record." if artifact
            else "Checkmarks are saved in this browser only.")
    body = f"""<div class="page">
<header class="head">
  <h1>{e(h1)}</h1>
  <span class="meta">{e(meta)}</span>
</header>
<section class="verdict {vcls}" aria-labelledby="br-vh">
  <h2 id="br-vh">{e(verdict)}</h2>
  <p class="counts" id="br-counts">{e(counts_line(ctx.findings))}</p>
  <div class="progress" aria-live="polite">
    <div class="bar" aria-hidden="true"><span class="b-ver" id="br-barver" style="width:0%"></span><span class="b-fix" id="br-barfix" style="width:0%"></span></div>
    <span class="legend"><span class="dot d-fix"></span><span id="br-nfix">0</span> of {nf} fixed in design</span>
    <span class="legend"><span class="dot d-ver"></span><span id="br-nver">0</span> confirmed in the data</span>
    <span class="legend"><span id="br-nbench">0</span> of {len(ctx.bench)} bench steps</span>
  </div>
  <div class="actions"><button class="btn" type="button" id="br-export">Export status</button>{analysis}<span class="save" id="br-save">{e(save)}</span></div>
</section>
<section class="list" id="br-list" aria-label="Findings">
{chr(10).join(finding_row(f, ctx) for f in problems) or '<p class="small">No confirmed problems.</p>'}
</section>
{questions_section(ctx)}
<div class="folds">
{chr(10).join(x for x in (bench_fold(ctx), changes_fold(ctx) if ctx.changes else "", power_tree_fold(ctx),
                          not_published_fold(ctx), firmware_fold(ctx), known_good_fold(ctx), coverage_fold(ctx),
                          unknown_fold(ctx), refuted_fold(ctx), supporting_fold(ctx, artifact),
                          outputs_fold(ctx)) if x)}
</div>
<p class="small">Written by python -m boardreview report from {e(ctx.findings_name)} and {e(ctx.facts.path.name)}. Findings hash {e(ctx.hash)}.</p>
</div>"""
    data = json.dumps(page_data(ctx), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    script = asset("report.js") + "\n" + asset("artifact.js" if artifact else "local.js")
    css = asset("report.css")
    tail = f'<script type="application/json" id="br-data">{data}</script>\n<script>\n{script}</script>\n'
    if artifact:
        return f"<title>{e(title_text)}</title>\n{fonts(ctx)}<style>\n{css}</style>\n{body}\n{tail}"
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            f"<title>{e(title_text)}</title>\n{fonts(ctx)}<style>\n{css}</style>\n</head>\n<body>\n{body}\n{tail}</body>\n</html>\n")
