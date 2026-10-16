"""Power blocks: filter direction, KiCad pin markup, shield beads, fixed-output feedback, LDOs and load switches."""

import pytest

from boardreview import blocks
from boardreview.blocks import filters, linear, regulators
from boardreview.model import naming
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph


def _board(rows, values=None, mpn=None, desc=None, dnp=(), kinds=None):
    """Model from (ref, pin, net, pin_name) rows."""
    m = BoardModel(pin_list_complete=True)
    for ref, pin, net, name in rows:
        m.add_pin(ref, pin, net, name)
    for ref, text in (desc or {}).items():
        m.component(ref).description = text
    for ref, text in (mpn or {}).items():
        m.component(ref).mpn = text
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


def _buck(ctrl, ind, vin, sw, out, vin_name="VIN", extra=()):
    rows = [(ctrl, "1", vin, vin_name), (ctrl, "2", sw, "SW"), (ctrl, "3", "GND", "GND"),
            (ctrl, "4", f"{out}_FB", "FB"), *extra]
    rows += _two(ind, sw, out) + _two(f"C{ctrl}1", out, "GND") + _two(f"C{ctrl}2", out, "GND")
    rows += _two(f"R{ctrl}1", out, f"{out}_FB") + _two(f"R{ctrl}2", f"{out}_FB", "GND")
    return rows


@pytest.mark.parametrize("pin, role", [("V_{IN}", "vin"), ("~{EN}", "en"), ("V^{+}", "vin"), ("P_{GOOD}", "pg"),
                                       ("~{RESET}", "reset"), ("V_{FB}", "fb")])
def test_kicad_pin_markup_is_normalized_before_roles(pin, role):
    assert naming.pin_is(pin, role)


def test_regulator_input_found_from_subscript_pin_names():
    extra = [("U6", "5", "5V_COMP", "COMP"), ("U6", "6", "5V_FSW", "F_{SW}"), ("U6", "7", "5V_MODE", "MODE"),
             ("U6", "8", "VDD_5V", "V_{DD}"), ("U6", "9", "5V_VIN", "V_{IN}")]
    rows = _buck("U6", "L4", "5V_VIN", "5V_SW", "5V0_SYS", vin_name="V_{IN}", extra=extra)
    rows += _two("C9", "5V_VIN", "GND") + _two("C8", "VDD_5V", "GND")
    b = regulators.find_switching_regulators(Graph(_board(rows)))[0]
    assert b.roles["input"] == ["5V_VIN"]
    assert not any(n.startswith("input unknown") for n in b.notes)


def _input_bead_board():
    rows = _buck("U6", "L4", "5V_VIN", "5V_SW", "5V0_SYS", vin_name="V_{IN}")
    rows += [("U6", "5", "5V_VIN", "V_{IN}")]
    rows += _two("F3", "VIN_RAW", "VIN") + _two("D14", "VIN", "GND") + [("TP16", "1", "VIN", "")]
    rows += [("J1", "1", "VIN_RAW", ""), ("J1", "2", "GND", "")]
    rows += _two("FB1", "VIN", "5V_VIN") + _two("C17", "5V_VIN", "GND") + _two("C22", "5V_VIN", "GND")
    rows += _two("C56", "5V_VIN", "GND") + _two("R91", "5V_VIN", "5V_EN")
    return _board(rows, desc={"FB1": "Ferrite bead"}, kinds={"D14": "tvs"})


def test_bead_into_a_regulator_input_flows_toward_the_regulator():
    found = blocks.find_all(_input_bead_board())
    fb1 = next(b for b in found if b.roles.get("element") == ["FB1"])
    assert (fb1.roles["upstream"], fb1.roles["downstream"]) == (["VIN"], ["5V_VIN"])
    assert any("U6" in e and "input" in e for e in fb1.evidence)


def test_bead_from_a_load_switch_output_flows_toward_the_connector():
    rows = [("IC3", "1", "5V0_SYS", "IN"), ("IC3", "2", "GND", "GND"), ("IC3", "3", "USB_EN", "~{EN}"),
            ("IC3", "4", "USB_FLT", "~{FLT}"), ("IC3", "5", "GND", "GND"), ("IC3", "6", "IC3_OUT", "OUT")]
    rows += _two("C1", "5V0_SYS", "GND") + _two("C31", "IC3_OUT", "GND") + _two("L2", "IC3_OUT", "USBC_VBUS")
    rows += _two("C35", "USBC_VBUS", "GND") + _two("R51", "USBC_VBUS", "CC_DET") + _two("R131", "USBC_VBUS", "GND")
    rows += [("J11", p, "USBC_VBUS", "VBUS") for p in ("A4", "A9", "B4", "B9")]
    found = blocks.find_all(_board(rows, desc={"L2": "Ferrite bead"}))
    l2 = next(b for b in found if b.roles.get("element") == ["L2"])
    assert (l2.roles["upstream"], l2.roles["downstream"]) == (["IC3_OUT"], ["USBC_VBUS"])
    sw = next(b for b in found if b.kind == "load_switch")
    assert sw.roles["device"] == ["IC3"] and sw.roles["input"] == ["5V0_SYS"] and sw.roles["output"] == ["IC3_OUT"]


