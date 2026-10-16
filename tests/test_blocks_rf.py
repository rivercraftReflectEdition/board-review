"""Synthetic RF netlists exercise evidence, topology, variants and finder integration."""

import json

import pytest

from boardreview import blocks
from boardreview.blocks import rf
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph


def _board(rows, kinds=None, text=None, values=None, dnp=()):
    model = BoardModel(pin_list_complete=True)
    for ref, number, net, name in rows:
        model.add_pin(ref, str(number), net, name)
    for ref, description in (text or {}).items():
        model.component(ref).description = description
    for c in model.components.values():
        c.classify()
    for ref, kind in (kinds or {}).items():
        model.component(ref).kind = kind
    for ref, value in (values or {}).items():
        model.component(ref).value = value
    for ref in dnp:
        model.component(ref).fitted = False
    return model.finalize()


def _two(ref, a, b):
    return [(ref, 1, a, ""), (ref, 2, b, "")]


def _only(found):
    assert len(found) == 1
    return found[0]


def _balun():
    return [("T1", 1, "n1", "UNBAL"), ("T1", 2, "n2", "BAL+"),
            ("T1", 3, "n3", "BAL-"), ("T1", 4, "bias", "DC_FEED"), ("T1", 5, "GND", "GND")]


def _switch():
    return [("U1", 1, "n1", "RFC"), ("U1", 2, "n2", "RF1"), ("U1", 3, "n3", "RF2"),
            ("U1", 4, "3V3", "VDD"), ("U1", 5, "select", "CTRL"), ("U1", 6, "GND", "GND")]


def _amp():
    return [("U2", 1, "n4", "RF_IN"), ("U2", 2, "n5", "RF_OUT"),
            ("U2", 3, "3V3", "VDD"), ("U2", 4, "GND", "GND")]


def test_balun_pin_roles_and_feed_bypass():
    model = _board(_balun() + _two("C1", "bias", "GND"), text={"T1": "RF balun"})
    b = _only(rf.find_baluns(Graph(model)))
    assert b.kind == "balun" and b.confidence == "high"
    assert b.roles["unbalanced"] == ["n1"] and b.roles["balanced"] == ["n2", "n3"]
    assert b.roles["dc_feed_pins"] == ["T1.4"] and b.roles["bypass_caps"] == ["C1"]
    assert b.subgraph["nets"]["bias"]["block_pins"] == ["C1.1", "T1.4"]


def test_balun_roles_work_without_transformer_kind_or_part_text():
    model = _board(_balun(), kinds={"T1": "other"})
    b = _only(rf.find_baluns(Graph(model)))
    assert b.confidence == "medium"
    assert b.roles["signal_nets"] == ["n1", "n2", "n3"]


def test_transformer_three_signal_topology_stays_low_confidence():
    rows = [("T1", 1, "a", ""), ("T1", 2, "b", ""), ("T1", 3, "c", ""), ("T1", 4, "GND", "")]
    b = _only(rf.find_baluns(Graph(_board(rows))))
    assert b.confidence == "low" and "balanced" not in b.roles
    assert any("winding" in e for e in b.evidence)


def test_four_terminal_isolated_transformer_is_not_automatically_a_balun():
    rows = [("T1", i, net, "") for i, net in enumerate(("a", "b", "c", "d"), 1)]
    assert rf.find_baluns(Graph(_board(rows))) == []


def test_explicit_balun_with_missing_pin_names_is_preserved():
    model = _board([("X1", 1, "a", ""), ("X1", 2, None, "")], kinds={"X1": "balun"}, dnp=["X1"])
    b = _only(rf.find_baluns(Graph(model)))
    assert b.confidence == "medium"
    assert any("DNP" in n for n in b.notes)


def test_switch_by_roles_preserves_block_caps_discharge_and_negative_supply():
    rows = _switch() + [("U1", 7, "-3V3", "VEE")]
    rows += _two("C1", "n1", "external") + _two("R1", "n1", "GND") + _two("C2", "3V3", "GND")
    rows += _two("C3", "n2", "external2")
    b = _only(rf.find_rf_switches(Graph(_board(rows, dnp=["C3"]))))
    assert b.confidence == "medium"
    assert b.roles["rf_ports"] == ["n1", "n2", "n3"]
    assert b.roles["control_pins"] == ["U1.5"] and b.roles["control_nets"] == ["select"]
    assert set(b.roles["supply"]) == {"3V3", "-3V3"}
    assert b.roles["dc_blocks"] == ["C1"] and b.roles["dc_blocks_dnp"] == ["C3"]
    assert b.roles["shunt_resistors"] == ["R1"] and b.roles["bypass_caps"] == ["C2"]


