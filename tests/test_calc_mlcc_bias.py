import numpy as np
import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.curves import parse_csv_table, unit_scale
from boardreview.calc.mlcc_bias import bias_curve_from_csv, dielectric_band, mlcc_effective

# Synthetic exports in the three shapes vendor tools produce. Not real part data.
PCT_CHANGE = """Part,SYNTHETIC-100NF-X7R
DC Bias [V],Capacitance Change [%]
0,0
1,-5
2,-12
3.3,-25
5,-40
"""

PCT_OF_NOM = "Voltage (V);C/C0 [%]\n0;100\n2,5;80\n5;55\n"

ABSOLUTE = "Voltage (V)\tCapacitance (uF)\n0\t1.00\n2\t0.80\n4\t0.55\n"


def test_dielectric_codes():
    assert dielectric_band("X7R") == (-55.0, 125.0, -0.15, 0.15)
    assert dielectric_band("X5R") == (-55.0, 85.0, -0.15, 0.15)
    assert dielectric_band("X7S") == (-55.0, 125.0, -0.22, 0.22)
    assert dielectric_band("Y5V") == (-30.0, 85.0, -0.82, 0.22)
    lo, hi, d_lo, d_hi = dielectric_band("C0G")
    assert (lo, hi) == (-55.0, 125.0) and d_hi == pytest.approx(0.003)
    with pytest.raises(ValueError):
        dielectric_band("Q9Q")


def test_parse_percent_change_curve():
    v, k = bias_curve_from_csv(PCT_CHANGE)
    assert list(v) == [0, 1, 2, 3.3, 5]
    assert k[3] == pytest.approx(0.75)


def test_parse_percent_of_nominal_with_decimal_comma():
    v, k = bias_curve_from_csv(PCT_OF_NOM)
    assert v[1] == pytest.approx(2.5) and k[1] == pytest.approx(0.80)


def test_parse_absolute_curve_in_uf():
    headers, data = parse_csv_table(ABSOLUTE)
    assert unit_scale(headers[1], "F") == 1e-6
    v, k = bias_curve_from_csv(ABSOLUTE, c_nom_f=1e-6)
    assert k[-1] == pytest.approx(0.55)


def test_worst_low_100nf_x7r_at_3v3():
    v, k = bias_curve_from_csv(PCT_CHANGE)
    r = mlcc_effective(100e-9, "X7R", 0.10, v_bias_v=3.3, curve_v=v, curve_ratio=k, c_required_f=50e-9)
    # 100 nF * 0.90 * 0.75 * 0.85
    assert r.outputs["c_low"].value == pytest.approx(57.375e-9, rel=1e-9)
    assert r.outputs["c_high"].value == pytest.approx(100e-9 * 1.10 * 0.75 * 1.15, rel=1e-9)
    assert r.verdict is Verdict.PASS


def test_interpolates_between_curve_points():
    v, k = bias_curve_from_csv(PCT_CHANGE)
    r = mlcc_effective(100e-9, "X7R", 0.0, v_bias_v=1.5, curve_v=v, curve_ratio=k)
    assert r.outputs["k_bias"].value == pytest.approx(1 - 0.085)


def test_class2_without_curve_is_unknown():
    r = mlcc_effective(10e-6, "X5R", 0.2, v_bias_v=3.3, c_required_f=1e-6)
    assert r.verdict is Verdict.UNKNOWN


def test_operating_range_beyond_rating_fails():
    r = mlcc_effective(10e-6, "X5R", 0.2, t_min_c=-40, t_max_c=105)
    assert r.verdict is Verdict.FAIL


def test_c0g_ppm_band_and_aging():
    r = mlcc_effective(10e-12, "C0G", 0.05, t_min_c=-40, t_max_c=85, aging_frac=0.0)
    assert r.outputs["c_low"].value == pytest.approx(10e-12 * 0.95 * (1 - 30e-6 * 65), rel=1e-12)
    r2 = mlcc_effective(1e-6, "X7R", 0.1, aging_frac=0.05)
    assert r2.outputs["c_low"].value == pytest.approx(1e-6 * 0.9 * 0.85 * 0.95)


def test_curve_must_be_sorted_for_interp():
    v, k = bias_curve_from_csv("DC Bias [V],Capacitance Change [%]\n5,-40\n0,0\n2,-12\n")
    assert np.all(np.diff(v) > 0)
