from pathlib import Path

from boardreview import lint
from boardreview.lint import nets, parts, pins
from boardreview.model import bom, kicad, protel
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph

FIX = Path(__file__).parent / "fixtures" / "model"


def _ti():
    return kicad.read_kicad_xml(FIX / "ti_buck_board.kicad.xml")


def _run(fn, model):
    return fn(model, Graph(model))


def _board(rows, mpn=None, dnp=(), complete=True):
    """Model from (ref, pin, net, pin_name) rows; mpn maps ref -> MPN."""
    m = BoardModel(pin_list_complete=complete)
    for ref, pin, net, name in rows:
        m.add_pin(ref, pin, net, name)
    for ref, value in (mpn or {}).items():
        m.component(ref).mpn = value
    for ref in dnp:
        m.component(ref).fitted = False
    for c in m.components.values():
        c.classify()
    return m.finalize()


def test_single_pin_net_flags_named_nets_only():
    found = _run(nets.single_pin_nets, _ti())
    assert [f.nets for f in found] == [["3V3"]]
    assert found[0].pins == ["R9.1"]


def test_labeled_pins_with_a_no_connect_flag_are_one_info_line():
    m = BoardModel(pin_list_complete=True)
    m.add_pin("U1", "91", "/CM5/BT_nDis", "BT_nDisable", "input", no_connect=True)
    m.add_pin("U1", "92", "/CM5/WL_nDis", "WL_nDisable", "input", no_connect=True)
    m.add_pin("U1", "5", "SPARE", "GPIO5", "bidirectional")
    m.finalize()
    found = [(f.severity, f.pins) for f in _run(nets.single_pin_nets, m)]
    assert ("warning", ["U1.5"]) in found
    assert ("info", ["U1.91", "U1.92"]) in found and len(found) == 2


def test_near_duplicate_rails_spelling_loose_and_case():
    found = _run(nets.near_duplicate_rails, _ti())
    assert [(f.severity, sorted(f.nets)) for f in found] == [("warning", ["+3V3", "3V3"])]
    m = _board([("C1", "1", "VCC_3V3", ""), ("C1", "2", "GND", ""), ("C2", "1", "3.3V", ""), ("C2", "2", "GND", ""),
                ("R1", "1", "Reset", ""), ("R1", "2", "RESET", "")])
    found = _run(nets.near_duplicate_rails, m)
    assert ("info", ["3.3V", "VCC_3V3"]) in [(f.severity, sorted(f.nets)) for f in found]
    assert ["RESET", "Reset"] in [sorted(f.nets) for f in found]


def test_near_duplicate_rails_leave_distinct_rails_alone():
    m = _board([("C1", "1", "1V8", ""), ("C1", "2", "GND", ""), ("C2", "1", "1V8-SW1", ""), ("C2", "2", "GND", ""),
                ("C3", "1", "3V3A", ""), ("C3", "2", "GND", ""), ("C4", "1", "3V3", ""), ("C4", "2", "GND", "")])
    assert _run(nets.near_duplicate_rails, m) == []


def test_dnp_only_link_from_kicad_dnp_property():
    found = _run(nets.dnp_only_link, _ti())
    assert [(f.severity, f.nets, f.pins) for f in found] == [("warning", ["/OPT_LINK"], ["U2.13", "R10.1"])]


def test_dnp_only_link_net_with_only_dnp_parts():
    m = _board([("R1", "1", "OPT", ""), ("R2", "1", "OPT", ""), ("R1", "2", "GND", ""), ("R2", "2", "GND", ""),
                ("C1", "1", "GND", ""), ("C2", "1", "GND", "")], dnp=("R1", "R2"))
    found = _run(nets.dnp_only_link, m)
    assert [(f.severity, f.nets) for f in found] == [("info", ["OPT"])]