@pytest.mark.parametrize("kind,description", [("rf_switch", ""), ("ic", "SPDT RF switch")])
def test_switch_part_kind_or_vendor_neutral_text(kind, description):
    b = _only(rf.find_rf_switches(Graph(_board(_switch(), kinds={"U1": kind}, text={"U1": description}))))
    assert b.confidence == "high"


def test_named_switch_without_port_names_remains_a_candidate():
    rows = [("U1", 1, "a", ""), ("U1", 2, "b", ""), ("U1", 3, "3V3", "VDD"),
            ("U1", 4, "control", "SEL"), ("U1", 5, "GND", "GND")]
    b = _only(rf.find_rf_switches(Graph(_board(rows, text={"U1": "SOI switch"}))))
    assert b.roles["rf_ports"] == ["a", "b"] and b.confidence == "medium"


def test_digital_mux_and_load_switch_do_not_become_rf_switches():
    rows = [("U1", i, net, name) for i, (net, name) in enumerate(
        [("a", "A"), ("b", "B"), ("select", "SEL"), ("3V3", "VDD"), ("GND", "GND")], 1)]
    rows += [("U2", 1, "5V", "VIN"), ("U2", 2, "5V_LOAD", "OUT"), ("U2", 3, "on", "EN")]
    assert rf.find_rf_switches(Graph(_board(rows, text={"U1": "digital mux", "U2": "load switch"}))) == []


def test_amplifier_rf_roles_with_bias_choke_and_bypass():
    rows = _amp() + _two("L1", "n5", "3V3") + _two("C1", "3V3", "GND") + _two("C2", "n4", "source")
    b = _only(rf.find_rf_amplifiers(Graph(_board(rows, text={"U2": "MMIC"}))))
    assert b.confidence == "high" and b.roles["input"] == ["n4"] and b.roles["output"] == ["n5"]
    assert b.roles["bias_chokes"] == ["L1"] and b.roles["dc_blocks"] == ["C2"]
    assert b.roles["bypass_caps"] == ["C1"]


def test_rf_named_ports_without_part_description_are_medium_confidence():
    b = _only(rf.find_rf_amplifiers(Graph(_board(_amp()))))
    assert b.confidence == "medium"


def test_generic_in_out_names_need_rf_part_evidence():
    rows = [("U2", 1, "a", "IN"), ("U2", 2, "b", "OUT"), ("U2", 3, "3V3", "VDD")]
    assert rf.find_rf_amplifiers(Graph(_board(rows, text={"U2": "operational amplifier"}))) == []
    b = _only(rf.find_rf_amplifiers(Graph(_board(rows, text={"U2": "low noise amplifier"}))))
    assert b.roles["input"] == ["a"] and b.confidence == "medium"


def test_rf_transistor_requires_rf_description():
    rows = [("Q1", 1, "gate", "G"), ("Q1", 2, "drain", "D"), ("Q1", 3, "GND", "S")]
    assert rf.find_rf_amplifiers(Graph(_board(rows))) == []
    b = _only(rf.find_rf_amplifiers(Graph(_board(rows, text={"Q1": "GaN RF amplifier"}))))
    assert b.roles["input_pins"] == ["Q1.1"] and b.roles["output_pins"] == ["Q1.2"]


def test_transceiver_with_multiple_ports_or_serial_control_is_not_generic_amplifier():
    rows = _amp() + [("U2", 5, "spi", "SDI")]
    assert rf.find_rf_amplifiers(Graph(_board(rows))) == []
    rows = _amp() + [("U2", 5, "other_input", "RFIN+")]
    assert rf.find_rf_amplifiers(Graph(_board(rows))) == []


def _pi(a="ANT_IN", b="RF_OUT"):
    return _two("R1", a, "GND") + _two("R2", a, b) + _two("R3", b, "GND")


