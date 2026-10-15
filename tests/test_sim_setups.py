import math
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from boardreview.calc.base import Result, Verdict
from boardreview.sim import measure, setups
from boardreview.sim.rawfile import RawFile, Variable
from boardreview.sim.runner import LTspice, RunResult, parse_log, run, schematic_to_netlist
from boardreview.sim.sanity import SanityReport, check_netlist, check_run

FIXTURES = Path(__file__).parent / "fixtures" / "sim"
LOCAL = Path(__file__).parent / "local" / "ltc3633"
needs_ltspice = pytest.mark.skipif(not LTspice().available(), reason="LTspice not installed")
COMMON = dict(top_resistor="Rtop", out_node="out", fsw_hz=500e3, c_out_f=10e-6, slew_up_a_per_s=1.6e6,
              slew_down_a_per_s=3.3e6)


def vm_buck_t(f: np.ndarray) -> np.ndarray:
    """Analytic loop gain of vm_buck_averaged.net: gm Zc 2 H_LC k."""
    s = 2j * np.pi * f
    zc = 1 / (1 / 10e6 + s * 11.6e-9)
    zl = 1 / (1 / 1.0 + 1 / (10e-3 + 1 / (s * 10e-6)))
    h = zl / (zl + s * 1e-6 + 10e-3)
    k = 2.22 / 12.22
    return 1e-3 * zc * 2 * h * k


def vm_buck_cff_t(f: np.ndarray, cff_f: float) -> np.ndarray:
    """Loop gain of vm_buck_averaged.net with Cff across Rtop: k = Rbot / (Rbot + Rtop || 1/(s Cff))."""
    s = 2j * np.pi * f
    ztop = 1 / (1 / 10e3 + s * cff_f)
    return vm_buck_t(f) / (2.22 / 12.22) * 2.22e3 / (2.22e3 + ztop)


def interp_complex(f_new: np.ndarray, f: np.ndarray, t: np.ndarray) -> np.ndarray:
    lf = np.log(f)
    return np.interp(np.log(f_new), lf, t.real) + 1j * np.interp(np.log(f_new), lf, t.imag)


def test_body_from_netlist_strips_analyses():
    body = setups.body_from_netlist(FIXTURES / "vm_buck_switching.net")
    assert ".tran" not in body and ".end" not in body.lower().split()
    assert "Rtop out fb 10k" in body


def test_replace_node_and_remove_element():
    body = "V1 in 0 5\nRtop out fb 10k\nRbot fb 0 2.2k"
    assert "Rtop lg_a fb 10k" in setups.replace_node(body, "rtop", "OUT", "lg_a")
    with pytest.raises(ValueError):
        setups.replace_node(body, "Rbot", "out", "x")
    rest, toks = setups.remove_element(body, "V1")
    assert toks[:3] == ["V1", "in", "0"] and "V1" not in rest


def test_injection_frequencies_stay_off_fsw_over_k():
    freqs = setups.injection_frequencies(1e3, 200e3, 25, 1.187e6)
    assert all(setups.subharmonic_fraction(f, 1.187e6) >= 0.25 - 1e-9 for f in freqs)
    assert freqs == sorted(freqs)


def test_loop_gain_netlist_opens_the_loop_at_the_top_resistor():
    s = setups.LoopGainSetup(body=setups.body_from_netlist(FIXTURES / "vm_buck_switching.net"), sw_node="sw",
                             **COMMON)
    net = s.netlist(10e3)
    assert "Rtop lg_a fb 10k" in net
    assert "Vbr_inj lg_a out SINE(0 0.002 10000 0.0003)" in net
    assert ".save V(lg_a) V(out) V(sw)" in net
    assert check_netlist(net, expected_fsw_hz=500e3).ok


