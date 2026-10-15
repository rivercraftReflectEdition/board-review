import copy
from pathlib import Path

from boardreview.model import compare, ipc356, kicad, protel
from boardreview.model.board import BoardModel

FIX = Path(__file__).parent / "fixtures" / "model"


def _ti():
    return kicad.read_kicad_xml(FIX / "ti_buck_board.kicad.xml")


def _move(model, key, net):
    model.pin(key).net = net
    model.invalidate()
    return model


def test_dropped_sheet_shows_as_one_connected_group():
    sch = protel.read_protel(FIX / "sch_missing_sheet.net")
    fab = ipc356.read_ipc356(FIX / "adi_buck_nonames.ipc")
    report = compare.compare([("schematic", sch), ("fab", fab)])
    pair = report.pairs[0]
    assert pair.only_b == ["C2", "L1", "R1", "R2", "U1"]
    assert pair.groups_only_b == [["C2", "L1", "R1", "R2", "U1"]]
    assert pair.added == ["NetC2_1", "NetL1_1", "NetR1_2"]
    assert not pair.moved and not pair.renamed
    assert pair.pins_only_b == [], "open pins missing from a Protel netlist are not differences"
    text = report.to_markdown()
    assert "5 parts are in fab but not in schematic" in text
    assert "dropped out of the compile" in text


def test_identical_models_are_clean():
    pair = compare.compare([("a", _ti()), ("b", _ti())]).pairs[0]
    assert pair.clean


def test_rename_is_not_reported_as_remove_and_add():
    b = _ti()
    for pin in b.pins.values():
        if pin.net == "NRST":
            pin.net = "MCU_RESET_N"
    b.invalidate()
    pair = compare.compare([("sch", _ti()), ("pcb", b)]).pairs[0]
    assert pair.renamed == [("NRST", "MCU_RESET_N")]
    assert not pair.moved and not pair.removed and not pair.added


def test_moved_pin_and_pin_left_open():
    b = _move(_ti(), "R8.2", "I2C1_SDA")
    b = _move(b, "C10.1", None)
    pair = compare.compare([("sch", _ti()), ("pcb", b)]).pairs[0]
    assert ("R8.2", "I2C1_SCL", "I2C1_SDA") in pair.moved
    assert ("C10.1", "NRST", None) in pair.moved
    assert len(pair.moved) == 2


def test_merge_and_split():
    b = _ti()
    for pin in b.pins.values():
        if pin.net == "3V3A":
            pin.net = "+3V3"
    b.invalidate()
    pair = compare.compare([("sch", _ti()), ("pcb", b)]).pairs[0]
    assert [(sorted(x), y) for x, y in pair.merged] == [(["+3V3", "3V3A"], "+3V3")]
    back = compare.compare([("pcb", b), ("sch", _ti())]).pairs[0]
    assert [(x, sorted(y)) for x, y in back.split] == [("+3V3", ["+3V3", "3V3A"])]


def test_three_way_names_the_odd_one_out():
    sch = _ti()
    pcb = _ti()
    for pin in pcb.pins.values():
        if pin.net == "NRST":
            pin.net = "RESET_N"
    pcb.invalidate()
    fab = _move(_ti(), "R8.2", "I2C1_SDA")
    report = compare.compare([("schematic", sch), ("pcb", pcb), ("fab", fab)])
    assert [(p.a, p.b) for p in report.pairs] == [("schematic", "pcb"), ("pcb", "fab"), ("schematic", "fab")]
    rows = {k: (v, odd) for k, v, odd in report.disagreements}
    assert rows == {"R8.2": (["I2C1_SCL", "I2C1_SCL", "I2C1_SDA"], "fab")}
    assert report.pairs[1].renamed == [("RESET_N", "NRST")]
    data = report.to_dict()
    assert data["stats"]["pcb"]["components"] == len(pcb.components)
    assert "| R8.2 | I2C1_SCL | I2C1_SCL | I2C1_SDA | fab |" in report.to_markdown()


def test_missing_parts_split_into_unconnected_groups():
    b = copy.deepcopy(_ti())
    for key in [k for k in b.pins if k[0] in ("U4", "R8", "Y1", "C8")]:
        del b.pins[key]
    b.invalidate()
    pair = compare.compare([("sch", _ti()), ("pcb", b)]).pairs[0]
    assert pair.only_a == ["C8", "R8", "U4", "Y1"]
    assert sorted(map(sorted, pair.groups_only_a)) == [["C8", "Y1"], ["R8", "U4"]]


def test_mechanical_parts_are_listed_apart():
    b = _ti()
    b.add_pin("MH1", "1", "GND")
    b.add_pin("FID1", "1", None)
    b.finalize()
    pair = compare.compare([("sch", _ti()), ("pcb", b)]).pairs[0]
    assert pair.only_b == [] and pair.mech_only_b == ["FID1", "MH1"]
    assert "Mechanical or test parts only in pcb" in compare.compare([("sch", _ti()), ("pcb", b)]).to_markdown()


def test_three_way_with_a_netlist_that_omits_open_pins():
    sch = protel.read_protel(FIX / "sch_missing_sheet.net")
    fab = ipc356.read_ipc356(FIX / "adi_buck_nonames.ipc")
    report = compare.compare([("schematic", sch), ("pcb", fab), ("fab", fab)])
    rows = {k: (v, odd) for k, v, odd in report.disagreements}
    assert "U2.4" not in rows
    assert rows["U1.1"] == (["<absent>", "VIN", "VIN"], "schematic")


def test_rail_used_only_by_missing_parts_joins_their_group():
    full = BoardModel(pin_list_complete=True)
    for ref, pin, net in [("U9", "1", "5V_AUX"), ("U9", "2", "GND"), ("C1", "1", "5V_AUX"), ("C1", "2", "GND"),
                          ("C2", "1", "5V_AUX"), ("C2", "2", "GND"), ("C3", "1", "3V3"), ("C3", "2", "GND"),
                          ("U2", "1", "3V3"), ("U2", "2", "GND")]:
        full.add_pin(ref, pin, net)
    full.finalize()
    part = copy.deepcopy(full)
    for key in [k for k in part.pins if k[0] in ("U9", "C1", "C2")]:
        del part.pins[key]
    part.invalidate()
    pair = compare.compare([("schematic", part), ("pcb", full)]).pairs[0]
    assert pair.groups_only_b == [["C1", "C2", "U9"]]
