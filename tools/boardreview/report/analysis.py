"""analysis.html: every check run, by block instance, with full Result tables, plots, digest values and sim sanity."""

from __future__ import annotations

import re

from boardreview.model.board import natural_key
from boardreview.report import review as rv
from boardreview.report.html import FONTS, _VERDICT_CHIP, asset, calc_html, e, plural, table

VERDICT_ORDER = ("fail", "marginal", "unknown", "pass", "not_applicable")
VERDICT_TEXT = {"fail": "Fail", "marginal": "Marginal", "unknown": "Unknown", "pass": "Pass",
                "not_applicable": "Not applicable"}


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()


def chip(verdict: str) -> str:
    return f'<span class="chip {_VERDICT_CHIP.get(verdict, "note")}">{e(VERDICT_TEXT.get(verdict, verdict))}</span>'


def counts(checks: list[dict]) -> str:
    n = {v: sum(1 for c in checks if c["verdict"] == v) for v in VERDICT_ORDER}
    return " · ".join(f"{n[v]} {VERDICT_TEXT[v].lower()}" for v in VERDICT_ORDER if n[v])


def _digest(rows: list[dict]) -> str:
    out = []
    for d in rows:
        src = ", ".join(x for x in (d.get("document", ""), f"p.{d['page']}") if x)
        vals = [e(f"{d[k]:g}") if isinstance(d.get(k), (int, float)) else "" for k in ("min", "typ", "max")]
        out.append([e(d.get("mpn", "")), e(d.get("parameter", "")), e(d.get("condition", "")), *vals,
                    e(d.get("unit", "")), e(src)])
    return table(out, ["MPN", "Parameter", "Condition", "Min", "Typ", "Max", "Unit", "Source"])


def _simulation(s: dict, uid: str) -> str:
    trusted = s["setup_verdict"] == "pass"
    head = (f'<p class="small">Setup {chip(s["setup_verdict"])} Measured {chip(s["measured_verdict"])} '
            + ("The measured verdict counts: every setup check passed." if trusted
               else "The measured verdict does not count until every setup check passes.") + "</p>")
    if s.get("setup"):
        head = f'<p class="small mono">{e(s["setup"])}</p>' + head
    rows = [[e(x["check"]), chip(x["verdict"]), e(x.get("detail", ""))] for x in s.get("sanity", [])]
    body = head + (table(rows, ["Sanity check", "Verdict", "Detail"]) if rows else "")
    body += "".join(calc_html(c, f"{uid}-s{i}") for i, c in enumerate(s.get("results", [])))
    if s.get("limits"):
        body += '<p class="small">Model limits: ' + e("; ".join(s["limits"])) + "</p>"
    return f'<details open><summary>Simulation</summary><div class="stack">{body}</div></details>'


def check_html(c: dict, report_href: str, known: set[str]) -> str:
    cid = c["id"]
    is_open = c["verdict"] in ("fail", "marginal", "unknown")
    link = ""
    if c.get("finding"):
        where = f"{report_href}#{c['finding']}" if c["finding"] in known else report_href
        link = f'<a href="{e(where)}">Finding {e(c["finding"])}</a>'
    parts = []
    if c.get("reason"):
        parts.append(f'<p>{e(c["reason"])}</p>')
    for i, r in enumerate(c.get("results", [])):
        parts.append(calc_html(r, f"{cid}-r{i}"))
    if c.get("digest_values"):
        parts.append(f'<details open><summary>Datasheet values used</summary>{_digest(c["digest_values"])}</details>')
    if c.get("not_published"):
        rows = [[e(n["item"]), e(n.get("searched", "")), e(n["consequence"].replace("_", " ")), e(n.get("action", ""))]
                for n in c["not_published"]]
        parts.append(f'<details open><summary>Not published</summary>'
                     f'{table(rows, ["Missing value", "Searched", "Became", "Action"])}</details>')
    if c.get("simulation"):
        parts.append(_simulation(c["simulation"], cid))
    if c.get("assumptions"):
        parts.append('<ul class="ev">' + "".join(f'<li><span class="ek">Assumes</span>{e(a)}</li>'
                                                 for a in c["assumptions"]) + "</ul>")
    if c.get("sources"):
        parts.append('<ul class="ev">' + "".join(
            f'<li><span class="ek">{e(s["kind"])}</span>{e(s["ref"])}' + (f": {e(s['detail'])}" if s.get("detail") else "")
            + "</li>" for s in c["sources"]) + "</ul>")
    if c.get("bench_test"):
        parts.append(f'<p class="small"><b>Bench test:</b> {e(c["bench_test"])}</p>')
    if link:
        parts.append(f'<p class="small">{link} in the report.</p>')
    by = f'<span class="fid">{e(c["by"])}</span>' if c.get("by") else ""
    return (f'<details class="chk" id="chk-{e(cid)}"{" open" if is_open else ""}>'
            f'<summary>{chip(c["verdict"])}<span class="fid">{e(c["item"])}</span>{e(c.get("title", ""))}'
            f'{(" · " + link) if link else ""}{by}</summary><div class="body">{"".join(parts)}</div></details>')


