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
DAMPER = Cap(1e-6, esr_ohm=1.0, esl_h=0.4e-9)

# Synthetic bead, not real part data: RDC 45 mohm in series with 270 nH || 170 ohm. Columns computed by hand from
# R = RDC + Rac (wL)^2/(Rac^2 + (wL)^2) and X = Rac^2 wL/(Rac^2 + (wL)^2). R includes RDC, as vendor exports do.
BEAD_CSV = """Frequency [MHz],R [Ohm],X [Ohm]
0.1,0.0451693,0.169646
0.2,0.0456772,0.339291
0.5,0.0492322,0.848209
0.8,0.055834,1.35708
0.9,0.0587116,1.52669
0.95,0.0602773,1.61149
0.9671,0.0608322,1.64049
1,0.0619276,1.69629
1.05,0.0636625,1.78109
1.1,0.065482,1.86588
1.2,0.0693747,2.03546
1.5,0.0830823,2.54412
2,0.11269,3.39157
5,0.467181,8.46124
10,1.72123,16.7973
20,6.5573,32.6295
50,33.9317,67.9149
100,84.8678,84.9998
200,135.931,68.085
500,163.48,32.7553
1000,168.355,16.8661
"""


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


def test_damper_on_a_spec_point_bead_is_not_a_pass():
    r = lc_filter(KPZ, C100N, [F_SW], dampers=[DAMPER])
    assert r.outputs["peak"].value < 3.0
    assert r.verdict is Verdict.MARGINAL
    assert "R/X curve" in r.reason


def test_damper_on_a_characterized_bead_passes():
    r = lc_filter(parse_bead_csv(BEAD_CSV, rdc_ohm=0.045), C100N, [F_SW], dampers=[DAMPER])
    assert r.outputs["peak"].value < 3.0
    assert r.verdict is Verdict.PASS


def test_curve_that_starts_above_the_resonance_is_not_a_pass():
    rows = BEAD_CSV.splitlines()
    from_2mhz = "\n".join(rows[:1] + rows[13:])
    r = lc_filter(parse_bead_csv(from_2mhz, rdc_ohm=0.045), C100N, [F_SW], dampers=[DAMPER])
    assert r.verdict is Verdict.MARGINAL
    assert "not characterized" in r.reason


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


def test_bead_curve_r_includes_rdc_and_sets_the_peak():
    curve = parse_bead_csv(BEAD_CSV, rdc_ohm=0.045, part="synthetic")
    z = curve.z(np.array([100e3, 1e6, 100e6]))
    assert z.real == pytest.approx([0.0451693, 0.0619276, 84.8678], rel=1e-9)
    assert z.imag == pytest.approx([0.169646, 1.69629, 84.9998], rel=1e-9)
    assert curve.l_low_h() == pytest.approx(270e-9, rel=1e-4)
    w = 2 * math.pi * 0.9671e6
    zc = complex(0.02, w * 0.4e-9 - 1 / (w * 100e-9))
    expected_db = 20 * math.log10(abs(zc / (complex(0.0608322, 1.64049) + zc)))
    assert expected_db == pytest.approx(26.158, abs=1e-3)
    r = lc_filter(curve, C100N, [F_SW])
    assert r.outputs["f_peak"].value == pytest.approx(0.9671e6, rel=0.01)
    assert r.outputs["peak"].value == pytest.approx(expected_db, abs=0.15)
    assert r.verdict is Verdict.FAIL


def test_export_with_rdc_subtracted_is_flagged():
    rows = BEAD_CSV.splitlines()
    minus_rdc = "\n".join(rows[:1] + [f"{f},{float(r) - 0.045:.6g},{x}" for f, r, x in (ln.split(",") for ln in rows[1:])])
    assert "subtracts RDC" in parse_bead_csv(minus_rdc, rdc_ohm=0.045).note
    assert "subtracts RDC" not in parse_bead_csv(BEAD_CSV, rdc_ohm=0.045).note


def test_below_the_curve_r_falls_to_rdc():
    rows = BEAD_CSV.splitlines()
    curve = parse_bead_csv("\n".join(rows[:1] + rows[8:]), rdc_ohm=0.045)
    assert curve.z(np.array([100e3]))[0].real == pytest.approx(0.045)
    assert curve.z(np.array([100e3]))[0].imag == pytest.approx(1.69629 * 0.1, rel=1e-9)
