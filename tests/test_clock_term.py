"""Clock worked examples W11 to W13 and explicit-limit result branches."""

import json
import math

import numpy as np
import pytest

from boardreview.calc import clock_term as ct
from boardreview.calc.base import Verdict, plain_problems


RX = dict(rx_cm_min_v=0.5, rx_cm_max_v=1.5, rx_vid_min_v=0.1, rx_vid_max_v=0.45,
          rx_abs_min_v=0.0, rx_abs_max_v=2.0)
AC_LIMITS = dict(xc_limit_ohm=5.0, fc_limit_hz=100e3, droop_limit_frac=0.01, dt_limit_s=100e-12)


def _term(**changes):
    args = dict(standard="LVPECL", vcc_v=3.3, z0_ohm=50,
                fitted_ohm={"r_up": 127, "r_down": 82.5}, error_limit_frac=0.02, context="worst_case")
    args.update(changes)
    return ct.termination(**args)


def _compat(**changes):
    args = dict(voh_v=1.375, vol_v=1.025, **RX, context="worst_case")
    args.update(changes)
    return ct.compat(**args)


def _ac(**changes):
    args = dict(c_f=100e-9, r_bias_ohm=50, f_clk_hz=10e6, duty=0.5, v_pp_v=3.3,
                slew_v_per_s=2.64e9, run_bits=5, bit_rate_hz=1.25e9, **AC_LIMITS, context="worst_case")
    args.update(changes)
    return ct.ac_coupling(**args)


SAMPLES = {
    "calc.clock_term.termination": [
        _term, lambda: _term(fitted_ohm={"r_up": 150, "r_down": 82.5}),
        lambda: _term(error_limit_frac=None), lambda: _term(fitted_ohm={"r_up": 127}),
        lambda: _term(context="nominal"), lambda: _term(fitted_ohm=None),
        lambda: ct.termination("LVPECL", 3.3, 50, topology="pull_down", output_cm_v=2,
                               pull_down_current_a=2 / 150),
        lambda: ct.termination("LP-HCSL", 3.3, 50, 17, fitted_ohm={"r_series": 33, "r_shunt": 50},
                               error_limit_frac=0.02, context="worst_case"),
    ],
    "calc.clock_term.compat": [
        _compat, lambda: _compat(voh_v=1.6), lambda: _compat(rx_cm_min_v=None),
        lambda: ct.compat(1.375, 1.025), lambda: _compat(context="example"),
        lambda: _compat(voh_v=[1.375, 1.4], vol_v=[1.025, 1.0], r_source_ohm=20,
                        r_bias_ohm=80, bias_v=1.2),
    ],
    "calc.clock_term.ac_coupling": [
        _ac, lambda: _ac(c_f=1e-9), lambda: _ac(xc_limit_ohm=None),
        lambda: _ac(**dict.fromkeys(AC_LIMITS)), lambda: _ac(context="ideal"),
        lambda: _ac(duty=0.45), lambda: _ac(run_bits=0, bit_rate_hz=None),
    ],
}


@pytest.mark.parametrize("vcc,up,down", [(3.3, 126.923076923, 82.5), (2.5, 250, 62.5)])
def test_w11_lvpecl_thevenin(vcc, up, down):
    # AN-828 Rev A p.3; AN-953 2017-03-06 p.17. Verify voltage and impedance independently.
    r = ct.termination("LVPECL", vcc, 50)
    actual_up, actual_down = r.outputs["r_up"].value, r.outputs["r_down"].value
    assert actual_up == pytest.approx(up, abs=1e-8)
    assert actual_down == pytest.approx(down, abs=1e-10)
    assert actual_up * actual_down / (actual_up + actual_down) == pytest.approx(50, abs=1e-10)
    assert vcc * actual_down / (actual_up + actual_down) == pytest.approx(vcc - 2, abs=1e-10)
    assert r.verdict is Verdict.INFO


def test_w11_lvcmos_source_series():
    # AN-953 2017-03-06 p.1: 50 ohm line less 7 ohm output resistance.
    r = ct.termination("LVCMOS", 3.3, 50, 7)
    assert r.outputs["r_series"].value == pytest.approx(43, abs=1e-12)


