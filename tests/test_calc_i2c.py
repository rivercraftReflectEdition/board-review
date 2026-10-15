import math

import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.i2c import i2c_pullup_range, i2c_rise_time


def test_rise_constant_is_ln_7_over_3():
    # UM10204 Rev 7.0 p. 50: t2 - t1 = (1.2039729 - 0.3566749) RC.
    assert math.log(0.7 / 0.3) == pytest.approx(0.8473, abs=1e-4)


def test_rise_time_4k7_100pf():
    fast = i2c_rise_time(4.7e3, 100e-12, "fast")
    assert fast.outputs["tr"].value == pytest.approx(398.23e-9, abs=0.01e-9)
    assert fast.verdict is Verdict.FAIL
    assert i2c_rise_time(4.7e3, 100e-12, "standard").verdict is Verdict.PASS


def test_rise_time_marginal_near_limit():
    assert i2c_rise_time(1.7e3, 200e-12, "fast").verdict is Verdict.MARGINAL


def test_pullup_range_3v3_fast_200pf():
    r = i2c_pullup_range(3.3, 200e-12, "fast", r_pullup_ohm=1.5e3)
    assert r.outputs["rp_min"].value == pytest.approx(2.9 / 3e-3)
    assert r.outputs["rp_max"].value == pytest.approx(300e-9 / (0.8473 * 200e-12))
    assert r.verdict is Verdict.PASS


def test_pullup_range_low_vdd_uses_0v2_vdd_at_2ma():
    r = i2c_pullup_range(1.8, 100e-12, "fast", r_pullup_ohm=470.0)
    assert r.outputs["rp_min"].value == pytest.approx(1.44 / 2e-3)
    assert r.verdict is Verdict.FAIL


def test_no_valid_pullup_and_cb_limit():
    # Fast-mode at 5 V: Rp(min) = 4.6 V/3 mA = 1533 ohm, Rp(max) = 300 ns/(0.8473*390 pF) = 908 ohm.
    r = i2c_pullup_range(5.0, 390e-12, "fast")
    assert r.outputs["rp_min"].value > r.outputs["rp_max"].value
    assert r.verdict is Verdict.FAIL
    assert i2c_pullup_range(3.3, 450e-12, "fast").verdict is Verdict.FAIL
