import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from boardreview.__main__ import main
from boardreview.model import placement

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "model"
LOCAL = Path(__file__).parent / "local" / "oracle"
LOCAL_BOARDS = sorted(d for d in LOCAL.glob("*") if d.is_dir() and any(d.glob("*.ipc"))) if LOCAL.exists() else []


def test_prep_writes_the_fact_files_and_the_index(tmp_path, capsys):
    out = tmp_path / "facts"
    netlist = FIX / "ti_buck_board.kicad.xml"
    assert main(["prep", str(netlist), "--out", str(out)]) == 0
    for name in ("board_model.json", "nets_by_net.md", "nets_by_component.md", "power_tree.md", "pinmaps/U1.md",
                 "lint.md", "lint.json", "blocks.md", "blocks.json", "facts.md"):
        assert (out / name).exists(), name
    facts = (out / "facts.md").read_text(encoding="utf-8")
    assert facts == capsys.readouterr().out
    assert hashlib.sha256(netlist.read_bytes()).hexdigest() in facts
    assert "| board_model.json |" in facts and "35 components" in facts
    lint = json.loads((out / "lint.json").read_text(encoding="utf-8"))
    errors = sum(1 for f in lint["findings"] if f["severity"] == "error")
    assert f"{errors} errors" in facts
    assert "- lint bom_netlist_mismatch: no BOM loaded" in facts
    assert "- compare (NET-1): no --compare netlist given" in facts
    assert "- BOM (NET-7): no --bom given" in facts
    assert not (out / "compare.md").exists()


