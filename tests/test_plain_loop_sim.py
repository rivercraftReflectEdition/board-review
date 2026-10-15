"""Loop and simulation Results read plainly: labels, a summary with the key numbers, and words that match the verdict."""

import math

import numpy as np
import pytest

from boardreview.calc import loop
from boardreview.calc.base import Verdict, fmt, plain_problems
from boardreview.sim import measure, sanity, setups


def _sr(**kw) -> measure.StepResponse:
    base = dict(t_step_s=1e-4, initial=3.3, final=3.3, peak_dev=-0.045, t_peak_s=1.08e-4, overshoot_pct=None,
                peaks=((1.08e-4, -0.045), (1.3e-4, 0.02), (1.5e-4, -0.009)), decay_ratio=0.2, ring_hz=20e3,
                zeta=0.25, pm_deg_est=25.0, settle_s=6e-5, band=0.01)
    base.update(kw)
    return measure.StepResponse(**base)


def _ring(zeta: float) -> measure.StepResponse:
    t = np.linspace(0, 2e-3, 40001)
    wn = 2 * math.pi * 10e3
    wd = wn * math.sqrt(1 - zeta ** 2)
    tau = np.clip(t - 1e-4, 0, None)
    y = 3.3 - 0.05 * (t >= 1e-4) * np.exp(-zeta * wn * tau) * np.sin(wd * tau)
    return measure.step_response(t, y, 1e-4)


def _t_loop(f: np.ndarray, blocks) -> np.ndarray:
    t = np.ones_like(f, dtype=complex)
    for b in blocks:
        t = t * b.response(f)
    return t


F = np.logspace(2, 7, 300)
GOOD = [loop.Integrator(20e3), loop.Pole(200e3), loop.Pole(2e6)]
THIN = [loop.Integrator(90e3), loop.Pole(60e3), loop.DoublePole(250e3, 1.2)]
BAD = [loop.Integrator(200e3), loop.DoublePole(150e3, 2.0)]


def _margins(blocks, scale: float = 1.0):
    return measure.margins_result(measure.loop_margins(F, scale * _t_loop(F, blocks)), f_hz=F,
                                  t_loop=scale * _t_loop(F, blocks))


def _square(period_s: float, dt_s: float, n: int = 40, jitter: bool = False):
    edges = np.cumsum([period_s * (1.2 if jitter and k % 2 else 0.8 if jitter else 1.0) for k in range(n)])
    t = np.arange(0, edges[-1], dt_s)
    k = np.searchsorted(edges, t, side="right")
    start = np.concatenate([[0.0], edges])[k]
    length = np.diff(np.concatenate([[0.0], edges]))[np.minimum(k, n - 1)]
    return t, np.where((t - start) < 0.4 * length, 5.0, 0.0)


def _startup(**kw) -> setups.Startup:
    base = dict(t_reg_s=1.2e-3, overshoot_pct=3.0, restarts=0, final_v=3.3, vin_min_after_ramp_v=4.9, monotonic=True)
    base.update(kw)
    return setups.Startup(**base)


SAMPLES = {
    "calc.loop.margins": [
        lambda: loop.margins(GOOD),
        lambda: loop.margins(THIN),
        lambda: loop.margins(BAD),
        lambda: loop.margins([loop.Gain(4.0), loop.Pole(1e3), loop.Pole(1e3), loop.Pole(1e3), loop.Gain(3.0)]),
        lambda: loop.margins([loop.Gain(0.1), loop.Pole(1e3)]),
        lambda: loop.margins([loop.Integrator(1e3), loop.Delay(1e-4)], 10, 2e3),
        lambda: loop.margins([loop.Integrator(30e3), loop.Pole(40e3), loop.Divider(100e3, 22e3, 22e-12)]),
    ],
    "calc.loop.cff_lead": [lambda: loop.cff_lead(100e3, 22e3, 22e-12, 50e3)],
    "sim.measure.ring_result": [
        lambda: measure.ring_result(_ring(0.1)),
        lambda: measure.ring_result(_ring(0.35)),
        lambda: measure.ring_result(_sr(zeta=0.6, pm_deg_est=60.0, decay_ratio=0.02)),
        lambda: measure.ring_result(_sr(decay_ratio=None, ring_hz=None, zeta=None, pm_deg_est=None)),
        lambda: measure.ring_result(_sr(decay_ratio=1.1, zeta=None, pm_deg_est=None)),
    ],
    "sim.measure.settling_result": [
        lambda: measure.settling_result(_sr(), 1e-4),
        lambda: measure.settling_result(_sr(), 2e-5),
        lambda: measure.settling_result(_sr()),
        lambda: measure.settling_result(_sr(settle_s=None), 1e-4),
    ],
    "sim.measure.deviation_result": [
        lambda: measure.deviation_result(_sr(), 0.05),
        lambda: measure.deviation_result(_sr(), 0.03),
        lambda: measure.deviation_result(_sr()),
    ],
    "sim.measure.margins_result": [
        lambda: _margins(GOOD),
        lambda: _margins(THIN),
        lambda: _margins(BAD),
        lambda: _margins(GOOD, 1e-4),
    ],
    "sim.setups.lockin_convergence": [
        lambda: setups.lockin_convergence(1.0 + 0.0j, 1.001 + 0.0j, 50e3),
        lambda: setups.lockin_convergence(1.0 + 0.0j, 1.07 + 0.0j, 50e3),
        lambda: setups.lockin_convergence(1.0 + 0.0j, 1.5 + 0.3j, 50e3),
    ],
    "sim.setups.linearity_result": [
        lambda: setups.linearity_result(60e3, 5e-3, 0.5, 0.12, -0.8),
        lambda: setups.linearity_result(60e3, 5e-3, 0.5, 1.4, 6.0),
    ],
    "sim.setups.startup_result": [
        lambda: setups.startup_result(_startup(), 3.3),
        lambda: setups.startup_result(_startup(monotonic=False), 3.3),
        lambda: setups.startup_result(_startup(overshoot_pct=14.0), 3.3),
        lambda: setups.startup_result(_startup(t_reg_s=None, restarts=3, final_v=1.1), 3.3),
    ],
    "sim.setups.impedance_result": [
        lambda: setups.impedance_result(0.05, 0.031, 180e3),
        lambda: setups.impedance_result(0.02, 0.031, 180e3),
        lambda: setups.impedance_result(None, 0.031, 180e3),
    ],
    "sim.sanity.injection_slew_check": [
        lambda: sanity.injection_slew_check(2e-3, 300e3, 5e6, 5e6, 40e-6),
        lambda: sanity.injection_slew_check(25e-3, 300e3, 5e6, 5e6, 40e-6),
        lambda: sanity.injection_slew_check(50e-3, 300e3, 5e6, 5e6, 40e-6),
        lambda: sanity.injection_slew_check(2e-3, 300e3, -1e6, 5e6, 40e-6),
    ],
    "sim.sanity.switching_frequency_check": [
        lambda: sanity.switching_frequency_check(*_square(2e-6, 2e-8), 500e3),
        lambda: sanity.switching_frequency_check(*_square(2e-6, 2e-8), 400e3),
        lambda: sanity.switching_frequency_check(*_square(2e-6, 2e-8, jitter=True), 500e3),
    ],
    "sim.sanity.edge_resolution_check": [
        lambda: sanity.edge_resolution_check(*_square(2e-6, 1e-8)),
        lambda: sanity.edge_resolution_check(np.linspace(0, 1e-4, 2001), np.full(2001, 3.3)),
        lambda: sanity.edge_resolution_check(*_trapezoid()),
    ],
}


