"""Report renderer: reviewed power tree and blocks override the prep heuristics; supporting files; fonts."""

import json
import re
import shutil
from pathlib import Path

import pytest

from boardreview.__main__ import main

BOARD = Path(__file__).parent / "fixtures" / "report"


@pytest.fixture(scope="module")
def facts(tmp_path_factory):
    out = tmp_path_factory.mktemp("facts")
    assert main(["prep", str(BOARD / "board.kicad.xml"), "--out", str(out)]) == 0
    return out


def _fold(text: str, fid: str) -> str:
    return re.search(rf'<details class="fold" id="{fid}">(.*?)</details>\n', text, re.S).group(1)


def _report(facts, out, *extra, findings=BOARD / "findings.json"):
    argv = ["report", "--findings", str(findings), "--facts", str(facts), "--out", str(out), *extra]
    assert main(argv) == 0
    return (out / "report.html").read_text(encoding="utf-8")


def test_reviewed_power_tree_replaces_the_heuristic_and_draws_ldo_and_switch_edges(facts, tmp_path):
    tree = {"edges": [
        {"part": "U1", "kind": "buck_regulator", "input": "VIN_24V", "output": "+5V"},
        {"part": "FB1", "kind": "ferrite_lc_filter", "input": "3V3A", "output": "+3V3"},
        {"part": "U7", "kind": "ldo", "input": "+5V", "output": "1V8"},
        {"part": "U8", "kind": "load_switch", "input": "+5V", "output": "USB_VBUS", "enable": "USB_EN"}]}
    (tmp_path / "power_tree.json").write_text(json.dumps(tree), encoding="utf-8")
    text = _report(facts, tmp_path / "out", "--power-tree", str(tmp_path / "power_tree.json"))
    fold = _fold(text, "br-power")
    assert "U7 LDO" in fold and "U8 load switch" in fold and "FB1 bead" in fold
    assert "U2 buck" not in fold
    assert "reviewed power_tree.json" in fold
    roots = re.findall(r'<ul class="tree"><li><span class="node"><span class="rail">([^<]+)<', fold)
    assert roots == ["3V3A"]


def test_prep_tree_says_it_is_heuristic_and_draws_ldo_blocks(facts, tmp_path):
    local = tmp_path / "facts"
    shutil.copytree(facts, local)
    blocks = json.loads((local / "blocks.json").read_text(encoding="utf-8"))
    blocks.append({"kind": "ldo", "name": "U7 +5V -> 1V8", "confidence": "high", "evidence": [],
                   "roles": {"device": ["U7"], "input": ["+5V"], "output": ["1V8"]}, "components": ["U7"],
                   "nets": ["+5V", "1V8"], "notes": [], "subgraph": {}})
    blocks.append({"kind": "load_switch", "name": "U8 +5V -> VBUS", "confidence": "medium", "evidence": [],
                   "roles": {"device": ["U8"], "input": ["+5V"], "output": ["VBUS"]}, "components": ["U8"],
                   "nets": ["+5V", "VBUS"], "notes": [], "subgraph": {}})
    (local / "blocks.json").write_text(json.dumps(blocks), encoding="utf-8")
    fold = _fold(_report(local, tmp_path / "out"), "br-power")
    assert "U1 buck" in fold and "U7 LDO" in fold and "U8 load switch" in fold
    assert "heuristic" in fold


def test_reviewed_blocks_replace_prep_blocks(facts, tmp_path):
    reviewed = {"blocks": [{"name": "U7", "checklist": "ldo", "parts": ["U7", "C40"],
                            "operating_point": {"part": "U7", "kind": "ldo", "input": "+5V", "output": "1V8"}}]}
    (tmp_path / "blocks.json").write_text(json.dumps(reviewed), encoding="utf-8")
    flist = json.loads((BOARD / "findings.json").read_text(encoding="utf-8"))
    (tmp_path / "f.json").write_text(json.dumps(flist), encoding="utf-8")
    text = _report(facts, tmp_path / "out", "--blocks", str(tmp_path / "blocks.json"), findings=tmp_path / "f.json")
    fold = _fold(text, "br-power")
    assert "U7 LDO" in fold and "U1 buck" not in fold
    assert "Ldo" in _fold(text, "br-coverage") or "LDO" in _fold(text, "br-coverage")


def test_supporting_files_fold_links_what_is_present(facts, tmp_path):
    review = tmp_path / "review"
    (review / "verify").mkdir(parents=True)
    shutil.copy(BOARD / "findings.json", review / "findings.json")
    (review / "verify" / "decisions.json").write_text("{}", encoding="utf-8")
    (review / "datasheets.md").write_text("# Datasheets\n", encoding="utf-8")
    (review / "skill_feedback.md").write_text("# Feedback\n", encoding="utf-8")
    text = _report(facts, review / "report", findings=review / "findings.json")
    fold = _fold(text, "br-supporting")
    assert 'href="../verify/decisions.json"' in fold
    assert 'href="../datasheets.md"' in fold and 'href="../skill_feedback.md"' in fold
    assert "Verification" in fold and "Source availability" in fold and "Feedback" in fold
    bare = tmp_path / "bare"
    bare.mkdir()
    shutil.copy(BOARD / "findings.json", bare / "findings.json")
    assert 'id="br-supporting"' not in _report(facts, bare / "report", findings=bare / "findings.json")


def test_system_fonts_by_default_and_google_fonts_only_on_request(facts, tmp_path):
    _report(facts, tmp_path / "a", "--detail", "full")
    for name in ("report.html", "report_artifact.html", "analysis.html"):
        text = (tmp_path / "a" / name).read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in text and "fonts.gstatic.com" not in text, name
        assert '"Segoe UI", system-ui' in text
    _report(facts, tmp_path / "b", "--detail", "full", "--google-fonts")
    for name in ("report.html", "analysis.html"):
        assert "fonts.googleapis.com" in (tmp_path / "b" / name).read_text(encoding="utf-8"), name
