import math
import shutil
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import brentq

from boardreview.calc.base import Verdict
from boardreview.sim import measure as m
from boardreview.sim.rawfile import read_raw
from boardreview.sim.runner import LTspice, run

FIXTURES = Path(__file__).parent / "fixtures" / "sim"
LOCAL = Path(__file__).parent / "local" / "ltc3633"
needs_ltspice = pytest.mark.skipif(not LTspice().available(), reason="LTspice not installed")
RNG = np.random.default_rng(7)


def jittered_time(t_end: float, n: int) -> np.ndarray:
    """SPICE-like variable step: uniform grid with random jitter, sorted."""
    t = np.linspace(0, t_end, n) + RNG.uniform(-0.3, 0.3, n) * t_end / n
    t[0], t[-1] = 0.0, t_end
    return np.sort(t)


def pwm(t: np.ndarray, f_hz: float, duty: float, high: float = 4.0) -> np.ndarray:
    return np.where((t * f_hz) % 1.0 < duty, high, 0.0)


def second_order_step(t: np.ndarray, zeta: float, f0_hz: float) -> np.ndarray:
    w = 2 * np.pi * f0_hz
    wd = w * math.sqrt(1 - zeta ** 2)
    return 1 - np.exp(-zeta * w * t) / math.sqrt(1 - zeta ** 2) * np.sin(wd * t + math.acos(zeta))


def test_dominant_frequency_with_trend_offset_and_jitter():
    t = jittered_time(1e-3, 200_000)
    y = 3.3 + 0.02 * np.sin(2 * np.pi * 123.4e3 * t) + 50.0 * t
    tone = m.dominant_frequency(t, y)
    assert tone.f_hz == pytest.approx(123.4e3, rel=1e-3)
    assert tone.amplitude == pytest.approx(0.02, rel=0.03)


def test_dominant_frequency_band_limit_finds_weaker_tone():
    t = np.linspace(0, 2e-3, 400_001)
    y = np.sin(2 * np.pi * 1.2e6 * t) + 0.05 * np.sin(2 * np.pi * 32.4e3 * t)
    assert m.dominant_frequency(t, y).f_hz == pytest.approx(1.2e6, rel=1e-3)
    assert m.dominant_frequency(t, y, f_max_hz=200e3).f_hz == pytest.approx(32.4e3, rel=2e-3)


@pytest.mark.parametrize("f_hz", [1.187e6, 747e3])
def test_switching_frequency_from_edges(f_hz):
    t = jittered_time(100e-6, 400_000)
    y = pwm(t, f_hz, 0.83) + RNG.normal(0, 0.05, len(t))
    sw = m.switching_frequency(t, y)
    assert sw.f_hz == pytest.approx(f_hz, rel=1e-3)
    assert sw.duty == pytest.approx(0.83, abs=0.01)
    assert sw.regular


def test_switching_frequency_flags_relaxation_cycle():
    t = np.linspace(0, 200e-6, 800_001)
    burst = (t * 31e3) % 1.0 < 0.8
    y = np.where(burst, pwm(t, 1.25e6, 0.93), 0.0)
    sw = m.switching_frequency(t, y)
    assert not sw.regular


def test_crossings_hysteresis_ignores_noise_chatter():
    t = np.linspace(0, 1e-3, 100_001)
    y = -np.cos(2 * np.pi * 10e3 * t) + RNG.normal(0, 0.02, len(t))
    assert len(m.crossings(t, y, 0.0, hysteresis=0.2)) == 10


def test_box_average_removes_switching():
    t = np.linspace(0, 50e-6, 200_001)
    tb, yb = m.box_average(t, pwm(t, 1e6, 0.25), 1e-6)
    assert np.allclose(yb[(tb > 2e-6) & (tb < 48e-6)], 1.0, atol=0.02)


