"""Score board reviews against expected findings: recall, precision and misses per board and split."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT =Path(__file__).resolve().parent.parent
FINDING_SCHEMA = ROOT / "skill" / "schemas" / "finding.schema.json"
EXPECTED_SCHEMA = Path(__file__).resolve().parent / "expected.schema.json"
BUG_CLASSES = Path(__file__).resolve().parent / "bug_classes.json"
TEXT_FIELDS = ("title", "claim", "mechanism", "fix", "instance", "check")
SPLITS = ("dev", "held-out")

BLOCK_ALIASES = {
    "buck": "buck_regulator", "smps": "buck_regulator", "switcher": "buck_regulator",
    "switching_regulator": "buck_regulator", "dc_dc": "buck_regulator",
    "linear_regulator": "ldo",
    "ferrite": "ferrite_lc_filter", "bead": "ferrite_lc_filter", "lc_filter": "ferrite_lc_filter",
    "filter": "ferrite_lc_filter",
    "pdn": "pdn_decoupling", "decoupling": "pdn_decoupling",
    "rails": "cascaded_rails", "power_tree": "cascaded_rails",
    "enable": "enable_uvlo_sequencing", "uvlo": "enable_uvlo_sequencing",
    "sequencing": "enable_uvlo_sequencing",
    "reset": "resets_supervisors_watchdogs", "resets": "resets_supervisors_watchdogs",
    "supervisor": "resets_supervisors_watchdogs", "watchdog": "resets_supervisors_watchdogs",
    "clock": "clocks_crystals", "clocks": "clocks_crystals", "crystal": "clocks_crystals",
    "oscillator": "clocks_crystals",
    "io": "io_levels_and_domains", "io_levels": "io_levels_and_domains",
    "domains": "io_levels_and_domains",
    "strap": "straps_and_boot_pins", "straps": "straps_and_boot_pins",
    "boot": "straps_and_boot_pins", "boot_pins": "straps_and_boot_pins",
    "ethernet": "ethernet_phy", "phy": "ethernet_phy",
    "camera": "camera_csi", "csi": "camera_csi", "mipi_csi": "camera_csi",
    "xspi": "xspi_memory", "memory": "xspi_memory", "qspi": "xspi_memory",
    "ospi": "xspi_memory", "flash": "xspi_memory", "psram": "xspi_memory",
    "protection": "protection_tvs", "tvs": "protection_tvs", "esd": "protection_tvs",
    "thermals": "thermal",
    "pcb_layout": "layout", "placement": "layout",
    "netlist": "netlist_integrity", "connectivity": "netlist_integrity",
    "compile": "netlist_integrity", "erc": "netlist_integrity",
}

MODE_SYNONYMS = {
    "oscillation": "loop_instability", "instability": "loop_instability",
    "limit_cycle": "loop_instability", "phase_margin": "loop_instability",
    "low_phase_margin": "loop_instability", "unstable": "loop_instability",
    "reverse": "reverse_current", "sink": "reverse_current", "pumping": "reverse_current",
    "backfeed": "reverse_current", "back_feed": "reverse_current",
    "back_powering": "back_power", "backpower": "back_power", "back_drive": "back_power",
    "back_bias": "back_power",
    "resonance": "lc_resonance", "peaking": "lc_resonance", "tank": "lc_resonance",
    "lc_tank": "lc_resonance",
    "typo": "wrong_value", "value_typo": "wrong_value", "value_error": "wrong_value",
    "bad_value": "wrong_value",
    "short": "net_short", "shorted_nets": "net_short", "name_collision": "net_short",
    "duplicate_net": "net_short",
    "floating": "open_net", "unconnected": "open_net", "open": "open_net",
    "single_pin_net": "open_net",
    "sheet_missing": "missing_sheet", "dropped_sheet": "missing_sheet",
    "compile_gap": "missing_sheet",
    "margin": "threshold_margin", "thin_margin": "threshold_margin",
    "threshold": "threshold_margin",
    "logic_level": "level_mismatch", "vih": "level_mismatch", "vil": "level_mismatch",
    "no_pullup": "missing_pullup", "pullup_missing": "missing_pullup",
    "strap": "strap_conflict", "straps": "strap_conflict",
    "boot": "boot_mode", "watchdog": "reset_hazard", "reset_loop": "reset_hazard",
    "swap": "pin_swap", "crossed": "pin_swap",
    "tvs": "protection_gap", "esd": "protection_gap", "standoff": "protection_gap",
    "overheat": "thermal_overstress", "isat": "saturation",
    "no_footprint": "missing_rework_option",
}

EQUIVALENT_BLOCKS = {
    "missing_pullup": ({"io_levels_and_domains", "resets_supervisors_watchdogs", "enable_uvlo_sequencing",
                        "camera_csi", "ethernet_phy"}, ("IO-7", "RST-4", "EN-8", "CSI-4", "ETH-3")),
    "strap_conflict": ({"straps_and_boot_pins", "ethernet_phy"}, ("STR-1", "STR-2", "ETH-1")),
    "reverse_current": ({"cascaded_rails", "buck_regulator"}, ("CR-1", "BR-5")),
    "back_power": ({"io_levels_and_domains", "camera_csi"}, ("IO-3", "CSI-4")),
    "net_short": ({"netlist_integrity", "xspi_memory"}, ("NET-2", "MEM-1")),
}

REFDES_RANGE = re.compile(r"^([A-Z]+)(\d+)\s*-\s*(?:\1)?(\d+)$")

PASS_PHRASE = re.compile(
    r"\b(?:is|are|was|were|stays|remains|looks|seems|appears|be) (?:stable|fine|ok|okay|correct|adequate"
    r"|sufficient|acceptable|safe|good|compliant|in spec|within (?:spec|limits|range|rating))\b"
    r"|\b(?:passes|passed)\b(?! (?:through|into|to|from|via|across|over|along|around)\b)"
    r"|\bno (?:issue|problem|concern|fault|violation)s?\b|\bno risk of\b|\bnone needed\b"
    r"|\bno (?:action|change)s? (?:needed|required)\b|\bnot an? (?:issue|problem|concern|bug|fault)\b")
NEGATED = re.compile(r"\b(?:not|never|t)(?: \w+)? $")
QUALIFIER = re.compile(r"\b(?:but|however|except|although|though|yet|until|unless|only)\b")
FAILING_VERDICTS = ("fail", "marginal")


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_schema(path: Path = FINDING_SCHEMA) -> dict:
    return load_json(path)


def vocab(schema: dict) -> tuple[set[str], set[str]]:
    """Block and failure-mode vocabularies from the finding schema."""
    defs = schema["$defs"]
    return set(defs["block"]["enum"]), set(defs["failure_mode"]["enum"])


def _type_ok(inst, types) -> bool:
    for t in types if isinstance(types, list) else [types]:
        if t in ("number", "integer"):
            if isinstance(inst, bool):
                continue
            if t == "integer" and isinstance(inst, int):
                return True
            if t == "number" and isinstance(inst, (int, float)):
                return True
        elif isinstance(inst, {"object": dict, "array": list, "string": str,
                               "boolean": bool, "null": type(None)}[t]):
            return True
    return False


def validate(inst, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Check an instance against the JSON Schema subset the skill schemas use."""
    root = root if root is not None else schema
    errs: list[str] = []
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        errs += validate(inst, node, root, path)
    if "type" in schema and not _type_ok(inst, schema["type"]):
        return errs + [f"{path}: expected {schema['type']}"]
    if "enum" in schema and inst not in schema["enum"]:
        errs.append(f"{path}: {inst!r} not in {schema['enum']}")
    if "const" in schema and inst != schema["const"]:
        errs.append(f"{path}: {inst!r} is not {schema['const']!r}")
    if isinstance(inst, str):
        if len(inst) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than {schema['minLength']}")
        if len(inst) > schema.get("maxLength", math.inf):
            errs.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], inst):
            errs.append(f"{path}: {inst!r} does not match {schema['pattern']}")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if inst < schema.get("minimum", -math.inf):
            errs.append(f"{path}: below {schema['minimum']}")
    if isinstance(inst, dict):
        errs += [f"{path}: missing {k}" for k in schema.get("required", []) if k not in inst]
        props, extra = schema.get("properties", {}), schema.get("additionalProperties", True)
        for k, v in inst.items():
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
            elif extra is False:
                errs.append(f"{path}: unexpected key {k}")
            elif isinstance(extra, dict):
                errs += validate(v, extra, root, f"{path}.{k}")
    if isinstance(inst, list):
        if len(inst) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, v in enumerate(inst):
                errs += validate(v, schema["items"], root, f"{path}[{i}]")
    for sub in schema.get("allOf", []):
        errs += validate(inst, sub, root, path)
    if "if" in schema:
        branch = "then" if not validate(inst, schema["if"], root, path) else "else"
        if branch in schema:
            errs += validate(inst, schema[branch], root, path)
    return errs


