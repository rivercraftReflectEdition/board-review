import math

import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.thermal import buck_ic_dissipation, junction_temp, via_resistance


def test_ltc3633a_datasheet_example_dissipation():
    # LTC3633A Rev B p. 20: 12 V to 1.8 V at 2 A, 2 MHz, RDS(on) 145/70 mohm at 70 C, 2.3 nC, IQ 0.65 mA.
    r = buck_ic_dissipation(12.0, 1.8, 2.0, 0.145, 0.070, 2e6, 2.3e-9, 0.65e-3)
    assert r.outputs["r_sw"].value == pytest.approx(81.3e-3, abs=0.1e-3)
    assert r.outputs["p_total"].value == pytest.approx(0.388, abs=0.001)


def test_ltc3633a_datasheet_example_junction_temperature():
    # Two channels, 0.776 W, thetaJA 43 C/W (QFN), 70 C ambient: Tj about 103 C.
    r = junction_temp(0.776, 43.0, 70.0, 125.0)
    assert r.outputs["tj"].value == pytest.approx(103.4, abs=0.05)
    assert r.verdict is Verdict.PASS
    assert junction_temp(0.776, 43.0, 70.0, 125.0, margin_c=25.0).verdict is Verdict.MARGINAL


def test_junction_temperature_verdicts():
    assert junction_temp(0.5, 43.0, 25.0, 125.0).verdict is Verdict.PASS
    assert junction_temp(1.5, 43.0, 70.0, 125.0).verdict is Verdict.FAIL


def test_via_resistance_0mm3_drill_25um_plating_1mm6_board():
    # By hand: A = pi*(0.15^2 - 0.125^2) mm^2 = 0.021598 mm^2; R1 = 1.6 mm / (390 W/mK * A) = 189.95 C/W.
    r = via_resistance(9, 0.3e-3, 25e-6, 1.6e-3)
    assert r.outputs["r_one"].value == pytest.approx(189.95, abs=0.05)
    assert r.outputs["r_total"].value == pytest.approx(189.95 / 9, abs=0.01)


def test_via_fill_lowers_resistance():
    open_via = via_resistance(1, 0.3e-3, 25e-6, 1.6e-3).outputs["r_one"].value
    filled = via_resistance(1, 0.3e-3, 25e-6, 1.6e-3, k_fill_w_per_mk=390.0).outputs["r_one"].value
    assert filled == pytest.approx(1.6e-3 / (390.0 * math.pi * 0.15e-3**2), rel=1e-9)
    assert filled < open_via