def test_loop_gain_moves_every_feedback_branch_to_the_injection_node():
    body = setups.body_from_netlist(FIXTURES / "vm_buck_averaged.net")
    cff = setups.LoopGainSetup(body=body + "\nCff out fb 22p", **COMMON).ac_netlist(1e3, 1e5)
    assert "Rtop lg_a fb 10k" in cff and "Cff lg_a fb 22p" in cff
    type3 = setups.LoopGainSetup(body=body + "\nC3 out x3 1n\nR3 x3 fb 1k", **COMMON).ac_netlist(1e3, 1e5)
    assert "C3 lg_a x3 1n" in type3 and "R3 x3 fb 1k" in type3
    assert "Rload out 0 1" in type3 and "C1 out 0 10u" in type3


def test_loop_gain_refuses_a_feedback_path_it_cannot_move():
    body = setups.body_from_netlist(FIXTURES / "vm_buck_averaged.net") + "\nBsense xs 0 V=V(out)\nRs xs fb 1meg"
    with pytest.raises(ValueError, match="Bsense"):
        setups.LoopGainSetup(body=body, **COMMON).ac_netlist(1e3, 1e5)


def test_loop_gain_check_flags_slew_and_high_frequency():
    s = setups.LoopGainSetup(body=setups.body_from_netlist(FIXTURES / "vm_buck_switching.net"),
                             top_resistor="Rtop", out_node="out", fsw_hz=500e3, c_out_f=18e-6, slew_up_a_per_s=57e3,
                             slew_down_a_per_s=485e3, amplitude_v=20e-3)
    rep = s.check([80e3, 150e3])
    assert any(r.verdict is Verdict.FAIL for r in rep.results)
    assert any("above fsw/5" in i.message for i in rep.issues)
    with pytest.raises(ValueError, match="fix the setup"):
        setups.run_loop_gain(s, [80e3], "unused")


def test_startup_metrics_count_hiccups():
    t = np.linspace(0, 3e-3, 30001)
    v = 3.3 * np.clip((t % 1e-3) / 0.3e-3, 0, 1)
    v[t > 2e-3] = 3.3 * np.clip((t[t > 2e-3] - 2e-3) / 0.3e-3, 0, 1)
    m = setups.startup_metrics(t, v, np.full_like(t, 4.0), 3.3, 1e-4)
    assert m.restarts == 2
    assert m.t_reg_s == pytest.approx(2.3e-3, rel=0.01)


def fake_run(tmp_path: Path, t: np.ndarray, **cols: np.ndarray) -> RunResult:
    """A finished transient run with the given node voltages and a clean log."""
    raw_path = tmp_path / "fake.raw"
    raw_path.write_bytes(b"synthetic")
    variables = [Variable(0, "time", "time")] + [Variable(i + 1, f"V({n})", "voltage") for i, n in enumerate(cols)]
    raw = RawFile(header={"plotname": "Transient Analysis"}, variables=variables,
                  data=np.vstack([t, *cols.values()]), step_bounds=[(0, len(t))])
    return RunResult("ltspice", (), tmp_path / "fake.net", raw_path, None, 0, 0.0, False, parse_log(""), raw)


def ring(t: np.ndarray, zeta: float, t_step_s: float = 1e-4, f_hz: float = 20e3) -> np.ndarray:
    x = np.clip(t - t_step_s, 0, None)
    return 3.3 - 0.05 * np.exp(-zeta * 2 * np.pi * f_hz * x) * np.sin(2 * np.pi * f_hz * x)


