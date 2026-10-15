import json
from pathlib import Path

from boardreview.blocks.__main__ import main as blocks_main
from boardreview.lint.__main__ import main as lint_main
from boardreview.model.__main__ import main

FIX = Path(__file__).parent / "fixtures" / "model"


def test_build_writes_model_digests_lint_and_blocks(tmp_path, capsys):
    out = tmp_path / "facts"
    assert main(["build", str(FIX / "ti_buck_board.kicad.xml"), "--out", str(out)]) == 0
    for name in ("board_model.json", "nets_by_net.md", "nets_by_component.md", "power_tree.md", "lint.md",
                 "lint.json", "blocks.md", "blocks.json", "pinmaps/U1.md"):
        assert (out / name).exists(), name
    model = json.loads((out / "board_model.json").read_text(encoding="utf-8"))
    assert model["stats"]["components"] == 35
    assert "U1 switching regulator (high): VIN -> +3V3 via L1" in (out / "power_tree.md").read_text(encoding="utf-8")
    assert "35 components" in capsys.readouterr().out


def test_build_model_only_with_bom(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_text("Designator,MPN\nU1,LT8609\n", encoding="utf-8")
    out = tmp_path / "facts"
    assert main(["build", str(FIX / "adi_buck_nonames.ipc"), "--bom", str(bom), "--out", str(out), "--model-only"]) == 0
    assert not (out / "lint.md").exists()
    assert json.loads((out / "bom_check.json").read_text(encoding="utf-8"))["netlist_only"][0] == "C1"


def test_compare_command(tmp_path, capsys):
    out = tmp_path / "cmp"
    assert main(["compare", str(FIX / "sch_missing_sheet.net"), str(FIX / "adi_buck_nonames.ipc"),
                 "--labels", "schematic,fab", "--out", str(out)]) == 0
    data = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert data["pairs"][0]["only_b"] == ["C2", "L1", "R1", "R2", "U1"]
    assert "5 parts are in fab but not in schematic" in capsys.readouterr().out


def test_lint_and_blocks_commands(tmp_path, capsys):
    report = tmp_path / "lint.json"
    assert lint_main([str(FIX / "ti_buck_board.kicad.xml"), "--json", str(report)]) == 1
    assert json.loads(report.read_text(encoding="utf-8"))["findings"]
    assert blocks_main([str(FIX / "mps_buck.eda_agent.json")]) == 0
    assert "U1 via L1 -> +5V" in capsys.readouterr().out
