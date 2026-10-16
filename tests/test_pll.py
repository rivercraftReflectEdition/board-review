"""Plan W19 to W23, with independent nodal solutions of the passive network."""

import json
import math
from itertools import product

import numpy as np
import pytest
from scipy.optimize import brentq

from boardreview.calc.base import Verdict, plain_problems
from boardreview.calc.pll import loop_filter_check, loop_filter_design


def _parts(result):
    return {key: q.value for key, q in result.outputs.items() if key.startswith(("c1_", "c2_", "r2_", "r3_", "c3_"))}


def _nodal(f_hz, icp_a=.005, kvco_hz_per_v=30e6, n=100, **parts):
    s = 2j * math.pi * f_hz
    y = s * parts["c1_f"] + 1 / (parts["r2_ohm"] + 1 / (s * parts["c2_f"]))
    if "r3_ohm" in parts:
        r3, c3 = parts["r3_ohm"], parts["c3_f"]
        matrix = np.array([[y + 1/r3, -1/r3], [-1/r3, 1/r3 + s*c3]])
        z = np.linalg.solve(matrix, np.array([1, 0]))[1]
    else:
        z = 1 / y
    return icp_a * kvco_hz_per_v * z / (n * s)


def _independent_metrics(**parts):
    fc = brentq(lambda f: abs(_nodal(f, **parts)) - 1, 1, 1e9, xtol=1e-7)
    g = _nodal(fc, **parts)
    phase = math.degrees(math.atan2(g.imag, g.real))
    if phase > 0:
        phase -= 360
    return fc, 180 + phase, 20 * math.log10(abs(_nodal(10e6, **parts)))


@pytest.fixture
def w20():
    return _parts(loop_filter_design(.005, 30e6, 100, 100e3, 45))


def test_w19_banerjee_second_order():
    # SNAA106C May 2017, printed pp.342 to 343.
    result = loop_filter_design(.001, 60e6, 39200, 10e3, 49.2, gamma=1.024)
    assert result.outputs["c1_f"].value == pytest.approx(.145e-9, abs=.0005e-9)
    assert result.outputs["c2_f"].value == pytest.approx(.906e-9, abs=.0005e-9)
    assert result.outputs["r2_ohm"].value == pytest.approx(47.78e3, abs=25)
    assert result.verdict is Verdict.INFO
    assert plain_problems(result) == []


def test_w20_second_order_design_and_check(w20):
    assert w20 == pytest.approx(dict(c1_f=1.574e-9, c2_f=7.599e-9, r2_ohm=505.6), rel=4e-4, abs=0)
    expected = _independent_metrics(**w20)
    assert expected == pytest.approx((100e3, 45, -72.3), abs=.05)
    result = loop_filter_check(.005, 30e6, 100, **w20, f_offset_hz=10e6, pm_min_deg=45, context="worst_case")
    assert [result.outputs[k].value for k in ("fc_hz", "pm_deg", "att_offset_db")] == pytest.approx(expected, rel=1e-10)
    assert result.verdict is Verdict.PASS


@pytest.mark.parametrize("gain,fc,pm", [(30e6,101.6e3,47.0), (20e6,73.9e3,46.0), (45e6,139.3e3,45.2)])
def test_w21_rounded_parts_and_vco_gain(gain, fc, pm):
    parts = dict(r2_ohm=510, c1_f=1.5e-9, c2_f=8.2e-9)
    result = loop_filter_check(.005, gain, 100, **parts)
    independent = _independent_metrics(kvco_hz_per_v=gain, **parts)
    assert result.outputs["fc_hz"].value == pytest.approx(fc, abs=.06e3)
    assert result.outputs["pm_deg"].value == pytest.approx(pm, abs=.06)
    assert result.outputs["fc_hz"].value == pytest.approx(independent[0], rel=1e-10)


def test_w21_x7r_bias_loss_is_marginal():
    result = loop_filter_check(.005, 30e6, 100, 510, 1.5e-9, 8.2e-9,
                               capacitor_bias_factor={"c2": .7}, pm_min_deg=45, pm_fail_deg=35)
    assert result.outputs["pm_deg"].value == pytest.approx(40.7, abs=.06)
    assert result.verdict is Verdict.MARGINAL


def test_w22_third_order_design_and_loaded_check():
    result = loop_filter_design(.005, 30e6, 100, 100e3, 45, order=3, t31=.4)
    parts = _parts(result)
    assert parts == pytest.approx(dict(c1_f=713.4e-12, c2_f=8.732e-9, c3_f=166.2e-12,
                                      r2_ohm=447.7, r3_ohm=1777), rel=3e-4, abs=0)
    independent = _independent_metrics(**parts)
    assert independent[0] == pytest.approx(100e3, abs=.001)
    assert independent[1] == pytest.approx(45, abs=1e-7)
    assert independent[2] == pytest.approx(-90.9, abs=.05)
    check = loop_filter_check(.005, 30e6, 100, **parts, f_pfd_hz=10e6)
    assert check.outputs["att_pfd_db"].value == pytest.approx(independent[2], abs=1e-8)
    assert check.outputs["pm_deg"].value == pytest.approx(independent[1], abs=1e-8)
    assert plain_problems(result) == plain_problems(check) == []


