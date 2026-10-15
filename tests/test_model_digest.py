from pathlib import Path

from boardreview.model import digest, kicad
from boardreview.model.graph import Graph

FIX = Path(__file__).parent / "fixtures" / "model"


def _model():
    return kicad.read_kicad_xml(FIX / "ti_buck_board.kicad.xml")


def test_nets_by_net_lists_every_net_and_open_pins():
    text = digest.nets_by_net(_model())
    assert ("**+3V3** (17): C3.1, C4.1, C5.1, C11.1, C12.1, FB1.1, J2.1, L1.2, R1.1, R5.1, R7.1, R8.1, R10.2, "
            "R11.1, U2.1, U3.3, U4.5") in text
    assert "**3V3** (1): R9.1" in text
    assert "- U2: 10 (PA5), 14 (PA12), 15 (VSS)" in text
    assert "- D2: 3 (GND)" in text


def test_nets_by_component_marks_dnp_and_pin_names():
    text = digest.nets_by_component(_model())
    assert "## R7 (resistor, 10k, RC0402FR-0710KL, DNP)" in text
    assert "- 2 (SW): SW" in text
    assert "- 15 (VSS): (no net)" in text


def test_graph_rail_evidence_by_name_and_by_structure():
    g = Graph(_model())
    rails = g.rails()
    assert rails["+3V3"][0] == "name" and "3V3A" in rails
    assert "SW" not in rails and "/FB_3V3" not in rails and "NRST" not in rails
    assert g.caps_to_ground("3V3A") == ["C6", "C7"]
    assert g.other_net("FB1", "+3V3") == "3V3A"


def test_power_tree_shows_rails_links_and_grounds():
    text = digest.power_tree(_model(), edges=["U1 buck: VIN -> +3V3 via L1"])
    assert "## Converters and switches found by blocks" in text and "U1 buck: VIN -> +3V3 via L1" in text
    assert "## +3V3 (3.3 V by name)" in text
    assert "FB1 (ferrite, 220R@100MHz, BLM18PG221SN1D) to 3V3A" in text
    assert "## GND (ground)" in text
    assert text.index("## +3V3") < text.index("## GND")


def test_power_tree_lists_dnp_caps_apart_from_fitted_caps():
    m = _model()
    m.components["C6"].fitted = False
    text = digest.power_tree(m)
    section = text[text.index("## 3V3A"):]
    assert "- caps to ground (1): C7" in section and "- DNP caps to ground (1): C6" in section


def test_pin_map_and_write_digests(tmp_path):
    m = _model()
    pm = digest.pin_map(m, "U1")
    assert "| 2 | SW | power_out | SW | C2, L1 |" in pm
    written = digest.write_digests(m, tmp_path)
    names = {p.relative_to(tmp_path).as_posix() for p in written}
    assert {"nets_by_net.md", "nets_by_component.md", "power_tree.md", "pinmaps/U1.md", "pinmaps/U2.md"} <= names
    assert "pinmaps/R1.md" not in names
