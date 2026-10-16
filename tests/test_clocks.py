"""Synthetic clock-buffer, PLL and jitter-cleaner netlists."""

import pytest

from boardreview import blocks
from boardreview.blocks.clocks import find_clocks
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph


def _model(names, kind="ic", description=""):
    model = BoardModel(pin_list_complete=True)
    for number, (name, net) in enumerate(names, 1):
        model.add_pin("U1", str(number), net, name)
    model.component("U1").kind = kind
    model.component("U1").description = description
    return model


@pytest.mark.parametrize("kind,description", [("clock_buffer", ""), ("ic", "Differential clock fanout buffer")])
def test_clock_buffer_by_kind_or_description(kind, description):
    model = _model([("IN_P","REF_P"),("IN_N","REF_N"),("Q0_P","CLK0_P"),("Q0_N","CLK0_N"),
                    ("Q1_P","CLK1_P"),("Q1_N","CLK1_N"),("VDD","3V3"),("GND","GND"),
                    ("OE","ENABLE"),("Q2",None)], kind, description)
    model.add_pin("U2", "1", "CLK0_P", "CLKIN")
    found = find_clocks(Graph(model))
    assert len(found) == 1
    b = found[0]
    assert b.kind == "clock_buffer" and b.confidence == "high"
    assert b.roles["output"] == ["CLK0_N", "CLK0_P", "CLK1_N", "CLK1_P"]
    assert b.roles["input"] == ["REF_N","REF_P"]
    assert "U1.10" in b.roles["output_pins"]
    assert b.roles["loads"] == ["U2.1"]


def test_clock_buffer_by_explicit_clock_pin_roles_and_no_vendor_name():
    model = _model([("CLKIN","REF"),("CLKOUT0","OUT_A"),("CLKOUT1","OUT_B"),("VCC","3V3")])
    b = find_clocks(Graph(model))[0]
    assert b.kind == "clock_buffer"
    assert b.roles["input_pins"] == ["U1.1"]


@pytest.mark.parametrize("description,kind", [("PLL frequency synthesizer", "pll"),
                                             ("Jitter attenuator", "jitter_cleaner"),
                                             ("Jitter cleaner", "jitter_cleaner")])
def test_integrated_clock_loop_has_no_external_pump(description, kind):
    model = _model([("REFIN_P","REF_P"),("REFIN_N","REF_N"),("CLKOUT0_P","CLK_P"),
                    ("CLKOUT0_N","CLK_N"),("LOL","LOCK_STATUS"),("VDD","1V8")], description=description)
    b = find_clocks(Graph(model))[0]
    assert b.kind == kind and b.roles["lock_pins"] == ["U1.5"]
    assert any("loop may be internal" in n for n in b.notes)
    assert b.roles["reference_pins"] == ["U1.1", "U1.2"]


def test_pll_by_pump_and_reference_roles_with_loop_filter_and_dnp():
    model = _model([("REFIN","REF"),("CP_OUT","PUMP"),("VTUNE","TUNE"),("RFOUTA_P","LO_P"),
                    ("RFOUTA_N","LO_N"),("FBCLKIN","FEEDBACK"),("VDD","3V3"),("GND","GND")])
    for ref, a, b in [("C1","PUMP","GND"),("R2","PUMP","CAP2"),("C2","CAP2","GND"),
                       ("R3","PUMP","TUNE"),("C3","TUNE","GND"),("C9","3V3","GND")]:
        model.add_pin(ref,"1",a)
        model.add_pin(ref,"2",b)
    model.component("C3").fitted = False
    b = find_clocks(Graph(model))[0]
    assert b.kind == "pll" and b.confidence == "high"
    assert b.roles["loop_filter_parts"] == ["C1","C2","R2","R3"]
    assert b.roles["loop_filter_parts_dnp"] == ["C3"]
    assert b.roles["loop_filter_nets"] == ["CAP2","PUMP","TUNE"]
    assert b.roles["feedback_pins"] == ["U1.6"]
    assert b.roles["bypass_caps"] == ["C9"]
    assert any("C3" in n and "DNP" in n for n in b.notes)


@pytest.mark.parametrize("kind", ["pll", "jitter_cleaner", "clock_generator"])
def test_explicit_part_kind_with_missing_pin_names_is_kept_as_candidate(kind):
    model = _model([("","A"),("","B")], kind=kind)
    b = find_clocks(Graph(model))[0]
    assert b.kind == ("pll" if kind == "clock_generator" else kind)
    assert b.confidence == "low" and any("no connected output" in n for n in b.notes)


def test_generic_logic_and_clock_consumers_are_not_clock_buffers():
    for names in [[("IN","A"),("OUT","B"),("VCC","3V3")],
                  [("CLKIN","CLK"),("DATA","D"),("VDD","3V3")]]:
        assert find_clocks(Graph(_model(names))) == []


def test_dnp_buffer_and_series_resistor_are_reported():
    model = _model([("CLKIN","REF"),("CLKOUT0","SOURCE"),("VCC","3V3")])
    model.component("U1").fitted = False
    model.add_pin("R1","1","SOURCE")
    model.add_pin("R1","2","SINK")
    model.component("R1").fitted = False
    model.add_pin("U2","1","SINK","CLKIN")
    b = find_clocks(Graph(model))[0]
    assert b.roles["series_resistors_dnp"] == ["R1"]
    assert any("U1 is DNP" in n for n in b.notes)


def test_new_clock_blocks_reach_find_all_and_markdown():
    model = _model([("CLKIN","REF"),("CLKOUT0","OUT"),("VCC","3V3")])
    found = blocks.find_all(model)
    assert any(b.kind == "clock_buffer" for b in found)
    assert "U1 clock buffer" in blocks.to_markdown(found)


def test_existing_crystal_and_oscillator_still_found_alongside_pll():
    model = _model([("REFIN","REF"),("CP","PUMP"),("RFOUTA","LO"),("VDD","3V3")])
    model.add_pin("Y1","1","XTALA")
    model.add_pin("Y1","2","XTALB")
    for pin,name,net in [("1","OE","3V3"),("2","GND","GND"),("3","OUT","REF"),("4","VDD","3V3")]:
        model.add_pin("Y2",pin,net,name)
    model.component("Y2").kind = "oscillator"
    found = find_clocks(Graph(model))
    assert [b.kind for b in found] == ["pll","crystal","oscillator"]


def test_oscillator_sees_explicitly_typed_clock_buffer_load():
    model = _model([("IN","REFERENCE"),("OUT","CLOCK"),("VCC","3V3")], kind="clock_buffer")
    for number,name,net in [("1","OE","3V3"),("2","GND","GND"),("3","OUT","REFERENCE"),("4","VDD","3V3")]:
        model.add_pin("Y2",number,net,name)
    model.component("Y2").kind = "oscillator"
    oscillator = next(b for b in find_clocks(Graph(model)) if b.kind == "oscillator")
    assert oscillator.roles["output"] == ["REFERENCE"] and oscillator.roles["loads"] == ["U1.1"]
