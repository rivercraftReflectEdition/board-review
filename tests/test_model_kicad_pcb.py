from boardreview import schema
from boardreview.model import compare, kicad_pcb, loaders, serialize
from boardreview.model.board import BoardModel

KICAD9_PCB = """(kicad_pcb
\t(version 20241229)
\t(generator "pcbnew")
\t(generator_version "9.0")
\t(net 0 "")
\t(net 1 "GND")
\t(net 2 "/Sensors/I2C_SDA")
\t(net 3 "unconnected-(U1-NC-Pad4)")
\t(footprint "Package_SO:SOIC-8"
\t\t(layer "F.Cu")
\t\t(at 100.5 80.25 90)
\t\t(property "Reference" "U1" (at 0 0 0) (layer "F.SilkS"))
\t\t(property "Value" "TMP117" (at 0 0 0) (layer "F.Fab"))
\t\t(property "MPN" "TMP117AIDRVR" (at 0 0 0) (layer "F.Fab") (hide yes))
\t\t(attr smd)
\t\t(fp_text user "label with (parens) and \\"quotes\\"" (at 0 0) (layer "F.Fab"))
\t\t(pad "1" smd rect (at -1 0) (size 1 1) (layers "F.Cu") (net 1 "GND") (pinfunction "GND") (pintype "power_in"))
\t\t(pad "2" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 2 "/Sensors/I2C_SDA") (pinfunction "SDA")
\t\t\t(pintype "bidirectional"))
\t\t(pad "3" smd rect (at 1 0) (size 1 1) (layers "F.Cu") (pinfunction "ADD0") (pintype "input"))
\t\t(pad "4" smd rect (at 2 0) (size 1 1) (layers "F.Cu") (net 3 "unconnected-(U1-NC-Pad4)") (pinfunction "NC")
\t\t\t(pintype "no_connect"))
\t\t(pad "" np_thru_hole circle (at 3 0) (size 1 1) (drill 1) (layers "*.Cu"))
\t)
\t(footprint "Resistor_SMD:R_0402"
\t\t(layer "B.Cu")
\t\t(at 10 20 180)
\t\t(fp_text reference "R7" (at 0 0) (layer "B.SilkS"))
\t\t(fp_text value "4k7" (at 0 0) (layer "B.Fab"))
\t\t(attr smd exclude_from_bom dnp)
\t\t(pad "1" smd rect (at 0 0) (size 1 1) (layers "B.Cu") (net 2 "/Sensors/I2C_SDA") (pintype "passive"))
\t\t(pad "2" smd rect (at 1 0) (size 1 1) (layers "B.Cu") (net 1 "GND") (pintype "passive"))
\t)
\t(footprint "Symbol:Logo"
\t\t(layer "F.Cu")
\t\t(at 5 5)
\t\t(property "Reference" "LOGO1" (at 0 0 0) (layer "F.SilkS"))
\t\t(property "Value" "~" (at 0 0 0) (layer "F.Fab"))
\t\t(attr board_only exclude_from_pos_files exclude_from_bom)
\t)
\t(segment (start 0 0) (end 1 1) (width 0.2) (layer "F.Cu") (net 2))
\t(zone (net 1) (net_name "GND") (layer "B.Cu") (polygon (pts (xy 0 0) (xy 1 0) (xy 1 1))))
)
"""


def _kicad10(text):
    out = text.replace("(version 20241229)", "(version 20260206)").replace('"9.0"', '"10.0"')
    for n, name in ((1, "GND"), (2, "/Sensors/I2C_SDA"), (3, "unconnected-(U1-NC-Pad4)")):
        out = out.replace(f'(net {n} "{name}")', f'(net "{name}")')
    for func, num in (("GND", "1"), ("SDA", "2"), ("ADD0", "3"), ("NC", "4")):
        out = out.replace(f'(pinfunction "{func}")', f'(pinfunction "{func}_{num}")')
    return "\n".join(ln for ln in out.splitlines() if not ln.startswith("\t(net "))


