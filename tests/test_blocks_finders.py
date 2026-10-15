from pathlib import Path

import pytest

from boardreview import blocks
from boardreview.blocks import clocks, filters, i2c, regulators, resets, straps
from boardreview.model import eda_agent, ipc356, kicad
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph

FIX = Path(__file__).parent / "fixtures" / "model"


def _ti():
    return kicad.read_kicad_xml(FIX / "ti_buck_board.kicad.xml")


def _mps():
    return eda_agent.read_eda_agent(FIX / "mps_buck.eda_agent.json")


def _adi():
    return ipc356.read_ipc356(FIX / "adi_buck_nonames.ipc")


def _board(rows, kinds=None, values=None, desc=None, dnp=()):
    """Model from (ref, pin, net, pin_name) rows with optional kind, value and description overrides."""
    m = BoardModel(pin_list_complete=True)
    for ref, pin, net, name in rows:
        m.add_pin(ref, pin, net, name)
    for ref, text in (desc or {}).items():
        m.component(ref).description = text
    for c in m.components.values():
        c.classify()
    for ref, kind in (kinds or {}).items():
        m.components[ref].kind = kind
    for ref, value in (values or {}).items():
        m.components[ref].value = value
    for ref in dnp:
        m.components[ref].fitted = False
    return m.finalize()


def _two(ref, a, b):
    return [(ref, "1", a, ""), (ref, "2", b, "")]


def _only(found, kind):
    got = [b for b in found if b.kind == kind]
    assert len(got) == 1, [b.name for b in found]
    return got[0]


def test_ti_buck_with_pin_names():
    b = _only(regulators.find_switching_regulators(Graph(_ti())), "switching_regulator")
    assert b.confidence == "high"
    assert b.roles["controller"] == ["U1"] and b.roles["inductor"] == ["L1"]
    assert b.roles["switch_node"] == ["SW"] and b.roles["output"] == ["+3V3"]
    assert b.roles["bootstrap"] == ["C2"] and b.roles["fb_pins"] == ["U1.4"]
    assert (b.roles["feedback_top"], b.roles["feedback_bottom"], b.roles["feedforward_cap"]) == (["R1"], ["R2"], ["C5"])
    assert b.roles["input"] == ["VIN"] and b.roles["enable_pins"] == ["U1.5"]
    assert any(e.startswith("switch pin name SW") for e in b.evidence)
    assert b.subgraph["nets"]["SW"]["block_pins"] == ["C2.2", "L1.1", "U1.2"]


def test_mps_buck_bootstrap_through_series_resistor():
    b = _only(regulators.find_switching_regulators(Graph(_mps())), "switching_regulator")
    assert b.confidence == "high"
    assert b.roles["switch_node"] == ["LX"] and b.roles["output"] == ["+5V"]
    assert b.roles["bootstrap"] == ["C3", "R6"] and b.roles["bootstrap_pins"] == ["U1.5"]
    assert b.roles["input"] == ["VIN_12V"]
    assert b.roles["enable_pins"] == ["U1.6"]


def test_adi_buck_found_by_structure_alone():
    model = _adi()
    assert not any(p.name for p in model.pins.values())
    b = _only(regulators.find_switching_regulators(Graph(model)), "switching_regulator")
    assert b.confidence == "high"
    assert not any("pin name" in e for e in b.evidence)
    assert b.roles["switch_node"] == ["NetL1_1"] and b.roles["fb_pins"] == ["U1.8"]
    assert b.roles["input"] == ["VIN"]


def test_unnamed_buck_with_a_cap_on_the_switch_node_is_kept_and_the_cap_reported():
    model = _adi()
    model.add_pin("C9", "1", "NetL1_1")
    model.add_pin("C9", "2", "GND")
    model.finalize()
    b = _only(regulators.find_switching_regulators(Graph(model)), "switching_regulator")
    assert b.roles["switch_node"] == ["NetL1_1"] and b.roles["output"] == ["+3V3"]
    assert b.roles["switch_node_caps"] == ["C9"]
    assert any("C9" in n and "switch node" in n for n in b.notes)
    assert not any(e.startswith("no caps to ground") for e in b.evidence)