def test_lockin_amplitude_and_phase():
    t = jittered_time(1e-3, 100_000)
    y = 0.5 + 0.003 * np.cos(2 * np.pi * 50e3 * t + 0.7) + 0.01 * np.sin(2 * np.pi * 1.187e6 * t)
    ph = m.lockin(t, y, 50e3, t_start_s=0.2e-3)
    assert abs(ph) == pytest.approx(0.003, rel=0.01)
    assert np.angle(ph) == pytest.approx(0.7, abs=0.01)


def test_zeta_formula_worked_example():
    # r = 0.5: ln 2 / sqrt(4 pi^2 + ln^2 2) = 0.6931 / 6.3212 = 0.1097
    assert m.zeta_from_decay_ratio(0.5) == pytest.approx(0.1097, abs=1e-4)
    assert m.pm_from_zeta(0.1097) == pytest.approx(10.97, abs=0.01)


def _standard_loop(f: np.ndarray, zeta: float, fn_hz: float) -> np.ndarray:
    s = 2j * np.pi * f
    wn = 2 * np.pi * fn_hz
    return wn ** 2 / (s * (s + 2 * zeta * wn))


@pytest.mark.parametrize("zeta", [0.1, 0.3, 0.5, 0.6])
def test_pm_rule_of_thumb_against_the_exact_standard_loop(zeta):
    # T = wn^2 / (s (s + 2 zeta wn)): PM = atan(2 zeta / sqrt(sqrt(1 + 4 zeta^4) - 2 zeta^2)) (Franklin et al. 6.4)
    exact = math.degrees(math.atan(2 * zeta / math.sqrt(math.sqrt(1 + 4 * zeta ** 4) - 2 * zeta ** 2)))
    f = np.logspace(2, 6, 4001)
    assert m.loop_margins(f, _standard_loop(f, zeta, 10e3)).phase_margin_deg == pytest.approx(exact, abs=0.05)
    assert m.pm_from_zeta(zeta) == pytest.approx(exact, abs=3.5)


def _ring(t: np.ndarray, t_step: float, zeta: float, fn_hz: float) -> np.ndarray:
    x = np.clip(t - t_step, 0, None)
    wn = 2 * np.pi * fn_hz
    return 3.3 - 0.05 * np.exp(-zeta * wn * x) * np.sin(wn * math.sqrt(1 - zeta ** 2) * x)


def test_ring_pm_is_informational_because_a_zero_breaks_the_rule():
    # T = (0.9 - 100 s) / (s^2 + 101 s + 0.1): 1 + T = (s^2 + s + 1) / den, so zeta = 0.5, yet PM = 8.98 deg
    num, den = [-100.0, 0.9], [1.0, 101.0, 0.1]
    assert np.allclose(np.polyadd(den, num), [1.0, 1.0, 1.0])

    def loop(w: float) -> complex:
        return np.polyval(num, 1j * w) / np.polyval(den, 1j * w)

    wc = brentq(lambda w: abs(loop(w)) - 1, 1e-4, 10)
    assert 180 + math.degrees(np.angle(loop(wc))) == pytest.approx(8.98, abs=0.01)
    t = np.linspace(0, 1e-3, 400_001)
    sr = m.step_response(t, _ring(t, 1e-4, 0.5, 10e3), 1e-4, min_peak_frac=0.01)
    assert sr.zeta == pytest.approx(0.5, rel=0.02)
    assert sr.pm_deg_est == pytest.approx(50.0, abs=1.0)
    res = m.ring_result(sr)
    assert res.verdict is Verdict.INFO
    assert "informational" in res.outputs["PM_est"].note
    assert any("Franklin" in r for r in res.refs)


