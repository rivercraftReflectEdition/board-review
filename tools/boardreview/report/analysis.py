"""analysis.html: every check run, by block instance, explained in words first and with the math folded."""

from __future__ import annotations

import re

from boardreview.model.board import natural_key
from boardreview.report import plain
from boardreview.report import review as rv
from boardreview.report.html import asset, fonts, plural
from boardreview.report.plain import e, word

ORDER = ("fail", "marginal", "unknown", "pass", "not_applicable")
COUNT_WORD = {"fail": "fail", "marginal": "marginal", "unknown": "unknown", "pass": "pass",
              "not_applicable": "not applicable"}


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()


def counts(checks: list[dict]) -> str:
    n = {v: sum(1 for c in checks if c["verdict"] == v) for v in ORDER}
    return ", ".join(f"{n[v]} {COUNT_WORD[v]}" for v in ORDER if n[v])


def headline(c: dict) -> str:
    return c.get("headline") or f"{c['instance']}: {c.get('title') or c['item']}"


def lead(c: dict) -> str:
    """The check's own summary, or its reason followed by the first calculation's summary."""
    if c.get("summary"):
        text = c["summary"]
    else:
        parts = [plain.sentence(c["reason"])] if c.get("reason") else []
        first = next((r for r in c.get("results", []) if r.get("summary")), None)
        if first:
            parts.append(first["summary"])
        text = " ".join(parts)
    return f'<p class="lead">{e(text)}</p>' if text else ""


def sim_fold(s: dict, uid: str) -> str:
    checks = s.get("sanity", [])
    passed = sum(1 for x in checks if x["verdict"] == "pass")
    counted = ("The measured result counts: every setup check passed." if s["setup_verdict"] == "pass"
               else "The measured result does not count until every setup check passes.")
    body = [f'<p>Setup {word(s["setup_verdict"])}. Measured {word(s["measured_verdict"])}. {counted}</p>']
    if s.get("setup"):
        body.append(f'<p class="small">Run: {e(s["setup"])}</p>')
    if checks:
        body.append('<ul class="plain">' + "".join(
            f"<li>{word(x['verdict'])} {e(x['check'])}" + (f": {e(x['detail'])}" if x.get("detail") else "") + "</li>"
            for x in checks) + "</ul>")
    body += [plain.calc_block(r, f"{uid}-s{i}") for i, r in enumerate(s.get("results", []))]
    if s.get("limits"):
        body.append(f'<p class="small">Model limits: {e("; ".join(s["limits"]))}.</p>')
    title = f"Simulation checks ({passed} passed)" if passed == len(checks) else \
        f"Simulation checks ({passed} of {len(checks)} passed)"
    return f'<details class="sub"><summary>{e(title)}</summary>{"".join(body)}</details>'


def check_html(c: dict, report_href: str, known: set[str]) -> str:
    cid = c["id"]
    results = c.get("results", [])
    flag = "".join(f'<p class="flagnote">{e(m)}</p>' for m in plain.check_problems(c, plain=True))
    bench = f'<p>Bench test: {e(plain.sentence(c["bench_test"]))}</p>' if c.get("bench_test") else ""
    link = ""
    if c.get("finding"):
        where = f"{report_href}#{c['finding']}" if c["finding"] in known else report_href
        link = f' · <a href="{e(where)}">Finding {e(c["finding"])} in the report</a>'
    assumptions = list(c.get("assumptions", [])) + [a for r in results for a in r.get("assumptions", [])]
    body = (lead(c) + plain.key_line(results) + flag + plain.sources(c) + plain.plots(results, cid) + bench
            + plain.math_fold(results) + plain.assumptions_fold(assumptions)
            + (sim_fold(c["simulation"], cid) if c.get("simulation") else "")
            + f'<p class="small">Checklist item {e(c["item"])}{link}</p>')
    is_open = c["verdict"] in ("fail", "marginal", "unknown")
    return (f'<details class="chk" id="chk-{e(cid)}"{" open" if is_open else ""}><summary>{word(c["verdict"])} '
            f'{e(headline(c))}</summary><div class="body">{body}</div></details>')


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
    toc, sections = [], []
    for block, inst, checks in groups:
        sid = "inst-" + slug(f"{block}-{inst}")
        name = rv.BLOCK_NAME.get(block, block)
        worst = next((v for v in ORDER if any(c["verdict"] == v for c in checks)), "pass")
        toc.append(f'<li>{word(worst)} <a href="#{sid}">{e(inst)}</a> <span class="small">{e(name)}, '
                   f'{e(counts(checks))}</span></li>')
        sections.append(f'<section class="inst" id="{sid}"><h2>{e(inst)}</h2><p class="small">{e(name)}, '
                        f'{len(checks)} {plural(len(checks), "check")}: {e(counts(checks))}</p>'
                        + "".join(check_html(c, report_href, known) for c in checks) + "</section>")
    flagged = [m for c in ctx.checks for m in plain.check_problems(c, plain=True)]
    one = len(flagged) == 1
    warn = (f'<p class="flagnote">{len(flagged)} {plural(len(flagged), "check")} {"reads" if one else "read"} better '
            f'than {"its" if one else "their"} numbers without saying why. Look for the notes below.</p>') if flagged else ""
    total = len(ctx.checks)
    body = f"""<div class="page">
<header class="head">
  <h1>{e(h1)}</h1>
  <span class="meta">{e(meta)}</span>
</header>
<section class="verdict" aria-labelledby="an-h">
  <h2 id="an-h">{total} {plural(total, "check")} on {len(groups)} {plural(len(groups), "part")} of the board</h2>
  <p class="small">{e(counts(ctx.checks))}. Failing, marginal and unknown checks are open; passes are folded.
  <a href="{e(report_href)}">Back to the report</a>.</p>
  {warn}
  <ul class="toc">{"".join(toc)}</ul>
</section>
{"".join(sections) or '<p class="small">No checks.</p>'}
<p class="small">Written by python -m boardreview report --detail full from {e(ctx.checks_name)}.</p>
</div>"""
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            f"<title>{e(ctx.board)} Analysis</title>\n{fonts(ctx)}<style>\n{asset('report.css')}</style>\n</head>\n<body>\n"
            f"{body}\n</body>\n</html>\n")