def test_unconnected_ic_pins_severity_by_pin_name():
    found = _run(pins.unconnected_ic_pins, _ti())
    by_sev = {(f.severity, tuple(f.pins)) for f in found}
    assert ("error", ("U2.15",)) in by_sev
    assert ("warning", ("U2.10",)) in by_sev
    assert ("warning", ("U4.3",)) in by_sev
    assert ("info", ("U2.14",)) in by_sev
    assert next(f for f in found if f.pins == ["U2.14"]).evidence["needs"] == "datasheet confirmation"


def test_unconnected_ic_pins_without_names_are_info_and_skip_on_protel():
    m = _board([("U1", "1", "VIN", ""), ("U1", "2", None, ""), ("U1", "3", "GND", "")])
    found = _run(pins.unconnected_ic_pins, m)
    assert [(f.severity, f.pins) for f in found] == [("info", ["U1.2"])]
    report = lint.run_all(protel.read_protel(FIX / "sch_missing_sheet.net"))
    assert "unconnected_ic_pin" in report.skipped


def test_open_nc_and_reserved_pins_need_datasheet_confirmation():
    # TPS55340-Q1, SLVSBV5C rev C, p. 3, Table 5-1: NC pins 10 and 14 are reserved and must be connected to ground.
    m = _board([("U1", "2", "VIN", "VIN"), ("U1", "6", "GND", "AGND"), ("U1", "10", None, "NC"),
                ("U1", "14", None, "NC"), ("U1", "15", None, "RESERVED")], mpn={"U1": "TPS55340QRTERQ1"})
    found = _run(pins.unconnected_ic_pins, m)
    assert [(f.severity, f.pins) for f in found] == [("warning", ["U1.10", "U1.14", "U1.15"])]
    assert found[0].evidence["needs"] == "datasheet confirmation"
    assert "tied to ground" in found[0].summary


def test_open_power_pin_is_an_error_even_with_a_no_connect_flag():
    m = BoardModel(pin_list_complete=True)
    m.add_pin("U1", "1", "VIN", "VIN", "power_in")
    m.add_pin("U1", "2", None, "VSS", "power_in", no_connect=True)
    m.add_pin("U1", "3", None, "NC", "power_in")
    m.add_pin("U1", "4", None, "PA3", "bidirectional", no_connect=True)
    m.finalize()
    found = _run(pins.unconnected_ic_pins, m)
    assert [(f.severity, f.pins) for f in found] == [("error", ["U1.2"]), ("error", ["U1.3"]), ("info", ["U1.4"])]


def test_bare_in_pin_is_not_treated_as_a_supply():
    m = _board([("U1", "1", "VCC", "VCC"), ("U1", "2", None, "IN"), ("U1", "3", "GND", "GND"), ("U2", "1", "GND", "IN")])
    found = _run(pins.unconnected_ic_pins, m)
    assert [(f.severity, f.pins) for f in found] == [("warning", ["U1.2"])]
    assert _run(pins.ground_pin_off_ground, m) == []


def test_ground_pin_off_ground_and_reverse():
    m = _board([("U5", "1", "SENSE_RTN", "GND"), ("U5", "2", "VIN", "EP"), ("U5", "3", "GND", "VDD"),
                ("U5", "4", "AGND", "AGND"), ("U5", "5", "GND", "PGND")])
    found = _run(pins.ground_pin_off_ground, m)
    assert [(f.severity, f.pins) for f in found] == [("error", ["U5.1"]), ("info", ["U5.2"]), ("warning", ["U5.3"])]


def test_protection_ground_by_pin_name():
    found = _run(pins.protection_ground_floating, _ti())
    assert [(f.severity, f.pins) for f in found] == [("error", ["D2.3"])]
    assert "pin names say ground" in found[0].summary


def test_protection_ground_by_same_mpn_sibling_without_pin_names():
    rows = []
    for ref, gnd in (("D1", None), ("D2", "GND"), ("D3", "GND")):
        rows += [(ref, "1", f"SIG_{ref}_A", ""), (ref, "2", f"SIG_{ref}_B", ""), (ref, "3", gnd, "")]
    m = _board(rows + [("C1", "1", "GND", "")], mpn={"D1": "RCLAMP0524P", "D2": "RCLAMP0524P", "D3": "RCLAMP0524P"})
    for ref in ("D1", "D2", "D3"):
        m.components[ref].kind = "tvs"
    found = _run(pins.protection_ground_floating, m)
    assert [(f.severity, f.pins, f.components) for f in found] == [("error", ["D1.3"], ["D1", "D2", "D3"])]