def test_load_step_ring_and_settling_verdicts_reach_the_result(tmp_path, monkeypatch):
    t = np.linspace(0, 1e-3, 200_001)
    ls = setups.LoadStepSetup(body="V1 out 0 3.3", out_node="out", i_from_a=0.0, i_to_a=1.0, t_step_s=1e-4,
                              t_stop_s=1e-3)
    monkeypatch.setattr(setups, "run", lambda *a, **k: fake_run(tmp_path, t, out=ring(t, 0.05)))
    res = setups.run_load_step(ls, tmp_path)
    assert res.report.ok
    rings = [r for r in res.results if r.name == "ring-down after step"]
    assert rings and rings[0].verdict is Verdict.FAIL
    assert res.verdict is Verdict.FAIL and "**Verdict**: fail" in res.to_markdown()
    monkeypatch.setattr(setups, "run", lambda *a, **k: fake_run(tmp_path, t, out=ring(t, 0.0)))
    res = setups.run_load_step(ls, tmp_path)
    settle = [r for r in res.results if r.name == "settling after step"]
    assert settle and settle[0].verdict is Verdict.FAIL
    assert res.verdict is Verdict.FAIL


def test_startup_overshoot_above_the_limit_fails(tmp_path, monkeypatch):
    m = setups.Startup(1e-3, 100.0, 0, 3.3, 5.0, True)
    assert setups.startup_result(m, 3.3).verdict is Verdict.FAIL
    assert setups.startup_result(replace(m, overshoot_pct=5.0), 3.3).verdict is Verdict.PASS
    assert setups.startup_result(replace(m, overshoot_pct=5.0, monotonic=False), 3.3).verdict is Verdict.MARGINAL
    t = np.linspace(0, 2e-3, 20_001)
    vout = 3.3 * np.clip(t / 2e-4, 0, 1) + 3.3 * np.exp(-(((t - 3e-4) / 1e-4) ** 2))
    su = setups.StartupSetup(body="Vin vin 0 5\nRx vin out 1\nRl out 0 1", in_node="vin", out_node="out", vin_v=5.0,
                             ramp_s=1e-4, t_stop_s=2e-3, v_target_v=3.3, input_source="Vin")
    monkeypatch.setattr(setups, "run", lambda *a, **k: fake_run(tmp_path, t, out=vout, vin=np.full_like(t, 5.0)))
    res = setups.run_startup(su, tmp_path)
    assert res.metrics.overshoot_pct == pytest.approx(100.0, abs=1.0)
    assert res.report.ok and res.verdict is Verdict.FAIL


def test_loop_gain_verdict_keeps_setup_and_margins_apart():
    good = measure.LoopMargins(5e3, 60.0, 50e3, 12.0, (5e3,), (60.0,))
    thin = measure.LoopMargins(5e3, 10.0, 20e3, 2.0, (5e3,), (10.0,))
    marginal = SanityReport(results=[Result("edge", "", {}, {}, Verdict.MARGINAL)])
    assert setups.LoopGainResult([], good, SanityReport()).verdict is Verdict.PASS
    assert setups.LoopGainResult([], thin, SanityReport()).verdict is Verdict.MARGINAL
    res = setups.LoopGainResult([], good, marginal)
    assert res.verdict is Verdict.UNKNOWN
    assert "setup marginal" in res.to_markdown()
    assert setups.LoopGainResult([], None, SanityReport()).verdict is Verdict.UNKNOWN


def test_impedance_netlist_shape():
    s = setups.ImpedanceSetup(caps_rail=[setups.Cap(10e-6, 5e-3, 0.5e-9, count=2)],
                              bead=setups.Bead(0.05, 1e-6, 100.0, 1e-12), transfer=True)
    net = s.netlist()
    assert "Iinj 0 rail 0 AC {inj}" in net and ".step param inj list 1 0" in net
    assert "Rser=0" in net


@needs_ltspice
def test_ac_loop_gain_matches_analytic(tmp_path):
    s = setups.LoopGainSetup(body=setups.body_from_netlist(FIXTURES / "vm_buck_averaged.net"), **COMMON)
    f, t = setups.loop_gain_from_ac(run(s.ac_netlist(1e3, 200e3, 50), tmp_path, "ac"), "out")
    assert np.allclose(t, vm_buck_t(f), rtol=1e-2)
    lm = measure.loop_margins(f, t)
    assert lm.crossover_hz == pytest.approx(4981, rel=0.01)
    assert lm.phase_margin_deg == pytest.approx(88.0, abs=0.5)
    assert lm.gain_margin_db == pytest.approx(11.8, abs=0.3)


