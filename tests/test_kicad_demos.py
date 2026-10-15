"""KiCad demo boards end to end. The demos are copied to a temp folder and never written in place."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from boardreview.__main__ import main
from boardreview.model import kicad_pcb, placement
from kicad_env import demos_dir, kicad_cli

CLI = kicad_cli()
DEMOS = demos_dir(CLI)
BOARDS = {"complex_hierarchy": "complex_hierarchy", "pic_programmer": "pic_programmer",
          "royalblue54L_feather": "RoyalBlue54L-Feather", "stickhub": "StickHub"}
CONNECTIVITY = ("only_a", "only_b", "pins_only_a", "pins_only_b", "renamed", "removed", "added", "moved", "merged",
                "split", "fitted_differs")
needs_demos = pytest.mark.skipif(DEMOS is None, reason="KiCad demos not installed")
slow_kicad = pytest.mark.skipif(CLI is None or DEMOS is None or not os.environ.get("BOARDREVIEW_SLOW"),
                                reason="needs kicad-cli, the KiCad demos and BOARDREVIEW_SLOW=1")


def _demo(name: str) -> Path:
    path = DEMOS / name
    if not (path / f"{BOARDS.get(name, name)}.kicad_pcb").exists():
        pytest.skip(f"demo {name} not installed")
    return path


def _copy(name: str, tmp_path: Path) -> Path:
    dst = tmp_path / name
    shutil.copytree(_demo(name), dst)
    return dst


def _export(dst: Path, stem: str) -> tuple[Path, Path]:
    out = dst / "out"
    out.mkdir()
    sch, pcb = dst / f"{stem}.kicad_sch", dst / f"{stem}.kicad_pcb"
    for args in (["sch", "export", "netlist", "--format", "kicadxml", "-o", str(out / "sch.xml"), str(sch)],
                 ["sch", "export", "bom", "--fields", "Reference,Value,Footprint,MPN,DNP", "-o", str(out / "bom.csv"),
                  str(sch)],
                 ["pcb", "export", "ipcd356", "-o", str(out / "pcb.d356"), str(pcb)]):
        subprocess.run([str(CLI), *args], check=True, capture_output=True, timeout=300)
    return out, pcb


def _pair(facts: Path, a: str, b: str) -> dict:
    cmp = json.loads((facts / "compare.json").read_text(encoding="utf-8"))
    return next(p for p in cmp["pairs"] if (p["a"], p["b"]) == (a, b))


@needs_demos
@pytest.mark.parametrize("name", sorted(BOARDS))
def test_demo_board_file_reads_with_placement(name):
    m = kicad_pcb.read_kicad_pcb(_demo(name) / f"{BOARDS[name]}.kicad_pcb")
    assert m.pins and placement.from_board(m, name) is not None
    assert not [w for w in m.warnings if "seen on" in w]


@slow_kicad
@pytest.mark.parametrize("name", sorted(BOARDS))
def test_unmodified_demo_compares_clean(name, tmp_path):
    out, pcb = _export(_copy(name, tmp_path), BOARDS[name])
    facts = tmp_path / "facts"
    assert main(["prep", str(out / "sch.xml"), "--bom", str(out / "bom.csv"), "--compare", str(pcb),
                 str(out / "pcb.d356"), "--out", str(facts)]) == 0
    for a, b in (("schematic", "pcb"), ("schematic", "fab"), ("pcb", "fab")):
        pair = _pair(facts, a, b)
        assert {k: pair[k] for k in CONNECTIVITY if pair[k]} == {}, (a, b)
    assert placement.for_facts(facts)[0].kind == "kicad_pcb"
    if name == "royalblue54L_feather":
        blocks = json.loads((facts / "blocks.json").read_text(encoding="utf-8"))
        assert any(b["kind"] == "switching_regulator" and b["confidence"] == "high" for b in blocks)


@slow_kicad
def test_part_deleted_from_the_schematic_is_caught(tmp_path):
    dst = _copy("stickhub", tmp_path)
    sch = dst / "StickHub.kicad_sch"
    text = sch.read_text(encoding="utf-8")
    block, ref = next((b, m.group(1)) for b in kicad_pcb.top_level_blocks(text, ("symbol",))
                      for m in [re.search(r'\(property "Reference" "(R\d+)"', b)] if m)
    sch.write_text(text.replace(block, "", 1), encoding="utf-8", newline="\n")
    out, pcb = _export(dst, "StickHub")
    facts = tmp_path / "facts"
    main(["prep", str(out / "sch.xml"), "--compare", str(pcb), str(out / "pcb.d356"), "--out", str(facts)])
    assert _pair(facts, "schematic", "pcb")["only_b"] == [ref]
    assert _pair(facts, "schematic", "fab")["only_b"] == [ref]