def test_w29_fitted_pi_pad_topology_and_values():
    # Plan W29: rounded 6 dB pi, two 150 ohm shunts and one 37.4 ohm series.
    model = _board(_pi(), values={"R1": "150", "R2": "37.4", "R3": "150"})
    b = _only(rf.find_attenuator_pads(Graph(model)))
    assert b.kind == "attenuator_pad" and b.confidence == "high"
    assert b.roles["series_resistors"] == ["R2"] and b.roles["shunt_resistors"] == ["R1", "R3"]
    assert b.roles["ports"] == ["ANT_IN", "RF_OUT"]
    assert b.subgraph["components"]["R2"]["value_si"] == pytest.approx(37.4, abs=1e-10)
    assert b.subgraph["components"]["R1"]["value_si"] == pytest.approx(150, abs=1e-10)


def test_w29_t_pad_and_rf_class_on_unnamed_nets():
    # Plan W29: ideal 6 dB T has about 16.61 ohm series arms, 66.93 ohm shunt.
    rows = _two("R1", "a", "center") + _two("R2", "center", "b") + _two("R3", "center", "GND")
    model = _board(rows, values={"R1": "16.61", "R2": "16.61", "R3": "66.93"})
    model.set_net_info("a", **{"class": "RF50"})
    b = _only(rf.find_attenuator_pads(Graph(model)))
    assert b.confidence == "high" and " T pad" in b.name
    assert b.roles["series_resistors"] == ["R1", "R2"] and b.roles["middle"] == ["center"]
    assert b.roles["shunt_resistors"] == ["R3"]
    assert b.subgraph["components"]["R3"]["value_si"] == pytest.approx(66.93, abs=1e-10)


@pytest.mark.parametrize("values,confidence", [(None, "low"), ({"R1": "150", "R2": "37.4", "R3": "150"}, "medium")])
def test_pad_topology_without_rf_names_stays_a_candidate(values, confidence):
    b = _only(rf.find_attenuator_pads(Graph(_board(_pi("a", "b"), values=values))))
    assert b.confidence == confidence


@pytest.mark.parametrize("a,b,values", [("3V3", "node", None), ("a", "b", {"R2": "0R"}),
                                        ("a", "a", None)])
def test_supply_dividers_zero_ohm_links_and_shorted_ports_are_not_pads(a, b, values):
    assert rf.find_attenuator_pads(Graph(_board(_pi(a, b), values=values))) == []


def test_t_center_with_active_load_is_not_an_isolated_pad():
    rows = _two("R1", "a", "center") + _two("R2", "center", "b") + _two("R3", "center", "GND")
    rows += [("U1", 1, "center", "FB")]
    assert rf.find_attenuator_pads(Graph(_board(rows))) == []


def test_dnp_pad_is_visible_with_fitted_state_and_note():
    b = _only(rf.find_attenuator_pads(Graph(_board(_pi(), dnp=["R2"]))))
    assert b.subgraph["components"]["R2"]["fitted"] is False
    assert any("DNP" in n and "R2" in n for n in b.notes)


@pytest.mark.parametrize("description", ["SMA", "U.FL", "coaxial connector", "I-PEX antenna connector"])
def test_rf_connector_family_names_are_vendor_neutral(description):
    rows = [("J1", 1, "a", "SIGNAL"), ("J1", 2, "GND", "SHIELD"), ("J1", 3, "GND", "SHIELD")]
    b = _only(rf.find_rf_connectors(Graph(_board(rows, text={"J1": description}))))
    assert b.confidence == "high" and b.roles["rf_ports"] == ["a"]
    assert b.roles["shield_pins"] == ["J1.2", "J1.3"]


def test_antenna_feed_without_shield_and_dnp_option():
    model = _board([("E1", 1, "ANT", "FEED")], kinds={"E1": "antenna_feed"}, dnp=["E1"])
    b = _only(rf.find_rf_connectors(Graph(model)))
    assert b.confidence == "medium" and "shield" not in b.roles
    assert any("return path" in n for n in b.notes) and any("DNP" in n for n in b.notes)


def test_unnamed_single_signal_with_shield_is_low_confidence():
    rows = [("J1", 1, "a", ""), ("J1", 2, "GND", ""), ("J1", 3, "GND", "")]
    b = _only(rf.find_rf_connectors(Graph(_board(rows))))
    assert b.confidence == "low" and any("header" in n for n in b.notes)


