import json
import zipfile
from pathlib import Path

import pytest

from boardreview import lint
from boardreview.model import bom, eda_agent, ipc356, kicad, loaders, protel, serialize, xlsx

FIX = Path(__file__).parent / "fixtures" / "model"
SCHEMA = Path(__file__).parents[1] / "skill" / "schemas" / "board_model.schema.json"


def test_ipc356_fixed_columns_alias_nc_and_vias():
    m = ipc356.read_ipc356(FIX / "adi_buck_nonames.ipc")
    assert m.pin_list_complete
    assert set(m.components) == {"J1", "C1", "U1", "C2", "L1", "C3", "C4", "R1", "R2", "U2", "R3"}
    assert m.nets["VERY_LONG_SENSOR_NET_NAME"].pins == ["J1.4", "R3.2", "U2.3"]
    assert m.nets["NetL1_1"].pins == ["C2.2", "L1.1", "U1.5", "U1.6"]
    assert [p.key for p in m.unconnected_pins()] == ["U1.7", "U1.10", "U2.4"]
    assert m.nets["GND"].attrs["vias"] == 5
    assert "J1.SHLD" in m.nets["GND"].pins and len(m.pins) == 35
    assert m.sources[0]["ver"] == "IPC-D-356A"


def test_ipc356_kicad_layout_alphanumeric_aliases_and_vias_without_a_dash():
    m = ipc356.read_ipc356(FIX / "kicad_d356_aliases.ipc")
    assert m.nets["SENSOR_OUTPUT_FILTERED"].pins == ["J1.3", "R1.2", "U2.3"]
    assert m.nets["I2C_SDA_TO_CONNECTOR"].pins == ["J1.4", "R2.2", "U2.5"]
    assert "M0000" not in m.nets and "M0001" not in m.nets
    assert (m.nets["GND"].attrs["vias"], m.nets["+3V3"].attrs["vias"]) == (3, 2)
    assert m.nets["I2C_SDA_TO_CONNECTOR"].attrs["vias"] == 1
    assert [p.key for p in m.unconnected_pins()] == ["U2.4"] and "VIA" not in m.components
    assert m.sources[0]["ver"] == "IPC-D-356A"


def test_ipc356_pin_overflowing_the_four_column_field():
    line = f"327{'SIG':<14}   {'U9':<6}-AB123     PA01X 000100Y 000200X0100Y0100R000 S0"
    m = ipc356.parse_ipc356("P  JOB X\n" + line + "\n999\n")
    assert m.pins[("U9", "AB123")].net == "SIG"


def test_ipc356_conflicting_pad_nets_warn():
    lines = [f"327{net:<14}   {'R1':<6}-{'1':<4}       A01X 000100Y 000200X0100Y0100R000 S0" for net in ("A", "B")]
    m = ipc356.parse_ipc356("\n".join(lines))
    assert m.pins[("R1", "1")].net == "A" and m.warnings


def test_kicad_xml_fields_types_dnp_and_unconnected():
    m = kicad.read_kicad_xml(FIX / "ti_buck_board.kicad.xml")
    u1 = {p.number: p for p in m.pins_of("U1")}
    assert (u1["2"].name, u1["2"].type, u1["2"].net) == ("SW", "power_out", "SW")
    assert m.components["U1"].mpn == "TPS54302DDCR"
    assert m.components["U1"].manufacturer == "Texas Instruments"
    assert not m.components["R7"].fitted and not m.components["R10"].fitted and m.components["R6"].fitted
    assert m.components["C10"].mpn == ""
    assert m.components["FB1"].kind == "ferrite" and m.components["D2"].kind == "tvs"
    assert m.components["Y1"].kind == "crystal"
    assert m.nets["+3V3"].net_class == "Power"
    assert "/FB_3V3" in m.nets
    assert m.pins[("U2", "14")].net is None and m.pins[("U2", "14")].no_connect
    assert m.pins[("U2", "10")].net is None and not m.pins[("U2", "10")].no_connect
    assert m.pins[("U3", "2")].name == "~{RESET}"
    assert m.components["R2"].value_si == pytest.approx(22.1e3)


def test_ti_fixture_supervisor_reset_is_push_pull_like_the_real_part():
    # TPS3839: TI SBVS193D rev D (July 2015), p. 5, Pin Functions: RESET has a push-pull output drive.
    m = kicad.read_kicad_xml(FIX / "ti_buck_board.kicad.xml")
    u3 = {p.number: (p.name, p.type) for p in m.pins_of("U3")}
    assert u3 == {"1": ("GND", "power_in"), "2": ("~{RESET}", "output"), "3": ("VDD", "power_in")}
    text = (FIX / "ti_buck_board.kicad.xml").read_text(encoding="utf-8")
    assert "open_collector" not in text.split('part="TPS3839"')[1].split("</libpart>")[0]


