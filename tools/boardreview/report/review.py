"""Everything the report shows, loaded and joined: findings, facts, placement, bench plan, checks and status."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from boardreview.model import fields, placement
from boardreview.model.board import natural_key

SEVERITIES = ("blocker", "major", "minor", "note")
SEV_NAME = {"blocker": "Blocker", "major": "Major", "minor": "Minor", "note": "Note"}
CHANGE_LABEL = {"bom_only": "BOM only", "layout": "Layout", "part_change": "Part change", "firmware": "Firmware",
                "none": "None"}
AREA_OF_BLOCK = {
    "buck_regulator": "Power", "ldo": "Power", "ferrite_lc_filter": "Power", "pdn_decoupling": "Power",
    "cascaded_rails": "Power", "enable_uvlo_sequencing": "Power", "resets_supervisors_watchdogs": "Resets",
    "clocks_crystals": "Clocks", "io_levels_and_domains": "I/O", "straps_and_boot_pins": "Straps",
    "ethernet_phy": "Ethernet", "camera_csi": "Camera", "xspi_memory": "Memory", "protection_tvs": "Protection",
    "thermal": "Thermal", "layout": "Layout", "netlist_integrity": "Netlist", "other": "Other",
}
BLOCK_ORDER = ["cascaded_rails", "buck_regulator", "ldo", "ferrite_lc_filter", "pdn_decoupling",
               "enable_uvlo_sequencing", "resets_supervisors_watchdogs", "io_levels_and_domains",
               "straps_and_boot_pins", "ethernet_phy", "camera_csi", "xspi_memory", "clocks_crystals",
               "protection_tvs", "thermal", "layout", "netlist_integrity", "other"]
BLOCK_NAME = {"buck_regulator": "Buck regulators", "ldo": "LDOs", "ferrite_lc_filter": "Filters",
              "pdn_decoupling": "Decoupling", "cascaded_rails": "Rails", "enable_uvlo_sequencing": "Enables and UVLO",
              "resets_supervisors_watchdogs": "Resets", "clocks_crystals": "Clocks", "io_levels_and_domains":
              "I/O levels", "straps_and_boot_pins": "Straps", "ethernet_phy": "Ethernet", "camera_csi": "Camera CSI",
              "xspi_memory": "Memory", "protection_tvs": "Protection", "thermal": "Thermal", "layout": "Layout",
              "netlist_integrity": "Netlist", "other": "Other"}
ID_OK = re.compile(r"^[A-Za-z0-9_.~:@+-]+$")


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def split_file(data) -> tuple[dict, list]:
    """Header and list from a file that is a list, or a dict with the list under 'findings', 'checks' or 'steps'."""
    if isinstance(data, list):
        return {}, data
    for key in ("findings", "checks", "steps", "items", "blocks", "edges"):
        if isinstance(data.get(key), list):
            return {k: v for k, v in data.items() if k != key}, data[key]
    return dict(data), []


def expand(items) -> list[str]:
    """Refdes list with ranges like R14-R22 expanded."""
    out: list[str] = []
    for raw in items or []:
        for r in fields.expand_refdes(str(raw)):
            if r not in out:
                out.append(r)
    return out


def refuted(f: dict) -> bool:
    return f.get("verification", {}).get("status") == "WRONG"


def is_question(f: dict) -> bool:
    """UNVERIFIABLE: paper cannot settle it, so it is an open question, not a confirmed problem."""
    return f.get("verification", {}).get("status") == "UNVERIFIABLE"


UNKNOWN_REASONS = {"no_datasheet": "No datasheet", "no_model": "No model", "needs_bench": "Needs bench",
                   "other": "Other"}
_DOC = r"(?:datasheets?|data sheets?|digests?|documents?|pdfs?|sources?)"
_NO_DOC = re.compile(rf"\b(?:no|without|missing|absent|unavailable|lacks?)\b[^.;]{{0,40}}\b{_DOC}\b|"
                     rf"\b{_DOC}\b[^.;]{{0,40}}\b(?:unavailable|absent|missing|not (?:supplied|available|provided|"
                     r"given|found))\b", re.I)
_MODEL = r"(?:models?|curves?|plant)"
_NO_MODEL = re.compile(rf"\b(?:no|without|missing|absent|unavailable)\b[^.;]{{0,40}}\b{_MODEL}\b|"
                       rf"\b{_MODEL}\b[^.;]{{0,40}}\b(?:unavailable|absent|missing|not (?:published|available))\b",
                       re.I)
_BENCH = re.compile(r"\bbench\b|\bmeasur", re.I)


def unknown_reason(check: dict) -> str:
    """Why an unknown check could not run: no_datasheet, no_model, needs_bench or other."""
    nps = check.get("not_published", [])
    text = " ".join([check.get("reason", ""), check.get("summary", "")]
                    + [f"{n.get('item', '')} {n.get('searched', '')}" for n in nps])
    cons = {n.get("consequence") for n in nps}
    if _NO_DOC.search(text) or "vendor_question" in cons:
        return "no_datasheet"
    if "model" in cons or _NO_MODEL.search(text):
        return "no_model"
    if "bench_test" in cons or check.get("bench_test") or _BENCH.search(text):
        return "needs_bench"
    return "other"


def unknown_groups(checks: list[dict]) -> dict[str, list[dict]]:
    """Unknown checks grouped by unknown_reason, in UNKNOWN_REASONS order, empty groups left out."""
    groups: dict[str, list[dict]] = {k: [] for k in UNKNOWN_REASONS}
    for c in checks:
        if c.get("verdict") == "unknown":
            groups[unknown_reason(c)].append(c)
    return {k: v for k, v in groups.items() if v}


def findings_hash(findings: list[dict]) -> str:
    """Hash of ids, titles and severities: stable when only status fields change."""
    rows = sorted([f.get("id", ""), f.get("title", ""), f.get("severity", "")] for f in findings)
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()[:12]


def sort_findings(findings: list[dict]) -> list[dict]:
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(findings, key=lambda f: (rank.get(f.get("severity"), 9), natural_key(f.get("id", ""))))


@dataclass
class Facts:
    """The parts of a facts folder the report and the re-review read."""

    path: Path
    components: dict[str, dict] = field(default_factory=dict)
    pins: dict[str, dict] = field(default_factory=dict)
    nets: dict[str, list[str]] = field(default_factory=dict)
    blocks: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    place: placement.Placement | None = None
    sheets: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def pins_of(self, ref: str) -> list[dict]:
        return sorted((p for k, p in self.pins.items() if k.partition(".")[0] == ref),
                      key=lambda p: natural_key(p["number"]))

    def sheet(self, ref: str) -> str:
        if ref in self.sheets:
            return self.sheets[ref]
        raw = self.components.get(ref, {}).get("attrs", {}).get("sheet", "")
        return raw.strip("/") or ("/ (root sheet)" if raw else "")


def load_facts(path: str | Path, placement_files: list[str] = (), units: str = "", with_placement: bool = True) -> Facts:
    """Read board_model.json and blocks.json from a facts folder, plus placement and sheets when asked."""
    path = Path(path)
    model_path = path / "board_model.json" if path.is_dir() else path
    if not model_path.exists():
        raise SystemExit(f"no board_model.json in {path}; run python -m boardreview prep first")
    model = read_json(model_path)
    facts = Facts(path if path.is_dir() else path.parent)
    facts.components = {c["refdes"]: c for c in model.get("components", [])}
    facts.pins = {f"{p['refdes']}.{p['number']}": p for p in model.get("pins", [])}
    facts.nets = {n["name"]: n["pins"] for n in model.get("nets", [])}
    facts.sources = model.get("sources", [])
    blocks = facts.path / "blocks.json"
    if blocks.exists():
        facts.blocks = read_json(blocks)
    if with_placement:
        extra = list(placement_files) + _source_files(facts)
        facts.place, facts.sheets, facts.notes = placement.for_facts(facts.path, extra, units)
    return facts


def _source_files(facts: Facts) -> list[Path]:
    """Source netlists named in board_model.json, found as written or relative to the facts folder."""
    out = []
    for s in facts.sources:
        if s.get("kind") not in ("ipc356", "kicad_xml") or not s.get("path"):
            continue
        p = Path(s["path"])
        for cand in (p, facts.path / p, facts.path / p.name):
            if cand.is_file():
                out.append(cand)
                break
    return out


EDGE_KIND = {"switching_regulator": "buck", "buck_regulator": "buck", "buck": "buck", "ldo": "LDO",
             "linear_regulator": "LDO", "load_switch": "load switch", "switch": "load switch", "ferrite_filter": "bead",
             "ferrite_lc_filter": "bead", "ferrite": "bead", "bead": "bead", "lc_filter": "LC filter",
             "diode": "diode", "fuse": "fuse"}


def _first(v) -> str:
    if isinstance(v, list):
        return str(v[0]) if v else ""
    return str(v or "")


def _edge_from_roles(kind: str, roles: dict) -> tuple[str, str, str, list[str]] | None:
    if kind == "switching_regulator" and roles.get("controller"):
        ind = _first(roles.get("inductor")) or "?"
        return (_first(roles.get("input")) or "input not found", _first(roles.get("output")) or "?",
                f"{roles['controller'][0]} buck, {ind}", roles["controller"] + roles.get("inductor", []))
    if kind in ("ferrite_filter", "lc_filter") and roles.get("element"):
        return (_first(roles.get("upstream")) or "?", _first(roles.get("downstream")) or "?",
                f"{roles['element'][0]} {EDGE_KIND[kind]}", list(roles["element"]))
    if kind in ("ldo", "load_switch") and roles.get("device"):
        return (_first(roles.get("input")) or "input not found", _first(roles.get("output")) or "?",
                f"{roles['device'][0]} {EDGE_KIND[kind]}", list(roles["device"]))
    return None


def power_edges(items: list) -> list[tuple[str, str, str, list[str]]]:
    """(input, output, label, parts) per edge, from prep blocks (roles) or reviewed edges and blocks (input, output)."""
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if isinstance(it.get("roles"), dict):
            edge = _edge_from_roles(str(it.get("kind", "")), it["roles"])
            if edge:
                out.append(edge)
            continue
        e = it.get("operating_point") if isinstance(it.get("operating_point"), dict) else it
        src = _first(e.get("input") or e.get("from") or e.get("source"))
        dst = _first(e.get("output") or e.get("to") or e.get("load"))
        if not src or not dst:
            continue
        part = _first(e.get("part") or it.get("part") or it.get("name") or it.get("instance"))
        kind = str(e.get("kind") or it.get("kind") or it.get("checklist") or "")
        label = f"{part} {EDGE_KIND.get(kind, kind.replace('_', ' '))}".strip()
        out.append((src, dst, label, [str(p) for p in (it.get("parts") or e.get("parts") or [part])]))
    return out


SUPPORTING = (
    ("Verification", ("verify/*", "verification*", "*refutation*", "validation*")),
    ("Source availability", ("datasheets.md", "datasheets.json", "digests/source_index.json",
                             "digests/unavailable_sources.json", "*source_availability*", "sources.local.json")),
    ("Feedback", ("*feedback*", "digests/*feedback*")),
    ("Review files", ("intake.md", "power_tree.json", "blocks.json", "domains.json", "straps.json", "bench.json",
                      "known_good.json", "checks.json", "calculations/README.md")),
)
SUPPORTING_SUFFIXES = {".json", ".md", ".csv", ".txt", ".html"}


def supporting_files(review: Path, out: Path, extra: list[str] = ()) -> list[tuple[str, Path]]:
    """(group, file) for verification, source availability, feedback and review files in the review folder."""
    review, out = review.resolve(), out.resolve()
    found: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for group, patterns in SUPPORTING:
        for pat in patterns:
            for p in sorted(review.glob(pat)):
                p = p.resolve()
                if p in seen or not p.is_file() or p.suffix.lower() not in SUPPORTING_SUFFIXES or out in p.parents:
                    continue
                seen.add(p)
                found.append((group, p))
    for x in extra:
        p = Path(x).resolve()
        if p.is_file() and p not in seen:
            seen.add(p)
            found.append(("Other", p))
    return found


@dataclass
class BenchStep:
    id: str
    title: str
    phase: str = ""
    rule: str = ""
    findings: list[str] = field(default_factory=list)
    detail: list[tuple[str, str]] = field(default_factory=list)


def load_bench(path: str | Path | None, findings: list[dict]) -> tuple[list[BenchStep], bool]:
    """Bench steps from a bench file, or one step per finding bench_test when no file is given."""
    if not path:
        steps = [BenchStep(f"b{i}", f["bench_test"], "From the findings", "", [f["id"]])
                 for i, f in enumerate((f for f in sort_findings(findings) if f.get("bench_test") and not refuted(f)), 1)]
        return steps, False
    _, rows = split_file(read_json(path))
    steps = []
    for i, r in enumerate(rows, 1):
        detail = [(label, r[key]) for key, label in (("setup", "Setup"), ("procedure", "Procedure"),
                                                      ("expected", "Expected"), ("on_fail", "On fail")) if r.get(key)]
        steps.append(BenchStep(str(r.get("id") or f"b{i}"), r.get("title") or r.get("step", ""), r.get("phase", ""),
                               r.get("pass", ""), list(r.get("findings") or r.get("settles") or []), detail))
    return steps, True


def load_list(path: str | Path | None) -> tuple[dict, list[dict]]:
    if not path:
        return {}, []
    return split_file(read_json(path))


@dataclass
class Status:
    """status.json: one entry per finding or bench id, the same fields as the artifact's status documents."""

    items: dict[str, dict] = field(default_factory=dict)
    board: str = ""
    revision: str = ""
    findings_hash: str = ""


