import math

import numpy as np
import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.lc_tank import (
    BeadRLC,
    Cap,
    bead_from_spec,
    damping_options,
    filter_response,
    lc_filter,
    parse_bead_csv,
)

# Sauron L5: TDK KPZ1608SHR121ATD, 120 ohm at 100 MHz, Rdc 45 mohm max, feeding 100 nF on 1V8-SW1-FILT.
# No vendor R/X curve on hand, so the bead comes from its one impedance spec point (UNSURE).
KPZ = bead_from_spec(120.0, 100e6, 0.045, "TDK KPZ1608SHR121ATD")
C100N = Cap(100e-9, esr_ohm=0.02, esl_h=0.4e-9)
F_SW = 1.19e6


def test_bead_from_spec_values():
    assert KPZ.l_h == pytest.approx(120 * math.sqrt(2) / (2 * math.pi * 100e6), rel=1e-12)
    assert abs(KPZ.z(np.array([100e6]))[0] - 0.045) == pytest.approx(120.0, rel=1e-3)
    assert "UNSURE" in KPZ.note


def test_kpz_bead_100nf_peaks_on_the_switcher():
    r = lc_filter(KPZ, C100N, [F_SW])
    assert r.outputs["f0"].value == pytest.approx(1 / (2 * math.pi * math.sqrt(KPZ.l_h * 100e-9)), rel=1e-12)
    assert 0.8e6 < r.outputs["f_peak"].value < 1.2e6
    assert r.outputs["peak"].value > 15.0
    assert r.verdict is Verdict.FAIL
    assert any("UNSURE" in a for a in r.assumptions)


def test_one_ohm_one_uf_damper_fixes_it():
    r = lc_filter(KPZ, C100N, [F_SW], dampers=[Cap(1e-6, esr_ohm=1.0, esl_h=0.4e-9)])
    assert r.outputs["peak"].value < 3.0
    assert r.verdict is Verdict.PASS


def test_peak_away_from_switcher_is_marginal():
    r = lc_filter(KPZ, C100N, [5e6], harmonics=1)
    assert r.verdict is Verdict.MARGINAL


@pytest.mark.parametrize("n", [1.0, 4.0, 10.0])
def test_rc_damper_optimum_matches_formula(n):
    l, c = 1e-6, 1e-6
    opt = damping_options(l, c, n)
    f = np.logspace(4, 6, 8001)

    def peak(rd):
        _, z = filter_response(BeadRLC(l, 0.0), Cap(c), f, [Cap(n * c, rd)])
        return float(np.abs(z).max())

    best = peak(opt["rd_opt"])
    assert best == pytest.approx(opt["zout_peak_opt"], rel=2e-3)
    assert peak(0.8 * opt["rd_opt"]) > best and peak(1.25 * opt["rd_opt"]) > best


def test_series_damping_values():
    o = damping_options(0.25e-6, 100e-9)
    assert o["r0"] == pytest.approx(math.sqrt(2.5))
    assert o["r_series_critical"] == pytest.approx(2 * math.sqrt(2.5))
    assert o["cd"] == pytest.approx(400e-9)


def test_bead_curve_csv_reproduces_the_rlc_model():
    f = np.logspace(5, 9, 41)
    z = KPZ.z(f) - KPZ.rdc_ohm
    text = "Frequency [MHz],R [Ohm],X [Ohm],|Z| [Ohm]\n" + "\n".join(
        f"{fi / 1e6:.6g},{zi.real:.6g},{zi.imag:.6g},{abs(zi):.6g}" for fi, zi in zip(f, z)
    )
    curve = parse_bead_csv(text, rdc_ohm=KPZ.rdc_ohm, part="synthetic")
    assert curve.l_low_h() == pytest.approx(KPZ.l_h, rel=1e-3)
    fc = np.array([300e3, 1e6, 30e6])
    assert np.allclose(curve.z(fc).imag, KPZ.z(fc).imag, rtol=2e-2)
    r1 = lc_filter(curve, C100N, [F_SW])
    r2 = lc_filter(KPZ, C100N, [F_SW])
    assert r1.outputs["f_peak"].value == pytest.approx(r2.outputs["f_peak"].value, rel=0.02)
