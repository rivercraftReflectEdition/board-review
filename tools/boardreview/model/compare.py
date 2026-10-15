"""Connectivity compare across two or three netlists (schematic, PCB, fab IPC-D-356)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from boardreview.model import naming
from boardreview.model.board import BoardModel, natural_key

ABSENT = "<absent>"
MECHANICAL = {"mechanical", "testpoint"}
IPC_REF_LEN = 6
IPC_PIN_LEN = 4


@dataclass
class Side:
    label: str
    pins: dict[str, str | None]
    comps: set[str]
    kinds: dict[str, str]
    complete: bool = True
    bom_only: set[str] = field(default_factory=set)
    apart: set[str] = field(default_factory=set)

    @classmethod
    def of(cls, label: str, model: BoardModel) -> "Side":
        """Pins and declared parts; BOM-only parts kept apart, pinless and board-excluded parts marked."""
        pins = {p.key: p.net for p in model.pins.values()}
        bom_only = {r for r, c in model.components.items() if c.attrs.get("bom_only")}
        with_pins = {p.refdes for p in model.pins.values()}
        comps = (set(model.components) - bom_only) | with_pins
        apart = {r for r in comps if (model.pin_list_complete and r not in with_pins)
                 or model.components[r].attrs.get("exclude_from_board")}
        return cls(label, pins, comps, {r: c.kind for r, c in model.components.items()}, model.pin_list_complete,
                   bom_only, apart)

    def net_or_absent(self, key: str) -> str | None:
        """Net of a pin; a missing pin on a present part counts as no net when the source omits open pins."""
        if key in self.pins:
            return self.pins[key]
        return None if not self.complete and _part(key) in self.comps else ABSENT

    def nets(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for key, net in self.pins.items():
            if net is not None:
                out.setdefault(net, []).append(key)
        return out


@dataclass
class PairDiff:
    a: str
    b: str
    only_a: list[str] = field(default_factory=list)
    only_b: list[str] = field(default_factory=list)
    mech_only_a: list[str] = field(default_factory=list)
    mech_only_b: list[str] = field(default_factory=list)
    groups_only_a: list[list[str]] = field(default_factory=list)
    groups_only_b: list[list[str]] = field(default_factory=list)
    pins_only_a: list[str] = field(default_factory=list)
    pins_only_b: list[str] = field(default_factory=list)
    open_only_a: list[str] = field(default_factory=list)
    open_only_b: list[str] = field(default_factory=list)
    cut_refs: list[tuple[str, list[str]]] = field(default_factory=list)
    cut_pins: list[tuple[str, str]] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    truncated: list[tuple[str, str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    merged: list[tuple[list[str], str]] = field(default_factory=list)
    split: list[tuple[str, list[str]]] = field(default_factory=list)
    moved: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    net_map: dict[str, str] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not (self.only_a or self.only_b or self.pins_only_a or self.pins_only_b or self.renamed
                    or self.removed or self.added or self.moved)


def _part(key: str) -> str:
    return key.partition(".")[0]


def _cut_refs(short: Side, long: Side) -> dict[str, list[str]]:
    """Designators of short that are long's designators cut to the 6-character IPC-D-356 field."""
    only_long = long.comps - short.comps
    out = {}
    for s in sorted(short.comps - long.comps, key=natural_key):
        full = sorted((r for r in only_long if len(r) > IPC_REF_LEN and r.startswith(s)), key=natural_key)
        if len(s) == IPC_REF_LEN and full:
            out[s] = full
    return out


def _refit(side: Side, drop: set[str], rename: dict[str, str]) -> Side:
    def ref(r: str) -> str:
        return rename.get(r, r)

    pins = {f"{ref(_part(k))}.{k.partition('.')[2]}": n for k, n in side.pins.items() if _part(k) not in drop}
    return Side(side.label, pins, {ref(r) for r in side.comps - drop},
                {ref(r): k for r, k in side.kinds.items() if r not in drop}, side.complete, side.bom_only - drop,
                {ref(r) for r in side.apart - drop})