def test_protel_netlist_classic_layout():
    m = protel.read_protel(FIX / "sch_missing_sheet.net")
    assert not m.pin_list_complete
    assert set(m.components) == {"J1", "C1", "C3", "C4", "U2", "R3"}
    assert m.components["R3"].value == "4.7k" and m.components["R3"].footprint == "R0402"
    assert m.nets["GND"].pins == ["C1.2", "C3.2", "C4.2", "J1.2", "J1.SHLD", "U2.2"]


def test_protel_netlist_keyword_layout_and_brackets_in_comment():
    text = "\n".join([
        "PROTEL NETLIST 2.0", "[ DESIGNATOR", "J4", "FOOTPRINT", "DF40C-60DS", "PARTTYPE", "DF40HC(4.0)-60DS", "]",
        "(", "NET_A", "J4-1 DF40 PASSIVE", "U1-B2 BGA PASSIVE", ")",
    ])
    m = protel.parse_protel(text)
    assert m.components["J4"].value == "DF40HC(4.0)-60DS"
    assert m.nets["NET_A"].pins == ["J4.1", "U1.B2"]


def test_eda_agent_snapshot_pins_parameters_and_variant():
    m = eda_agent.read_eda_agent(FIX / "mps_buck.eda_agent.json")
    u1 = {p.number: p for p in m.pins_of("U1")}
    assert (u1["3"].name, u1["3"].net) == ("SW", "LX")
    assert u1["6"].name == "EN/SYNC"
    assert m.components["U1"].mpn == "MP2315GJ-Z"
    assert m.components["U1"].attrs["sheet"] == "Power.SchDoc"
    assert m.components["L1"].description.startswith("Power inductor")
    assert m.components["C1"].value == "22uF" and m.components["U1"].value == ""
    assert m.pins[("J2", "3")].net is None
    assert m.components["R5"].fitted
    v = eda_agent.read_eda_agent(FIX / "mps_buck.eda_agent.json", variant="NoAAM")
    assert not v.components["R5"].fitted and v.components["R5"].variant == "NoAAM"
    with pytest.raises(ValueError):
        eda_agent.read_eda_agent(FIX / "mps_buck.eda_agent.json", variant="Nope")


def test_eda_agent_get_nets_and_pcb_pads_shapes():
    nets = {"pins": [{"component": "U1", "pin": "1", "pin_name": "VCC", "net": "+3V3"},
                     {"component": "U1", "pin": "2", "pin_name": "NC", "net": "?"}], "count": 2}
    m = eda_agent.parse_eda_agent(nets)
    assert m.pins[("U1", "1")].name == "VCC" and m.pins[("U1", "2")].net is None
    pads = {"designator": "U1", "pad_count": 1, "pads": [{"name": "1", "x": 10, "y": 20, "net": "+3V3", "layer": "Top"}]}
    p = eda_agent.parse_eda_agent(pads)
    assert p.pins[("U1", "1")].net == "+3V3" and p.pins[("U1", "1")].name == ""


def test_eda_agent_completeness_needs_a_pin_inventory():
    assert eda_agent.read_eda_agent(FIX / "mps_buck.eda_agent.json").pin_list_complete
    pads = {"designator": "U1", "pads": [{"name": "1", "net": "+3V3"}, {"name": "2", "net": ""}]}
    assert eda_agent.parse_eda_agent(pads).pin_list_complete
    parts_only = {"components": [{"designator": "U1", "parameters": {"Manufacturer Part Number": "X"}}]}
    no_nets = {"components": [{"designator": "U1", "pins": [{"pin": "1", "name": "VCC"}, {"pin": "2", "name": "GND"}]}]}
    by_net = {"pins": [{"component": "U1", "pin": "1", "pin_name": "VCC", "net": "+3V3"}]}
    for payload in (parts_only, no_nets, by_net):
        m = eda_agent.parse_eda_agent(payload)
        assert not m.pin_list_complete
        assert any("pin list not complete" in w for w in m.warnings)
        assert "unconnected_ic_pin" in lint.run_all(m).skipped
    open_list = {"unconnected_pins": [{"designator": "U1", "pin_number": "2", "pin_name": "NC"}]}
    assert eda_agent.parse_eda_agent([by_net, open_list]).pin_list_complete


