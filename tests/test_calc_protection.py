import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.divider import regulator_output
from boardreview.calc.protection import tvs_clamp, tvs_standoff

LT8640 = "LT8640/LT8640-1 data sheet Rev F p. 3 (VFB 0.958 to 0.982 V over temperature)"
RCLAMP = "Semtech RClamp3374N data sheet, revision 7/24/2012, p. 2"


def test_lt8640_4v_rail_against_5v_standoff_is_marginal():
    rail = regulator_output(0.958, 0.970, 0.982, 12.7e3, 3.24e3, r_tol=0.01, refs=(LT8640,))
    v_max = rail.outputs["vout_max"].value
    assert v_max == pytest.approx(4.909, abs=5e-4)
    r = tvs_standoff(v_max, 5.0, refs=(LT8640,))
    assert r.outputs["margin"].value == pytest.approx(0.091, abs=5e-4)
    assert r.verdict is Verdict.MARGINAL


def test_ripple_pushes_rail_over_standoff():
    r = tvs_standoff(4.909, 5.0, ripple_pp_v=0.2)
    assert r.outputs["v_peak"].value == pytest.approx(5.009)
    assert r.verdict is Verdict.FAIL


def test_rail_at_breakdown_fails():
    assert tvs_standoff(5.6, 5.0, v_br_min_v=5.6).verdict is Verdict.FAIL


def test_standoff_pass_with_margin():
    assert tvs_standoff(3.465, 5.0).verdict is Verdict.PASS


def test_rclamp3374n_clamp_interpolation():
    # VC max 5.5 V at 1 A and 10.5 V at 10 A, 8/20 us, any I/O to ground.
    pts = [(1.0, 5.5), (10.0, 10.5), (25.0, 18.0)]
    r = tvs_clamp(4.0, 4.0, pts, refs=(RCLAMP,))
    assert r.outputs["v_clamp"].value == pytest.approx(5.5 + (10.5 - 5.5) / 9 * 3, rel=1e-12)
    assert r.outputs["r_dyn"].value == pytest.approx(5.0 / 9)
    assert r.verdict is Verdict.FAIL


def test_clamp_extrapolates_past_last_point():
    r = tvs_clamp(30.0, 30.0, [(10.0, 10.5), (25.0, 18.0)])
    assert r.outputs["v_clamp"].value == pytest.approx(18.0 + 0.5 * 5.0)
    assert r.verdict is Verdict.PASS