def test_ring_verdict_rests_on_the_measured_damping():
    t = np.linspace(0, 1e-3, 400_001)
    sr = m.step_response(t, _ring(t, 1e-4, 0.35, 10e3), 1e-4, min_peak_frac=0.01)
    assert m.ring_result(sr).verdict is Verdict.MARGINAL
    assert m.ring_result(m.step_response(t, _ring(t, 1e-4, 0.0, 10e3), 1e-4)).verdict is Verdict.FAIL
    flat = m.step_response(t, np.full_like(t, 3.3) + 1e-4 * (t > 1e-4), 1e-4)
    assert m.ring_result(flat).verdict is Verdict.INFO


@pytest.mark.parametrize("zeta", [0.1, 0.3])
def test_step_response_recovers_zeta_and_overshoot(zeta):
    t = jittered_time(1e-3, 300_000)
    t_step = 100e-6
    y = np.where(t < t_step, 0.0, second_order_step(np.clip(t - t_step, 0, None), zeta, 20e3))
    sr = m.step_response(t, y, t_step, final=1.0, initial=0.0)
    expected_os = 100 * math.exp(-math.pi * zeta / math.sqrt(1 - zeta ** 2))
    assert sr.overshoot_pct == pytest.approx(expected_os, rel=0.01)
    assert sr.zeta == pytest.approx(zeta, rel=0.02)
    assert sr.ring_hz == pytest.approx(20e3 * math.sqrt(1 - zeta ** 2), rel=0.01)


def test_load_step_with_switching_ripple_needs_smoothing():
    fsw = 1.187e6
    t = np.linspace(0, 400e-6, 2_000_001)
    t_step = 50e-6
    ring = np.where(t < t_step, 0.0, -0.05 * np.exp(-0.15 * 2 * np.pi * 60e3 * (t - t_step))
                    * np.sin(2 * np.pi * 60e3 * math.sqrt(1 - 0.15 ** 2) * (t - t_step)))
    y = 3.3 + ring + 0.004 * (((t * fsw) % 1.0) - 0.5)
    sr = m.step_response(t, y, t_step, smooth_period_s=1 / fsw)
    assert sr.overshoot_pct is None
    assert sr.peak_dev < 0
    assert sr.zeta == pytest.approx(0.15, rel=0.05)
    res = m.ring_result(sr)
    assert res.verdict is Verdict.FAIL
    assert "ln(1/r)" in res.formula


def _type1_two_pole(f: np.ndarray, k: float, p1: float, p2: float) -> np.ndarray:
    s = 2j * np.pi * f
    return k / (s * (1 + s / (2 * np.pi * p1)) * (1 + s / (2 * np.pi * p2)))


def test_loop_margins_against_exact_roots():
    k, p1, p2 = 2 * np.pi * 50e3, 80e3, 400e3
    f = np.logspace(3, 7, 61)
    lm = m.loop_margins(f, _type1_two_pole(f, k, p1, p2))
    fc = brentq(lambda x: abs(_type1_two_pole(np.array([x]), k, p1, p2)[0]) - 1, 1e3, 1e7)
    pm = 180 + math.degrees(np.angle(_type1_two_pole(np.array([fc]), k, p1, p2)[0]))
    f180 = math.sqrt(p1 * p2)
    gm = -20 * math.log10(abs(_type1_two_pole(np.array([f180]), k, p1, p2)[0]))
    assert lm.crossover_hz == pytest.approx(fc, rel=0.01)
    assert lm.phase_margin_deg == pytest.approx(pm, abs=0.5)
    assert lm.phase_crossover_hz == pytest.approx(f180, rel=0.01)
    assert lm.gain_margin_db == pytest.approx(gm, abs=0.2)
    assert m.margins_result(lm).verdict in (Verdict.PASS, Verdict.MARGINAL)


def test_loop_margins_unstable_loop_fails():
    f = np.logspace(3, 7, 61)
    lm = m.loop_margins(f, _type1_two_pole(f, 2 * np.pi * 2e6, 80e3, 400e3))
    assert lm.phase_margin_deg < 0
    assert m.margins_result(lm).verdict is Verdict.FAIL