def test_bom_csv_title_rows_ranges_dnp_and_merge(tmp_path):
    csv_text = "\n".join([
        "Project,Demo", "",
        "Designator,Comment,Description,Manufacturer Part Number,Manufacturer,DNP",
        '"R1-R3",10k,"10k 1% 0402 resistor",RC0402FR-0710KL,Yageo,',
        "C1;C2,100n,Ceramic capacitor,GRM155R71C104KA88D,Murata,",
        "R9,DNP,Resistor,,,x",
        "Z1,,Mystery,,,",
    ])
    path = tmp_path / "bom.csv"
    path.write_text(csv_text, encoding="utf-8")
    lines = bom.read_bom(path)
    assert lines[0].refdes == ["R1", "R2", "R3"] and lines[1].refdes == ["C1", "C2"]
    assert not lines[2].fitted
    m = protel.parse_protel("[\nR1\nR0402\n\n]\n(\nA\nR1-1\nC1-1\n)\n(\nB\nR9-1\nQ7-1\n)\n")
    cross = bom.apply_bom(m, lines, str(path))
    assert m.components["R1"].mpn == "RC0402FR-0710KL" and m.components["R1"].value == "10k"
    assert m.components["C1"].value == "100n" and m.components["C1"].value_si == pytest.approx(1e-7)
    assert not m.components["R9"].fitted
    assert cross["bom_only"] == ["R2", "R3", "C2", "Z1"] or set(cross["bom_only"]) == {"R2", "R3", "C2", "Z1"}
    assert cross["netlist_only"] == ["Q7"]


def _write_xlsx(path: Path, rows: list[list[object]]) -> None:
    strings: list[str] = []
    cells_xml = []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, val in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if isinstance(val, (int, float)):
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            elif r == 2 and c == 0:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{val}</t></is></c>')
            else:
                strings.append(str(val))
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        cells_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel_ns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rel_ns}><sheets><sheet name="BOM" sheetId="1" r:id="rId1"/>'
                                      "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{''.join(cells_xml)}</sheetData></worksheet>")


def test_bom_xlsx_altium_layout(tmp_path):
    path = tmp_path / "bom.xlsx"
    _write_xlsx(path, [
        ["Name", "Description", "Designator", "Quantity", "Fitted", "Manufacturer 1"],
        ["CRCW040210K0FKED", "10k 1% 50V 63mW 0402 Thick Film Resistor", "R1, R2", 2, "Fitted", "Vishay"],
        ["CRCW040210K0FKED", "10k 1% 50V 63mW 0402 Thick Film Resistor", "R3", 0, "Not Fitted", "Vishay"],
        ["CGA2B3X7R1H104K050BB", "100n 10% 50V X7R 0402 Multilayer Ceramic Capacitor", "C1", 1, "Fitted", "TDK"],
    ])
    assert xlsx.sheet_names(path) == ["BOM"]
    rows = xlsx.read_rows(path)
    assert rows[1][3] == "2"
    lines = bom.read_bom(path)
    assert [ln.refdes for ln in lines] == [["R1", "R2"], ["R3"], ["C1"]]
    assert lines[0].mpn == "CRCW040210K0FKED" and lines[0].manufacturer == "Vishay" and not lines[1].fitted
    m = protel.parse_protel("(\nN1\nR1-1\nR3-1\nC1-1\n)\n")
    bom.apply_bom(m, lines)
    assert m.components["R1"].value == "10k" and m.components["R1"].attrs["value_from"] == "bom description"
    assert m.components["C1"].value == "100nF" and not m.components["R3"].fitted


@pytest.mark.parametrize("name, fmt", [("adi_buck_nonames.ipc", "ipc356"), ("ti_buck_board.kicad.xml", "kicad_xml"),
                                       ("sch_missing_sheet.net", "protel_net"), ("mps_buck.eda_agent.json", "eda_agent_json")])
def test_sniff_and_load(name, fmt):
    assert loaders.sniff(FIX / name) == fmt
    assert loaders.load(FIX / name).pins


