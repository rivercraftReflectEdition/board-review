import math

import numpy as np
import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.loop import (
    Delay,
    Divider,
    DoublePole,
    Gain,
    Integrator,
    IntegratorZero,
    ParallelRC,
    Pole,
    Zero,
    bode,
    cff_lead,
    loop_response,
    margins,
    peaking_at_crossover,
    peaking_at_f180,
)

# Sauron rev1 LTC3633A ch1 feedback divider R48 54.9k (top) / R50 12.1k (bottom).
R48, R50 = 54.9e3, 12.1e3

# Fitted Sauron model, board 2: G in A/V referred to VOUT, Zout = 16.6 ohm || 4 caps (35.1 uF).
SAURON = [
    Gain(40.6, "A/V"),
    IntegratorZero(30e3),
    Pole(113.1e3),
    DoublePole(1.185e6 / 2, 0.64),
    Delay(0.3e-6),
    ParallelRC(16.6, 35.1e-6),
]


def test_cff_22pf():
    r = cff_lead(R48, R50, 22e-12, 100e3)
    assert r.outputs["fz"].value == pytest.approx(131.8e3, abs=0.1e3)
    assert r.outputs["fp"].value == pytest.approx(729.6e3, abs=0.1e3)
    # Exact lead is 29.39 deg; 29.3 comes from rounding fz, fp to 132k, 730k.
    assert r.outputs["lead_at_f"].value == pytest.approx(29.3, abs=0.1)


def test_cff_47pf():
    r = cff_lead(R48, R50, 47e-12, 100e3)
    assert r.outputs["fz"].value == pytest.approx(61.7e3, abs=0.05e3)
    assert r.outputs["fp"].value == pytest.approx(341.5e3, abs=0.5e3)
    assert r.outputs["lead_at_f"].value == pytest.approx(42.0, abs=0.05)


@pytest.mark.parametrize("cff", [1e-12, 22e-12, 47e-12, 1e-9])
def test_cff_max_lead_depends_only_on_divider(cff):
    r = cff_lead(R48, R50, cff, 100e3)
    assert r.outputs["lead_max"].value == pytest.approx(44.0, abs=0.05)
    fz, fp = r.outputs["fz"].value, r.outputs["fp"].value
    assert fp / fz == pytest.approx((R48 + R50) / R50, rel=1e-12)


def test_cff_lead_matches_divider_block_phase():
    blk = Divider(R48, R50, 47e-12)
    assert float(blk.phase_deg(np.array([100e3]))[0]) == pytest.approx(cff_lead(R48, R50, 47e-12, 100e3).outputs["lead_at_f"].value)
    assert abs(blk.response(np.array([1.0]))[0]) == pytest.approx(R50 / (R48 + R50), rel=1e-9)


def test_sauron_four_caps_no_cff_is_unstable():
    r = margins(SAURON)
    assert r.outputs["fc"].value == pytest.approx(125e3, abs=1.5e3)
    assert r.outputs["pm"].value == pytest.approx(-3.9, abs=0.1)
    assert r.outputs["gm"].value < 0
    assert r.verdict is Verdict.FAIL


def test_sauron_four_caps_22pf():
    r = margins(SAURON + [Divider(R48, R50, 22e-12, include_dc=False)])
    assert r.outputs["fc"].value == pytest.approx(163e3, abs=1.5e3)
    assert r.outputs["pm"].value == pytest.approx(20.4, abs=0.1)
    assert r.outputs["gm"].value == pytest.approx(3.86, abs=0.05)
    assert r.outputs["peak_fc"].value == pytest.approx(1 / (2 * math.sin(math.radians(20.4448) / 2)), rel=1e-3)
    assert r.verdict is Verdict.FAIL


def test_sauron_47pf_pushes_crossover_into_the_delay_and_loses_margin():
    r = margins(SAURON + [Divider(R48, R50, 47e-12, include_dc=False)])
    assert r.outputs["fc"].value > 200e3
    assert r.outputs["pm"].value < 0


def test_hand_checked_phase_at_125k():
    _, ph = loop_response(SAURON, 125e3)
    # Zout -89.87, (1 + wz/s) -13.50, pole -47.86, double pole -19.03, delay -13.50 deg.
    assert ph[0] == pytest.approx(-183.77, abs=0.05)


def test_integrator_loop_has_90_deg_margin():
    r = margins([Integrator(10e3)], 10, 1e6)
    assert r.outputs["fc"].value == pytest.approx(10e3, rel=1e-6)
    assert r.outputs["pm"].value == pytest.approx(90.0, abs=1e-9)
    assert r.outputs["n_phase_crossings"].value == 0
    assert r.verdict is Verdict.PASS


