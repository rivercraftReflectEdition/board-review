"""The plain reading order: verdict in a word, sentences with numbers, key line, sources as sentences, plot, then the math."""

from __future__ import annotations

import html

from boardreview.calc.base import fmt
from boardreview.report import svgplot

WORD = {"pass": "Passes", "fail": "Fails", "marginal": "Marginal", "unknown": "Unknown",
        "not_applicable": "Not applicable", "info": "Info"}
RANK = {"pass": 0, "marginal": 1, "unknown": 2, "fail": 3}
SAYS = {"netlist": "The netlist shows", "bom": "The BOM says", "variant": "The variant says", "pcb": "The PCB shows",
        "datasheet": "The datasheet says", "errata": "The errata say", "app_note": "The app note says",
        "calculator": "Worked out with", "simulation": "Simulated with", "bench": "On the bench:",
        "lint": "Lint found", "compare": "The netlist compare shows", "design_notes": "The design notes say"}
BECOMES = {"footprint": "the board needs a footprint to fix it on the bench", "bench_test": "a bench test settles it",
           "vendor_question": "it is a question for the vendor", "model": "a model estimate stands in for it"}
_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "G": 1e9}
_BASE = {"V", "A", "Hz", "F", "H", "s", "W", "ohm", "Ω"}


def e(text) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def word(verdict: str) -> str:
    """The verdict as a colored word."""
    return f'<span class="vw v-{e(verdict)}">{e(WORD.get(verdict, verdict.capitalize()))}</span>'


def sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".!?" else text + "."


def value(v: float | None, unit: str) -> str:
    """fmt, with prefixed units from digests ('uH', 'kohm') scaled first."""
    if v is not None and len(unit) > 1 and unit[0] in _PREFIX and unit[1:] in _BASE:
        return fmt(v * _PREFIX[unit[0]], unit[1:])
    return fmt(v, unit)


def key_line(calcs: list[dict], limit: int = 4) -> str:
    """'Phase margin 30.2° (want 45° or more) · Crossover 64.2 kHz' from the calculations' key numbers."""
    seen: set[str] = set()
    bits = []
    for c in calcs:
        for k in c.get("key", []):
            if k["label"] in seen or len(bits) >= limit:
                continue
            seen.add(k["label"])
            bits.append(f"{e(k['label'])} <b>{e(fmt(k.get('value'), k.get('unit', '')))}</b>"
                        + (f" (want {e(k['want'])})" if k.get("want") else ""))
    return f'<p class="keyline">{" · ".join(bits)}</p>' if bits else ""


def _lower_first(text: str) -> str:
    first = text.split(" ", 1)[0]
    return text if first.isupper() or len(first) < 2 or not first[1:].islower() else text[:1].lower() + text[1:]


def digest_clause(d: dict) -> str:
    """'EN rising threshold is 1.15 to 1.25 V'."""
    unit = d.get("unit", "")
    lo, typ, hi = d.get("min"), d.get("typ"), d.get("max")
    if lo is not None and hi is not None:
        a, b = value(lo, unit), value(hi, unit)
        same = a.partition(" ")[2] and a.partition(" ")[2] == b.partition(" ")[2]
        rng = f"{a.partition(' ')[0]} to {b}" if same else f"{a} to {b}"
    elif typ is not None:
        rng = f"typically {value(typ, unit)}"
    elif hi is not None:
        rng = f"at most {value(hi, unit)}"
    elif lo is not None:
        rng = f"at least {value(lo, unit)}"
    else:
        rng = "given"
    what = _lower_first(d.get("parameter", "")) + (f" ({d['condition']})" if d.get("condition") else "")
    return f"{what} is {rng}"


def digest_sentences(rows: list[dict]) -> list[str]:
    """Values from the same document page in one sentence: 'The datasheet says A is X and B is Y (doc, p.5).'"""
    groups: list[tuple[str, list[dict]]] = []
    for d in rows:
        where = ", ".join(x for x in (d.get("document") or d.get("mpn", ""), f"p.{d['page']}") if x)
        if groups and groups[-1][0] == where:
            groups[-1][1].append(d)
        else:
            groups.append((where, [d]))
    out = []
    for where, ds in groups:
        clauses = [digest_clause(d) for d in ds]
        joined = clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + " and " + clauses[-1]
        out.append(f"The datasheet says {joined} ({where}).")
    return out


def digest_sentence(d: dict) -> str:
    """'The datasheet says EN rising threshold is 1.15 to 1.25 V (U1 datasheet rev A, p.5).'"""
    return digest_sentences([d])[0]


def source_sentence(s: dict) -> str:
    ref = s.get("ref", "") + (f": {s['detail']}" if s.get("detail") else "")
    return sentence(f"{SAYS.get(s.get('kind'), s.get('kind', '').capitalize())} {ref}")


