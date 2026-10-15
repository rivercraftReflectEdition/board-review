import copy
from pathlib import Path

from boardreview.model import bom, compare, ipc356, kicad, protel
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


def _ipc_line(net, ref, pin):
    return f"327{net:<14}   {ref:<6}-{pin:<4}       A01X 000100Y 000200X0100Y0100R000 S0"


def test_kicad_ipc356_cut_names_are_a_format_limit_not_renames():
    sch = BoardModel(pin_list_complete=True)
    rows = [("/Connectors/I2C.SCL", "U1.1 J1.1"), ("Net-(U1-P1.00/XL1)", "U1.2 Y1.1"),
            ("/ampli_ht_horizontal/Vpil_0_3,3V", "U1.3 R1.1"), ("/ampli_ht_vertical/Vpil_0_3,3V", "U1.4 R2.1"),
            ("GND", "U1.5 R1.2 R2.2 J1.2 Y1.2"), ("AGND", "U1.7 C1.1"), ("unconnected-(U1-NC-Pad6)", "U1.6")]
    for net, keys in rows:
        for key in keys.split():
            sch.add_pin(*key.split("."), net)
    sch.finalize()
    ipc = [("ECTORS/I2C.SCL", "U1 1 J1 1"), (".00{SLASH}XL1)", "U1 2 Y1 1"), ("AL/VPIL_0_3,3V", "U1 3 R1 1"),
           ("PIL_0_3,3V#1", "U1 4 R2 1"), ("GND", "U1 5 R1 2 R2 2 J1 2 Y1 2"), ("SGND", "U1 7 C1 1"),
           ("(U1-NC-PAD6)", "U1 6")]
    lines = []
    for net, refs in ipc:
        parts = refs.split()
        lines += [_ipc_line(net, parts[i], parts[i + 1]) for i in range(0, len(parts), 2)]
    pcb = ipc356.parse_ipc356("\n".join(lines) + "\n999\n")
    assert pcb.pins[("U1", "6")].net is None
    pair = compare.compare([("schematic", sch), ("pcb", pcb)]).pairs[0]
    assert pair.renamed == [("AGND", "SGND")]
    assert len(pair.truncated) == 4 and not pair.moved and not pair.added and not pair.removed
    text = compare.compare([("schematic", sch), ("pcb", pcb)]).to_markdown()
    assert "4 net names in pcb are schematic names cut to the 14-character IPC-D-356 field" in text
    assert "ECTORS/I2C.SCL" not in text


def _model(rows, complete=True):
    m = BoardModel(pin_list_complete=complete)
    for key, net in rows:
        m.add_pin(*key.split("."), net)
    return m.finalize()


def test_three_way_table_reads_a_cut_name_as_the_full_name():
    sch = _model([("U1.1", "VCC"), ("U1.43", None), ("C1.1", "VCC")])
    pcb = _model([("U1.1", "VCC"), ("U1.43", "Net-(U1-TEST1#)"), ("C1.1", "VCC"), ("R5.1", "VCC"),
                  ("R5.2", "Net-(U1-TEST1#)")])
    fab = _model([("U1.1", "VCC"), ("U1.43", "ET-(U1-TEST1#)"), ("C1.1", "VCC"), ("R5.1", "VCC"),
                  ("R5.2", "ET-(U1-TEST1#)")])
    rows = {k: (v, odd) for k, v, odd in compare.compare([("schematic", sch), ("pcb", pcb), ("fab", fab)]).disagreements}
    assert rows["R5.2"] == (["<absent>", "Net-(U1-TEST1#)", "Net-(U1-TEST1#)"], "schematic")
    assert rows["U1.43"][1] == "schematic"


def test_fitted_state_that_differs_between_sources_that_state_it():
    sch = _model([("R1.1", "A"), ("R1.2", "B"), ("R2.1", "A"), ("R2.2", "B")])
    sch.sources.append({"kind": "kicad_xml", "path": "sch.xml"})
    sch.component("R1").fitted = False
    pcb = _model([("R1.1", "A"), ("R1.2", "B"), ("R2.1", "A"), ("R2.2", "B")])
    pcb.sources.append({"kind": "kicad_pcb", "path": "board.kicad_pcb"})
    fab = _model([("R1.1", "A"), ("R1.2", "B"), ("R2.1", "A"), ("R2.2", "B")])
    fab.sources.append({"kind": "ipc356", "path": "fab.ipc"})
    report = compare.compare([("schematic", sch), ("pcb", pcb), ("fab", fab)])
    assert report.pairs[0].fitted_differs == [("R1", False, True)]
    assert report.pairs[1].fitted_differs == [] and report.pairs[2].fitted_differs == []
    assert "R1 (schematic DNP, pcb fitted)" in report.to_markdown()


def test_designator_cut_to_six_characters_is_matched_when_unique():
    sch = _model([("Module301.1", "A"), ("Module301.2", "B"), ("R1.1", "A"), ("R2.1", "B")])
    pcb = _model([("Module.1", "A"), ("Module.2", "B"), ("R1.1", "A"), ("R2.1", "B")])
    report = compare.compare([("schematic", sch), ("pcb", pcb)])
    pair = report.pairs[0]
    assert pair.clean and pair.cut_refs == [("Module", ["Module301"])]
    assert "6-character IPC-D-356 designator field" in report.to_markdown()


def test_designators_that_collide_when_cut_are_left_out_of_the_compare():
    sch = _model([("Module301.1", "A"), ("Module302.1", "B"), ("R1.1", "A"), ("R1.2", "B"), ("R2.1", "A")])
    pcb = _model([("Module.1", "A"), ("R1.1", "A"), ("R1.2", "B"), ("R2.1", "A")])
    pair = compare.compare([("schematic", sch), ("pcb", pcb)]).pairs[0]
    assert pair.cut_refs == [("Module", ["Module301", "Module302"])]
    assert pair.clean and not pair.only_a and not pair.only_b