@pytest.mark.parametrize("filtered", ["12V_FILT", "NetL7_2"])
def test_input_filter_into_an_ic_with_caps_on_both_sides_stays_a_filter(filtered):
    rows = _two("L7", "VIN", filtered) + _two("C1", filtered, "GND") + _two("C2", filtered, "GND")
    rows += _two("C5", "VIN", "GND") + _two("C18", filtered, "N_X") + _two("R2", "N_X", "N_INT")
    rows += [("U13", "1", filtered, ""), ("U13", "2", filtered, ""), ("U13", "3", "GND", ""),
             ("U13", "4", "N_INT", ""), ("U13", "5", "N_INT", ""), ("U13", "6", "N_INT", "")]
    found = blocks.find_all(_board(rows))
    assert [b.kind for b in found if b.kind in ("switching_regulator", "lc_filter")] == ["lc_filter"]


def test_regulator_with_lx_vfb_pgood_run_names_and_no_bootstrap():
    rows = [("U7", "1", "VIN", "VIN"), ("U7", "2", "LX_1V2", "LX"), ("U7", "3", "GND", "GND"),
            ("U7", "4", "FB_1V2", "VFB"), ("U7", "5", "EN_1V2", "RUN"), ("U7", "6", "PG_1V2", "PGOOD")]
    rows += _two("L4", "LX_1V2", "1V2") + _two("C1", "1V2", "GND") + _two("C2", "1V2", "GND")
    rows += _two("R1", "1V2", "FB_1V2") + _two("R2", "FB_1V2", "GND") + _two("C9", "VIN", "GND")
    b = _only(regulators.find_switching_regulators(Graph(_board(rows))), "switching_regulator")
    assert b.confidence == "high"
    assert b.roles["enable_pins"] == ["U7.5"] and b.roles["power_good_pins"] == ["U7.6"]
    assert "bootstrap" not in b.roles


def test_inductor_with_caps_on_both_sides_is_a_filter_not_a_regulator():
    rows = _two("L9", "5V", "5V_PLL") + _two("C1", "5V", "GND") + _two("C2", "5V_PLL", "GND")
    rows += [("U3", "1", "5V", "VDD"), ("U3", "2", "5V_PLL", "VDDPLL"), ("U3", "3", "GND", "GND")]
    g = Graph(_board(rows))
    assert regulators.find_switching_regulators(g) == []
    b = _only(filters.find_series_filters(g), "lc_filter")
    assert b.roles["upstream"] == ["5V"] and b.roles["downstream"] == ["5V_PLL"]
    assert b.roles["caps_downstream"] == ["C2"] and b.roles["loads_downstream"] == ["U3.2"]


def test_ferrite_filter_from_fixture_with_values():
    b = _only(filters.find_series_filters(Graph(_ti())), "ferrite_filter")
    assert b.roles["element"] == ["FB1"] and b.roles["downstream"] == ["3V3A"]
    assert b.roles["caps_downstream"] == ["C6", "C7"]
    assert any("downstream C total 1.1e-06 F" in n for n in b.notes)


def test_crystal_with_load_caps_and_series_resistor():
    rows = _two("Y3", "X_A", "X_B") + _two("C1", "X_A", "GND") + _two("C2", "X_B", "GND")
    rows += _two("R5", "X_B", "XOUT_MCU") + [("U1", "1", "X_A", "XIN"), ("U1", "2", "XOUT_MCU", "XOUT"),
                                             ("U1", "3", "GND", "GND")]
    b = _only(clocks.find_clocks(Graph(_board(rows))), "crystal")
    assert b.confidence == "high"
    assert b.roles["load_caps"] == ["C1", "C2"] and b.roles["series_resistors"] == ["R5"]
    assert sorted(b.roles["driver_pins"]) == ["U1.1", "U1.2"]


def test_oscillator_output_enable_and_open_pin():
    rows = [("Y5", "1", "OSC_OE", "OE"), ("Y5", "2", "GND", "GND"), ("Y5", "3", "CLK25", "OUT"), ("Y5", "4", "3V3", "VDD"),
            ("Y5", "5", None, "NC"), ("U2", "1", "CLK25", "CLKIN"), ("U2", "2", "3V3", "VDD")]
    rows += _two("R7", "3V3", "OSC_OE") + _two("C1", "3V3", "GND") + _two("C2", "3V3", "GND") + _two("C3", "3V3", "GND")
    b = _only(clocks.find_clocks(Graph(_board(rows, desc={"Y5": "25MHz oscillator"}))), "oscillator")
    assert b.roles["output"] == ["CLK25"] and b.roles["loads"] == ["U2.1"]
    assert b.roles["enable_nets"] == ["OSC_OE"] and b.roles["supply"] == ["3V3"]
    assert any("Y5.5" in n for n in b.notes)