def fit_refs(a: Side, b: Side) -> tuple[Side, Side, list[tuple[str, list[str]]]]:
    """Match designators one side cut to 6 characters; leave out parts whose cut designators collide."""
    cuts: list[tuple[str, list[str]]] = []
    for short_is_b in (True, False):
        short, long = (b, a) if short_is_b else (a, b)
        found = _cut_refs(short, long)
        if not found:
            continue
        rename = {s: full[0] for s, full in found.items() if len(full) == 1}
        collide = {s: full for s, full in found.items() if len(full) > 1}
        short = _refit(short, set(collide), rename)
        long = _refit(long, {r for full in collide.values() for r in full}, {})
        a, b = (long, short) if short_is_b else (short, long)
        cuts += list(found.items())
    return a, b, cuts


def _cut_pins(short: Side, long: Side) -> dict[str, str]:
    """Pins of short whose numbers are one pin number of long cut to the 4-character IPC-D-356 field."""
    common = short.comps & long.comps
    only_long: dict[str, list[str]] = {}
    for k in long.pins:
        if k not in short.pins and _part(k) in common and len(k.partition(".")[2]) > IPC_PIN_LEN:
            only_long.setdefault(_part(k), []).append(k)
    out = {}
    for k in short.pins:
        ref, _, num = k.partition(".")
        if k in long.pins or len(num) != IPC_PIN_LEN:
            continue
        full = [x for x in only_long.get(ref, []) if x.partition(".")[2].startswith(num)]
        if len(full) == 1:
            out[k] = full[0]
    return out


def fit_pins(a: Side, b: Side) -> tuple[Side, Side, list[tuple[str, str]]]:
    """Match pin numbers one side cut to 4 characters, where the full number is the only candidate."""
    cuts: list[tuple[str, str]] = []
    for short_is_b in (True, False):
        short, long = (b, a) if short_is_b else (a, b)
        rename = _cut_pins(short, long)
        if not rename:
            continue
        short = Side(short.label, {rename.get(k, k): n for k, n in short.pins.items()}, short.comps, short.kinds,
                     short.complete, short.bom_only, short.apart)
        a, b = (long, short) if short_is_b else (short, long)
        cuts += sorted(((full, k) for k, full in rename.items()), key=lambda t: natural_key(t[0]))
    return a, b, cuts


def _explained(side: Side, other: Side, keys: list[str]) -> bool:
    """True when every pin of a net is on a part set apart on its side and absent from the other."""
    return all(_part(k) in side.apart and _part(k) not in other.comps for k in keys)


def _match(a: Side, b: Side, common: set[str]) -> tuple[Counter, dict[str, str]]:
    """Overlap counts of (a net, b net) over shared pins and the a->b net map."""
    overlap: Counter = Counter()
    for key in common:
        na, nb = a.pins[key], b.pins[key]
        if na is not None and nb is not None:
            overlap[(na, nb)] += 1
    best_b: dict[str, tuple[int, str]] = {}
    best_a: dict[str, tuple[int, str]] = {}
    for (na, nb), n in overlap.items():
        if n > best_b.get(na, (0, ""))[0] or (n == best_b.get(na, (0, ""))[0] and nb == na):
            best_b[na] = (n, nb)
        if n > best_a.get(nb, (0, ""))[0] or (n == best_a.get(nb, (0, ""))[0] and na == nb):
            best_a[nb] = (n, na)
    net_map = {}
    for na, (_, nb) in best_b.items():
        if overlap.get((na, na)):
            net_map[na] = na
        elif best_a.get(nb, (0, ""))[1] == na:
            net_map[na] = nb
    return overlap, net_map


def _groups(side: Side, refs: list[str]) -> list[list[str]]:
    """Cluster refdes that share signal nets, or rails that only they touch, on their own side."""
    wanted = set(refs)
    parent = {r: r for r in refs}

    def find(r: str) -> str:
        while parent[r] != r:
            parent[r] = parent[parent[r]]
            r = parent[r]
        return r

    for net, keys in side.nets().items():
        inside = all(_part(k) in wanted for k in keys)
        if naming.net_kind(net) != "signal" and not inside:
            continue
        members = sorted({_part(k) for k in keys if _part(k) in wanted})
        for other in members[1:]:
            parent[find(other)] = find(members[0])
    clusters: dict[str, list[str]] = {}
    for r in refs:
        clusters.setdefault(find(r), []).append(r)
    return sorted((sorted(c, key=natural_key) for c in clusters.values()), key=lambda c: (-len(c), natural_key(c[0])))