def test_pin_numbers_cut_to_four_characters_are_a_format_limit():
    sch = _model([("USB1.A1B12", "GND"), ("USB1.A5", "CC"), ("R1.1", "GND"), ("R1.2", "CC")])
    pcb = _model([("USB1.A1B1", "GND"), ("USB1.A5", "CC"), ("R1.1", "GND"), ("R1.2", "CC")])
    report = compare.compare([("schematic", sch), ("pcb", pcb)])
    pair = report.pairs[0]
    assert pair.clean and pair.cut_pins == [("USB1.A1B12", "USB1.A1B1")]
    assert "4-character IPC-D-356 pin field" in report.to_markdown()


def test_nets_only_on_board_excluded_parts_are_not_missing_nets():
    sch = _model([("R1.1", "A"), ("R1.2", "B"), ("SW1.1", "EN"), ("R9.2", "EN"), ("R9.1", "A")])
    for ref in ("SW1", "R9"):
        sch.component(ref).attrs["exclude_from_board"] = "yes"
    pcb = _model([("R1.1", "A"), ("R1.2", "B")])
    pair = compare.compare([("schematic", sch), ("pcb", pcb)]).pairs[0]
    assert pair.removed == [] and pair.mech_only_a == ["R9", "SW1"] and pair.clean


def test_pinless_and_board_excluded_parts_are_listed_apart():
    sch = _model([("R1.1", "A"), ("R1.2", "B"), ("SW1.1", "A"), ("SW1.2", "B")])
    sch.component("LOGO1")
    sch.component("SW1").attrs["exclude_from_board"] = "yes"
    pcb = _model([("R1.1", "A"), ("R1.2", "B")])
    pair = compare.compare([("schematic", sch), ("pcb", pcb)]).pairs[0]
    assert pair.only_a == [] and pair.mech_only_a == ["LOGO1", "SW1"] and pair.clean


def test_open_pads_present_on_one_side_only_are_not_differences():
    sch = _model([("U1.1", "A"), ("U1.2", "B"), ("R1.1", "A"), ("R1.2", "B"), ("J1.1", "A"), ("J1.M1", None)])
    pcb = _model([("U1.1", "A"), ("U1.2", "B"), ("U1.9", None), ("R1.1", "A"), ("R1.2", "B"), ("J1.1", "A")])
    report = compare.compare([("schematic", sch), ("pcb", pcb)])
    pair = report.pairs[0]
    assert pair.clean and not pair.pins_only_a and not pair.pins_only_b
    assert pair.open_only_a == ["J1.M1"] and pair.open_only_b == ["U1.9"]
    assert "pins with no net exist in only one source" in report.to_markdown()


def test_a_connected_pin_present_on_one_side_only_is_still_a_difference():
    sch = _model([("U1.1", "A"), ("R1.1", "A"), ("U1.2", "B"), ("R1.2", "B")])
    pcb = _model([("U1.1", "A"), ("R1.1", "A"), ("R1.2", "B"), ("U1.3", "B")])
    pair = compare.compare([("schematic", sch), ("pcb", pcb)]).pairs[0]
    assert pair.pins_only_a == ["U1.2"] and pair.pins_only_b == ["U1.3"] and not pair.clean


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
    for ref in ("U4", "R8", "Y1", "C8"):
        del b.components[ref]
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
    assert "Mechanical or test parts, parts with no pins, and parts excluded from the board, only in pcb" in compare.compare([("sch", _ti()), ("pcb", b)]).to_markdown()


def test_three_way_with_a_netlist_that_omits_open_pins():
    sch = protel.read_protel(FIX / "sch_missing_sheet.net")
    fab = ipc356.read_ipc356(FIX / "adi_buck_nonames.ipc")
    report = compare.compare([("schematic", sch), ("pcb", fab), ("fab", fab)])
    rows = {k: (v, odd) for k, v, odd in report.disagreements}
    assert "U2.4" not in rows
    assert rows["U1.1"] == (["<absent>", "VIN", "VIN"], "schematic")


def test_deleted_part_with_no_connected_pins_is_not_clean():
    full = protel.parse_protel("[\nR5\nR0402\n10k\n]\n[\nU1\nSOIC8\nX\n]\n[\nMH1\nHOLE\nM3\n]\n(\nA\nU1-1\nC1-1\n)\n")
    cut = protel.parse_protel("[\nU1\nSOIC8\nX\n]\n(\nA\nU1-1\nC1-1\n)\n")
    pair = compare.compare([("sch", full), ("pcb", cut)]).pairs[0]
    assert pair.only_a == ["R5"] and pair.mech_only_a == ["MH1"]
    assert not pair.clean


def test_bom_only_parts_are_listed_apart_and_not_compared(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text("Designator,MPN\nU1,X\nZ9,Y\n", encoding="utf-8")
    with_bom = protel.parse_protel("[\nU1\nSOIC8\nX\n]\n(\nA\nU1-1\nC1-1\n)\n")
    bom.apply_bom(with_bom, bom.read_bom(path), str(path))
    plain = protel.parse_protel("[\nU1\nSOIC8\nX\n]\n(\nA\nU1-1\nC1-1\n)\n")
    report = compare.compare([("sch", with_bom), ("pcb", plain)])
    assert report.pairs[0].clean
    assert "| BOM-only parts | 1 | 0 |" in report.to_markdown()


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
    for ref in ("U9", "C1", "C2"):
        del part.components[ref]
    part.invalidate()
    pair = compare.compare([("schematic", part), ("pcb", full)]).pairs[0]
    assert pair.groups_only_b == [["C1", "C2", "U9"]]