def _check(m):
    assert set(m.components) == {"U1", "R7", "LOGO1"}
    assert m.pins[("U1", "2")].net == "/Sensors/I2C_SDA" and m.pins[("U1", "2")].name == "SDA"
    assert m.pins[("U1", "3")].net is None and m.pins[("U1", "4")].net is None
    assert m.pins[("U1", "4")].type == "no_connect" and m.pins[("U1", "1")].type == "power_in"
    assert ("U1", "") not in m.pins and len(m.pins_of("U1")) == 4
    assert m.nets["/Sensors/I2C_SDA"].pins == ["R7.1", "U1.2"]
    u1, r7, logo = m.components["U1"], m.components["R7"], m.components["LOGO1"]
    assert (u1.value, u1.mpn, u1.footprint) == ("TMP117", "TMP117AIDRVR", "Package_SO:SOIC-8")
    assert (u1.attrs["x_mm"], u1.attrs["y_mm"], u1.attrs["rot_deg"], u1.attrs["side"]) == ("100.5", "80.25", "90",
                                                                                          "top")
    assert (r7.value, r7.fitted, r7.attrs["side"], r7.attrs["exclude_from_bom"]) == ("4k7", False, "bottom", "yes")
    assert logo.attrs["board_only"] == "yes" and logo.attrs["rot_deg"] == "0" and not m.pins_of("LOGO1")
    assert m.pin_list_complete and m.sources[0]["kind"] == "kicad_pcb"


def test_kicad9_board_pads_nets_and_placement():
    _check(kicad_pcb.parse_kicad_pcb(KICAD9_PCB))


def test_kicad10_board_net_names_on_pads_and_numbered_pin_functions():
    m = kicad_pcb.parse_kicad_pcb(_kicad10(KICAD9_PCB))
    _check(m)
    assert m.pins[("U1", "3")].name == "ADD0"


def test_escaped_characters_in_net_names_read_as_the_netlist_writes_them():
    text = KICAD9_PCB.replace('"/Sensors/I2C_SDA"', '"/Sensors/SDA{slash}SDI"')
    m = kicad_pcb.parse_kicad_pcb(text)
    assert m.pins[("U1", "2")].net == "/Sensors/SDA/SDI"


def test_repeated_pad_numbers_on_unconnected_nets_do_not_conflict():
    extra = ('\t\t(pad "4" smd rect (at 5 0) (size 1 1) (layers "F.Cu") (net 9 "unconnected-(U1-NC-Pad4)_1")'
             ' (pinfunction "NC") (pintype "no_connect"))\n\t\t(pad "" np_thru_hole')
    m = kicad_pcb.parse_kicad_pcb(KICAD9_PCB.replace('\t\t(pad "" np_thru_hole', extra, 1))
    assert m.pins[("U1", "4")].net is None
    assert not [w for w in m.warnings if "seen on" in w]


def test_sniff_and_load_a_board_file(tmp_path):
    path = tmp_path / "board.kicad_pcb"
    path.write_text(KICAD9_PCB, encoding="utf-8")
    assert loaders.sniff(path) == "kicad_pcb"
    _check(loaders.load(path))


def test_board_against_its_schematic_is_clean():
    sch = BoardModel(pin_list_complete=True)
    for ref, pin, net in (("U1", "1", "GND"), ("U1", "2", "/Sensors/I2C_SDA"), ("U1", "3", None),
                          ("U1", "4", "unconnected-(U1-NC-Pad4)"), ("R7", "1", "/Sensors/I2C_SDA"), ("R7", "2", "GND")):
        sch.add_pin(ref, pin, net)
    sch.component("LOGO1")
    sch.finalize()
    pair = compare.compare([("schematic", sch), ("pcb", kicad_pcb.parse_kicad_pcb(KICAD9_PCB))]).pairs[0]
    assert pair.clean and not pair.truncated and not pair.mech_only_a and not pair.mech_only_b


def test_board_model_from_a_board_file_matches_the_schema():
    data = serialize.to_dict(kicad_pcb.parse_kicad_pcb(KICAD9_PCB))
    assert schema.validate(data, schema.load("board_model")) == []


def test_placement_table():
    text = kicad_pcb.placement_markdown(kicad_pcb.parse_kicad_pcb(KICAD9_PCB), "board.kicad_pcb")
    assert "| R7 | bottom | 10 | 20 | 180 | Resistor_SMD:R_0402 | 4k7 | no |" in text
    assert "| U1 | top | 100.5 | 80.25 | 90 |" in text
    assert "2 top, 1 bottom" in text
    assert "same X and the negated Y" in text