def compare_pair(a: Side, b: Side) -> PairDiff:
    """Differences from a to b: parts, pins, renamed, removed, added, merged, split and moved."""
    a, b, cuts = fit_refs(a, b)
    a, b, cut_pins = fit_pins(a, b)
    d = PairDiff(a.label, b.label, cut_refs=cuts, cut_pins=cut_pins)
    common_parts = a.comps & b.comps
    for refs, side, real, mech in ((a.comps - b.comps, a, d.only_a, d.mech_only_a),
                                   (b.comps - a.comps, b, d.only_b, d.mech_only_b)):
        for r in sorted(refs, key=natural_key):
            (mech if side.kinds.get(r) in MECHANICAL or r in side.apart else real).append(r)
    d.groups_only_a = _groups(a, d.only_a)
    d.groups_only_b = _groups(b, d.only_b)
    for here, there, conn, open_ in ((a, b, d.pins_only_a, d.open_only_a), (b, a, d.pins_only_b, d.open_only_b)):
        for k in sorted((k for k in here.pins if k not in there.pins and _part(k) in common_parts), key=natural_key):
            if here.pins[k] is not None:
                conn.append(k)
            elif there.complete:
                open_.append(k)
    common = {k for k in a.pins if k in b.pins}
    overlap, d.net_map = _match(a, b, common)
    pairs = sorted(((na, nb) for na, nb in d.net_map.items() if na != nb), key=lambda t: natural_key(t[0]))
    d.truncated = [(na, nb) for na, nb in pairs if naming.is_ipc356_form(na, nb) or naming.is_ipc356_form(nb, na)]
    d.renamed = [t for t in pairs if t not in d.truncated]
    a_nets, b_nets = a.nets(), b.nets()
    mapped_b = set(d.net_map.values())
    d.removed = sorted((n for n, keys in a_nets.items() if n not in d.net_map and n not in b_nets
                        and not _explained(a, b, keys)), key=natural_key)
    d.added = sorted((n for n, keys in b_nets.items() if n not in mapped_b and n not in a_nets
                      and not _explained(b, a, keys)), key=natural_key)
    by_b: dict[str, list[str]] = {}
    by_a: dict[str, list[str]] = {}
    for (na, nb), n in overlap.items():
        if n >= 2:
            by_b.setdefault(nb, []).append(na)
            by_a.setdefault(na, []).append(nb)
    d.merged = sorted(((sorted(v, key=natural_key), nb) for nb, v in by_b.items() if len(v) > 1),
                      key=lambda t: natural_key(t[1]))
    d.split = sorted(((na, sorted(v, key=natural_key)) for na, v in by_a.items() if len(v) > 1),
                     key=lambda t: natural_key(t[0]))
    for key in sorted(common, key=natural_key):
        na, nb = a.pins[key], b.pins[key]
        expected = d.net_map.get(na, na) if na is not None else None
        if expected != nb:
            d.moved.append((key, na, nb))
    return d


@dataclass
class CompareReport:
    labels: list[str]
    sides: list[Side]
    pairs: list[PairDiff]
    disagreements: list[tuple[str, list[str], str]]

    def to_dict(self) -> dict:
        return {
            "labels": self.labels,
            "stats": {s.label: {"components": len(s.comps), "pins": len(s.pins), "nets": len(s.nets()),
                                "bom_only": sorted(s.bom_only, key=natural_key)} for s in self.sides},
            "pairs": [
                {"a": p.a, "b": p.b, "only_a": p.only_a, "only_b": p.only_b, "groups_only_a": p.groups_only_a,
                 "groups_only_b": p.groups_only_b, "mech_only_a": p.mech_only_a, "mech_only_b": p.mech_only_b,
                 "pins_only_a": p.pins_only_a, "pins_only_b": p.pins_only_b, "open_only_a": p.open_only_a,
                 "open_only_b": p.open_only_b, "cut_refs": p.cut_refs, "cut_pins": p.cut_pins,
                 "renamed": p.renamed, "truncated": p.truncated, "removed": p.removed, "added": p.added, "merged": p.merged,
                 "split": p.split, "moved": p.moved}
                for p in self.pairs
            ],
            "disagreements": [{"pin": k, "nets": v, "odd_one_out": o} for k, v, o in self.disagreements],
        }

    def to_markdown(self, limit: int = 60) -> str:
        return _markdown(self, limit)