def read_status(path: str | Path | None) -> Status:
    if not path:
        return Status()
    data = read_json(path)
    items = data.get("items", data.get("status", {})) if isinstance(data, dict) else {}
    if isinstance(items, list):
        items = {d["id"]: {k: v for k, v in d.items() if k != "id"} for d in items if "id" in d}
    return Status(dict(items), data.get("board", ""), data.get("revision", ""), data.get("findings_hash", ""))


def merge_status(findings: list[dict], status: Status) -> list[dict]:
    """Copy of the findings with status.json entries folded into each finding's status object."""
    out = copy.deepcopy(findings)
    for f in out:
        item = status.items.get(f["id"])
        if not item:
            continue
        st = dict(f.get("status", {}))
        if "done" in item:
            st["fixed"] = bool(item["done"])
            if item.get("at"):
                st["fixed_at"] = item["at"]
            if item.get("by"):
                st["fixed_by"] = item["by"]
            elif not item["done"]:
                st.pop("fixed_by", None)
        if isinstance(item.get("verified"), bool):
            st["verified_in_data"] = item["verified"]
            if item.get("verifyNote"):
                st["verify_note"] = item["verifyNote"]
            if item.get("verifiedAt"):
                st["verified_at"] = item["verifiedAt"]
        f["status"] = st
    return out