@needs_ltspice
def test_ac_loop_gain_with_cff_matches_analytic(tmp_path):
    # Cff 1 nF across Rtop 10k: zero 15.9 kHz, pole 87.6 kHz. Breaking only Rtop reported GM 11.4 dB.
    body = setups.body_from_netlist(FIXTURES / "vm_buck_averaged.net") + "\nCff out fb 1n"
    s = setups.LoopGainSetup(body=body, **COMMON)
    f, t = setups.loop_gain_from_ac(run(s.ac_netlist(1e3, 200e3, 50), tmp_path, "cff"), "out")
    assert np.allclose(t, vm_buck_cff_t(f, 1e-9), rtol=1e-2)
    lm = measure.loop_margins(f, t)
    exact = measure.loop_margins(f, vm_buck_cff_t(f, 1e-9))
    assert lm.crossover_hz == pytest.approx(exact.crossover_hz, rel=0.01)
    assert lm.gain_margin_db == pytest.approx(exact.gain_margin_db, abs=0.2)
    assert exact.gain_margin_db == pytest.approx(7.26, abs=0.1)


@needs_ltspice
def test_switching_injection_with_cff_matches_analytic(tmp_path):
    body = setups.body_from_netlist(FIXTURES / "vm_buck_switching.net") + "\nCff out fb 1n"
    s = setups.LoopGainSetup(body=body, sw_node="sw", amplitude_v=5e-3, t_settle_s=1e-3, **COMMON)
    for f in setups.injection_frequencies(4e3, 40e3, 3, 500e3):
        r = run(s.netlist(f), tmp_path, f"cff_{f:.0f}")
        p = setups.measure_loop_gain_point(r, s, f)
        expected = vm_buck_cff_t(np.array([f]), 1e-9)[0]
        assert p.mag_db == pytest.approx(20 * math.log10(abs(expected)), abs=0.3)
        assert p.phase_deg == pytest.approx(math.degrees(np.angle(expected)), abs=2.0)


@needs_ltspice
def test_switching_injection_matches_averaged_ac(tmp_path):
    s = setups.LoopGainSetup(body=setups.body_from_netlist(FIXTURES / "vm_buck_switching.net"), sw_node="sw",
                             amplitude_v=5e-3, t_settle_s=1e-3, **COMMON)
    freqs = setups.injection_frequencies(2e3, 80e3, 7, 500e3)
    res = setups.run_loop_gain(s, freqs, tmp_path, max_workers=3, refine=3, linearity=True)
    assert res.report.ok, res.to_markdown()
    lin = [r for r in res.report.results if r.name == "loop gain linearity"]
    assert lin and lin[0].verdict is Verdict.PASS
    assert "f_c interpolated between measured points" in res.to_markdown()
    for p in res.points:
        expected = vm_buck_t(np.array([p.f_hz]))[0]
        tol_db, tol_deg = (0.2, 1.0) if p.f_hz < 50e3 else (0.5, 3.0)
        assert p.mag_db == pytest.approx(20 * math.log10(abs(expected)), abs=tol_db)
        assert p.phase_deg == pytest.approx(math.degrees(np.angle(expected)), abs=tol_deg)
    assert res.margins.crossover_hz == pytest.approx(4981, rel=0.02)
    assert res.margins.phase_margin_deg == pytest.approx(88.0, abs=1.0)
    assert res.margins.gain_margin_db == pytest.approx(11.8, abs=1.5)
    assert res.margins_result().verdict is Verdict.PASS


