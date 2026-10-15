"""Connectivity compare across two or three netlists (schematic, PCB, fab IPC-D-356)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from boardreview.model import naming
from boardreview.model.board import BoardModel, natural_key

ABSENT = "<absent>"
MECHANICAL = {"mechanical", "testpoint"}


@dataclass
class Side:
    label: str
    pins: dict[str, str | None]
    comps: set[str]
    kinds: dict[str, str]
    complete: bool = True

    @classmethod
    def of(cls, label: str, model: BoardModel) -> "Side":
        pins = {p.key: p.net for p in model.pins.values()}
        comps = {p.refdes for p in model.pins.values()}
        return cls(label, pins, comps, {r: c.kind for r, c in model.components.items()}, model.pin_list_complete)

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
    renamed: list[tuple[str, str]] = field(default_factory=list)
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
    """Cluster refdes that share signal nets (rails and grounds excluded) on their own side."""
    wanted = set(refs)
    parent = {r: r for r in refs}

    def find(r: str) -> str:
        while parent[r] != r:
            parent[r] = parent[parent[r]]
            r = parent[r]
        return r

    for net, keys in side.nets().items():
        if naming.net_kind(net) != "signal":
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
    d = PairDiff(a.label, b.label)
    common_parts = a.comps & b.comps
    for refs, side, real, mech in ((a.comps - b.comps, a, d.only_a, d.mech_only_a),
                                   (b.comps - a.comps, b, d.only_b, d.mech_only_b)):
        for r in sorted(refs, key=natural_key):
            (mech if side.kinds.get(r) in MECHANICAL else real).append(r)
    d.groups_only_a = _groups(a, d.only_a)
    d.groups_only_b = _groups(b, d.only_b)
    d.pins_only_a = sorted((k for k in a.pins if k not in b.pins and _part(k) in common_parts
                            and (b.complete or a.pins[k] is not None)), key=natural_key)
    d.pins_only_b = sorted((k for k in b.pins if k not in a.pins and _part(k) in common_parts
                            and (a.complete or b.pins[k] is not None)), key=natural_key)
    common = {k for k in a.pins if k in b.pins}
    overlap, d.net_map = _match(a, b, common)
    d.renamed = sorted(((na, nb) for na, nb in d.net_map.items() if na != nb), key=lambda t: natural_key(t[0]))
    a_nets, b_nets = a.nets(), b.nets()
    mapped_b = set(d.net_map.values())
    d.removed = sorted((n for n in a_nets if n not in d.net_map and n not in b_nets), key=natural_key)
    d.added = sorted((n for n in b_nets if n not in mapped_b and n not in a_nets), key=natural_key)
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
            "stats": {s.label: {"components": len(s.comps), "pins": len(s.pins), "nets": len(s.nets())}
                      for s in self.sides},
            "pairs": [
                {"a": p.a, "b": p.b, "only_a": p.only_a, "only_b": p.only_b, "groups_only_a": p.groups_only_a,
                 "groups_only_b": p.groups_only_b, "mech_only_a": p.mech_only_a, "mech_only_b": p.mech_only_b, "pins_only_a": p.pins_only_a, "pins_only_b": p.pins_only_b,
                 "renamed": p.renamed, "removed": p.removed, "added": p.added, "merged": p.merged,
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
    maps = [{}] + [_translate(sides[0], s) for s in sides[1:]]
    keys = sorted(set().union(*(s.pins for s in sides)), key=natural_key)
    disagreements = []
    for key in keys:
        vals = []
        for s, mp in zip(sides, maps):
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
            out.append(f"Mechanical or test parts only in {here}, not {there}: {_list(mech, limit)}.")
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
    if p.pins_only_a or p.pins_only_b:
        out.append(f"Pin lists differ on shared parts: {len(p.pins_only_a)} pins only in {p.a}"
                   f" ({_list(p.pins_only_a, 20)}), {len(p.pins_only_b)} only in {p.b} ({_list(p.pins_only_b, 20)}).")
    return out


def _markdown(r: CompareReport, limit: int) -> str:
    lines = [f"# Connectivity compare: {' vs '.join(r.labels)}", "",
             "Pins are compared as REF.PIN -> net. Net names are matched by shared pins, so a rename is reported",
             "as a rename and not as a removed and an added net. Pins with no net count as '(no net)'.", "",
             "| | " + " | ".join(r.labels) + " |", "|---|" + "---|" * len(r.labels)]
    for label, getter in (("parts with pins", lambda s: len(s.comps)), ("pins", lambda s: len(s.pins)),
                          ("nets", lambda s: len(s.nets())),
                          ("pins with no net", lambda s: sum(1 for v in s.pins.values() if v is None))):
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
