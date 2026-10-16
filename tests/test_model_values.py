"""KiCad library-style values (C_10u_0603, R_52k3_0402, FB_120Z_3A_...) parse to SI values."""

import pytest

from boardreview.__main__ import main
from boardreview.model import parts, serialize
from boardreview.model.board import BoardModel


@pytest.mark.parametrize("text, kind, value", [
    ("C_10u_0603", "capacitor", 10e-6), ("C_100n_50V_0402", "capacitor", 100e-9),
    ("C_1n2_50V_0402", "capacitor", 1.2e-9), ("C_6p_0402", "capacitor", 6e-12),
    ("C_10u_1206_50V", "capacitor", 10e-6), ("C_Pol_330u_6.3V_KEMET-T520-B", "capacitor", 330e-6),
    ("R_52k3_0402", "resistor", 52.3e3), ("R_0R_0402", "resistor", 0.0), ("R_3R3_0402", "resistor", 3.3),
    ("R_1M_0402", "resistor", 1e6), ("R_8k66_0402", "resistor", 8.66e3), ("R_100R_0402", "resistor", 100.0),
    ("L_2u2_1.6A_1210", "inductor", 2.2e-6), ("L_3u3_9.2A_Vishay-IHLP-3232DZ-01", "inductor", 3.3e-6),
    ("FB_120Z_3A_Murata-BLM18SG_0603", "ferrite", 120.0), ("FB_10Z_10A_WE-MPSB_1206", "ferrite", 10.0),
])
def test_library_style_values_parse(text, kind, value):
    assert parts.value_si(text, kind) == pytest.approx(value)


@pytest.mark.parametrize("text, kind", [
    ("C_0603", "capacitor"), ("C_10u_0603", "resistor"), ("R_52k3_0402", "capacitor"), ("L_2u2_1210", "capacitor"),
    ("FB_120Z_3A", "inductor"), ("C_DNP_0402", "capacitor"), ("U_10k", "resistor"), ("SYN5V-BUCK", "ic"),
])
def test_package_and_rating_tokens_never_become_values(text, kind):
    assert parts.value_si(text, kind) is None


def test_the_original_value_text_is_kept(tmp_path):
    m = BoardModel(pin_list_complete=True)
    m.add_pin("C1", "1", "VIN")
    m.add_pin("C1", "2", "GND")
    m.component("C1").value = "C_10u_0603"
    m.finalize()
    data = serialize.to_dict(m)["components"][0]
    assert data["value"] == "C_10u_0603" and data["value_si"] == pytest.approx(10e-6)


def test_prep_facts_count_parsed_and_unparsed_values(tmp_path):
    m = BoardModel(pin_list_complete=True)
    values = {"C1": "C_10u_0603", "C2": "C_100n_0402", "R1": "R_52k3_0402", "L1": "L_2u2_1.6A_1210",
              "FB1": "FB_120Z_3A_0603", "R2": "see note", "C3": "C_DNP_0402", "U1": "SYN-LDO"}
    for i, (ref, value) in enumerate(values.items()):
        m.add_pin(ref, "1", f"N{i}")
        m.add_pin(ref, "2", "GND")
        m.component(ref).value = value
    m.finalize()
    src = tmp_path / "model.json"
    serialize.write_json(m, src)
    assert main(["prep", str(src), "--out", str(tmp_path / "facts")]) == 0
    facts = (tmp_path / "facts" / "facts.md").read_text(encoding="utf-8")
    assert "## Values" in facts
    assert "5 of 7 passive values parsed" in facts
    assert "C_10u_0603 = 10 µF (C1)" in facts and "R_52k3_0402 = 52.3 kΩ (R1)" in facts
    assert "not parsed: C_DNP_0402 (C3), see note (R2)" in facts