def norm_token(s) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def canon_block(s, blocks: set[str]) -> str:
    t = norm_token(s)
    return t if t in blocks else BLOCK_ALIASES.get(t, t)


def canon_mode(s, modes: set[str]) -> str:
    t = norm_token(s)
    return t if t in modes else MODE_SYNONYMS.get(t, t)


def norm_parts(items) -> set[str]:
    out: set[str] = set()
    for raw in items or []:
        s = str(raw).strip().upper()
        m = REFDES_RANGE.match(s)
        if m and 0 <= int(m[3]) - int(m[2]) <= 500:
            out.update(f"{m[1]}{i}" for i in range(int(m[2]), int(m[3]) + 1))
        elif s:
            out.add(s)
    return out


def norm_net(s) -> str:
    """Upper case, '_' and spaces as '-', hierarchy path kept as '/'-separated segments."""
    segs = [re.sub(r"[\s_]+", "-", p.strip()) for p in str(s).strip().upper().split("/") if p.strip()]
    if segs:
        segs[-1] = segs[-1].lstrip("+")
    return "/".join(segs)


def same_net(a: str, b: str) -> bool:
    """Equal names; a name without a path also equals any hierarchical name with that last segment."""
    if a == b:
        return True
    if "/" in a and "/" in b:
        return False
    return a.rsplit("/", 1)[-1] == b.rsplit("/", 1)[-1]