def test_prep_with_bom_and_three_way_compare(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_text("Designator,MPN\nU1,LT8609\n", encoding="utf-8")
    out = tmp_path / "facts"
    ipc = str(FIX / "adi_buck_nonames.ipc")
    assert main(["prep", str(FIX / "sch_missing_sheet.net"), "--bom", str(bom), "--compare", ipc, ipc,
                 "--out", str(out)]) == 0
    cmp = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert cmp["labels"] == ["schematic", "pcb", "fab"]
    facts = (out / "facts.md").read_text(encoding="utf-8")
    assert "schematic vs pcb: 5 parts only in pcb" in facts
    assert f"{len(cmp['disagreements'])} pins where the three disagree" in facts
    assert "| bom_check.json |" in facts
    assert "- lint unconnected_ic_pin: the netlist format omits pins with no net" in facts
    assert "compare (NET-1)" not in facts and "BOM (NET-7)" not in facts


def test_prep_reads_a_previous_snapshot_before_replacing_it(tmp_path):
    out = tmp_path / "facts"
    assert main(["prep", str(FIX / "adi_buck_nonames.ipc"), "--out", str(out)]) == 0
    assert main(["prep", str(FIX / "sch_missing_sheet.net"), "--compare", str(out / "board_model.json"),
                 "--labels", "current,previous", "--out", str(out)]) == 0
    pair = json.loads((out / "compare.json").read_text(encoding="utf-8"))["pairs"][0]
    assert pair["only_b"] == ["C2", "L1", "R1", "R2", "U1"]
    facts = (out / "facts.md").read_text(encoding="utf-8")
    assert "- 3-way compare (NET-1): two netlists given" in facts
    assert "| compare (previous) | board_model.json | board_model |" in facts


def test_prep_records_a_compare_input_it_cannot_load(tmp_path):
    junk = tmp_path / "junk.txt"
    junk.write_text("not a netlist\n", encoding="utf-8")
    out = tmp_path / "facts"
    assert main(["prep", str(FIX / "ti_buck_board.kicad.xml"), "--compare", str(junk), "--out", str(out)]) == 1
    facts = (out / "facts.md").read_text(encoding="utf-8")
    assert "- compare (NET-1): could not load a netlist: cannot tell the netlist format" in facts
    assert (out / "board_model.json").exists()


def test_prep_counts_parts_the_schematic_excludes_from_the_bom(tmp_path):
    from test_model_import import KICAD10_XML
    sch = tmp_path / "sch.xml"
    sch.write_text(KICAD10_XML, encoding="utf-8")
    bom = tmp_path / "bom.csv"
    bom.write_text("Refs,Value,Qty,DNP\nU1,BUCK1,1,\nR1,10k,1,\n", encoding="utf-8")
    assert main(["prep", str(sch), "--bom", str(bom), "--out", str(tmp_path / "f")]) == 0
    facts = (tmp_path / "f" / "facts.md").read_text(encoding="utf-8")
    assert "0 only in the BOM, 0 only in the netlist, 1 excluded from the BOM by the schematic" in facts


def test_prep_compares_against_a_kicad_board_and_writes_placement(tmp_path):
    from test_model_kicad_pcb import KICAD9_PCB
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text(KICAD9_PCB, encoding="utf-8")
    out = tmp_path / "f"
    assert main(["prep", str(FIX / "ti_buck_board.kicad.xml"), "--compare", str(pcb), "--out", str(out)]) == 0
    facts = (out / "facts.md").read_text(encoding="utf-8")
    assert "| compare (pcb) | board.kicad_pcb | kicad_pcb |" in facts
    assert "| placement.md, placement.json | part side, position and rotation from board.kicad_pcb | 3 parts |" in facts
    assert "| R7 | bottom | 10 | -20 | 180 |" in (out / "placement.md").read_text(encoding="utf-8")
    assert placement.for_facts(out)[0].kind == "kicad_pcb"


def test_prep_without_a_board_file_says_where_placement_comes_from(tmp_path):
    out = tmp_path / "f"
    assert main(["prep", str(FIX / "ti_buck_board.kicad.xml"), "--out", str(out)]) == 0
    assert "- placement: no .kicad_pcb or IPC-D-356 given" in (out / "facts.md").read_text(encoding="utf-8")
    assert not (out / "placement.json").exists()


def test_prep_takes_placement_from_ipc356_without_a_board_file(tmp_path):
    out = tmp_path / "f"
    assert main(["prep", str(FIX / "ti_buck_board.kicad.xml"), "--compare", str(FIX / "kicad_d356_aliases.ipc"),
                 "--out", str(out)]) == 0
    assert placement.for_facts(out)[0].kind == "ipc356"
    assert "pad centres" in (out / "placement.md").read_text(encoding="utf-8")


def test_prep_names_the_bom_when_the_bom_fails(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_text("Item,Value\n1,10k\n", encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        main(["prep", str(FIX / "ti_buck_board.kicad.xml"), "--bom", str(bom), "--out", str(tmp_path / "f")])
    text = str(stop.value.code)
    assert "bom.csv" in text and "BOM" in text and "ti_buck_board" not in text


def test_prep_names_the_netlist_when_the_netlist_fails(tmp_path):
    with pytest.raises(SystemExit) as stop:
        main(["prep", str(FIX / "nope.xml"), "--out", str(tmp_path / "f")])
    assert "nope.xml" in str(stop.value.code)


@pytest.mark.parametrize("argv", [
    ["--compare", "a", "b", "c"],
    ["--compare", "a", "--labels", "x,y,z"],
])
def test_prep_rejects_bad_arguments(tmp_path, argv):
    with pytest.raises(SystemExit) as stop:
        main(["prep", str(FIX / "ti_buck_board.kicad.xml"), *argv, "--out", str(tmp_path)])
    assert stop.value.code == 2


def test_python_dash_m_boardreview_runs(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "tools"))
    run = subprocess.run([sys.executable, "-m", "boardreview", "prep", str(FIX / "mps_buck.eda_agent.json"),
                          "--out", str(tmp_path)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    assert run.stdout.startswith("# Facts")


@pytest.mark.skipif(not LOCAL_BOARDS, reason="no local boards in tests/local/oracle")
@pytest.mark.parametrize("board", LOCAL_BOARDS, ids=lambda d: d.name)
def test_prep_on_local_boards(tmp_path, board):
    netlist = next(board.glob("*.ipc"))
    bom = next(iter(sorted(board.glob("*.xlsx")) + sorted(board.glob("*.csv"))), None)
    argv = ["prep", str(netlist), "--out", str(tmp_path)] + (["--bom", str(bom)] if bom else [])
    assert main(argv) == 0
    stats = json.loads((tmp_path / "board_model.json").read_text(encoding="utf-8"))["stats"]
    assert f"{stats['components']} components" in (tmp_path / "facts.md").read_text(encoding="utf-8")