def test_impedance_peak_and_q_of_parallel_rlc():
    r, l, c = 2.0, 1e-6, 10e-6
    f = np.logspace(3, 7, 801)
    w = 2 * np.pi * f
    z = 1 / (1 / r + 1 / (1j * w * l) + 1j * w * c)
    s = m.impedance_summary(f, m.impedance(z), z_target_ohm=0.5)
    f0 = 1 / (2 * np.pi * math.sqrt(l * c))
    assert s.f_at_max_hz == pytest.approx(f0, rel=0.01)
    assert s.max_z_ohm == pytest.approx(r, rel=0.01)
    assert s.peaks[0].q == pytest.approx(r * math.sqrt(c / l), rel=0.03)
    (lo, hi), = s.bands_over_target_hz
    assert lo < f0 < hi


def test_steady_state_detects_drift():
    t = np.linspace(0, 1e-3, 10_001)
    flat = 3.3 + 0.001 * np.sin(2 * np.pi * 1e5 * t)
    assert m.steady_state(t, flat, 0.1e-3).settled
    assert not m.steady_state(t, flat + 100 * t, 0.1e-3).settled


@needs_ltspice
def test_ltspice_series_rlc_ring_matches_theory(tmp_path):
    shutil.copy(FIXTURES / "lc_step.net", tmp_path / "lc.net")
    raw = run(tmp_path / "lc.net").raw()
    for k, c in enumerate((1e-6, 4e-6)):
        t, v = raw.axis(step=k), raw.get("V(out)", step=k)
        zeta = (0.5 + 1e-3) / 2 * math.sqrt(c / 10e-6)
        sr = m.step_response(t, v, 2e-6, initial=0.0, final=1.0)
        assert sr.zeta == pytest.approx(zeta, rel=0.03)
        assert sr.ring_hz == pytest.approx(1 / (2 * np.pi * math.sqrt(10e-6 * c)) * math.sqrt(1 - zeta ** 2), rel=0.01)
        assert m.dominant_frequency(t, v, t_start_s=5e-6).f_hz == pytest.approx(sr.ring_hz, rel=0.02)


@pytest.mark.skipif(not (LOCAL / "NEW_3V3_6p8uH_FCM.raw").exists(), reason="local LTC3633 raw not present")
def test_real_ltc3633_switching_frequency_and_rail():
    raw = read_raw(LOCAL / "NEW_3V3_6p8uH_FCM.raw")
    t = raw.axis()
    sw = m.switching_frequency(t, raw["V(sw1)"], t_start_s=500e-6)
    assert sw.f_hz == pytest.approx(1.187e6, rel=0.005)
    assert m.mean_value(t, raw["V(out1)"], 500e-6) == pytest.approx(3.30, abs=0.03)
    unc, period = m.edge_timing_uncertainty(t, raw["V(sw1)"], t_start_s=500e-6)
    assert unc / period < 2e-3


def test_lockin_is_not_biased_by_drift():
    t = np.linspace(0, 1e-3, 200_001)
    y = 3.3 + 40.0 * t + 0.005 * np.cos(2 * np.pi * 6e3 * t - 0.3)
    ph = m.lockin(t, y, 6e3)
    assert abs(ph) == pytest.approx(0.005, rel=1e-3)
    assert np.angle(ph) == pytest.approx(-0.3, abs=1e-3)


def test_edge_timing_uncertainty_step_vs_smooth_edges():
    t = np.arange(0, 100e-6, 40e-9)
    unc, period = m.edge_timing_uncertainty(t, pwm(t, 500e3, 0.66))
    assert period == pytest.approx(2e-6, rel=1e-3)
    assert unc == pytest.approx(40e-9, rel=1e-6)
    tri = np.abs(((t * 500e3) % 1.0) - 0.5) * 2
    smooth = 2.5 * (1 + np.tanh(12.5 * (0.66 - tri)))
    assert m.edge_timing_uncertainty(t, smooth)[0] == 0.0
