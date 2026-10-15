import shutil
from pathlib import Path

import numpy as np
import pytest

from boardreview.calc.base import Verdict
from boardreview.sim import sanity
from boardreview.sim.netlist import parse_netlist, parse_value
from boardreview.sim.runner import LTspice, run, schematic_to_netlist

FIXTURES = Path(__file__).parent / "fixtures" / "sim"
LOCAL = Path(__file__).parent / "local" / "ltc3633"
needs_ltspice = pytest.mark.skipif(not LTspice().available(), reason="LTspice not installed")


def test_parse_value_suffixes():
    assert parse_value("6.8µ") == pytest.approx(6.8e-6)
    assert parse_value("10meg") == pytest.approx(10e6)
    assert parse_value("2.2uF") == pytest.approx(2.2e-6)
    assert parse_value("54.9K") == pytest.approx(54.9e3)
    assert parse_value("{L}") is None
    assert parse_value("2N3904") is None


def test_parse_netlist_elements_and_pnba():
    nl = parse_netlist(
        "* t\nR1 a b 1k\nL3 SW1 OUT1 6.8µ Rser=0.22\n"
        "X§U1 a b 0 PART ;§pnba IN)OUT)GND\nQ1 c b 0 2N3904\nE1 o 0 value={V(a)*2}\n"
        "+ \n.lib PART.sub\n.tran 0 1m 0 10n startup\n.end\n")
    els = {e.name: e for e in nl.elements}
    assert els["L3"].nodes == ("SW1", "OUT1") and els["L3"].params["rser"] == "0.22"
    assert els["X§U1"].model == "PART" and els["X§U1"].pin_names == ("IN", "OUT", "GND")
    assert els["Q1"].nodes == ("c", "b", "0") and els["Q1"].model == "2N3904"
    assert els["E1"].nodes == ("o", "0")
    assert nl.libs == [(8, "PART.sub")]
    assert sanity.tran_time_args(nl) == {"tstep": 0.0, "tstop": 1e-3, "tstart": 0.0, "dtmax": 10e-9}


def test_floating_second_channel_pins_are_errors():
    rep = sanity.check_netlist(FIXTURES / "dual_reg_floating.net")
    assert not rep.ok
    msgs = " ".join(i.message for i in rep.errors)
    assert "pin 5 (FB2)" in msgs and "pin 6 (SW2)" in msgs and "pin 8 (PGOOD)" in msgs


def test_declared_open_pins_pass_but_stay_listed():
    rep = sanity.check_netlist(FIXTURES / "dual_reg_floating.net", allow_open=["PGOOD", "XU1.FB2", "nc_2"])
    assert rep.ok, rep.to_markdown()
    assert sum(1 for i in rep.issues if i.rule == "open-pin" and i.severity == "info") == 3


def test_rt_resistor_off_its_pin_is_caught_statically():
    rep = sanity.check_netlist(FIXTURES / "osc_rt_open.net")
    texts = [i.message for i in rep.errors]
    assert any(t.startswith("XU1 pin 1 (RT)") for t in texts)
    assert any(t.startswith("R47 terminal 1") for t in texts)
    assert sanity.check_netlist(FIXTURES / "osc_rt.net").ok


def test_subckt_pin_count_mismatch_and_missing_lib(tmp_path):
    text = "* t\nV1 a 0 1\nX1 a b 0 extra DIV\nR9 b 0 1k\nR8 extra 0 1k\n.subckt DIV a b g\nR1 a b 1k\nR2 b g 1k\n" \
           ".ends\n.lib nosuch.lib\n.op\n"
    rep = sanity.check_netlist(text)
    rules = {(i.rule, i.severity) for i in rep.issues}
    assert ("subckt-pins", "error") in rules
    assert ("model-file", "error") in rules


