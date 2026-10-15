import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.thermal import buck_ic_dissipation, junction_temp


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