@needs_ltspice
def test_quantized_switch_edges_are_flagged(tmp_path):
    body = setups.body_from_netlist(FIXTURES / "vm_buck_switching.net").replace("tanh(5*", "tanh(200*")
    s = setups.LoopGainSetup(body=body, sw_node="sw", amplitude_v=5e-3, t_settle_s=1e-3, **COMMON)
    r = run(s.netlist(12e3), tmp_path, "stiff")
    rep = check_run(r, "sw", 500e3, t_start_s=1e-3)
    flagged = [x for x in rep.results if x.name.startswith("switch edge resolution")]
    assert flagged and flagged[0].verdict is Verdict.MARGINAL


@needs_ltspice
def test_load_step_ring_estimates_phase_margin_of_a_standard_loop(tmp_path):
    # cm_loop_averaged is an integrator times one pole: the standard second-order loop where PM ~ 100 zeta holds
    body = setups.body_from_netlist(FIXTURES / "cm_loop_averaged.net")
    lg = setups.LoopGainSetup(body=body, top_resistor="Rtop", out_node="out", fsw_hz=1e6, c_out_f=10e-6,
                              slew_up_a_per_s=1e6, slew_down_a_per_s=1e6)
    f, t = setups.loop_gain_from_ac(run(lg.ac_netlist(100, 1e6, 50), tmp_path, "ac"), "out")
    pm = measure.loop_margins(f, t).phase_margin_deg
    assert pm == pytest.approx(35.0, abs=1.0)
    ls = setups.LoadStepSetup(body=body, out_node="out", i_from_a=0.0, i_to_a=0.3, t_step_s=200e-6,
                              t_stop_s=600e-6, t_back_s=400e-6, edge_s=100e-9, max_step_s=50e-9)
    res = setups.run_load_step(ls, tmp_path)
    assert res.report.ok
    down, up = res.steps
    assert down.peak_dev < 0 < up.peak_dev
    for sr in res.steps:
        assert sr.pm_deg_est == pytest.approx(pm, abs=6.0)
        assert sr.ring_hz == pytest.approx(measure.loop_margins(f, t).crossover_hz, rel=0.15)
    rings = [r for r in res.results if r.name == "ring-down after step"]
    assert [r.verdict for r in rings] == [Verdict.MARGINAL, Verdict.MARGINAL]
    assert "PM_est ~ 100 zeta" in res.to_markdown() and "informational" in res.to_markdown()
    assert res.verdict is Verdict.MARGINAL


@needs_ltspice
def test_switching_load_step_and_startup(tmp_path):
    body = setups.body_from_netlist(FIXTURES / "vm_buck_switching.net")
    ls = setups.LoadStepSetup(body=body, out_node="out", i_from_a=0.0, i_to_a=1.0, t_step_s=1e-3, t_stop_s=1.4e-3,
                              edge_s=1e-6, fsw_hz=500e3, sw_node="sw")
    res = setups.run_load_step(ls, tmp_path)
    assert res.report.ok, res.to_markdown()
    assert res.steps[0].peak_dev < -5e-3
    assert res.steps[0].final == pytest.approx(3.3, abs=0.02)
    su = setups.StartupSetup(body=body, in_node="vin", out_node="out", vin_v=5.0, ramp_s=200e-6, t_stop_s=1.5e-3,
                             v_target_v=3.3, input_source="Vin", fsw_hz=500e3, sw_node="sw")
    assert "Vbr_ramp vin 0 PWL(0 0 0.0002 5)" in su.netlist()
    windup = setups.run_startup(su, tmp_path)
    assert windup.metrics.overshoot_pct > 20
    assert windup.results[0].verdict is Verdict.FAIL
    assert windup.verdict is not Verdict.PASS
    clamp = "Dclamp comp vclamp DIDEAL\nVclamp vclamp 0 2.6\n.model DIDEAL D(Ron=0.1 Roff=1e9 Vfwd=0)"
    su.body = body + "\n" + clamp
    st = setups.run_startup(su, tmp_path, name="startup_clamped")
    assert st.metrics.restarts == 0 and st.metrics.t_reg_s is not None
    assert st.metrics.final_v == pytest.approx(3.3, abs=0.05)
    assert st.report.ok, st.to_markdown()
    assert st.metrics.overshoot_pct == pytest.approx(23.5, abs=2.0)
    assert st.verdict is Verdict.FAIL
    su.body = su.body.replace("Vref ref 0 0.6", "Vref ref 0 PWL(0 0 300u 0.6)")
    soft = setups.run_startup(su, tmp_path, name="startup_soft")
    assert soft.metrics.overshoot_pct < 1.0
    assert soft.verdict is Verdict.PASS, soft.to_markdown()