def test_reset_tree_roles():
    found = resets.find_reset_nets(Graph(_ti()))
    nrst = next(b for b in found if b.roles["net"] == ["NRST"])
    assert nrst.confidence == "high"
    assert nrst.roles["pullups"] == ["R5"] and nrst.roles["delay_caps"] == ["C10"]
    assert nrst.roles["supervisors"] == ["U3"] and nrst.roles["driver_pins"] == ["U3.2"]
    assert nrst.roles["diodes"] == ["D1"] and nrst.roles["linked_nets"] == ["SYS_RST_N"]
    sys_rst = next(b for b in found if b.roles["net"] == ["SYS_RST_N"])
    assert sys_rst.roles["connectors"] == ["J2.3"]


def test_reset_found_by_pin_name_when_net_is_auto_named():
    rows = [("U1", "1", "NetU1_1", "NRST"), ("U2", "3", "NetU1_1", "~{RESET}")] + _two("R1", "NetU1_1", "3V3")
    rows += _two("C1", "3V3", "GND") + _two("C2", "3V3", "GND") + _two("C3", "3V3", "GND")
    b = _only(resets.find_reset_nets(Graph(_board(rows))), "reset")
    assert b.roles["pullups"] == ["R1"] and "reset-named pins U1.1, U2.3" in b.evidence


def test_i2c_pairs_by_name_and_flags_split_pullup_rails():
    b = _only(i2c.find_i2c_buses(Graph(_ti())), "i2c_bus")
    assert (b.roles["sda"], b.roles["scl"]) == (["I2C1_SDA"], ["I2C1_SCL"])
    assert b.roles["devices"] == ["U2", "U4"]
    assert any("different rails" in n for n in b.notes)


def test_i2c_pairs_by_pin_names_and_shared_devices():
    rows = [("U5", "1", "N_A", "SDA"), ("U5", "2", "N_B", "SCL"), ("U6", "7", "N_A", "SDA"), ("U6", "8", "N_B", "SCL")]
    rows += _two("R1", "N_A", "3V3") + _two("C1", "3V3", "GND") + _two("C2", "3V3", "GND") + _two("C3", "3V3", "GND")
    b = _only(i2c.find_i2c_buses(Graph(_board(rows))), "i2c_bus")
    assert (b.roles["sda"], b.roles["scl"]) == (["N_A"], ["N_B"])
    assert "pairing: same devices on both lines" in b.evidence
    assert any("no pull-up found on N_B" in n for n in b.notes)


def test_caps_alone_do_not_make_a_rail_of_a_net_with_i2c_or_reset_pins():
    rows = [("U5", "1", "BUS_D", "SDA"), ("U5", "2", "BUS_C", "SCL"), ("U6", "7", "BUS_D", "SDA"),
            ("U6", "8", "BUS_C", "SCL"), ("U5", "3", "N_R", "NRST"), ("U6", "9", "N_R", "~{RESET}")]
    rows += _two("C1", "BUS_D", "GND") + _two("C2", "BUS_D", "GND") + _two("C3", "BUS_D", "GND")
    rows += _two("C4", "N_R", "GND") + _two("C5", "N_R", "GND") + _two("C6", "N_R", "GND")
    rows += _two("R1", "BUS_D", "3V3") + _two("R2", "BUS_C", "3V3") + _two("C7", "3V3", "GND")
    g = Graph(_board(rows))
    assert g.rail_evidence("BUS_D") == [] and g.rail_evidence("N_R") == []
    b = _only(i2c.find_i2c_buses(g), "i2c_bus")
    assert (b.roles["sda"], b.roles["scl"]) == (["BUS_D"], ["BUS_C"])
    assert [x.roles["net"] for x in resets.find_reset_nets(g)] == [["N_R"]]


def test_straps_report_topology_and_fitted_state_and_role_tags():
    found = {b.roles["net"][0]: b for b in straps.find_straps(Graph(_ti()))}
    assert found["/BOOT0"].confidence == "high"
    assert found["/BOOT0"].roles["pulldowns"] == ["R6"] and found["/BOOT0"].roles["pullups_dnp"] == ["R7"]
    assert "pulled toward GND by R6; not fitted: R7 to +3V3" in found["/BOOT0"].notes
    assert any("enable" in n for n in found["/EN_BUCK"].notes)
    assert "no fitted pull resistor; not fitted: R10 to +3V3" in found["/OPT_LINK"].notes
    assert "I2C1_SDA" not in found


def test_strap_finder_does_not_claim_a_logic_level():
    rows = [("U1", "1", "MODE", "MODE"), ("U1", "2", "3V3", "VDD"), ("U1", "3", "GND", "GND")]
    rows += _two("R1", "MODE", "3V3") + _two("C1", "3V3", "GND")
    b = _only(straps.find_straps(Graph(_board(rows, values={"R1": "1M"}))), "strap")
    text = " ".join(b.notes).lower()
    assert "high" not in text and "low" not in text
    assert "pulled toward 3V3 by R1" in b.notes
    assert any(n.startswith("level: UNSURE") and "VIH" in n and "internal pull" in n for n in b.notes)