def test_sweep_ending_before_the_phase_crossing_is_unknown():
    # Phase = -90 - 360 f Td reaches -180 at f = 90/(360 Td) = 2250 Hz, past the 2 kHz sweep.
    r = margins([Integrator(1000), Delay(1 / 9000)], 10, 2e3)
    assert r.outputs["pm"].value == pytest.approx(50.0, abs=1e-6)
    assert r.verdict is Verdict.UNKNOWN
    assert "f_stop" in r.reason


def test_integrator_with_delay_gain_margin_worked():
    # |T(2250 Hz)| = 1000/2250, so GM = 20 log10(2.25) = 7.044 dB: under 10 dB, over 6 dB.
    r = margins([Integrator(1000), Delay(1 / 9000)], 10, 10e3)
    assert r.outputs["f180"].value == pytest.approx(2250.0, rel=1e-6)
    assert r.outputs["gm"].value == pytest.approx(20 * math.log10(2.25), abs=1e-6)
    assert r.verdict is Verdict.MARGINAL


def test_gain_margin_bounded_above_the_sweep_can_pass():
    # No crossing below 1 MHz; above it |T| <= 1000/1e6, so any phase crossing there has GM >= 60 dB.
    r = margins([Integrator(1000), Delay(1e-9)], 10, 1e6)
    assert r.outputs["n_phase_crossings"].value == 0
    assert r.outputs["gm"].value == pytest.approx(60.0, abs=1e-9)
    assert r.verdict is Verdict.PASS


def test_block_without_bounds_and_no_phase_crossing_is_unknown():
    class Opaque:
        def response(self, f_hz):
            return Integrator(1000).response(f_hz)

        def phase_deg(self, f_hz):
            return Integrator(1000).phase_deg(f_hz)

        def params(self):
            return {}

        def text(self):
            return "opaque"

    assert margins([Opaque()], 10, 1e6).verdict is Verdict.UNKNOWN


def test_three_poles_gain_margin_worked():
    # T = K/(1+s/w)^3 crosses -180 at w*sqrt(3), where |T| = K/8; K = 4 gives GM = 6.02 dB.
    r = margins([Gain(4.0), Pole(1e3), Pole(1e3), Pole(1e3)], 1, 1e6, gm_fail_db=3)
    assert r.outputs["f180"].value == pytest.approx(1e3 * math.sqrt(3), rel=1e-6)
    assert r.outputs["gm"].value == pytest.approx(20 * math.log10(2), abs=1e-6)
    assert r.outputs["peak_f180"].value == pytest.approx(2.0, rel=1e-6)


def test_multiple_gain_crossings_are_reported():
    # Flat -6 dB above 1 kHz, then a Q = 20 resonance lifts |T| back above 0 dB: three crossings.
    r = margins([Integrator(1e3), Zero(1e3), DoublePole(100e3, 20.0), Gain(0.5)], 10, 10e6)
    assert r.outputs["fc_1"].value == pytest.approx(1e3 / math.sqrt(3), rel=1e-3)
    assert r.outputs["n_gain_crossings"].value == 3
    assert "3 gain crossings" in r.reason


def test_conditionally_stable_loop_is_marginal():
    # Three integrators then three zeros: phase starts at -270, gain is high there, fc lands with phase lead.
    blocks = [Integrator(1e3), Integrator(1e3), Integrator(1e3), Zero(10.0), Zero(30.0), Zero(100.0), Pole(30e3), Pole(30e3)]
    r = margins(blocks, 0.1, 1e7, gm_min_db=0, gm_fail_db=0, pm_min_deg=0, pm_fail_deg=0)
    assert r.outputs["pm"].value > 0
    assert "conditionally stable" in r.reason
    assert r.verdict is Verdict.MARGINAL


def test_peaking_formulas():
    assert peaking_at_crossover(60.0) == pytest.approx(1.0)
    assert peaking_at_crossover(-1.0) == math.inf
    assert peaking_at_f180(6.0206) == pytest.approx(2.0, rel=1e-4)


def test_bode_grid_and_rhp_zero_phase():
    f, mag, ph = bode([Zero(1e3, rhp=True), Gain(-1.0)], 1, 1e6, 100)
    assert len(f) == 601
    assert ph[np.argmin(abs(f - 1e3))] == pytest.approx(-225.0, abs=0.5)
    assert mag[0] == pytest.approx(0.0, abs=1e-3)