def test_power_connector_and_multisignal_header_are_not_rf_candidates():
    rows = [("J1", 1, "3V3", ""), ("J1", 2, "GND", ""), ("J2", 1, "a", ""),
            ("J2", 2, "b", ""), ("J2", 3, "GND", ""), ("J3", 1, "logic", ""), ("J3", 2, "GND", "")]
    assert rf.find_rf_connectors(Graph(_board(rows))) == []


def test_antenna_pin_role_identifies_unnamed_two_pin_feed():
    rows = [("J1", 1, "a", "ANT"), ("J1", 2, "GND", "")]
    b = _only(rf.find_rf_connectors(Graph(_board(rows))))
    assert b.roles["rf_ports"] == ["a"] and b.confidence == "low"


def test_find_all_registration_markdown_serialization_and_strap_exclusion():
    rows = _switch() + _amp() + _balun() + _pi()
    rows += [("J1", 1, "ANT_IN", "RF"), ("J1", 2, "GND", "GND")]
    rows += _two("R9", "n2", "GND")
    model = _board(rows, text={"J1": "SMA", "U1": "RF switch", "U2": "LNA", "T1": "balun"})
    found = blocks.find_all(model)
    expected = {"balun", "rf_switch", "rf_amplifier", "attenuator_pad", "rf_connector"}
    assert expected <= {b.kind for b in found}
    assert all(b.roles.get("net") != ["n2"] for b in found if b.kind == "strap")
    rendered = blocks.to_markdown(found)
    for kind in expected:
        assert f"## {kind.replace('_', ' ')}" in rendered
    assert json.loads(json.dumps([b.to_dict() for b in found]))


def test_empty_graph_and_insertion_order_are_stable():
    assert rf.find_rf(Graph(BoardModel())) == []
    rows = _switch() + _amp() + _pi()
    first = rf.find_rf(Graph(_board(rows)))
    second = rf.find_rf(Graph(_board(list(reversed(rows)))))
    assert [b.to_dict() for b in first] == [b.to_dict() for b in second]


def test_power_in_ground_pin_does_not_hide_pad_shunts():
    model = _board(_pi(), values={"R1": "150", "R2": "37.4", "R3": "150"})
    model.add_pin("U9", "1", "GND", "GND", type="power_in")
    b = _only(rf.find_attenuator_pads(Graph(model)))
    assert b.roles["shunt_resistors"] == ["R1", "R3"]


def test_switch_zero_port_and_voltage_control_pin_names():
    rows = [("U1", 1, "a", "RF0"), ("U1", 2, "b", "RF1"), ("U1", 3, "c", "RF2"),
            ("U1", 4, "select", "V1"), ("U1", 5, "GND", "GND")]
    b = _only(rf.find_rf_switches(Graph(_board(rows))))
    assert b.roles["rf_ports"] == ["a", "b", "c"] and b.roles["control_pins"] == ["U1.4"]


def test_mixer_with_lo_pin_does_not_become_amplifier():
    rows = _amp() + [("U2", 5, "osc", "LO")]
    assert rf.find_rf_amplifiers(Graph(_board(rows))) == []


def test_no_connect_and_nc_pins_do_not_become_switch_ports():
    rows = [("U1", 1, "a", ""), ("U1", 2, "b", ""), ("U1", 3, "unused", "NC1")]
    model = _board(rows, kinds={"U1": "rf_switch"})
    model.add_pin("U1", "4", "unfitted", "", no_connect=True)
    b = _only(rf.find_rf_switches(Graph(model)))
    assert b.roles["rf_ports"] == ["a", "b"]


def test_connector_family_in_cad_footprint_is_recognized():
    rows = [("J1", 1, "a", ""), ("J1", 2, "GND", "")]
    model = _board(rows)
    model.component("J1").footprint = "Connector_Coaxial:U.FL_Generic"
    b = _only(rf.find_rf_connectors(Graph(model)))
    assert b.confidence == "high"


def test_ambiguous_resistor_topology_does_not_hide_existing_strap_candidates():
    rows = _pi("a", "b") + [("U9", 1, "a", "CONFIG"), ("U9", 2, "b", "MODE")]
    model = _board(rows, values={"R1": "100k", "R2": "10k", "R3": "100k"})
    found = blocks.find_all(model)
    pad = _only([b for b in found if b.kind == "attenuator_pad"])
    assert pad.confidence == "medium"
    assert {b.roles["net"][0] for b in found if b.kind == "strap"} == {"a", "b"}
