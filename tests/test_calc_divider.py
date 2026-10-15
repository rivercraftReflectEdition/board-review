import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.divider import divider_output, enable_thresholds, regulator_output

LTC3633A_P3 = "LTC3633A/LTC3633A-1 data sheet Rev B (3633a1fb) p. 3, RUN threshold and leakage"


def run1():
    # Sauron rev1 RUN1: 57.6k top, 27.4k bottom, 1 % resistors. LTC3633A RUN rising 1.18/1.22/1.26 V,
    # falling 0.98/1.01/1.04 V, leakage 0 +-3 uA (Rev B p. 3).
    return enable_thresholds(1.18, 1.22, 1.26, 0.98, 1.01, 1.04, 57.6e3, 27.4e3, r_tol=0.01, i_leak_a=3e-6,
                             vin_min_v=4.03, refs=(LTC3633A_P3,))


def test_run1_nominal_thresholds():
    r = run1()
    assert r.outputs["enable_nom"].value == pytest.approx(3.785, abs=5e-4)
    assert r.outputs["disable_nom"].value == pytest.approx(3.133, abs=5e-4)


def test_run1_worst_enable_is_above_the_4v03_input():
    r = run1()
    assert r.outputs["enable_max"].value == pytest.approx(4.137, abs=5e-4)
    assert r.verdict is Verdict.FAIL


def test_run1_worst_low_corners():
    r = run1()
    # 1.18*(1 + 57.024/27.674) - 3 uA*57.024k and 0.98*(...) - 3 uA*57.024k.
    assert r.outputs["enable_min"].value == pytest.approx(1.18 * (1 + 57.024 / 27.674) - 0.171072, abs=1e-6)
    assert r.outputs["disable_min"].value == pytest.approx(0.98 * (1 + 57.024 / 27.674) - 0.171072, abs=1e-6)


def test_lt8640_4v_rail_worst_high():
    # LT8640 Rev F p. 3: VFB 0.958/0.970/0.982 V over temperature, FB current +-20 nA. R39 12.7k / 3.24k, 1 %.
    r = regulator_output(0.958, 0.970, 0.982, 12.7e3, 3.24e3, r_tol=0.01, i_fb_a=20e-9,
                         refs=("LT8640/LT8640-1 data sheet Rev F p. 3 (VFB, IFB) and p. 17 (FB resistor network)",))
    assert "Rev F p. 3" in r.refs[1]
    assert r.outputs["vout_nom"].value == pytest.approx(0.970 * (1 + 12.7 / 3.24), rel=1e-12)
    assert r.outputs["vout_max"].value == pytest.approx(4.909, abs=5e-4)


def test_regulator_output_limit_check():
    r = regulator_output(0.594, 0.6, 0.606, 54.9e3, 12.1e3, v_out_max_allowed_v=3.40)
    assert r.outputs["vout_nom"].value == pytest.approx(0.6 * 67.0 / 12.1, rel=1e-12)
    assert r.verdict is Verdict.FAIL


def test_divider_output_with_leakage():
    r = divider_output(3.3, 10e3, 10e3, r_tol=0.0, i_leak_a=10e-6)
    assert r.outputs["v_nom"].value == pytest.approx(1.65)
    # Thevenin 5k: +-10 uA moves the tap +-50 mV.
    assert r.outputs["v_max"].value == pytest.approx(1.70)
    assert r.outputs["v_min"].value == pytest.approx(1.60)
