"""checks.json skeleton: one unknown entry per checklist item per block instance, from blocks.json and the checklists."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CHECKLISTS = Path(__file__).resolve().parents[2] / "skill" / "checklists"
KIND_CHECKLIST = {"switching_regulator": "buck_regulator", "ldo": "ldo", "load_switch": "enable_uvlo_sequencing",
                  "ferrite_filter": "ferrite_lc_filter", "lc_filter": "ferrite_lc_filter",
                  "crystal": "clocks_crystals", "oscillator": "clocks_crystals",
                  "clock_buffer": "clock_distribution", "pll": "clock_distribution",
                  "jitter_cleaner": "clock_distribution",
                  "balun": "rf_front_end", "rf_switch": "rf_front_end",
                  "rf_amplifier": "rf_front_end", "attenuator_pad": "rf_front_end",
                  "rf_connector": "rf_front_end",
                  "adc": "data_converters", "dac": "data_converters",
                  "reset": "resets_supervisors_watchdogs", "i2c_bus": "io_levels_and_domains",
                  "strap": "straps_and_boot_pins"}
BOARD_WIDE = ("netlist_integrity", "cascaded_rails", "pdn_decoupling", "thermal", "layout")
PRIMARY = ("controller", "device", "element", "crystal", "oscillator", "net", "sda")
ITEM = re.compile(r"^## ([A-Z]+-\d+[a-z]?) (.+?)\s*$", re.M)
RUN_IT = "Not run yet: skeleton entry from python -m boardreview checks. Run the item and set the verdict."
NO_BLOCK = ("Not run yet: no block in blocks.json uses this checklist. Run it over the board, or set not_applicable "
            "with the reason.")


def checklist_items(directory: Path = CHECKLISTS) -> dict[str, list[tuple[str, str]]]:
    """(item, title) per checklist, in page order."""
    return {p.stem: ITEM.findall(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.md"))}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_.") or "block"


def instances(blocks: list[dict]) -> list[tuple[str, str, str]]:
    """(checklist, instance, id base) per block: prep blocks by kind, reviewed blocks by their checklist field."""
    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        roles = b.get("roles") if isinstance(b.get("roles"), dict) else {}
        named = b.get("checklists") or b.get("checklist") or KIND_CHECKLIST.get(str(b.get("kind", "")), "")
        name = str(b.get("instance") or b.get("name") or "")
        primary = next((roles[k][0] for k in PRIMARY if roles.get(k)), "")
        if not primary:
            m = re.match(r"[A-Za-z0-9_.-]+", name)
            primary = m.group(0) if m else ""
        for checklist in [named] if isinstance(named, str) else named:
            if checklist and name:
                out.append((checklist, name, _slug(b.get("id") or primary or name)))
    return out


def skeleton(blocks: list[dict], items: dict[str, list[tuple[str, str]]]) -> list[dict]:
    """Unknown entries for every item of every block's checklist, then board-wide and unused checklists once."""
    identified = instances(blocks)
    checklists = {c for c, _, _ in identified}
    kinds = {b.get("kind") for b in blocks if isinstance(b, dict)}
    aggressor = bool(checklists & {"buck_regulator", "clocks_crystals", "clock_distribution"}
                     or kinds & {"switching_regulator", "clock", "crystal", "oscillator",
                                 "clock_buffer", "pll", "jitter_cleaner"})
    sensitive = bool(checklists & {"rf_front_end", "data_converters", "clock_distribution"}
                     or kinds & {"balun", "rf_switch", "rf_amplifier", "attenuator_pad",
                                 "rf_connector", "adc", "dac", "clock_buffer", "pll", "jitter_cleaner"})
    board_wide = BOARD_WIDE + (("spur_plan",) if aggressor and sensitive else ())
    found = [x for x in identified if x[0] in items and x[0] != "spur_plan"]
    used = {c for c, _, _ in found}
    found += [(c, "board", "board") for c in items if c in board_wide or c not in used]
    out: list[dict] = []
    bases: dict[tuple[str, str], str] = {}
    taken: set[str] = set()
    for checklist, inst, base in found:
        key = (inst, base)
        if key not in bases:
            n, b = 1, base
            while any(f"{b}.{item}" in taken for item, _ in items[checklist]):
                n += 1
                b = f"{base}-{n}"
            bases[key] = b
        for item, title in items[checklist]:
            cid = f"{bases[key]}.{item}"
            if cid in taken:
                continue
            taken.add(cid)
            out.append({"id": cid, "block": checklist, "instance": inst, "item": item, "title": title,
                        "verdict": "unknown", "reason": RUN_IT if inst != "board" or checklist in board_wide
                        else NO_BLOCK})
    return out


def _blocks(args: argparse.Namespace) -> list[dict]:
    path = Path(args.blocks) if args.blocks else Path(args.facts) / "blocks.json"
    if not path.exists():
        raise SystemExit(f"checks: no {path}; run python -m boardreview prep first or give --blocks")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("blocks", []) if isinstance(data, dict) else data


def run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    items = checklist_items(Path(args.checklists) if args.checklists else CHECKLISTS)
    header: dict = {"board": args.board} if args.board else {}
    kept: list[dict] = []
    if out.exists():
        old = json.loads(out.read_text(encoding="utf-8"))
        kept = old.get("checks", []) if isinstance(old, dict) else old
        header = {k: v for k, v in old.items() if k != "checks"} if isinstance(old, dict) else header
    have = {c.get("id") for c in kept}
    new = [c for c in skeleton(_blocks(args), items) if c["id"] not in have]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**header, "checks": kept + new}, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"{out}: {len(new)} new checks, {len(kept)} kept, {len(kept) + len(new)} in all. Each new one is unknown "
          "until it is run; validate with python -m boardreview validate --schema checks.")
    return 0


def add_parser(sub) -> None:
    """The checks subcommand of python -m boardreview."""
    c = sub.add_parser("checks", help="checks.json skeleton: one unknown entry per checklist item per block instance")
    c.add_argument("--facts", default="facts", help="facts folder from prep; its blocks.json is read")
    c.add_argument("--blocks", help="blocks.json to read instead, prep's or a reviewed one with a checklist per block")
    c.add_argument("--checklists", help="checklist folder; default: the skill's checklists")
    c.add_argument("--board", default="", help="board name for a new file")
    c.add_argument("--out", required=True, help="checks.json to write; entries already in it are kept")