def _translate(ref_side: Side, side: Side) -> dict[str, str]:
    """Map net names of a side into the reference side's names where a match exists."""
    common = {k for k in side.pins if k in ref_side.pins}
    _, net_map = _match(side, ref_side, common)
    return net_map


def compare(models: list[tuple[str, BoardModel]]) -> CompareReport:
    """Compare two or three labelled models; the first is the naming reference."""
    sides = [Side.of(label, m) for label, m in models]
    pairs = [compare_pair(sides[i], sides[i + 1]) for i in range(len(sides) - 1)]
    if len(sides) == 3:
        pairs.append(compare_pair(sides[0], sides[2]))
    rows, left_out = [sides[0]], set()
    for s in sides[1:]:
        ref, other, _ = fit_refs(sides[0], s)
        left_out |= sides[0].comps - ref.comps
        rows.append(fit_pins(ref, other)[1])
    maps = [{}] + [_translate(sides[0], s) for s in rows[1:]]
    keys = sorted((k for k in set().union(*(s.pins for s in rows)) if _part(k) not in left_out), key=natural_key)
    disagreements = []
    for key in keys:
        vals = []
        for s, mp in zip(rows, maps):
            net = s.net_or_absent(key)
            vals.append("(no net)" if net is None else net if net == ABSENT else mp.get(net, net))
        if len(set(vals)) > 1:
            counts = Counter(vals)
            odd = ""
            if len(sides) == 3 and len(counts) == 2:
                odd = sides[[counts[v] for v in vals].index(1)].label
            disagreements.append((key, vals, odd))
    return CompareReport([s.label for s in sides], sides, pairs, disagreements)


def _list(items: list[str], limit: int) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f", and {len(items) - limit} more" if len(items) > limit else "")


