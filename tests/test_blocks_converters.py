"""Converter finder cases use synthetic parts, pin names and nets only."""

import json

import pytest

from boardreview.blocks import find_all, to_markdown
from boardreview.blocks.converters import find_converters
from boardreview.checks import checklist_items, instances, skeleton
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph


def _model(kind="ic", description="", pins=None, fitted=True):
    model = BoardModel(pin_list_complete=True)
    device = model.component("U1")
    device.kind, device.description, device.fitted = kind, description, fitted
    for index, (name, net, pin_type) in enumerate(pins or [], 1):
        model.add_pin("U1", str(index), net, name, pin_type)
    return model.finalize()


ADC_PINS = [("AINP", "INPUT_P", "input"), ("AINN", "INPUT_N", "input"),
            ("D0", "DATA0", "output"), ("D1", "DATA1", "output"),
            ("VREF", "REFERENCE", "input"), ("CLKP", "SAMPLE_P", "input"),
            ("SYSREFP", "SYSREF_P", "input"), ("VCM", "COMMON_MODE", "output"),
            ("AVDD", "AVDD", "power_in"), ("SYNC~", "SYNC_N", "output")]
DAC_PINS = [("IOUTAP", "OUT_P", "output"), ("IOUTAN", "OUT_N", "output"),
            ("DIN0", "DATA0", "input"), ("DIN1", "DATA1", "input"),
            ("REFIO", "REFERENCE", "bidirectional"), ("CLK", "SAMPLE", "input")]


def test_adc_by_part_metadata_and_pin_roles():
    model = _model(description="Synthetic 16-bit ADC", pins=ADC_PINS)
    block, = find_converters(Graph(model))
    assert block.kind == "adc" and block.confidence == "high"
    assert block.roles["device"] == ["U1"]
    assert block.roles["analog_input_pins"] == ["U1.1", "U1.2"]
    assert block.roles["digital_output_pins"] == ["U1.3", "U1.4"]
    assert block.roles["reference_nets"] == ["REFERENCE"]
    assert block.roles["clock_nets"] == ["SAMPLE_P"]
    assert block.roles["sysref_pins"] == ["U1.7"]
    assert block.roles["common_mode_nets"] == ["COMMON_MODE"]
    assert "AVDD" not in block.roles["analog_input_nets"]
    assert len(block.evidence) >= 5
    assert block.subgraph["nets"]["INPUT_P"]["block_pins"] == ["U1.1"]
    json.dumps(block.to_dict(), allow_nan=False)


def test_adc_structural_evidence_without_part_name():
    block, = find_converters(Graph(_model(pins=ADC_PINS)))
    assert block.kind == "adc" and block.confidence == "medium"
    assert any("analog input pin names" in evidence for evidence in block.evidence)


@pytest.mark.parametrize("positive,negative", [("IN+", "IN-"), ("VIN+", "VIN-"), ("VIN_A+", "VIN_A-")])
def test_differential_analog_pins_are_not_confused_with_supplies(positive, negative):
    pins = [(positive, "INPUT_P", "input"), (negative, "INPUT_N", "input"), *ADC_PINS[2:]]
    block, = find_converters(Graph(_model("adc", pins=pins)))
    assert block.roles["analog_input_pins"] == ["U1.1", "U1.2"]
    assert block.roles["supply_pins"] == ["U1.9"]


@pytest.mark.parametrize("kind,description", [("dac", ""), ("ic", "Digital-to-analog converter")])
def test_dac_by_kind_or_description(kind, description):
    block, = find_converters(Graph(_model(kind, description, DAC_PINS)))
    assert block.kind == "dac" and block.confidence == "high"
    assert block.roles["analog_output_nets"] == ["OUT_N", "OUT_P"]
    assert block.roles["digital_input_pins"] == ["U1.3", "U1.4"]


def test_dac_structural_evidence_and_parallel_input_direction():
    pins = [*DAC_PINS[:2], ("D0", "DATA0", "input"), *DAC_PINS[4:]]
    block, = find_converters(Graph(_model(pins=pins)))
    assert block.kind == "dac"
    assert "digital_output_pins" not in block.roles


@pytest.mark.parametrize("kind", ["adc", "dac"])
def test_explicit_part_with_missing_names_is_a_low_confidence_candidate(kind):
    block, = find_converters(Graph(_model(kind, pins=[("", "SIGNAL", "")], fitted=False)))
    assert block.kind == kind and block.confidence == "low"
    assert any("incomplete" in note for note in block.notes)
    assert any("DNP" in note for note in block.notes)


def test_unconnected_pins_are_kept_as_evidence():
    pins = [(name, None if name == "AINN" else net, t) for name, net, t in ADC_PINS]
    block, = find_converters(Graph(_model("adc", pins=pins)))
    assert "U1.2" in block.roles["analog_input_pins"]
    assert block.roles["analog_input_nets"] == ["INPUT_P"]


@pytest.mark.parametrize("pins", [ADC_PINS[:2], ADC_PINS[2:6], [("ADC_ENABLE", "ADC_EN", "input")],
                                 [("VIN", "VIN", "power_in"), ("VOUT", "VOUT", "power_out"),
                                  ("SCLK", "SCLK", "input"), ("SDO", "SDO", "output")]])
def test_generic_ic_without_corroborating_roles_is_not_a_converter(pins):
    assert find_converters(Graph(_model(pins=pins))) == []


def test_connector_is_not_inferred_from_converter_net_or_pin_names():
    assert find_converters(Graph(_model("connector", "ADC cable", ADC_PINS))) == []


def test_mixed_converter_has_both_candidate_kinds():
    model = _model("transceiver", "ADC and DAC transceiver", ADC_PINS + DAC_PINS)
    assert {block.kind for block in find_converters(Graph(model))} == {"adc", "dac"}


def test_finder_registration_preserves_other_blocks_and_renders_converters():
    model = _model("adc", pins=ADC_PINS)
    model.component("Y1").kind = "crystal"
    model.add_pin("Y1", "1", "XTAL_A")
    model.add_pin("Y1", "2", "XTAL_B")
    model.add_pin("U2", "1", "XTAL_A", "XI")
    model.add_pin("U2", "2", "XTAL_B", "XO")
    blocks = find_all(model)
    assert {block.kind for block in blocks} >= {"adc", "crystal"}
    assert "U1 ADC" in to_markdown(blocks)
    assert "Y1 crystal" in to_markdown(blocks)
    assert len([block for block in blocks if block.kind == "adc"]) == 1


def test_converter_blocks_produce_per_device_checklist_entries():
    blocks = [b.to_dict() for b in find_all(_model("adc", pins=ADC_PINS))]
    assert ("data_converters", "U1 ADC", "U1") in instances(blocks)
    rows = [row for row in skeleton(blocks, checklist_items()) if row["block"] == "data_converters"]
    assert [row["item"] for row in rows] == [f"ADC-{n}" for n in range(1, 12)]
    assert all(row["instance"] == "U1 ADC" for row in rows)