def test_encrypted_lib_uses_symbol_pin_count(tmp_path):
    (tmp_path / "REG.sub").write_bytes(b"<Binary File>\n\x00\x01\x02")
    sym = tmp_path / "sym"
    sym.mkdir()
    (sym / "REG.asy").write_text("Version 4\nSymbolType CELL\nPIN 0 0 LEFT 8\nPINATTR PinName IN\n"
                                 "PINATTR SpiceOrder 1\nPIN 0 0 LEFT 8\nPINATTR PinName SW\nPINATTR SpiceOrder 2\n"
                                 "PIN 0 0 LEFT 8\nPINATTR PinName FB\nPINATTR SpiceOrder 4\n")
    net = tmp_path / "t.net"
    net.write_text("* t\nV1 in 0 5\nXU1 in sw MP_1 fb REG\nL1 sw 0 1u\n.lib REG.sub\n.op\n")
    rep = sanity.check_netlist(net, lib_dirs=[sym])
    assert any(i.rule == "model-file" and "encrypted" in i.message for i in rep.issues)
    assert any(i.rule == "open-pin" and "pin 4 (FB)" in i.message for i in rep.errors)
    assert not any(i.rule == "subckt-pins" for i in rep.issues)
    net.write_text("* t\nV1 in 0 5\nXU1 in sw 0 REG\nL1 sw 0 1u\n.lib REG.sub\n.op\n")
    rep = sanity.check_netlist(net, lib_dirs=[sym])
    assert any(i.rule == "subckt-pins" and "3 nodes but REG has 4 pins" in i.message for i in rep.errors)


def test_node_between_capacitors_has_no_dc_path():
    rep = sanity.check_netlist("* t\nV1 a 0 1\nC1 a x 1n\nC2 x 0 1n\nR1 a 0 1k\n.op\n")
    assert any(i.rule == "no-dc-path" and "x" in i.message for i in rep.issues)


def test_tran_step_too_coarse_for_switching():
    rep = sanity.check_netlist("* t\nV1 a 0 1\nR1 a 0 1\n.tran 0 1m 0 100n\n", expected_fsw_hz=1.187e6)
    assert "tran-step" in rep.rules("warning")


def test_nodes_read_in_expressions_count_as_connections():
    text = ("* t\nVramp ramp 0 PULSE(0 1 0 1u 1n 0 2u)\nVin vin 0 5\nBsw sw 0 V=V(vin)*(V(ramp,0)>0.5)\n"
            "R1 sw 0 1k\n.op\n")
    assert sanity.check_netlist(text).ok
    rep = sanity.check_netlist(text.replace("V(vin)*", "5*"))
    assert [i.where for i in rep.errors] == ["Vin"]


def test_up_slew_bench_record():
    # 3V3 board 2, 2026-10-14: up-ramp 0.12 A/us = (4.03 V x 0.89 - 3.32 V) / 2.2 uH
    assert sanity.up_slew(4.03, 0.89, 3.32, 2.2e-6) == pytest.approx(0.121e6, rel=0.01)


def test_injection_slew_limit_bench_records():
    # 2026-10-06 loop-gain review: 57 mA/us at 6.8 uH and 18 uF limits a 20 mV sine above about 63 kHz
    assert sanity.slew_limited_amplitude(57e3, 63e3, 18e-6) == pytest.approx(20e-3, rel=0.02)
    assert sanity.injection_slew_check(20e-3, 80e3, 57e3, 18e-6).verdict is Verdict.FAIL
    assert sanity.injection_slew_check(3e-3, 80e3, 57e3, 18e-6).verdict is Verdict.PASS
    # 2026-10-07 residual ring: 177 mA/us, 115 kHz, 17 uF clamps at 20 mV (40 mV pk-pk on the scope)
    assert sanity.slew_limited_amplitude(177e3, 115e3, 17e-6) == pytest.approx(20e-3, rel=0.02)


def test_marginal_or_unknown_setup_check_is_not_a_pass():
    t = np.arange(0, 100e-6, 40e-9)
    edge = sanity.edge_resolution_check(t, np.where((t * 500e3) % 1.0 < 0.66, 4.0, 0.0))
    assert edge.verdict is Verdict.MARGINAL
    rep = sanity.SanityReport(results=[edge])
    assert rep.verdict is Verdict.MARGINAL and not rep.ok and not rep.failed
    assert "pass" not in rep.to_markdown().splitlines()[0]
    unknown = sanity.edge_resolution_check(t, np.linspace(0.0, 4.0, len(t)))
    assert unknown.verdict is Verdict.UNKNOWN
    assert sanity.SanityReport(results=[unknown]).verdict is Verdict.UNKNOWN
    assert sanity.SanityReport(issues=[sanity.Issue("run", "error", "x")]).failed
    assert sanity.SanityReport().ok and "pass" in sanity.SanityReport().to_markdown()