def _pair_findings(p: PairDiff, limit: int) -> list[str]:
    out = []
    for only, groups, here, there in ((p.only_a, p.groups_only_a, p.a, p.b), (p.only_b, p.groups_only_b, p.b, p.a)):
        if not only:
            continue
        big = [g for g in groups if len(g) >= 3]
        line = f"{len(only)} parts are in {here} but not in {there}: {_list(only, limit)}."
        if big:
            line += (f" {len(big)} connected group(s), largest {len(big[0])} parts ({_list(big[0], 12)})."
                     " A connected group missing from one side usually means a schematic sheet dropped out of"
                     " the compile, or its parts were excluded from the board or the netlist.")
        out.append(line)
    for mech, here, there in ((p.mech_only_a, p.a, p.b), (p.mech_only_b, p.b, p.a)):
        if mech:
            out.append(f"Mechanical or test parts, parts with no pins, and parts excluded from the board, only in"
                       f" {here}, not {there}: {_list(mech, limit)}.")
    if p.cut_refs:
        out.append(f"{len(p.cut_refs)} designators are cut to the 6-character IPC-D-356 designator field: "
                   + _list([f"{', '.join(full)} -> {s}" for s, full in p.cut_refs], limit)
                   + ". A cut name with one full designator is matched to it; parts whose cut names collide are"
                     " left out of this compare. Compare against the .kicad_pcb file to check them.")
    if p.cut_pins:
        out.append(f"{len(p.cut_pins)} pin numbers are cut to the 4-character IPC-D-356 pin field and matched to"
                   " the full number: " + _list([f"{x} -> {y}" for x, y in p.cut_pins], limit) + ".")
    if p.truncated:
        cut, full = (p.b, p.a) if all(naming.is_ipc356_form(x, y) for x, y in p.truncated) else (p.a, p.b)
        out.append(f"{len(p.truncated)} net names in {cut} are {full} names cut to the 14-character IPC-D-356 field"
                   " (KiCad keeps the last 14 characters, in upper case). This is a format limit, not a rename;"
                   " a difference in the cut-off part cannot be seen. Compare against the .kicad_pcb file for"
                   " full names.")
    if p.renamed:
        out.append(f"{len(p.renamed)} nets renamed from {p.a} to {p.b}: "
                   + _list([f"{x} -> {y}" for x, y in p.renamed], limit) + ".")
    if p.merged:
        out.append(f"{len(p.merged)} nets in {p.b} join nets that are separate in {p.a}: "
                   + _list([f"{' + '.join(x)} -> {y}" for x, y in p.merged], limit) + ".")
    if p.split:
        out.append(f"{len(p.split)} nets in {p.a} are split in {p.b}: "
                   + _list([f"{x} -> {' + '.join(y)}" for x, y in p.split], limit) + ".")
    if p.moved:
        out.append(f"{len(p.moved)} pins are on a different net in {p.b} than in {p.a}: "
                   + _list([f"{k} {x or '(no net)'} -> {y or '(no net)'}" for k, x, y in p.moved], limit) + ".")
    if p.removed:
        out.append(f"{len(p.removed)} nets of {p.a} have no counterpart in {p.b}: {_list(p.removed, limit)}.")
    if p.added:
        out.append(f"{len(p.added)} nets of {p.b} have no counterpart in {p.a}: {_list(p.added, limit)}.")
    if p.open_only_a or p.open_only_b:
        out.append(f"{len(p.open_only_a) + len(p.open_only_b)} pins with no net exist in only one source"
                   f" ({p.a}: {_list(p.open_only_a, 20) or 'none'}; {p.b}: {_list(p.open_only_b, 20) or 'none'})."
                   " Not a connectivity difference; confirm each is a mounting, shield or unused pad and not an"
                   " exposed pad that belongs on a net.")
    if p.pins_only_a or p.pins_only_b:
        out.append(f"Pin lists differ on shared parts: {len(p.pins_only_a)} pins only in {p.a}"
                   f" ({_list(p.pins_only_a, 20)}), {len(p.pins_only_b)} only in {p.b} ({_list(p.pins_only_b, 20)}).")
    return out


def _markdown(r: CompareReport, limit: int) -> str:
    lines = [f"# Connectivity compare: {' vs '.join(r.labels)}", "",
             "Pins are compared as REF.PIN -> net. Net names are matched by shared pins, so a rename is reported",
             "as a rename and not as a removed and an added net. Pins with no net count as '(no net)'.", "",
             "| | " + " | ".join(r.labels) + " |", "|---|" + "---|" * len(r.labels)]
    for label, getter in (("parts in the netlist", lambda s: len(s.comps)), ("pins", lambda s: len(s.pins)),
                          ("nets", lambda s: len(s.nets())),
                          ("pins with no net", lambda s: sum(1 for v in s.pins.values() if v is None)),
                          ("BOM-only parts", lambda s: len(s.bom_only))):
        lines.append(f"| {label} | " + " | ".join(str(getter(s)) for s in r.sides) + " |")
    lines.append("")
    for p in r.pairs:
        lines += [f"## {p.a} vs {p.b}", ""]
        findings = _pair_findings(p, limit)
        lines += [f"{i}. {f}" for i, f in enumerate(findings, 1)] if findings else ["No differences."]
        lines.append("")
    if len(r.sides) == 3 and r.disagreements:
        lines += [f"## Pins where the sources disagree ({len(r.disagreements)})", "",
                  "Net names are shown in the naming of " + r.labels[0] + ".", "",
                  "| Pin | " + " | ".join(r.labels) + " | Odd one out |", "|---|" + "---|" * (len(r.labels) + 1)]
        for key, vals, odd in r.disagreements[: limit * 4]:
            lines.append(f"| {key} | " + " | ".join(vals) + f" | {odd or '-'} |")
        if len(r.disagreements) > limit * 4:
            lines.append(f"\n{len(r.disagreements) - limit * 4} more rows in compare.json.")
        lines.append("")
    return "\n".join(lines)
