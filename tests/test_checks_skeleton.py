"""python -m boardreview checks: one unknown entry per checklist item per block instance, ready to fill in."""

import json
import re
from pathlib import Path

import pytest

from boardreview.__main__ import main
from boardreview.checks import KIND_CHECKLIST, NO_BLOCK, RUN_IT, checklist_items, skeleton
from boardreview.schema import check_file

ROOT = Path(__file__).resolve().parent.parent
BOARD = Path(__file__).parent / "fixtures" / "report"
CHECKLISTS = ROOT / "skill" / "checklists"


def _items(checklist: str) -> list[str]:
    text = (CHECKLISTS / f"{checklist}.md").read_text(encoding="utf-8")
    return re.findall(r"^## ([A-Z]+-\d+[a-z]?) ", text, re.M)


@pytest.fixture(scope="module")
def facts(tmp_path_factory):
    out = tmp_path_factory.mktemp("facts")
    assert main(["prep", str(BOARD / "board.kicad.xml"), "--out", str(out)]) == 0
    return out


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["checks"]


def test_skeleton_covers_every_item_of_every_block_and_validates(facts, tmp_path, capsys):
    out = tmp_path / "checks.json"
    assert main(["checks", "--facts", str(facts), "--out", str(out)]) == 0
    assert check_file(out, "checks") == []
    checks = _load(out)
    assert all(c["verdict"] == "unknown" and c["reason"] for c in checks)
    u1 = [c["item"] for c in checks if c["block"] == "buck_regulator" and c["instance"].startswith("U1 ")]
    assert u1 == _items("buck_regulator")
    assert [c["item"] for c in checks if c["block"] == "ferrite_lc_filter"] == _items("ferrite_lc_filter")
    assert any(c["id"] == "U1.BR-1" for c in checks)
    on_board = {c["block"] for c in checks if c["instance"] == "board"}
    assert {"netlist_integrity", "cascaded_rails", "ethernet_phy"} <= on_board
    assert {p.stem for p in CHECKLISTS.glob("*.md")} <= {c["block"] for c in checks}
    assert "checks.json" in capsys.readouterr().out


def test_reviewed_blocks_name_their_checklist(facts, tmp_path):
    reviewed = {"blocks": [{"name": "IC4", "checklist": "ldo", "parts": ["IC4"]},
                           {"name": "U6 5V buck", "checklist": "buck_regulator", "parts": ["U6", "L4"]}]}
    (tmp_path / "blocks.json").write_text(json.dumps(reviewed), encoding="utf-8")
    out = tmp_path / "checks.json"
    assert main(["checks", "--blocks", str(tmp_path / "blocks.json"), "--out", str(out)]) == 0
    checks = _load(out)
    assert [c["item"] for c in checks if c["instance"] == "IC4"] == _items("ldo")
    assert [c["id"] for c in checks if c["instance"] == "U6 5V buck"][0] == "U6.BR-1"
    assert check_file(out, "checks") == []


def test_rerun_keeps_what_was_filled_in(facts, tmp_path):
    out = tmp_path / "checks.json"
    assert main(["checks", "--facts", str(facts), "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    first = data["checks"][0]
    first.update(verdict="pass", summary="Checked by hand.")
    first.pop("reason")
    out.write_text(json.dumps(data), encoding="utf-8")
    assert main(["checks", "--facts", str(facts), "--out", str(out)]) == 0
    again = _load(out)
    assert len(again) == len(data["checks"])
    assert again[0]["verdict"] == "pass" and again[0]["summary"] == "Checked by hand."


@pytest.mark.parametrize("kind,checklist", [("clock_buffer", "clock_distribution"),
    ("pll", "clock_distribution"), ("jitter_cleaner", "clock_distribution"),
    ("balun", "rf_front_end"), ("rf_switch", "rf_front_end"), ("rf_amplifier", "rf_front_end"),
    ("attenuator_pad", "rf_front_end"), ("rf_connector", "rf_front_end"),
    ("adc", "data_converters"), ("dac", "data_converters")])
def test_new_block_kinds_get_their_checklist(kind, checklist):
    checks = skeleton([{"kind": kind, "name": "U9 synthetic block"}], checklist_items())
    assert KIND_CHECKLIST[kind] == checklist
    assert [c["item"] for c in checks if c["instance"] == "U9 synthetic block"] == _items(checklist)


@pytest.mark.parametrize("blocks,reason", [
    ([{"kind": "switching_regulator", "name": "U1"}, {"kind": "adc", "name": "U2"}], RUN_IT),
    ([{"kind": "oscillator", "name": "Y1"}, {"kind": "balun", "name": "T1"}], RUN_IT),
    ([{"kind": "clock_buffer", "name": "U3"}], RUN_IT),
    ([{"name": "reviewed source", "checklist": "buck_regulator"},
      {"name": "reviewed RF", "checklists": ["rf_front_end", "spur_plan"]}], RUN_IT),
    ([{"kind": "adc", "name": "U1"}], NO_BLOCK),
    ([{"kind": "switching_regulator", "name": "U1"}], NO_BLOCK),
    ([], NO_BLOCK),
])
def test_spur_plan_is_one_board_instance_with_applicability_reason(blocks, reason):
    checks = [c for c in skeleton(blocks, checklist_items()) if c["block"] == "spur_plan"]
    assert [c["item"] for c in checks] == _items("spur_plan")
    assert all(c["instance"] == "board" and c["reason"] == reason for c in checks)
    assert len({c["id"] for c in checks}) == len(checks)