def group(checks: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """(block, instance, checks) in power-first block order, then instance, then item."""
    keys: dict[tuple[str, str], list[dict]] = {}
    for c in checks:
        keys.setdefault((c["block"], c["instance"]), []).append(c)
    order = sorted(keys, key=lambda k: (rv.BLOCK_ORDER.index(k[0]) if k[0] in rv.BLOCK_ORDER else 99,
                                        natural_key(k[1])))
    return [(b, i, sorted(keys[(b, i)], key=lambda c: natural_key(c["item"]))) for b, i in order]


def render(ctx, report_href: str = "report.html") -> str:
    """The analysis page; finding links point at report_href."""
    known = {f["id"] for f in ctx.findings}
    groups = group(ctx.checks)
    h1 = f"{ctx.board} · Rev {ctx.revision}" if ctx.revision else ctx.board
    meta = " · ".join(x for x in ("Full analysis", ctx.header.get("date", ""), ctx.header.get("scope", "")) if x)
    toc = []
    sections = []
    for block, inst, checks in groups:
        sid = "inst-" + slug(f"{block}-{inst}")
        name = rv.BLOCK_NAME.get(block, block)
        worst = next((v for v in VERDICT_ORDER if any(c["verdict"] == v for c in checks)), "pass")
        toc.append(f'<li>{chip(worst)}<a href="#{sid}">{e(inst)}</a><span class="fid">{e(name)} · '
                   f'{e(counts(checks))}</span></li>')
        sections.append(f'<section class="inst" id="{sid}"><header><h2>{e(inst)}</h2><span class="chip outline">'
                        f'{e(name)}</span><span class="fid">{e(counts(checks))}</span></header>'
                        + "".join(check_html(c, report_href, known) for c in checks) + "</section>")
    total = len(ctx.checks)
    body = f"""<div class="page">
<header class="head">
  <h1>{e(h1)}</h1>
  <span class="meta">{e(meta)}</span>
</header>
<section class="verdict" aria-labelledby="an-h">
  <h2 id="an-h">{total} {plural(total, "check")} on {len(groups)} block {plural(len(groups), "instance")}</h2>
  <p class="small">{e(counts(ctx.checks))}. Failing, marginal and unknown checks are open; passes are folded.
  <a href="{e(report_href)}">Back to the report</a>.</p>
  <ul class="toc">{"".join(toc)}</ul>
</section>
{"".join(sections) or '<p class="small">No checks.</p>'}
<p class="small">Written by python -m boardreview report --detail full from {e(ctx.checks_name)}.</p>
</div>"""
    title = f"{ctx.board} Analysis"
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            f"<title>{e(title)}</title>\n{FONTS}\n<style>\n{asset('report.css')}</style>\n</head>\n<body>\n{body}\n"
            f"</body>\n</html>\n")