def _trapezoid():
    t = np.arange(0, 80e-6, 1e-9)
    phase = (t % 2e-6) / 2e-6
    y = np.clip(np.minimum(phase, 0.4 - phase + 0.01) * 5.0 / 0.01, 0.0, 5.0)
    return t, y


CASES = [(name, i) for name, fns in SAMPLES.items() for i in range(len(fns))]


@pytest.mark.parametrize("name,i", CASES, ids=[f"{n}[{i}]" for n, i in CASES])
def test_result_reads_plainly(name, i):
    r = SAMPLES[name][i]()
    assert plain_problems(r) == [], (r.verdict, r.summary)
    for k in r.key:
        q = r.quantity(k.name)
        assert math.isfinite(q.value), k.name


@pytest.mark.parametrize("name", [n for n in SAMPLES if len(SAMPLES[n]) > 1])
def test_samples_reach_more_than_one_verdict(name):
    assert len({f().verdict for f in SAMPLES[name]}) > 1


def test_loop_summary_reads_like_the_example():
    r = loop.margins(THIN)
    assert r.verdict is Verdict.MARGINAL
    assert r.summary.startswith("The loop crosses over at 64.2 kHz with 30.2° of phase margin.")
    assert "We want at least 45°, so the rail will ring for a few cycles after each load step" in r.summary
    assert [k["label"] for k in r.key_line()] == ["Phase margin", "Gain margin", "Crossover frequency"]
    assert [k["want"] for k in r.key_line()] == ["45° or more", "10 dB or more", ""]
    assert r.plots[0].caption == ("Read the phase where the gain crosses 0 dB (dashed line, 64.2 kHz): it is 30.2° "
                                  "above -180°.")
    assert r.inputs["b1_f_unity"].label == "Block 1 unity-gain frequency"
    assert "n_gain_crossings" not in {k.name for k in r.key}


def test_sim_margins_target_is_ten_db():
    r = _margins(THIN)
    assert r.inputs["gm_min"].value == 10.0 and "target 10" in r.reason
    assert r.verdict is Verdict.MARGINAL and "10 dB of gain margin" in r.summary


def test_plots_carry_a_caption():
    sr = _ring(0.35)
    t = np.linspace(0, 2e-3, 2001)
    y = 3.3 + 0.0 * t
    plots = [
        loop.margins(THIN).plots[0],
        _margins(THIN).plots[0],
        measure.step_plot(t, y, sr),
        measure.impedance_plot(F, 0.01 + 1j * F * 1e-9, measure.impedance_summary(F, 0.01 + 1j * F * 1e-9, 0.05)),
        setups.startup_plot(t, np.clip(t * 3e3, 0, 3.3), np.full_like(t, 5.0), _startup(), 3.3),
        setups.transfer_plot(F, 1 / (1 + 1j * F / 1e5)),
    ]
    for p in plots:
        assert p.caption and "\u2014" not in p.caption and p.caption.endswith("."), p.title
    assert fmt(_margins(THIN).outputs["f_c"].value, "Hz") in plots[1].caption