def _validate(value, schema, path="$"):
    """Small JSON Schema subset check: type, const, enum, required, properties, items, additionalProperties."""
    types = schema.get("type")
    if types:
        allowed = types if isinstance(types, list) else [types]
        py = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
        ok = any((t == "integer" and isinstance(value, int) and not isinstance(value, bool))
                 or (t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
                 or (t in py and isinstance(value, py[t])) for t in allowed)
        assert ok, f"{path}: {value!r} is not {allowed}"
    if "const" in schema:
        assert value == schema["const"], path
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} not in enum"
    if isinstance(value, dict):
        for key in schema.get("required", []):
            assert key in value, f"{path}: missing {key}"
        props = schema.get("properties", {})
        for key, sub in value.items():
            if key in props:
                _validate(sub, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise AssertionError(f"{path}: unexpected {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                _validate(sub, schema["additionalProperties"], f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{i}]")


@pytest.mark.parametrize("name", ["adi_buck_nonames.ipc", "ti_buck_board.kicad.xml", "mps_buck.eda_agent.json"])
def test_board_model_json_matches_schema_and_round_trips(name, tmp_path):
    m = loaders.load(FIX / name)
    data = serialize.to_dict(m)
    _validate(data, json.loads(SCHEMA.read_text(encoding="utf-8")))
    path = serialize.write_json(m, tmp_path / "board_model.json")
    back = loaders.load(path)
    assert serialize.to_dict(back) == data


def _kicad_nets(nets):
    """Minimal KiCad XML with one IC U1 and the given (name, [(pin, name, pintype)]) nets."""
    body = "".join(f'<net code="{i}" name="{name}">' + "".join(
        f'<node ref="{ref}" pin="{pin}" pinfunction="{fn}" pintype="{pt}"/>' for ref, pin, fn, pt in nodes) + "</net>"
        for i, (name, nodes) in enumerate(nets, 1))
    return kicad.parse_kicad_xml('<export version="E"><components><comp ref="U1"><value>X</value></comp>'
                                 '<comp ref="R1"><value>10k</value></comp></components>'
                                 f"<nets>{body}</nets></export>")


def test_kicad_stacked_open_pins_are_unconnected_and_keep_their_flags():
    m = _kicad_nets([
        ("unconnected-(U1-VDD-Pad1)", [("U1", "1", "VDD", "power_in+no_connect"), ("U1", "2", "VDD", "power_in+no_connect")]),
        ("Net-(U1-VDD-Pad3)", [("U1", "3", "VDD", "power_in"), ("U1", "4", "VDD", "power_in")]),
        ("Net-(U1-OUT)", [("U1", "5", "OUT", "output"), ("U1", "6", "IN-", "input")]),
        ("unconnected-(U1-NC-Pad7)", [("U1", "7", "NC", "no_connect"), ("R1", "1", "", "passive")]),
        ("GND", [("U1", "8", "GND", "power_in"), ("R1", "2", "", "passive")]),
    ])
    assert [p.key for p in m.unconnected_pins()] == ["U1.1", "U1.2", "U1.3", "U1.4"]
    assert m.pins[("U1", "1")].no_connect and not m.pins[("U1", "3")].no_connect
    assert m.nets["Net-(U1-OUT)"].pins == ["U1.5", "U1.6"]
    assert m.nets["unconnected-(U1-NC-Pad7)"].pins == ["R1.1", "U1.7"]
    errors = [f.pins for f in lint.run_all(m, only=["unconnected_ic_pin"]).findings if f.severity == "error"]
    assert errors == [["U1.1"], ["U1.2"], ["U1.3"], ["U1.4"]]


def _ti_with_bom(tmp_path, text):
    path = tmp_path / "bom.csv"
    path.write_text(text, encoding="utf-8")
    m = kicad.read_kicad_xml(FIX / "ti_buck_board.kicad.xml")
    bom.apply_bom(m, bom.read_bom(path), str(path))
    return m


def test_bom_without_population_column_keeps_netlist_dnp(tmp_path):
    m = _ti_with_bom(tmp_path, "Designator,MPN\nR7,RC0402FR-0710KL\nR6,RC0402FR-0710KL\n")
    assert [ln.fitted for ln in bom.read_bom(tmp_path / "bom.csv")] == [None, None]
    assert not m.components["R7"].fitted and m.components["R6"].fitted
    assert not any("R7" in w for w in m.warnings)


def test_bom_dnp_marker_in_value_keeps_the_netlist_value(tmp_path):
    m = _ti_with_bom(tmp_path, "Designator,Value\nR7,DNP\n")
    assert not m.components["R7"].fitted
    assert m.components["R7"].value == "10k" and m.components["R7"].value_si == pytest.approx(10e3)


def test_bom_population_that_contradicts_the_netlist_is_flagged(tmp_path):
    m = _ti_with_bom(tmp_path, "Designator,MPN,DNP\nR7,RC0402FR-0710KL,\nR6,RC0402FR-0710KL,DNP\n")
    assert m.components["R7"].fitted and not m.components["R6"].fitted
    assert "netlist DNP" in m.components["R7"].attrs["fitted_conflict"]
    assert "netlist fitted" in m.components["R6"].attrs["fitted_conflict"]
    assert sum("R6" in w or "R7" in w for w in m.warnings) == 2