def shared_nets(e_nets: set[str], r_nets: set[str]) -> int:
    return sum(any(same_net(e, r) for r in r_nets) for e in e_nets)


def finding_parts(f: dict) -> set[str]:
    return norm_parts(f.get("parts")) | {str(p).split(".")[0].strip().upper() for p in f.get("pins", [])}


def finding_nets(f: dict) -> set[str]:
    return {m for n in f.get("nets", []) if (m := norm_net(n))}


def norm_text(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def finding_text(f: dict) -> str:
    """Text a mechanism can be read from: the finding's prose plus the reason of each failing calculation."""
    reasons = [str(c.get("reason", "")) for c in f.get("calculations", [])
               if c.get("verdict") in FAILING_VERDICTS]
    return norm_text(" ".join([str(f.get(k, "")) for k in TEXT_FIELDS] + reasons))


def asserts_pass(f: dict) -> bool:
    """True when the finding says the circuit is fine: an unqualified pass phrase, or only passing calculations."""
    verdicts = [c.get("verdict") for c in f.get("calculations", []) if c.get("verdict") != "info"]
    if verdicts and all(v == "pass" for v in verdicts):
        return True
    text = norm_text(f"{f.get('title', '')} {f.get('claim', '')}")
    if QUALIFIER.search(text):
        return False
    return any(not NEGATED.search(text[:m.start()]) for m in PASS_PHRASE.finditer(text))


def keyword_hit(alternatives: str, text: str) -> bool:
    """True when any '|' alternative starts a word in text, or appears with spaces removed."""
    squashed = text.replace(" ", "")
    for alt in alternatives.split("|"):
        a = norm_text(alt)
        if not a:
            continue
        if re.search(r"\b" + re.escape(a), text):
            return True
        a2 = a.replace(" ", "")
        if len(a2) >= 6 and a2 in squashed:
            return True
    return False


def keywords_needed(keywords: list[str]) -> int:
    return max(1, math.ceil(len(keywords) / 2))


def accepted_blocks(exp: dict, blocks: set[str], modes: set[str]) -> set[str]:
    """E's block and alt_blocks, plus the equivalence row for E's failure mode when one of them is in it."""
    own = {canon_block(b, blocks) for b in [exp.get("block", ""), *exp.get("alt_blocks", [])]}
    row = EQUIVALENT_BLOCKS.get(canon_mode(exp.get("failure_mode", ""), modes), (set(), ()))[0]
    return own | row if own & row else own


def evaluate(exp: dict, rev: dict, blocks: set[str], modes: set[str]) -> tuple[bool, float]:
    """Match rule: block, location and stated mechanism agree and no pass is asserted; returns (match, specificity)."""
    ok_block = canon_block(rev.get("block", ""), blocks) in accepted_blocks(exp, blocks, modes)
    e_parts, e_nets = norm_parts(exp.get("parts")), finding_nets(exp)
    r_parts, r_nets = finding_parts(rev), finding_nets(rev)
    overlap = len(e_parts & r_parts) + shared_nets(e_nets, r_nets)
    union = len(e_parts | r_parts) + len(e_nets) + len(r_nets) - shared_nets(e_nets, r_nets)
    ok_loc = overlap > 0 or not (e_parts or e_nets)
    rm = canon_mode(rev.get("failure_mode", ""), modes)
    ok_tag = rm == canon_mode(exp.get("failure_mode", ""), modes) or rm in {
        canon_mode(m, modes) for m in exp.get("alt_failure_modes", [])}
    kws = exp.get("keywords", [])
    text = finding_text(rev)
    hits = sum(keyword_hit(k, text) for k in kws)
    ok_mech = bool(kws) and hits >= keywords_needed(kws)
    ok = ok_block and ok_loc and ok_mech and not asserts_pass(rev)
    return ok, (overlap / union if union else 0.0) + (hits / len(kws) if kws else 0.0) + ok_tag


def max_matching(spec: list[list[float | None]]) -> list[tuple[int, int]]:
    """Most pairs possible, one to one; among those, the highest total specificity."""
    cells = [(i, j, w) for i, row in enumerate(spec) for j, w in enumerate(row) if w is not None]
    if not cells:
        return []
    big = 1.0 + sum(w for _, _, w in cells)
    weights = np.zeros((len(spec), len(spec[0])))
    for i, j, w in cells:
        weights[i, j] = big + w
    rows, cols = linear_sum_assignment(weights, maximize=True)
    return sorted((int(i), int(j)) for i, j in zip(rows, cols) if spec[i][j] is not None)


def scored_findings(review: list[dict], include_refuted: bool) -> tuple[list[dict], int]:
    keep = [f for f in review
            if include_refuted or f.get("verification", {}).get("status") != "WRONG"]
    return keep, len(review) - len(keep)


def ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def score_board(expected: dict, review: list[dict], schema: dict,
                include_refuted: bool = False) -> dict:
    """Pair expected and review findings by maximum matching and count the outcome."""
    blocks, modes = vocab(schema)
    exp = expected.get("findings", [])
    good = expected.get("known_good", [])
    revs, refuted = scored_findings(review, include_refuted)
    spec = [[s if ok else None for ok, s in (evaluate(e, r, blocks, modes) for r in revs)] for e in exp]
    matches = max_matching(spec)
    e_used, r_used = {ei for ei, _ in matches}, {ri for _, ri in matches}
    paired_r = {ri for row in spec for ri, s in enumerate(row) if s is not None}
    dups, good_hits, fps = [], [], []
    for ri, r in enumerate(revs):
        if ri in r_used:
            continue
        if ri in paired_r:
            dups.append(r)
            continue
        hit = next((g for g in good if evaluate(g, r, blocks, modes)[0]), None)
        if hit is not None:
            good_hits.append((r, hit))
        fps.append(r)
    sev: dict[str, list[int]] = {}
    cls: dict[str, list[int]] = {}
    for ei, e in enumerate(exp):
        for table, key in ((sev, e.get("severity", "unspecified")), (cls, e.get("bug_class"))):
            if key is None:
                continue
            row = table.setdefault(key, [0, 0])
            row[0] += ei in e_used
            row[1] += 1
    schema_errors = [f"{r.get('id', '?')}: {msg}" for r in review for msg in validate(r, schema)]
    expected_errors = validate(expected, load_json(EXPECTED_SCHEMA))
    tp = len(matches)
    return {
        "board": expected.get("board", ""),
        "expected": len(exp),
        "scored": len(revs),
        "refuted_excluded": refuted,
        "tp": tp,
        "fp": len(fps),
        "duplicates": len(dups),
        "recall": ratio(tp, len(exp)),
        "precision": ratio(tp, tp + len(fps)),
        "recall_by_severity": sev,
        "detected_by_bug_class": cls,
        "matches": [{"expected": exp[ei].get("id"), "review": revs[ri].get("id")} for ei, ri in matches],
        "misses": [{k: e.get(k) for k in ("id", "title", "severity", "block", "bug_class", "lesson") if e.get(k)}
                   for ei, e in enumerate(exp) if ei not in e_used],
        "false_positives": [{"id": r.get("id"), "title": r.get("title")} for r in fps],
        "known_good_hits": [{"review": r.get("id"), "known_good": g.get("id")} for r, g in good_hits],
        "duplicate_ids": [r.get("id") for r in dups],
        "schema_errors": schema_errors,
        "expected_errors": expected_errors,
    }


def review_list(data) -> list[dict]:
    return data if isinstance(data, list) else data.get("findings", [])


def resolve_board(entry: dict, base: Path, reviews_dir: Path | None) -> tuple[dict | None, list | None, str]:
    exp_rel = entry.get("expected")
    if exp_rel is None:
        expected = {"board": entry["name"], "findings": []}
    else:
        p = base / exp_rel
        if not p.exists():
            return None, None, f"expected file not found ({exp_rel})"
        expected = load_json(p)
    candidates = []
    if reviews_dir is not None:
        candidates.append(reviews_dir / f"{entry['name']}.json")
    if entry.get("review"):
        candidates.append(base / entry["review"])
    rp = next((c for c in candidates if c.exists()), None)
    if rp is None:
        return expected, None, "no review file"
    return expected, review_list(load_json(rp)), ""


def total(rows: list[dict]) -> dict:
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    exp = sum(r["expected"] for r in rows)
    return {"boards": len(rows), "expected": exp, "tp": tp, "fp": fp,
            "recall": ratio(tp, exp), "precision": ratio(tp, tp + fp)}


def score_manifest(manifest_path: Path, reviews_dir: Path | None = None,
                   include_refuted: bool = False, schema: dict | None = None) -> dict:
    """Score every board in the manifest and total by split and by seeded bug class."""
    schema = schema or load_schema()
    manifest = load_json(manifest_path)
    base = manifest_path.parent
    known_classes = [c["name"] for c in load_json(BUG_CLASSES)["classes"]] if BUG_CLASSES.exists() else []
    boards, skipped = [], []
    for entry in manifest["boards"]:
        if entry.get("split") not in SPLITS:
            raise ValueError(f"{entry['name']}: split must be one of {SPLITS}")
        expected, review, why = resolve_board(entry, base, reviews_dir)
        if review is None:
            skipped.append({"board": entry["name"], "split": entry["split"], "reason": why})
            continue
        row = score_board(expected, review, schema, include_refuted)
        row.update(board=entry["name"], split=entry["split"], kind=entry.get("kind", ""))
        boards.append(row)
    overall = {s: total([b for b in boards if b["split"] == s]) for s in SPLITS}
    overall["all"] = total(boards)
    by_class: dict[str, dict[str, list[int]]] = {}
    for b in boards:
        for name, (hit, n) in b["detected_by_bug_class"].items():
            row = by_class.setdefault(b["split"], {}).setdefault(name, [0, 0])
            row[0] += hit
            row[1] += n
    unknown = sorted({c for t in by_class.values() for c in t} - set(known_classes)) if known_classes else []
    return {"boards": boards, "skipped": skipped, "overall": overall,
            "detected_by_bug_class": by_class, "bug_classes": known_classes,
            "unknown_bug_classes": unknown}


def fmt_ratio(num: int, den: int) -> str:
    return f"{num}/{den} = {num / den:.2f}" if den else f"{num}/0 = n/a"


def format_board(b: dict, reveal: bool) -> list[str]:
    lines = [f"## {b['board']} ({b.get('split', '')}, {b.get('kind', '')})",
             f"recall    {fmt_ratio(b['tp'], b['expected'])}",
             f"precision {fmt_ratio(b['tp'], b['tp'] + b['fp'])}"
             f"  (scored {b['scored']}, duplicates {b['duplicates']}, refuted excluded {b['refuted_excluded']})"]
    if b["recall_by_severity"]:
        lines.append("by severity: " + ", ".join(
            f"{k} {h}/{n}" for k, (h, n) in sorted(b["recall_by_severity"].items())))
    if b["schema_errors"]:
        lines.append(f"schema errors in review: {len(b['schema_errors'])}")
    if b["expected_errors"]:
        lines.append(f"schema errors in expected file: {len(b['expected_errors'])}")
    if b.get("split") == "held-out" and not reveal:
        lines.append("details hidden for a held-out board (use --reveal-heldout after the checklists are frozen)")
        return lines
    lines += [f"MISS {m['id']} [{m.get('severity', '')}] {m.get('block', '')}: {m.get('title', '')}"
              + (f" (lesson {m['lesson']})" if m.get("lesson") else "") for m in b["misses"]]
    lines += [f"FALSE POSITIVE {f['id']}: {f['title']}" for f in b["false_positives"]]
    lines += [f"KNOWN-GOOD FLAGGED {k['review']} matches {k['known_good']}" for k in b["known_good_hits"]]
    lines += [f"DUPLICATE {d}" for d in b["duplicate_ids"]]
    lines += [f"match {m['expected']} <- {m['review']}" for m in b["matches"]]
    lines += [f"schema: {e}" for e in b["schema_errors"]]
    lines += [f"expected file: {e}" for e in b["expected_errors"]]
    return lines


def format_report(result: dict, reveal_heldout: bool = False) -> str:
    lines = ["# Eval score"]
    for split in (*SPLITS, "all"):
        t = result["overall"][split]
        lines.append(f"{split:8s} boards {t['boards']}  recall {fmt_ratio(t['tp'], t['expected'])}"
                     f"  precision {fmt_ratio(t['tp'], t['tp'] + t['fp'])}")
    for split, table in sorted(result["detected_by_bug_class"].items()):
        lines.append(f"seeded bug classes ({split}):")
        for name in sorted(set(table) | set(result.get("bug_classes", []))):
            hit, n = table.get(name, [0, 0])
            lines.append(f"  {name:36s} {hit}/{n}" + ("" if n else "  (not seeded)"))
    if result.get("unknown_bug_classes"):
        lines.append("unknown bug classes: " + ", ".join(result["unknown_bug_classes"]))
    for s in result["skipped"]:
        lines.append(f"skipped {s['board']} ({s['split']}): {s['reason']}")
    for b in result["boards"]:
        lines.append("")
        lines += format_board(b, reveal_heldout)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, help="score every board in a manifest")
    ap.add_argument("--reviews", type=Path, help="directory of <board>.json review files")
    ap.add_argument("--expected", type=Path, help="score one board: expected findings file")
    ap.add_argument("--review", type=Path, help="score one board: review findings file")
    ap.add_argument("--include-refuted", action="store_true", help="also score findings marked WRONG")
    ap.add_argument("--reveal-heldout", action="store_true", help="print misses for held-out boards")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    schema = load_schema()
    if args.manifest:
        result = score_manifest(args.manifest, args.reviews, args.include_refuted, schema)
        print(json.dumps(result, indent=2) if args.json else format_report(result, args.reveal_heldout))
        return 0
    if args.expected and args.review:
        row = score_board(load_json(args.expected), review_list(load_json(args.review)),
                          schema, args.include_refuted)
        print(json.dumps(row, indent=2) if args.json else "\n".join(format_board(row, True)))
        return 0
    ap.error("give --manifest, or --expected with --review")
    return 2


if __name__ == "__main__":
    sys.exit(main())