@needs_ltspice
def test_pdn_impedance_matches_analytic(tmp_path):
    caps_rail = [setups.Cap(10e-6, 5e-3, 0.5e-9, count=2), setups.Cap(100e-9, 30e-3, 0.3e-9, count=4)]
    caps_src = [setups.Cap(22e-6, 5e-3, 1e-9)]
    bead = setups.Bead(0.05, 1e-6, 100.0, 1e-12)
    s = setups.ImpedanceSetup(caps_rail=caps_rail, bead=bead, caps_src=caps_src, source_r_ohm=10e-3,
                              source_l_h=5e-9, f_start_hz=1e3, f_stop_hz=1e9, transfer=True)
    res = setups.run_impedance(s, tmp_path, z_target_ohm=0.1)
    w = 2 * np.pi * res.f_hz

    def zcap(c: setups.Cap) -> np.ndarray:
        return (1 / (1j * w * c.c_f) + c.esr_ohm + 1j * w * c.esl_h) / c.count

    def par(*zs: np.ndarray) -> np.ndarray:
        return 1 / sum(1 / z for z in zs)

    up = par(10e-3 + 1j * w * 5e-9, *[zcap(c) for c in caps_src])
    zb = 0.05 + par(1j * w * 1e-6, np.full_like(w, 100.0, dtype=complex), 1 / (1j * w * 1e-12))
    expected = par(up + zb, *[zcap(c) for c in caps_rail])
    assert np.allclose(res.z, expected, rtol=5e-3)
    assert res.transfer is not None and res.transfer.shape == res.z.shape
    assert res.summary.peaks
    assert "rail impedance" in res.to_markdown()


@needs_ltspice
@pytest.mark.skipif(not (LOCAL / "NEW_3V3_6p8uH_FCM.asc").exists() or not os.environ.get("BOARDREVIEW_SLOW"),
                    reason="local LTC3633 schematic absent or BOARDREVIEW_SLOW not set (about 1 minute)")
def test_real_ltc3633_loop_gain(tmp_path):
    # 2026-10-06 review, 6.8 uH and 18 uF in FCM at 1.187 MHz: crossover about 169 kHz, PM about 42 deg at 3 mV
    (tmp_path / "fcm.asc").write_bytes((LOCAL / "NEW_3V3_6p8uH_FCM.asc").read_bytes())
    body = setups.body_from_netlist(schematic_to_netlist(tmp_path / "fcm.asc"))
    s = setups.LoopGainSetup(body=body, top_resistor="R48", out_node="OUT1", fsw_hz=1.187e6, c_out_f=18e-6,
                             slew_up_a_per_s=57e3, slew_down_a_per_s=485e3, sw_node="SW1", amplitude_v=1e-3,
                             t_settle_s=500e-6, allow_open=("Pgood1", "Pgood2", "Track/SS1", "Track/SS2"))
    freqs = setups.injection_frequencies(30e3, 200e3, 6, 1.187e6)
    res = setups.run_loop_gain(s, freqs, tmp_path, max_workers=3, refine=2, linearity=True)
    assert res.report.ok, res.to_markdown()
    assert 150e3 < res.margins.crossover_hz < 220e3
    assert 35 < res.margins.phase_margin_deg < 55
