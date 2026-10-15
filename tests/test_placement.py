from pathlib import Path

import pytest

from boardreview.model import placement

FIX = Path(__file__).parent / "fixtures"
BOARD = FIX / "report"

INCH_UNITS = """C  Synthetic IPC-D-356A in 0.0001 inch units, two parts, two sides (no real board)
P  JOB   synth
P  UNITS {units}
P  VER   IPC-D-356A
327VCC              U1    -1          A01X+010000Y+020000X0600Y0600R000 S0
327GND              U1    -2          A01X+012000Y+020000X0600Y0600R000 S0
327VCC              C7    -1          A04X+030000Y+005000X0600Y0600R000 S0
327GND              C7    -2          A04X+031000Y+005000X0600Y0600R000 S0
317GND              J3    -1    D0400PA00X+000000Y+000000X0600Y0600R000 S0
317GND              J3    -2    D0400PA00X+000000Y+001000X0600Y0600R000 S0
317GND              VIA        MD0120PA00X+040000Y+030000X0600Y0600R000 S3
999
"""


@pytest.mark.parametrize("units", ["CUST 0", "CUST"])
def test_ipc356_inch_units_and_both_sides(units):
    p = placement.parse_ipc356_places(INCH_UNITS.format(units=units), "synth.ipc")
    assert p.units == "0.0001 in"
    # U1 pads at 1.0 and 1.2 in, y 2.0 in: centre 1.1 in = 27.94 mm, 50.8 mm.
    assert p.parts["U1"].x_mm == pytest.approx(27.94, abs=1e-9)
    assert p.parts["U1"].y_mm == pytest.approx(50.8, abs=1e-9)
    assert p.parts["U1"].side == "top"
    # A04 is the highest SMT layer number in the file: bottom.
    assert p.parts["C7"].side == "bottom"
    assert p.parts["C7"].x_mm == pytest.approx(3.05 * 25.4, abs=1e-9)
    assert p.parts["J3"].side == "through"
    assert p.extent_from == "pads"
    assert p.extent_mm == pytest.approx((0.0, 0.0, 4.0 * 25.4, 3.0 * 25.4))
    assert "VIA" not in p.parts
    assert any("layer 4" in n for n in p.notes)


def test_ipc356_metric_units_from_the_fixture_board():
    p = placement.read_placement(BOARD / "board.d356")
    assert p.units == "0.001 mm"
    assert (p.parts["U3"].x_mm, p.parts["U3"].y_mm, p.parts["U3"].side) == (pytest.approx(38.0), pytest.approx(16.0), "top")
    assert p.parts["U4"].side == "bottom" and p.parts["R61"].side == "bottom"
    assert p.parts["R61"].x_mm == pytest.approx(56.0) and p.parts["R61"].y_mm == pytest.approx(6.0)
    assert p.parts["J1"].side == "through"
    assert p.extent_mm == pytest.approx((1.0, 1.0, 59.0, 39.0))
    assert "board outline" in p.caption()


def test_kicad_d356_fixture_reads_as_inches():
    p = placement.read_placement(FIX / "model" / "kicad_d356_aliases.ipc")
    # U2 pads at 1.2 to 1.4 in.
    assert p.parts["U2"].x_mm == pytest.approx(1.3 * 25.4)
    assert p.parts["U2"].side == "top"


def test_unknown_units_are_flagged():
    _, label, notes = placement.ipc356_units("P  UNITS SI\n")
    assert label == "0.001 mm" and "UNSURE" in notes[0]
    _, label, notes = placement.ipc356_units("C  no units\n")
    assert label == "0.0001 in" and "No UNITS" in notes[0]


def test_kicad_pos_csv_in_mm():
    p = placement.read_placement(BOARD / "board-pos.csv", units="mm")
    assert p.kind == "kicad_pos" and p.units == "mm" and not p.notes
    assert (p.parts["R61"].x_mm, p.parts["R61"].y_mm, p.parts["R61"].side) == (56.0, 6.0, "bottom")
    assert p.parts["J1"].side == "top"
    assert p.extent_from == "parts" and p.extent_mm == (3.0, 6.0, 56.0, 34.0)


def test_kicad_pos_csv_without_units_says_so():
    text = '"Ref","Val","Package","PosX","PosY","Rot","Side"\n"R1","10k","R_0402",1.2500,0.5000,90,bottom\n'
    p = placement.parse_kicad_pos(text, "a-pos.csv")
    assert p.units == "in" and "UNSURE" in p.notes[0]
    assert p.parts["R1"].x_mm == pytest.approx(31.75) and p.parts["R1"].rotation_deg == 90
    big = text.replace("1.2500", "120.0")
    assert placement.parse_kicad_pos(big, "b-pos.csv").units == "mm"


def test_kicad_pos_ascii_reads_its_unit_line():
    text = ("### Footprint positions - created on 2026-10-01 ###\n## Unit = mm, Angle = deg.\n## Side : All\n"
            "# Ref     Val       Package       PosX       PosY       Rot  Side\n"
            "C1        100n      C_0402      10.5000   -20.2500    0.0000  top\n"
            "U9        BUCK      QFN-24      30.0000   -15.0000   90.0000  bottom\n## End\n")
    p = placement.parse_kicad_pos(text, "board.pos", units="in")
    assert p.units == "mm"
    assert (p.parts["C1"].x_mm, p.parts["C1"].y_mm, p.parts["C1"].side) == (10.5, -20.25, "top")
    assert p.parts["U9"].side == "bottom"


def test_sheets_from_kicad_xml():
    sheets = placement.parse_kicad_sheets((BOARD / "board.kicad.xml").read_text(encoding="utf-8"))
    assert sheets["R61"] == "Ethernet" and sheets["U2"] == "Power_3V3"
    root = '<export><components><comp ref="R1"><sheetpath names="/" tstamps="/"/></comp></components></export>'
    assert placement.parse_kicad_sheets(root)["R1"] == "/ (root sheet)"


def test_facts_folder_prefers_a_position_file(tmp_path):
    (tmp_path / "board.d356").write_bytes((BOARD / "board.d356").read_bytes())
    p, sheets, notes = placement.for_facts(tmp_path, [BOARD / "board-pos.csv", BOARD / "board.kicad.xml"], "mm")
    assert p.kind == "kicad_pos"
    assert sheets["U3"] == "MCU"
    assert any("own origin" in n for n in notes)
    p, _, _ = placement.for_facts(tmp_path)
    assert p.kind == "ipc356"
    empty = tmp_path / "empty"
    empty.mkdir()
    p, _, notes = placement.for_facts(empty)
    assert p is None and "not shown" in notes[0]