@pytest.mark.parametrize("standard,z0,rout,key,expected", [
    ("LVDS", 50, None, "r_diff", 100), ("HCSL", 50, None, "r_shunt", 50),
    ("CML", 50, None, "r_shunt", 50), ("LP-HCSL", 50, 17, "r_series", 33),
    ("LP-HCSL", 42.5, 15.5, "r_series", 27),
])
def test_other_output_standards(standard, z0, rout, key, expected):
    # Plan table 9.1; the 85 ohm LP-HCSL example explicitly supplies its effective Rout.
    r = ct.termination(standard, 3.3, z0, rout)
    assert r.outputs[key].value == pytest.approx(expected, abs=1e-12)


def test_pull_down_uses_driver_operating_point():
    r = ct.termination("LVPECL", 3.3, 50, topology="pull_down", output_cm_v=2,
                       pull_down_current_a=2 / 150, fitted_ohm={"r_down": 150},
                       error_limit_frac=0.01, context="worst_case")
    assert r.outputs["r_down"].value == pytest.approx(150, abs=1e-10)
    assert r.verdict is Verdict.PASS
    assert any("Si534x" in a for a in r.assumptions)


def test_fitted_values_and_limit_are_both_required():
    assert _term().verdict is Verdict.PASS
    assert _term(fitted_ohm={"r_up": 150, "r_down": 82.5}).verdict is Verdict.FAIL
    assert _term(fitted_ohm={"r_up": 127}).verdict is Verdict.UNKNOWN
    assert _term(error_limit_frac=None).verdict is Verdict.INFO
    assert _term(fitted_ohm=None).verdict is Verdict.INFO
    assert _term(context="nominal").verdict is Verdict.UNKNOWN
    assert _term().outputs["error_pct"].value == pytest.approx(100 * (127 / (165 / 1.3) - 1), abs=1e-10)


def test_resistor_error_boundary_is_inclusive():
    args = dict(standard="LVDS", vcc_v=3.3, z0_ohm=50, fitted_ohm={"r_diff": 102}, context="worst_case")
    assert ct.termination(**args, error_limit_frac=0.02).verdict is Verdict.PASS
    assert ct.termination(**args, error_limit_frac=0.019).verdict is Verdict.FAIL


def test_lp_hcsl_double_termination_is_identified():
    r = ct.termination("LP-HCSL", 3.3, 50, 17, fitted_ohm={"r_series": 33, "r_shunt": 50},
                       error_limit_frac=0.02, context="worst_case")
    assert r.verdict is Verdict.FAIL
    assert "end termination" in r.summary


def test_vendor_network_overrides_generic_values_and_allows_integrated_series():
    # Synthetic vendor target, not a collected vendor model.
    r = ct.termination("LP-HCSL", 1.8, 50, vendor_values_ohm={"r_series": 0},
                       fitted_ohm={"r_series": 0}, error_limit_frac=0, context="worst_case")
    assert r.verdict is Verdict.PASS
    assert r.outputs["error_pct"].value == 0
    r = ct.termination("LP-HCSL", 1.8, 50, vendor_values_ohm={"r_series": 0},
                       fitted_ohm={"r_series": 1}, error_limit_frac=0, context="worst_case")
    assert r.verdict is Verdict.FAIL
    json.dumps(r.to_dict(), allow_nan=False)
    assert plain_problems(r) == []


def test_w12_reported_swing_envelope():
    # Plan W12 quotes AN-828 Rev A p.11 Fig.11: 626 mVpp per leg versus 450 mVpp maximum.
    # UNSURE: source figure/text is absent offline. This tests its quoted envelope, not its divider or conclusion.
    r = _compat(voh_v=1.513, vol_v=0.887)
    assert r.outputs["vid_max"].value == pytest.approx(0.626, abs=1e-12)
    assert r.outputs["margin_vid_max"].value == pytest.approx(-0.176, abs=1e-12)
    assert r.verdict is Verdict.FAIL