def test_bead_from_a_usb_connector_flows_toward_the_ic_supply_pins():
    rows = _two("L3", "5V0_DBG", "USB_DBG_VBUS") + [("J9", "1", "USB_DBG_VBUS", "VBUS"), ("J9", "5", "GND", "GND")]
    rows += _two("C67", "5V0_DBG", "GND") + _two("C72", "5V0_DBG", "GND") + _two("D17", "5V0_DBG", "5V0_SYS")
    rows += [("IC5", "19", "5V0_DBG", "VCC"), ("IC5", "4", "GND", "GND")]
    found = blocks.find_all(_board(rows, desc={"L3": "Ferrite bead"}))
    l3 = next(b for b in found if b.roles.get("element") == ["L3"])
    assert (l3.roles["upstream"], l3.roles["downstream"]) == (["USB_DBG_VBUS"], ["5V0_DBG"])


@pytest.mark.parametrize("a, b", [("USB_SHIELD", "CHASSIS"), ("GND", "HDMI_SHIELD"), ("EGND", "GND")])
def test_beads_between_ground_or_shield_nets_are_not_power_filters(a, b):
    rows = _two("L7", a, b) + _two("C14", a, "GND") + _two("C15", b, "GND")
    assert filters.find_series_filters(Graph(_board(rows, desc={"L7": "Ferrite bead"}))) == []


def _fixed_buck(mpn=""):
    rows = [("U2", "8", "3V3_VIN", "VIN"), ("U2", "10", "3V3_SW", "SW"), ("U2", "3", "GND", "GND"),
            ("U2", "4", "3V3_FB", "FB"), ("U2", "1", "3V3_SYS", "VOUT")]
    rows += _two("L1", "3V3_SW", "3V3_SYS") + _two("C9", "3V3_SYS", "GND") + _two("C20", "3V3_SYS", "GND")
    rows += _two("R48", "3V3_SYS", "3V3_FB") + _two("R118", "3V3_SYS", "3V3_FB") + _two("R119", "3V3_FB", "GND")
    rows += _two("C19", "3V3_VIN", "GND")
    return _board(rows, values={"R48": "R_0R_0402", "R118": "R_100k_0402", "R119": "R_44k2_0402"},
                  mpn={"U2": mpn} if mpn else None, dnp=("R118", "R119"))


def test_fb_straight_to_the_output_is_not_a_missing_divider():
    b = regulators.find_switching_regulators(Graph(_fixed_buck()))[0]
    assert not any("no fitted top or bottom leg" in n for n in b.notes)
    assert b.roles["feedback_direct"] == ["R48"]
    note = next(n for n in b.notes if "senses the output directly" in n)
    assert "UNSURE" in note and "fixed" in note


def test_fixed_output_from_the_mpn():
    b = regulators.find_switching_regulators(Graph(_fixed_buck("LM3671MF-3.3/NOPB")))[0]
    assert b.roles["fixed_output"] == ["3.3 V from MPN LM3671MF-3.3/NOPB"]
    assert not any("UNSURE" in n and "senses the output directly" in n for n in b.notes)


def test_a_real_divider_with_a_missing_leg_still_warns():
    m = _fixed_buck()
    m.components["R48"].value = "R_100k_0402"
    b = regulators.find_switching_regulators(Graph(m))[0]
    assert any("no fitted top or bottom leg" in n for n in b.notes)


def test_ldo_found_with_input_output_and_enable():
    rows = [("IC4", "1", "5V0_SYS", "IN"), ("IC4", "2", "GND", "GND"), ("IC4", "3", "LDO_EN", "EN"),
            ("IC4", "4", None, "NC"), ("IC4", "5", "1V8_SYS", "OUT")]
    rows += _two("C5", "1V8_SYS", "GND") + _two("C65", "1V8_SYS", "GND") + _two("C1", "5V0_SYS", "GND")
    found = blocks.find_all(_board(rows))
    ldo = next(b for b in found if b.kind == "ldo")
    assert ldo.roles["device"] == ["IC4"] and ldo.roles["input"] == ["5V0_SYS"] and ldo.roles["output"] == ["1V8_SYS"]
    assert ldo.roles["enable_pins"] == ["IC4.3"] and ldo.roles["output_caps"] == ["C5", "C65"]
    assert "IC4 ldo (high): 5V0_SYS -> 1V8_SYS" in blocks.power_edges(found)


def test_unclear_pass_device_is_a_low_confidence_ldo_and_level_shifters_are_not_found():
    rows = [("U9", "1", "RAIL_A", "IN"), ("U9", "2", "GND", "GND"), ("U9", "3", "RAIL_B", "OUT")]
    rows += _two("C1", "RAIL_B", "GND") + _two("C2", "RAIL_A", "GND")
    rows += [("U3", "1", "1V8", "VCCA"), ("U3", "2", "3V3", "VCCB"), ("U3", "3", "A1", "A1"), ("U3", "4", "B1", "B1")]
    rows += _two("C3", "1V8", "GND") + _two("C4", "3V3", "GND")
    found = linear.find_linear(Graph(_board(rows)))
    assert [(b.kind, b.roles["device"], b.confidence) for b in found] == [("ldo", ["U9"], "low")]
    assert any("LDO or load switch" in n for n in found[0].notes)
