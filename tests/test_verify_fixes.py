import json
import re
from pathlib import Path

import pytest

from boardreview.__main__ import main
from boardreview.report import review as rv
from boardreview.report.verify import Intent, check_fix, check_intent, parse_fix, verify_fixes

BOARD = Path(__file__).parent / "fixtures" / "report"


def revise(text: str, r11: str = "10k", dnp_r61: bool = True) -> str:
    text = text.replace('<comp ref="R11"><value>10R0</value>', f'<comp ref="R11"><value>{r11}</value>')
    if dnp_r61:
        text = re.sub(r'(<comp ref="R61">.*?)(</comp>)', r'\1<property name="dnp"/>\2', text, flags=re.S)
    return text


def facts_for(tmp_path: Path, name: str, text: str) -> Path:
    src = tmp_path / f"{name}.kicad.xml"
    src.write_text(text, encoding="utf-8")
    out = tmp_path / name
    assert main(["prep", str(src), "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def old_new(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("verify")
    base = (BOARD / "board.kicad.xml").read_text(encoding="utf-8")
    old = facts_for(tmp, "v1", base)
    new = facts_for(tmp, "v2", revise(base))
    wrong = facts_for(tmp, "v3", revise(base, r11="4.7k", dnp_r61=False))
    load = lambda p: rv.load_facts(p, with_placement=False)
    return load(old), load(new), load(wrong), old, new


def finding(fid: str, fix: str, fixed: bool = True) -> dict:
    return {"id": fid, "title": "synthetic finding", "severity": "major", "block": "other", "failure_mode": "other",
            "claim": "synthetic claim text", "evidence": [{"kind": "bom", "ref": "row"}], "fix": fix,
            "verification": {"status": "CONFIRMED"}, "status": {"fixed": fixed}}


def test_parse_fix_reads_only_what_it_can_check():
    intents, unread = parse_fix("DNP R61. R11 to 10.0k; Connect U6.5 to GND.")
    assert intents == [Intent("dnp", "R61"), Intent("value", "R11", "10.0k"), Intent("net", "U6.5", "GND")]
    assert unread == []
    intents, _ = parse_fix("R14-R16 DNP.")
    assert [i.target for i in intents] == ["R14", "R15", "R16"]
    intents, unread = parse_fix("Use the 30 V standoff part and recheck the clamp.")
    assert intents == [] and unread
    _, unread = parse_fix("DNP R61. Check the BOM that goes to the assembler.")
    assert unread == []


def test_dnp_change_is_confirmed(old_new):
    old, new, wrong, *_ = old_new
    assert check_fix(finding("F-002", "DNP R61."), old, new) == (True, "R61 is DNP in the new data")
    ok, note = check_fix(finding("F-002", "DNP R61."), old, wrong)
    assert ok is False and note == "R61 is still fitted in the new data"


def test_value_change_is_confirmed(old_new):
    old, new, wrong, *_ = old_new
    assert check_fix(finding("F-001", "R11 to 10.0k."), old, new) == (True, "R11 is 10k in the new data (was 10R0)")
    ok, note = check_fix(finding("F-001", "R11 to 10.0k."), old, wrong)
    assert ok is False and note == "R11 is 4.7k; the fix says 10.0k"
    ok, note = check_fix(finding("F-001", "R11 to 10.0k."), old, old)
    assert ok is False and "still 10R0" in note


def test_unverifiable_fix_is_left_unset(old_new):
    old, new, *_ = old_new
    ok, note = check_fix(finding("F-004", "Add 2.2k pull-ups from I2C2_SDA and I2C2_SCL to +3V3."), old, new)
    assert ok is None and note.startswith("needs a reviewer")
    ok, note = check_fix(finding("F-002", "DNP R61. Add a 10k pull-down at U5.3."), old, new)
    assert ok is None and "R61 is DNP in the new data" in note and "cannot check" in note
    ok, note = check_fix(finding("F-009", "DNP R32."), old, new)
    assert ok is None and "not fitted in the old data either" in note


def test_net_change(old_new):
    old, new, *_ = old_new
    assert check_intent(Intent("net", "U6.5", "SENSOR_ALERT"), None, new) == (True, "U6.5 is on SENSOR_ALERT in the new data")
    ok, note = check_intent(Intent("net", "U6.5", "GND"), old, new)
    assert ok is False and "still on SENSOR_ALERT" in note


def test_verify_fixes_sets_the_status_fields(old_new):
    old, new, *_ = old_new
    fs = [finding("F-001", "R11 to 10.0k."), finding("F-002", "DNP R61."),
          finding("F-004", "Add 2.2k pull-ups to +3V3."), finding("F-005", "DNP D1.", fixed=False)]
    fs[2]["status"]["verified_in_data"] = True
    out = verify_fixes(fs, old, new, "2026-10-15T00:00:00+00:00")
    assert [(i, ok) for i, ok, _ in out] == [("F-001", True), ("F-002", True), ("F-004", None)]
    assert fs[0]["status"]["verified_in_data"] is True and fs[0]["status"]["verified_at"].startswith("2026-10-15")
    assert "verified_in_data" not in fs[2]["status"] and fs[2]["status"]["verify_note"].startswith("needs a reviewer")
    assert fs[3]["status"] == {"fixed": False}


def test_cli_round_trip_into_the_report(old_new, tmp_path):
    *_, old_dir, new_dir = old_new
    out = tmp_path / "findings_v2.json"
    status_out = tmp_path / "status_v2.json"
    assert main(["verify-fixes", "--findings", str(BOARD / "findings.json"), "--old-facts", str(old_dir),
                 "--new-facts", str(new_dir), "--status", str(BOARD / "status.json"), "--out", str(out),
                 "--status-out", str(status_out)]) == 0
    by = {f["id"]: f for f in json.loads(out.read_text(encoding="utf-8"))["findings"]}
    assert by["F-001"]["status"]["verified_in_data"] is True
    assert "verified_in_data" not in by["F-004"]["status"]
    assert "verified_in_data" not in by["F-002"].get("status", {})
    items = json.loads(status_out.read_text(encoding="utf-8"))["items"]
    assert items["F-001"]["verified"] is True and items["F-001"]["verifyNote"].startswith("R11 is 10k")
    assert items["b1"]["done"] is True and items["F-004"]["done"] is True
    rep = tmp_path / "rep"
    assert main(["report", "--findings", str(BOARD / "findings.json"), "--facts", str(new_dir),
                 "--status", str(status_out), "--out", str(rep)]) == 0
    text = (rep / "report.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r'id="br-data">(.*?)</script>', text, re.S).group(1).replace("<\\/", "</"))
    assert data["status"]["F-001"]["verified"] is True
    assert "Not ready to build. One blocker." in text