def test_two_pin_tvs_either_way_round_is_fine():
    m = _board([("D9", "1", "CHASSIS", ""), ("D9", "2", "GND", ""), ("D10", "1", "GND", ""), ("D10", "2", "5V", "")],
               mpn={"D9": "SMAJ5.0CA", "D10": "SMAJ5.0CA"})
    for ref in ("D9", "D10"):
        m.components[ref].kind = "tvs"
    assert _run(pins.protection_ground_floating, m) == []


def test_fitted_without_mpn_and_skip_without_part_data():
    found = _run(parts.fitted_without_mpn, _ti())
    assert [f.components for f in found] == [["C10"]]
    report = lint.run_all(protel.read_protel(FIX / "sch_missing_sheet.net"))
    assert "fitted_without_mpn" in report.skipped


def test_bom_netlist_mismatch(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text("Designator,MPN\nR1,RC0402\nR7,RC0402\nMH1,\n", encoding="utf-8")
    m = protel.parse_protel("(\nA\nR1-1\nC1-1\n)\n")
    bom.apply_bom(m, bom.read_bom(path), str(path))
    found = _run(parts.bom_netlist_mismatch, m)
    summaries = [(f.severity, f.components) for f in found]
    assert ("warning", ["R7"]) in summaries and ("info", ["MH1"]) in summaries and ("warning", ["C1"]) in summaries


def test_parts_excluded_from_the_bom_by_the_schematic_are_not_missing(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text("Reference,Value\nR1,10k\n", encoding="utf-8")
    m = BoardModel(pin_list_complete=True)
    for ref in ("R1", "R2", "U7", "JP1"):
        m.add_pin(ref, "1", "A")
        m.add_pin(ref, "2", "B")
    for ref in ("R2", "U7", "JP1"):
        m.component(ref).attrs["exclude_from_bom"] = "yes"
    m.component("R2").fitted = False
    m.finalize()
    check = bom.apply_bom(m, bom.read_bom(path), str(path))
    assert check["netlist_only"] == [] and check["excluded_from_bom"] == ["JP1", "R2", "U7"]
    found = {(f.severity, tuple(f.components)) for f in _run(parts.bom_netlist_mismatch, m)}
    assert ("warning", ("U7",)) in found
    assert ("info", ("JP1", "R2", "U7")) in found
    assert not any(sev == "warning" and "R2" in comps for sev, comps in found)


def test_bom_netlist_mismatch_reports_fitted_state_conflicts(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text("Designator,MPN,DNP\nR7,RC0402FR-0710KL,\nR6,RC0402FR-0710KL,x\n", encoding="utf-8")
    m = _ti()
    bom.apply_bom(m, bom.read_bom(path), str(path))
    found = [f for f in _run(parts.bom_netlist_mismatch, m) if "fitted_conflict" in f.evidence]
    assert [(f.severity, f.components) for f in found] == [("warning", ["R6"]), ("warning", ["R7"])]
    assert "netlist DNP" in found[1].summary


def test_run_all_orders_by_severity_and_serializes():
    report = lint.run_all(_ti())
    sev = [f.severity for f in report.findings]
    assert sev == sorted(sev, key=lambda s: {"error": 0, "warning": 1, "info": 2}[s])
    assert report.skipped == {"bom_netlist_mismatch": "no BOM loaded"}
    data = report.to_dict()
    assert {f["check"] for f in data["findings"]} >= {"single_pin_net", "protection_ground_floating",
                                                       "near_duplicate_rails", "dnp_only_link", "fitted_without_mpn"}
    assert "2 errors" in report.to_markdown()