def test_compat_divider_loading_and_common_mode():
    # Synthetic 100 ohm series with a 200/200 ohm divider to 3.3 V and ground.
    # KCL: (Vout - Vin)/100 + Vout/200 + (Vout - 3.3)/200 = 0.
    r = _compat(voh_v=2.4, vol_v=1.6, r_source_ohm=100, r_bias_ohm=100, bias_v=1.65,
                rx_cm_max_v=2.0, rx_abs_max_v=2.5)
    high, low = (2.4 / 100 + 3.3 / 200) / 0.02, (1.6 / 100 + 3.3 / 200) / 0.02
    assert r.outputs["cm_max"].value == pytest.approx((high + low) / 2, abs=1e-12)
    assert r.outputs["vid_min"].value == pytest.approx(high - low, abs=1e-12)
    assert r.verdict is Verdict.PASS


def test_compat_ac_coupling_replaces_common_mode():
    r = _compat(voh_v=2.4, vol_v=1.6, r_source_ohm=100, r_bias_ohm=100, bias_v=1.2, ac_coupled=True)
    assert r.outputs["cm_min"].value == pytest.approx(1.2, abs=1e-12)
    assert r.outputs["vid_max"].value == pytest.approx(0.4, abs=1e-12)
    assert r.outputs["abs_max"].value == pytest.approx(1.4, abs=1e-12)
    assert r.verdict is Verdict.PASS


def test_compat_uses_every_paired_corner():
    r = _compat(voh_v=[1.375, 1.6], vol_v=[1.025, 1.0])
    assert r.outputs["vid_min"].value == pytest.approx(0.35, abs=1e-12)
    assert r.outputs["vid_max"].value == pytest.approx(0.6, abs=1e-12)
    assert r.verdict is Verdict.FAIL


@pytest.mark.parametrize("limit,value", [("rx_cm_min_v", 1.3), ("rx_cm_max_v", 1.1),
                                        ("rx_vid_min_v", 0.4), ("rx_vid_max_v", 0.3),
                                        ("rx_abs_min_v", 1.1), ("rx_abs_max_v", 1.3)])
def test_each_receiver_limit_can_fail(limit, value):
    r = _compat(**{limit: value})
    assert r.verdict is Verdict.FAIL


def test_compat_missing_limits_and_nominal_inputs_stay_unknown():
    assert ct.compat(1.375, 1.025).verdict is Verdict.UNKNOWN
    assert _compat(rx_cm_min_v=None).verdict is Verdict.UNKNOWN
    assert _compat(context="nominal").verdict is Verdict.UNKNOWN
    assert _compat(rx_vid_max_v=0.5, voh_v=1.5, vol_v=1.0).verdict is Verdict.PASS


def test_w13_corner_and_reactance():
    # W13, AN1051 Rev 0.3 sec.2.2 p.7; independently evaluated RC and capacitor impedance.
    r = _ac()
    assert r.outputs["fc_hz"].value == pytest.approx(31830.9886, rel=1e-8)
    assert r.outputs["xc_ohm"].value == pytest.approx(0.159154943, rel=1e-8)
    assert r.verdict is Verdict.PASS
    small = _ac(c_f=1e-9)
    assert small.outputs["xc_ohm"].value == pytest.approx(15.9154943, rel=1e-8)
    assert small.verdict is Verdict.FAIL
    assert _ac(r_bias_ohm=5e3).outputs["fc_hz"].value == pytest.approx(318.309886, rel=1e-8)


def test_w13_duty_offset_and_run_length():
    # W13, SCAA112 2010-11 pp.2, 6 to 7; offset/edge shift/droop are derived in the plan.
    r = _ac(duty=0.45, f_clk_hz=100e6)
    assert r.outputs["dv_v"].value == pytest.approx(-0.165, abs=1e-12)
    assert r.outputs["dt_s"].value == pytest.approx(62.5e-12, abs=1e-22)
    assert r.outputs["duty_shift_frac"].value == pytest.approx(0.0125, abs=1e-12)
    assert r.outputs["run_s"].value == pytest.approx(4e-9, abs=1e-20)
    assert r.outputs["droop"].value == pytest.approx(0.000799680085, rel=1e-9)