def status_item(f: dict) -> dict:
    """A finding's status as a status document: {done, at, by, verified, verifyNote}."""
    st = f.get("status", {})
    out: dict = {}
    if "fixed" in st:
        out["done"] = bool(st["fixed"])
    if st.get("fixed_at"):
        out["at"] = st["fixed_at"]
    if st.get("fixed_by"):
        out["by"] = st["fixed_by"]
    if isinstance(st.get("verified_in_data"), bool):
        out["verified"] = st["verified_in_data"]
    if st.get("verify_note"):
        out["verifyNote"] = st["verify_note"]
    if st.get("verified_at"):
        out["verifiedAt"] = st["verified_at"]
    return out


def _overlap(a: dict, b: dict) -> float:
    pa = set(expand(a.get("parts"))) | {p.split(".")[0] for p in a.get("pins", [])}
    pb = set(expand(b.get("parts"))) | {p.split(".")[0] for p in b.get("pins", [])}
    na, nb = {n.upper() for n in a.get("nets", [])}, {n.upper() for n in b.get("nets", [])}
    union = len(pa | pb) + len(na | nb)
    return (len(pa & pb) + len(na & nb)) / union if union else 0.0


def match(old: list[dict], new: list[dict]) -> list[tuple[int, int]]:
    """(old, new) index pairs of one problem: same block, and same failure mode with shared parts or nets, or same id."""
    if not old or not new:
        return []
    w = np.zeros((len(old), len(new)))
    for i, a in enumerate(old):
        for j, b in enumerate(new):
            if a.get("block") != b.get("block"):
                continue
            same_id = a.get("id") == b.get("id")
            ov = _overlap(a, b)
            if (a.get("failure_mode") == b.get("failure_mode") and ov > 0) or same_id:
                w[i, j] = 1.0 + ov + (1.0 if same_id else 0.0)
    rows, cols = linear_sum_assignment(w, maximize=True)
    return sorted((int(i), int(j)) for i, j in zip(rows, cols) if w[i, j] > 0)