def test_w23_naive_extra_pole_loses_margin(w20):
    parts = dict(w20, r3_ohm=1000, c3_f=157e-12)
    independent = _independent_metrics(**parts)
    result = loop_filter_check(.005, 30e6, 100, **parts, f_offset_hz=10e6, pm_min_deg=45, pm_fail_deg=35)
    assert independent[0] == pytest.approx(97.3e3, abs=50)
    assert independent[1] == pytest.approx(38.1, abs=.05)
    assert independent[2] == pytest.approx(-92.3, abs=.05)
    assert result.outputs["fc_hz"].value == pytest.approx(97.3e3, abs=.05e3)
    assert result.outputs["pm_deg"].value == pytest.approx(38.1, abs=.05)
    assert result.outputs["att_offset_db"].value == pytest.approx(-92.3, abs=.05)
    assert result.verdict is Verdict.MARGINAL


def test_tolerance_and_bias_endpoints_against_nodal_solutions():
    result = loop_filter_check(.005, [20e6, 30e6, 45e6], 100, 510, 1.5e-9, 8.2e-9,
                               component_tolerance_frac={"r2": .01, "c1": .05, "c2": .1},
                               capacitor_bias_factor={"c2": (.7, .9)}, f_offset_hz=10e6)
    expected = [_independent_metrics(kvco_hz_per_v=k, r2_ohm=r, c1_f=c1, c2_f=c2)
                for k,r,c1,c2 in product([20e6,30e6,45e6], [504.9,515.1],
                                        [1.425e-9,1.575e-9], [8.2e-9*.9*.7,8.2e-9*1.1*.9])]
    assert result.outputs["corners"].value == 24
    assert result.outputs["pm_deg"].value == pytest.approx(min(x[1] for x in expected), abs=1e-8)
    assert result.outputs["fc_min_hz"].value == pytest.approx(min(x[0] for x in expected), rel=1e-10)
    assert result.outputs["fc_max_hz"].value == pytest.approx(max(x[0] for x in expected), rel=1e-10)
    assert result.outputs["att_offset_db"].value == pytest.approx(max(x[2] for x in expected), abs=1e-8)
    assert result.inputs["c2_bias_min"].value == .7
    assert result.inputs["r2_tolerance"].value == .01


def test_third_order_tolerances_and_bias_loss_against_nodal_solutions():
    parts = dict(c1_f=713.4e-12, c2_f=8.732e-9, c3_f=166.2e-12, r2_ohm=447.7, r3_ohm=1777)
    result = loop_filter_check(.005, [20e6, 45e6], 100, **parts, component_tolerance_frac=.05,
                               capacitor_bias_factor={"c3": .8}, f_offset_hz=10e6)
    independent = []
    for gain, factors in product([20e6, 45e6], product([.95, 1.05], repeat=5)):
        corner = {p: v*k*(.8 if p == "c3_f" else 1) for (p,v), k in zip(parts.items(), factors)}
        independent.append(_independent_metrics(kvco_hz_per_v=gain, **corner))
    assert result.outputs["corners"].value == 64
    assert result.outputs["pm_deg"].value == pytest.approx(min(c[1] for c in independent), abs=1e-8)
    assert result.outputs["att_offset_db"].value == pytest.approx(max(c[2] for c in independent), abs=1e-8)
    assert plain_problems(result) == []


def test_negative_margin_is_not_wrapped_to_a_positive_number():
    parts = dict(c1_f=1.5e-9, c2_f=8.2e-9, r2_ohm=510, r3_ohm=1e5, c3_f=10e-9)
    expected = _independent_metrics(**parts)
    result = loop_filter_check(.005, 30e6, 100, **parts, pm_min_deg=0, context="worst_case")
    assert result.outputs["pm_deg"].value == pytest.approx(expected[1], abs=1e-8)
    assert result.outputs["pm_deg"].value == pytest.approx(-77.12, abs=.01)
    assert result.verdict is Verdict.FAIL and plain_problems(result) == []
    assert any(y < -180 for s in result.plots[0].series if s.unit == "deg" for y in s.y)


