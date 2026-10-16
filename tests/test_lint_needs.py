"""NC, reserved and option pins need datasheet confirmation with a reason; never an error, never a pass."""

from boardreview import lint
from boardreview.lint import nets, pins
from boardreview.model.board import BoardModel
from boardreview.model.graph import Graph

NEEDS = "needs datasheet confirmation"


def _run(fn, m):
    return fn(m, Graph(m))


def _model(rows, dnp=(), mpn=None):
    m = BoardModel(pin_list_complete=True)
    for row in rows:
        ref, pin, net, name, *rest = row
        m.add_pin(ref, pin, net, name, rest[0] if rest else "", no_connect=bool(rest[1]) if len(rest) > 1 else False)
    for ref in dnp:
        m.component(ref).fitted = False
    for ref, value in (mpn or {}).items():
        m.component(ref).mpn = value
    for c in m.components.values():
        c.classify()
    return m.finalize()


def _needs(f):
    return f.evidence.get("needs") == "datasheet confirmation" and f.evidence.get("reason") and NEEDS in f.summary


def test_unused_pgood_needs_the_datasheet_and_says_why():
    m = _model([("U2", "1", "3V3", "VOUT"), ("U2", "2", "GND", "GND"), ("U2", "5", None, "PGOOD")])
    found = _run(pins.unconnected_ic_pins, m)
    assert [(f.severity, f.pins) for f in found] == [("info", ["U2.5"])]
    assert _needs(found[0]) and "power-good" in found[0].evidence["reason"]


def test_nc_and_reserved_pins_carry_a_reason_and_are_never_errors():
    m = _model([("U1", "1", "VIN", "VIN", "power_in"), ("U1", "2", None, "VSS", "power_in", True),
                ("U1", "3", None, "NC", "power_in"), ("U1", "4", None, "PA3", "bidirectional", True),
                ("U1", "5", None, "RESERVED", "passive")])
    found = _run(pins.unconnected_ic_pins, m)
    assert [(f.severity, f.pins) for f in found] == [("error", ["U1.2"]), ("warning", ["U1.3", "U1.4", "U1.5"])]
    nc = found[1]
    assert _needs(nc)
    assert "U1.3" in nc.evidence["reason"] and "typed power" in nc.evidence["reason"]
    assert "no-connect flag" in nc.evidence["reason"] and "tied to ground" in nc.summary


def test_other_open_pins_need_the_datasheet_too():
    m = _model([("U1", "1", "VCC", "VCC"), ("U1", "2", None, "IN"), ("U1", "3", "GND", "GND")])
    found = _run(pins.unconnected_ic_pins, m)
    assert [(f.severity, f.pins) for f in found] == [("warning", ["U1.2"])]
    assert _needs(found[0])


def test_dnp_option_pin_needs_the_datasheet():
    m = _model([("IC7", "3", "MODE_OPT", "CURRENT_MODE"), ("IC7", "1", "5V", "VCC"), ("R54", "1", "5V", ""),
                ("R54", "2", "MODE_OPT", ""), ("C1", "1", "5V", ""), ("C1", "2", "GND", "")], dnp=("R54",))
    found = _run(nets.dnp_only_link, m)
    assert [(f.severity, f.pins) for f in found] == [("warning", ["IC7.3", "R54.2"])]
    assert _needs(found[0]) and "R54" in found[0].evidence["reason"]


def test_power_pin_left_open_by_a_dnp_part_is_an_error():
    m = _model([("U4", "1", "VDD_OPT", "VDD", "power_in"), ("U4", "2", "GND", "GND"), ("R9", "1", "3V3", ""),
                ("R9", "2", "VDD_OPT", ""), ("C9", "1", "3V3", ""), ("C9", "2", "GND", ""), ("C10", "1", "3V3", ""),
                ("C10", "2", "GND", "")], dnp=("R9",))
    found = _run(nets.dnp_only_link, m)
    assert [(f.severity, f.pins) for f in found] == [("error", ["U4.1", "R9.2"])]
    assert "power pin" in found[0].summary


def test_lint_never_passes_an_open_ic_pin():
    m = _model([("U1", "1", "VCC", "VCC"), ("U1", "2", "GND", "GND"), ("U1", "3", None, "NC"),
                ("U1", "4", None, "PG"), ("U1", "5", None, "SDA")])
    report = lint.run_all(m)
    covered = {p for f in report.findings for p in f.pins}
    assert {"U1.3", "U1.4", "U1.5"} <= covered
    assert all(f.severity != "error" for f in report.findings if f.check == "unconnected_ic_pin")