def test_source_resistance_and_bias_offset():
    r = _ac(r_source_ohm=50, duty=0.45, bias_offset_v=0.1)
    assert r.outputs["tau_s"].value == pytest.approx(10e-6, abs=1e-16)
    assert r.outputs["dv_v"].value == pytest.approx(0.0175, abs=1e-12)
    assert r.outputs["dt_s"].value == pytest.approx(0.0175 / 2.64e9, rel=1e-12)


@pytest.mark.parametrize("limit,value", [("xc_limit_ohm", 0.1), ("fc_limit_hz", 10e3),
                                        ("droop_limit_frac", 0.0001), ("dt_limit_s", 1e-12)])
def test_each_coupling_limit_can_fail(limit, value):
    assert _ac(duty=0.45, **{limit: value}).verdict is Verdict.FAIL


def test_ac_coupling_requires_explicit_limits():
    assert _ac(**dict.fromkeys(AC_LIMITS)).verdict is Verdict.INFO
    assert _ac(xc_limit_ohm=None).verdict is Verdict.UNKNOWN
    assert _ac(context="nominal").verdict is Verdict.UNKNOWN
    assert _ac(run_bits=0, bit_rate_hz=None).outputs["droop"].value == 0


def test_ac_plots_match_independent_transfer_and_decay():
    r = _ac(r_source_ohm=50)
    p, decay = r.plots
    index = p.x.index(10e6)
    zc = 1 / (2j * math.pi * 10e6 * 100e-9)
    expected_db = 20 * math.log10(abs(50 / (50 + 50 + zc)))
    assert p.series[0].y[index] == pytest.approx(expected_db, abs=1e-10)
    assert decay.series[0].y[-1] == pytest.approx(math.exp(-4e-9 / 10e-6), abs=1e-12)


@pytest.mark.parametrize("make", [fn for fns in SAMPLES.values() for fn in fns])
def test_results_are_plain_and_serializable(make):
    r = make()
    assert plain_problems(r) == [], (r.verdict, r.summary)
    assert r.context and r.key
    json.dumps(r.to_dict(), allow_nan=False)
    for plot in r.plots:
        assert plot.caption and any(c.isdigit() for c in plot.caption)
        assert np.all(np.isfinite(plot.series[0].y))


@pytest.mark.parametrize("make", [
    lambda: ct.termination("other", 3.3, 50), lambda: _term(vcc_v=0), lambda: _term(vcc_v=2),
    lambda: _term(error_limit_frac=-1), lambda: _term(vtt_v=float("nan")),
    lambda: _term(fitted_ohm={"typo": 100}), lambda: _term(fitted_ohm={"r_up": -1}),
    lambda: _term(vendor_values_ohm={}), lambda: _term(topology="pull_down"),
    lambda: ct.termination("LVDS", 3.3, 50, topology="pull_down"),
    lambda: ct.termination("LVCMOS", 3.3, 50), lambda: ct.termination("LP-HCSL", 3.3, 50, 60),
    lambda: _compat(voh_v=[]), lambda: _compat(voh_v=float("nan")),
    lambda: _compat(vol_v=2), lambda: _compat(voh_v=[[1.3]]), lambda: _compat(rx_vid_min_v=-1),
    lambda: _compat(rx_cm_min_v=2), lambda: _compat(r_bias_ohm=0), lambda: _compat(ac_coupled=True),
    lambda: _ac(c_f=0), lambda: _ac(r_bias_ohm=float("inf")), lambda: _ac(duty=1),
    lambda: _ac(run_bits=-1), lambda: _ac(run_bits=0.5), lambda: _ac(bit_rate_hz=None),
    lambda: _ac(dt_limit_s=-1), lambda: _ac(droop_limit_frac=1.1), lambda: _ac(slew_v_per_s=0),
])
def test_invalid_inputs_are_rejected(make):
    with pytest.raises(ValueError):
        make()
