"""Find a fix in the data: part removed or DNP, value changed, pin moved to a net. Anything else needs a reviewer."""

from __future__ import annotations

import re
from dataclasses import dataclass

from boardreview.model import fields, parts

REF = r"[A-Z]{1,4}\d{1,5}"
REFS = rf"{REF}(?:\s*-\s*(?:[A-Z]{{1,4}})?\d{{1,5}})?(?:\s*(?:,|and|&)\s*{REF}(?:\s*-\s*(?:[A-Z]{{1,4}})?\d{{1,5}})?)*"
PIN = rf"{REF}\.[A-Za-z0-9_+-]+"
VALUE = r"\d+(?:[.,]\d+)?\s*(?:meg|[pnuµμmkKMGRr])?\d*\s*(?:ohms?|Ω|F|H|Hz)?"
NET = r"[A-Za-z0-9_+/.~()-]+"
_ADVICE = re.compile(r"^(?:check|recheck|verify|confirm|measure|keep|note|document|write down|see)\b", re.I)
_PATTERNS = [
    ("dnp", re.compile(rf"^(?:dnp|depopulate|remove|delete|do not (?:fit|place|populate)|unfit)\s+({REFS})$", re.I)),
    ("dnp", re.compile(rf"^({REFS})\s*(?:to\s+)?(?:dnp|not fitted|unfitted|removed|depopulated)$", re.I)),
    ("value", re.compile(rf"^(?:change\s+|set\s+)?({REF})\s*(?:to|=|->|→)\s*({VALUE})$", re.I)),
    ("net", re.compile(rf"^(?:connect|tie|move|reconnect)\s+({PIN})\s+to\s+(?:net\s+)?({NET})$", re.I)),
    ("net", re.compile(rf"^({PIN})\s+(?:to|->|→)\s+(?:net\s+)?({NET})$", re.I)),
]


@dataclass(frozen=True)
class Intent:
    kind: str
    target: str
    want: str = ""


def clauses(fix: str) -> list[str]:
    """Sentences and semicolon parts of a fix, trimmed of end punctuation."""
    out = []
    for part in re.split(r"(?<=[.;])\s+|;\s*", fix.strip()):
        part = part.strip().rstrip(".;").strip()
        if part:
            out.append(part)
    return out


def parse_fix(fix: str) -> tuple[list[Intent], list[str]]:
    """Intents a script can check, and the clauses it cannot read."""
    intents: list[Intent] = []
    unread: list[str] = []
    for c in clauses(fix):
        if _ADVICE.match(c):
            continue
        for kind, rx in _PATTERNS:
            m = rx.match(c)
            if not m:
                continue
            if kind == "dnp":
                refs = re.split(r"\s*(?:,|and|&)\s*", m.group(1))
                intents += [Intent("dnp", r) for item in refs for r in fields.expand_refdes(item.replace(" ", ""))]
            else:
                intents.append(Intent(kind, m.group(1), m.group(2).strip()))
            break
        else:
            unread.append(c)
    return intents, unread


def _value(text: str, kind: str) -> float | None:
    return parts.value_si(text, kind) if text else None


def _same_net(a: str | None, b: str) -> bool:
    if a is None:
        return False
    x, y = a.upper().strip("/"), b.upper().strip("/")
    return x == y or x.rsplit("/", 1)[-1] == y.rsplit("/", 1)[-1]


def check_intent(it: Intent, old, new) -> tuple[bool | None, str]:
    """True when the new facts show the change (and the old ones did not), False when they show it was not made."""
    if it.kind == "dnp":
        now = new.components.get(it.target)
        before = old.components.get(it.target) if old is not None else None
        if old is not None and (before is None or not before.get("fitted", True)):
            return None, f"{it.target} was not fitted in the old data either"
        if now is None:
            return True, f"{it.target} is gone from the new data"
        if not now.get("fitted", True):
            return True, f"{it.target} is DNP in the new data"
        return False, f"{it.target} is still fitted in the new data"
    if it.kind == "value":
        now = new.components.get(it.target)
        if now is None:
            return False, f"{it.target} is not in the new data"
        want = _value(it.want, now.get("kind", ""))
        got = now.get("value_si")
        got = got if got is not None else _value(now.get("value", ""), now.get("kind", ""))
        if want is None or got is None:
            return None, f"cannot read {it.target} {now.get('value', '')!r} or {it.want!r} as a value"
        before = old.components.get(it.target) if old is not None else None
        was = before.get("value_si") if before else None
        if abs(got - want) <= 0.005 * abs(want):
            if was is not None and abs(was - want) <= 0.005 * abs(want):
                return None, f"{it.target} was already {before.get('value')} in the old data"
            return True, f"{it.target} is {now.get('value')} in the new data" + (
                f" (was {before.get('value')})" if before else "")
        if was is not None and abs(got - was) <= 0.005 * abs(was or 1.0):
            return False, f"{it.target} is still {now.get('value')}; the fix says {it.want}"
        return False, f"{it.target} is {now.get('value')}; the fix says {it.want}"
    if it.kind == "net":
        now = new.pins.get(it.target)
        if now is None:
            return False, f"{it.target} is not in the new data"
        before = old.pins.get(it.target) if old is not None else None
        if _same_net(now.get("net"), it.want):
            if before is not None and _same_net(before.get("net"), it.want):
                return None, f"{it.target} was already on {it.want} in the old data"
            return True, f"{it.target} is on {now.get('net')} in the new data" + (
                f" (was {before.get('net') or 'no net'})" if before is not None else "")
        if before is not None and before.get("net") == now.get("net"):
            return False, f"{it.target} is still on {now.get('net') or 'no net'}; the fix says {it.want}"
        return False, f"{it.target} is on {now.get('net') or 'no net'}; the fix says {it.want}"
    return None, f"cannot check {it.kind}"


def check_fix(finding: dict, old, new) -> tuple[bool | None, str]:
    """Verdict on one finding's fix with a one-line note; None means a reviewer has to look."""
    intents, unread = parse_fix(finding.get("fix", ""))
    if not intents:
        return None, "needs a reviewer: the fix names no part removal, value change or pin move a script can check"
    results = [check_intent(it, old, new) for it in intents]
    bad = [n for ok, n in results if ok is False]
    if bad:
        return False, "; ".join(bad)
    if any(ok is None for ok, _ in results) or unread:
        seen = [n for ok, n in results if ok]
        rest = [n for ok, n in results if ok is None] + [f"cannot check '{c}'" for c in unread]
        return None, "needs a reviewer: " + "; ".join(seen + rest)
    return True, "; ".join(n for _, n in results)


def verify_fixes(findings: list[dict], old, new, now: str) -> list[tuple[str, bool | None, str]]:
    """Set verified_in_data on every finding marked fixed; returns (id, verdict, note) per finding checked."""
    out = []
    for f in findings:
        st = f.get("status", {})
        if not st.get("fixed") or f.get("verification", {}).get("status") == "WRONG":
            continue
        ok, note = check_fix(f, old, new)
        st = dict(st)
        if ok is None:
            st.pop("verified_in_data", None)
        else:
            st["verified_in_data"] = ok
        st["verify_note"] = note
        st["verified_at"] = now
        f["status"] = st
        out.append((f["id"], ok, note))
    return out
