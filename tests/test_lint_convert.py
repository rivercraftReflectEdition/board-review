import importlib.util
import json
from pathlib import Path

from boardreview import lint
from boardreview.lint import Finding, convert, to_finding, to_findings
from boardreview.model import bom, loaders
from boardreview.model.board import BoardModel

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "model"
spec = importlib.util.spec_from_file_location("evals_score", ROOT / "evals" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)
SCHEMA = json.loads((ROOT / "skill" / "schemas" / "finding.schema.json").read_text(encoding="utf-8"))


def _with_bom(name: str, tmp_path: Path) -> BoardModel:
    model = loaders.load(FIX / name)
    path = tmp_path / "bom.csv"
    path.write_text("Designator,MPN\nU1,PART-1\nR999,RC0402\n", encoding="utf-8")
    bom.apply_bom(model, bom.read_bom(path), str(path))
    return model


def _protection_and_ground_board() -> BoardModel:
    m = BoardModel(pin_list_complete=True)
    for ref, pin, net, name in (("U5", "1", "SENSE_RTN", "GND"), ("U5", "2", "VIN", "VIN"), ("U5", "3", "GND", "VDD"),
                                ("D1", "1", "SIG_A", "IO1"), ("D1", "2", "SIG_B", "IO2"), ("D1", "3", None, "GND"),
                                ("C1", "1", "VIN", ""), ("C1", "2", "GND", "")):
        m.add_pin(ref, pin, net, name)
    for c in m.components.values():
        c.classify()
    m.components["U5"].kind = "ic"
    m.components["D1"].kind = "tvs"
    return m.finalize()


def _all_fixture_findings(tmp_path: Path) -> list[Finding]:
    models = [loaders.load(FIX / n) for n in ("ti_buck_board.kicad.xml", "adi_buck_nonames.ipc",
                                              "sch_missing_sheet.net", "mps_buck.eda_agent.json")]
    models += [_with_bom("adi_buck_nonames.ipc", tmp_path), _protection_and_ground_board()]
    return [f for m in models for f in lint.run_all(m).findings]


def test_every_lint_check_has_a_mapping_to_a_real_checklist_item():
    assert set(convert.CHECKS) == set(lint.CHECKS)
    blocks, modes = score.vocab(SCHEMA)
    for block, item, mode, fix in list(convert.CHECKS.values()) + [convert.DEFAULT]:
        assert block in blocks and mode in modes and len(fix) >= 3
        text = (ROOT / "skill" / "checklists" / f"{block}.md").read_text(encoding="utf-8")
        assert f"## {item} " in text, (block, item)


def test_synthetic_fixture_findings_validate_against_the_schema(tmp_path):
    found = _all_fixture_findings(tmp_path)
    assert {f.check for f in found} == set(lint.CHECKS)
    converted = to_findings(found)
    assert len(converted) == len(found)
    for f in converted:
        assert score.validate(f, SCHEMA) == [], f
        assert f["verification"] == {"status": "PENDING"}
        assert f["evidence"][0]["kind"] == "lint"
    assert len({f["id"] for f in converted}) == len(converted)


def test_protection_ground_maps_to_prot_4():
    report = lint.run_all(loaders.load(FIX / "ti_buck_board.kicad.xml"))
    f = to_findings(report.by_check("protection_ground_floating"))[0]
    assert (f["id"], f["severity"], f["block"], f["check"], f["failure_mode"]) == (
        "lint.protection_ground_floating.1", "major", "protection_tvs", "protection_tvs#PROT-4", "protection_gap")
    assert f["pins"] == ["D2.3"]
    assert f["evidence"][0]["ref"] == "lint protection_ground_floating (error)"


def test_severity_steps_down_from_blocker():
    for lint_sev, sev in (("error", "major"), ("warning", "minor"), ("info", "note")):
        assert to_finding(Finding("single_pin_net", lint_sev, "net X reaches only U1.1"))["severity"] == sev


def test_pins_the_schema_cannot_hold_move_to_the_evidence_detail():
    f = to_finding(Finding("single_pin_net", "warning", "net X reaches only J1-A.1", pins=["J1-A.1", "U1.2"]))
    assert f["pins"] == ["U1.2"]
    assert "pins: J1-A.1, U1.2" in f["evidence"][0]["detail"]
    assert score.validate(f, SCHEMA) == []


def test_long_and_short_summaries_stay_inside_the_schema():
    long = to_finding(Finding("fitted_without_mpn", "warning", "200 fitted parts have no MPN: " + ", ".join(
        f"R{i}" for i in range(200))))
    assert len(long["title"]) <= 140 and long["title"].endswith("...")
    short = to_finding(Finding("new_check", "info", "odd"))
    assert short["block"] == "netlist_integrity" and short["failure_mode"] == "other"
    assert score.validate(long, SCHEMA) == [] and score.validate(short, SCHEMA) == []


def test_prep_writes_lint_findings(tmp_path, capsys):
    from boardreview.__main__ import main

    assert main(["prep", str(FIX / "ti_buck_board.kicad.xml"), "--out", str(tmp_path)]) == 0
    findings = json.loads((tmp_path / "lint_findings.json").read_text(encoding="utf-8"))
    lint_json = json.loads((tmp_path / "lint.json").read_text(encoding="utf-8"))
    assert len(findings) == len(lint_json["findings"]) > 0
    assert all(score.validate(f, SCHEMA) == [] for f in findings)
    row = f"| lint_findings.json | lint results as candidate findings, verification PENDING | {len(findings)} findings |"
    assert row in capsys.readouterr().out