def unpublished_sentence(n: dict) -> str:
    where = f" (looked in {n['searched']})" if n.get("searched") else ""
    action = f": {n['action']}" if n.get("action") else ""
    return sentence(f"The {n['item']} is not published{where}, so {BECOMES.get(n['consequence'], 'it stays open')}"
                    f"{action}")


def sources(check: dict) -> str:
    lines = digest_sentences(check.get("digest_values", []))
    lines += [source_sentence(s) for s in check.get("sources", [])]
    lines += [unpublished_sentence(n) for n in check.get("not_published", [])]
    return f'<p class="srcs">{" ".join(e(x) for x in lines)}</p>' if lines else ""


def plots(calcs: list[dict], uid: str) -> str:
    out = []
    for i, c in enumerate(calcs):
        for j, p in enumerate(c.get("plots", [])):
            cap = f"<figcaption>{e(p['caption'])}</figcaption>" if p.get("caption") else ""
            out.append(f'<figure class="plot">{svgplot.plot_svg(p, f"{uid}-{i}-{j}")}{cap}</figure>')
    return "".join(out)


def _rows(quantities: dict, cls: str = "") -> str:
    return "".join(f'<tr{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}><td>{e(q.get("label") or k)}</td>'
                   f'<td class="num">{e(fmt(q.get("value"), q.get("unit", "")))}</td>'
                   f'<td class="src">{e(q.get("note", ""))}</td></tr>' for k, q in quantities.items())


def math_fold(calcs: list[dict]) -> str:
    """'The math': for each calculation the formula, every input with its note, every output, the references."""
    if not calcs:
        return ""
    parts = []
    for c in calcs:
        refs = "; ".join(c.get("refs", []))
        parts.append(f'<div class="mathpart"><p class="small">{word(c.get("verdict", "info"))} '
                     f'<span class="mono">{e(c.get("calculator", ""))}</span>'
                     + (f" · {e(c['reason'])}" if c.get("reason") else "") + "</p>"
                     f'<p class="formula">{e(c.get("formula", ""))}</p>'
                     f'<div class="scroll"><table class="io"><tbody>{_rows(c.get("inputs", {}))}'
                     f'{_rows(c.get("outputs", {}), "out")}</tbody></table></div>'
                     + (f'<p class="small">References: {e(refs)}</p>' if refs else "") + "</div>")
    return f'<details class="sub"><summary>The math</summary>{"".join(parts)}</details>'


def assumptions_fold(items: list[str]) -> str:
    items = list(dict.fromkeys(a for a in items if a))
    if not items:
        return ""
    lis = "".join(f"<li>{e(sentence(a[:1].upper() + a[1:]))}</li>" for a in items)
    return f'<details class="sub"><summary>Assumptions ({len(items)})</summary><ul class="plain">{lis}</ul></details>'


def calc_block(c: dict, uid: str) -> str:
    """One calculation in reading order, for a finding's Math fold."""
    name = c.get("name") or c.get("calculator", "")
    head = f'<p class="hl">{word(c.get("verdict", "info"))} {e(name[:1].upper() + name[1:])}</p>'
    lead = f'<p class="lead">{e(c["summary"])}</p>' if c.get("summary") else ""
    return (f'<div class="calcx">{head}{lead}{key_line([c])}{plots([c], uid)}{math_fold([c])}'
            f'{assumptions_fold(c.get("assumptions", []))}</div>')


def worst(calcs: list[dict]) -> str:
    ranked = [c.get("verdict") for c in calcs if c.get("verdict") in RANK]
    return max(ranked, key=RANK.__getitem__) if ranked else ""


def check_problems(check: dict, plain: bool = False) -> list[str]:
    """A check that reads better than its worst calculation without a summary saying why; plain=True for readers."""
    v = check.get("verdict")
    sim = check.get("simulation", {})
    calcs = list(check.get("results", [])) + (list(sim.get("results", [])) if sim.get("setup_verdict") == "pass" else [])
    soft = sorted({c["context"] for c in calcs if c.get("context") in ("nominal", "example", "ideal")})
    if v == "pass" and soft:
        if plain:
            return [f"This check says Passes, but its numbers come from {' and '.join(soft)} inputs, not the worst case."]
        return [f"{check['id']} says pass from {', '.join(soft)} inputs; only worst-case inputs can pass a check"]
    w = worst(calcs)
    if not (v in RANK and w and RANK[v] < RANK[w]) or check.get("summary", "").strip():
        return []
    if plain:
        return [f"This check says {WORD[v]}, but its calculation says {WORD[w]}, and the check does not say why."]
    who = next(c.get("calculator", "") for c in calcs if c.get("verdict") == w)
    return [f"{check['id']} says {WORD[v]} but {who} says {WORD[w]}; give the check a summary that says why"]