def test_measured_verdict_stands_only_on_a_passed_setup():
    assert sanity.trusted_verdict(Verdict.PASS, Verdict.FAIL) is Verdict.FAIL
    assert sanity.trusted_verdict(Verdict.PASS, Verdict.PASS) is Verdict.PASS
    for setup in (Verdict.MARGINAL, Verdict.UNKNOWN, Verdict.FAIL):
        assert sanity.trusted_verdict(setup, Verdict.PASS) is Verdict.UNKNOWN
    assert sanity.worst([Verdict.INFO, Verdict.PASS]) is Verdict.PASS
    assert sanity.worst([Verdict.MARGINAL, Verdict.UNKNOWN, Verdict.PASS]) is Verdict.UNKNOWN


def test_switching_frequency_check_on_synthetic_747khz():
    t = np.linspace(0, 50e-6, 500_001)
    v = np.where((t * 747e3) % 1.0 < 0.8, 4.0, 0.0)
    res = sanity.switching_frequency_check(t, v, 1.187e6)
    assert res.verdict is Verdict.FAIL
    assert "-37" in res.reason


@needs_ltspice
def test_run_check_catches_wrong_switching_frequency(tmp_path):
    for name, verdict in (("osc_rt.net", Verdict.PASS), ("osc_rt_open.net", Verdict.FAIL)):
        shutil.copy(FIXTURES / name, tmp_path / name)
        rep = sanity.check_run(run(tmp_path / name), "V(sw)", 1.187e6, t_start_s=10e-6)
        assert [r.verdict for r in rep.results] == [verdict]
    assert rep.results[0].outputs["f_sw"].value == pytest.approx(252.4e3, rel=0.01)


@needs_ltspice
def test_check_log_reports_syntax_error(tmp_path):
    shutil.copy(FIXTURES / "syntax_error.net", tmp_path / "bad.net")
    rep = sanity.check_log(run(tmp_path / "bad.net"))
    assert not rep.ok and any("bad.net(3)" in i.message for i in rep.errors)


@pytest.mark.skipif(not (LOCAL / "3V3_FCM_L_sweep.net").exists(), reason="local LTC3633 netlists not present")
def test_real_ltc3633_netlists():
    allow = ["Pgood1", "Pgood2", "Track/SS1", "Track/SS2"]
    hand = sanity.check_netlist(LOCAL / "3V3_FCM_L_sweep.net", allow_open=allow)
    floating = {i.message.split(" is on")[0] for i in hand.errors}
    assert floating == {"XU9 pin 9 (VFB2)", "XU9 pin 12 (Von2)", "XU9 pin 13 (SW2), pin 14 (SW2 dup)",
                        "XU9 pin 17 (Boost2)"}


@needs_ltspice
def test_schematic_wire_short_of_pin_is_caught(tmp_path):
    shutil.copy(FIXTURES / "short_wire.asc", tmp_path / "short_wire.asc")
    rep = sanity.check_netlist(schematic_to_netlist(tmp_path / "short_wire.asc"))
    assert [i.where for i in rep.errors] == ["C1"]


@needs_ltspice
@pytest.mark.skipif(not (LOCAL / "NEW_3V3_6p8uH_FCM.asc").exists(), reason="local LTC3633 schematic not present")
def test_real_rt_wire_short_of_pin_runs_at_747_khz(tmp_path):
    # 2026-10-06: the RT wire in NEW_3V3_6p8uH_FCM.asc stopped 16 units short of the Rt pin; the model ran at 747 kHz
    allow = ["Pgood1", "Pgood2", "Track/SS1", "Track/SS2"]
    asc = (LOCAL / "NEW_3V3_6p8uH_FCM.asc").read_bytes()
    (tmp_path / "ok.asc").write_bytes(asc)
    (tmp_path / "rt_open.asc").write_bytes(asc.replace(b"WIRE 0 784 0 736", b"WIRE 0 768 0 736"))
    ok_net, open_net = schematic_to_netlist(tmp_path / "ok.asc"), schematic_to_netlist(tmp_path / "rt_open.asc")
    assert sanity.check_netlist(ok_net, allow_open=allow).ok
    static = sanity.check_netlist(open_net, allow_open=allow)
    assert {i.where for i in static.errors} == {"X§U1", "R47"}
    text = open_net.read_text(encoding="utf-8").replace(".tran 0 800u 0 20n startup", ".tran 0 600u 0 20n startup")
    open_net.write_text(text, encoding="utf-8")
    fsw = sanity.check_run(run(open_net), "SW1", 1.187e6, t_start_s=500e-6).results[0]
    assert fsw.verdict is Verdict.FAIL
    assert fsw.outputs["f_sw"].value == pytest.approx(747e3, rel=0.01)