@dataclass
class Changes:
    since: str
    reopened: list[tuple[dict, dict]] = field(default_factory=list)
    still_open: list[tuple[dict, dict]] = field(default_factory=list)
    new: list[dict] = field(default_factory=list)
    fixed: list[tuple[dict, str]] = field(default_factory=list)
    not_found: list[tuple[dict, str]] = field(default_factory=list)

    def tag(self, fid: str) -> str:
        if any(n["id"] == fid for _, n in self.reopened):
            return "Reopened"
        if any(n["id"] == fid for n in self.new):
            return "New"
        return ""

    def previous_of(self, fid: str) -> dict | None:
        for o, n in self.reopened + self.still_open:
            if n["id"] == fid:
                return o
        return None

    def summary(self) -> str:
        bits = [(len(self.reopened), "reopened"), (len(self.new), "new"), (len(self.fixed), "fixed"),
                (len(self.not_found), "not found again"), (len(self.still_open), "still open")]
        return " · ".join(f"{n} {w}" for n, w in bits if n) or "no change"


def changes(old: list[dict], new: list[dict], facts: Facts, since: str = "") -> Changes:
    """What changed against a previous review; an old finding counts as fixed only when the fix shows in the facts."""
    from boardreview.report.verify import check_fix

    old = [f for f in old if not refuted(f)]
    new = [f for f in new if not refuted(f)]
    pairs = match(old, new)
    out = Changes(since)
    paired_old = {i for i, _ in pairs}
    paired_new = {j for _, j in pairs}
    for i, j in pairs:
        st = old[i].get("status", {})
        (out.reopened if st.get("fixed") or st.get("verified_in_data") else out.still_open).append((old[i], new[j]))
    out.new = [f for j, f in enumerate(new) if j not in paired_new]
    for i, f in enumerate(old):
        if i in paired_old:
            continue
        ok, note = check_fix(f, None, facts)
        if ok is None and f.get("status", {}).get("verified_in_data") is True:
            ok, note = True, f["status"].get("verify_note", "confirmed in an earlier re-review")
        (out.fixed if ok else out.not_found).append((f, note))
    return out


def check_ids(findings: list[dict], bench: list[BenchStep]) -> list[str]:
    """Problems with ids the page keys on: duplicates, clashes between findings and bench steps, bad characters."""
    errs = []
    ids = [f["id"] for f in findings] + [b.id for b in bench]
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            errs.append(f"id {i} is used twice")
        seen.add(i)
        if not ID_OK.match(i) or i in (".", ".."):
            errs.append(f"id {i} has characters a status document cannot use")
    return errs