def test_strap_with_both_sides_fitted_is_called_out():
    found = {b.roles["net"][0]: b for b in straps.find_straps(_ti_dnp())}
    assert not any("both fitted" in n for n in found["/BOOT0"].notes)
    m = _ti()
    m.components["R7"].fitted = True
    b = {x.roles["net"][0]: x for x in straps.find_straps(Graph(m))}["/BOOT0"]
    assert any("R7 to +3V3 and R6 to GND are both fitted" in n for n in b.notes)


def test_find_all_skips_nets_explained_elsewhere_and_reports_edges():
    found = blocks.find_all(_ti())
    kinds = sorted(b.kind for b in found)
    assert kinds == ["crystal", "ferrite_filter", "i2c_bus", "reset", "reset", "strap", "strap", "strap",
                     "switching_regulator"]
    assert all(b.roles.get("net") != ["/FB_3V3"] for b in found)
    edges = blocks.power_edges(found)
    assert edges == ["U1 switching regulator (high): VIN -> +3V3 via L1", "FB1 ferrite filter (medium): +3V3 -> 3V3A"]
    text = blocks.to_markdown(found)
    assert "## switching regulator (1)" in text and "### U1 via L1 -> +3V3 (high)" in text


def _ti_dnp(*refs):
    m = _ti()
    for ref in refs:
        m.components[ref].fitted = False
    return Graph(m)


def test_filter_total_uses_fitted_caps_and_lists_dnp_apart():
    b = _only(filters.find_series_filters(_ti_dnp("C6")), "ferrite_filter")
    assert b.roles["caps_downstream"] == ["C7"] and b.roles["caps_downstream_dnp"] == ["C6"]
    assert any("downstream C total 1e-07 F" in n for n in b.notes)
    assert any("DNP options: C6 1uF (DNP)" in n for n in b.notes)


def test_i2c_pullups_are_fitted_parts_only():
    b = _only(i2c.find_i2c_buses(_ti_dnp("R8")), "i2c_bus")
    assert b.roles["pullups"] == ["R9"] and b.roles["pullups_dnp"] == ["R8"]
    assert b.roles["pullup_rails"] == ["3V3"]
    assert any("no fitted pull-up on I2C1_SCL" in n and "R8" in n for n in b.notes)
    assert not any("different rails" in n for n in b.notes)


def test_regulator_output_caps_and_bootstrap_from_fitted_parts():
    b = _only(regulators.find_switching_regulators(_ti_dnp("C3", "C2")), "switching_regulator")
    assert b.roles["output_caps"] == ["C4", "C11", "C12"] and b.roles["output_caps_dnp"] == ["C3"]
    assert "bootstrap" not in b.roles and b.roles["bootstrap_dnp"] == ["C2"]
    assert any("bootstrap" in n and "C2" in n and "DNP" in n for n in b.notes)


def test_regulator_divider_with_a_dnp_leg_is_not_a_divider():
    b = _only(regulators.find_switching_regulators(_ti_dnp("R1")), "switching_regulator")
    assert "feedback_top" not in b.roles and b.roles["feedback_top_dnp"] == ["R1"]
    assert b.roles["feedback_bottom"] == ["R2"]
    assert not any(e.startswith("divider") for e in b.evidence)
    assert any("no fitted top or bottom leg" in n for n in b.notes)


def test_reset_pullup_and_delay_cap_from_fitted_parts():
    found = resets.find_reset_nets(_ti_dnp("R5", "C10"))
    b = next(x for x in found if x.roles["net"] == ["NRST"])
    assert "pullups" not in b.roles and b.roles["pullups_dnp"] == ["R5"]
    assert "delay_caps" not in b.roles and b.roles["delay_caps_dnp"] == ["C10"]


def test_crystal_load_caps_from_fitted_parts():
    b = _only(clocks.find_clocks(_ti_dnp("C8")), "crystal")
    assert b.roles["load_caps"] == ["C9"] and b.roles["load_caps_dnp"] == ["C8"]
    assert any("no fitted load cap" in n for n in b.notes)


@pytest.mark.parametrize("loader", [_ti, _mps, _adi])
def test_block_dicts_are_json_ready(loader):
    import json
    for b in blocks.find_all(loader()):
        json.dumps(b.to_dict())