@pytest.mark.parametrize("order,gamma,t31", [(2,.8,.4), (2,1.5,.4), (3,.8,.2), (3,1.5,.6)])
def test_other_synthesis_shapes_reach_the_requested_operating_point(order, gamma, t31):
    result = loop_filter_design(.001, 50e6, 200, 25e3, 50, order=order, gamma=gamma, t31=t31)
    fc, pm, _ = _independent_metrics(icp_a=.001, kvco_hz_per_v=50e6, n=200, **_parts(result))
    assert fc == pytest.approx(25e3, abs=1e-6)
    assert pm == pytest.approx(50, abs=1e-8)
    assert result.plots and plain_problems(result) == []


@pytest.mark.parametrize("kwargs,verdict", [
    ({}, Verdict.INFO),
    ({"pm_min_deg": 40, "context": "worst_case"}, Verdict.PASS),
    ({"pm_min_deg": 40}, Verdict.UNKNOWN),
    ({"pm_min_deg": 50}, Verdict.FAIL),
    ({"pm_min_deg": 50, "pm_fail_deg": 40}, Verdict.MARGINAL),
    ({"pm_min_deg": 60, "pm_fail_deg": 50}, Verdict.FAIL),
    ({"pm_min_deg": 40, "att_max_db": -80, "f_offset_hz": 10e6}, Verdict.FAIL),
    ({"att_max_db": -60, "f_offset_hz": 10e6}, Verdict.INFO),
    ({"pm_min_deg": 40, "att_max_db": -60, "f_offset_hz": 10e6, "context": "worst_case"}, Verdict.PASS),
])
def test_verdicts_and_plain_results(w20, kwargs, verdict):
    result = loop_filter_check(.005, 30e6, 100, **w20, **kwargs)
    assert result.verdict is verdict
    assert plain_problems(result) == []
    assert result.context
    json.dumps(result.to_dict(), allow_nan=False)


def test_missing_limits_are_explicit_and_not_baked_in(w20):
    result = loop_filter_check(.005, 30e6, 100, **w20, f_offset_hz=10e6)
    assert "board requirement or datasheet" in result.summary
    assert "spur budget or datasheet" in result.summary
    assert "pm_min_deg" not in result.inputs and "att_max_db" not in result.inputs


def test_bode_curves_and_markers_match_nodal_solution(w20):
    result = loop_filter_check(.005, 30e6, 100, **w20, f_offset_hz=10e6, pm_min_deg=45, att_max_db=-70)
    plot = result.plots[0]
    for f, db, phase in zip(plot.x, plot.series[0].y, plot.series[1].y):
        g = _nodal(f, **w20)
        assert db == pytest.approx(20*math.log10(abs(g)), abs=1e-8)
        assert phase == pytest.approx(math.degrees(math.atan2(g.imag,g.real)), abs=1e-8)
    assert plot.x_log and any(m.y == -180 for m in plot.markers)
    assert any(m.x == pytest.approx(100e3, rel=1e-9) and m.y == 0 for m in plot.markers)
    assert any(m.x == 10e6 for m in plot.markers)
    g = _nodal(10e6, **w20)
    assert result.outputs["reference_transfer_db"].value == pytest.approx(20*math.log10(abs(g/(1+g))), abs=1e-8)


@pytest.mark.parametrize("kw", [
    {"icp_a": 0}, {"kvco_hz_per_v": -1}, {"n": 0}, {"fc_hz": math.nan},
    {"pm_deg": 90}, {"pm_deg": 0}, {"order": 4}, {"gamma": 0}, {"order": 3, "t31": 0},
])
def test_bad_design_inputs(kw):
    args = dict(icp_a=.005, kvco_hz_per_v=30e6, n=100, fc_hz=100e3, pm_deg=45)
    args.update(kw)
    with pytest.raises(ValueError):
        loop_filter_design(**args)


@pytest.mark.parametrize("kw", [
    {"r3_ohm": 1000}, {"c3_f": 1e-9}, {"c1_f": -1}, {"kvco_hz_per_v": []},
    {"kvco_hz_per_v": [30e6, math.inf]}, {"pm_fail_deg": 35}, {"pm_min_deg":45, "pm_fail_deg":50},
    {"att_max_db": -70}, {"f_offset_hz": 0}, {"f_offset_hz": 1e6, "f_pfd_hz": 1e6},
    {"component_tolerance_frac": 1}, {"component_tolerance_frac": {"c4": .1}},
    {"capacitor_bias_factor": {"r2": .5}}, {"capacitor_bias_factor": {"c2": (1,.7)}},
    {"capacitor_bias_factor": 0}, {"pm_min_deg": math.nan},
])
def test_bad_check_inputs(kw):
    args = dict(icp_a=.005, kvco_hz_per_v=30e6, n=100, r2_ohm=510, c1_f=1.5e-9, c2_f=8.2e-9)
    args.update(kw)
    with pytest.raises(ValueError):
        loop_filter_check(**args)
