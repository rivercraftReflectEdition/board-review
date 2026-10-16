"""Converter arithmetic, explicit limits and plain output, using synthetic inputs and plan W38/W39."""

import json
import math

import pytest
from scipy.optimize import brentq

from boardreview.calc.base import Verdict, plain_problems
from boardreview.calc.converter import jesd_lane_rate, sar_rc, sysref


# W37 has no input set in the plan. This is synthetic, not the AD46 worked example.
SAR = dict(n_bits=16, v_ref_v=5.0, t_acq_s=600e-9, c_ext_f=2.7e-9)
KICKBACK = dict(SAR, t_conv_s=700e-9, c_dac_f=30e-12, f_hz=100e3, v_pk_v=2.5)
SAMPLES = {
    "calc.converter.sar_rc": [
        lambda: sar_rc(**SAR),
        lambda: sar_rc(**SAR, r_ohm=18, context="worst_case"),
        lambda: sar_rc(**SAR, r_ohm=22, context="worst_case"),
        lambda: sar_rc(**SAR, r_ohm=18),
        lambda: sar_rc(**SAR, r_ohm=18, c_dac_f=200e-12, c_ratio_min=20),
        lambda: sar_rc(**KICKBACK, r_ohm=18, c_ratio_min=20, context="worst_case"),
        lambda: sar_rc(**dict(KICKBACK, f_hz=1e-6), r_ohm=1000, context="worst_case"),
        lambda: sar_rc(**dict(KICKBACK, f_hz=1e-6)),
    ],
    "calc.converter.jesd_lane_rate": [
        lambda: jesd_lane_rate(2, 16, 1e9, 2, "8b/10b"),
        lambda: jesd_lane_rate(2, 16, 1e9, 2, "8b/10b", lane_max_bps=12.5e9),
        lambda: jesd_lane_rate(2, 16, 1e9, 4, "8b/10b", lane_max_bps=12.5e9, context="worst_case"),
        lambda: jesd_lane_rate(2, 16, 1e9, 4, "8b/10b", lane_max_bps=12.5e9),
        lambda: jesd_lane_rate(2, 16, 1e9, 4, "64b/66b", lane_min_bps=9e9, lane_max_bps=16e9),
        lambda: jesd_lane_rate(2, 16, 1e9, 4, "64b/66b", lane_min_bps=5e9),
    ],
    "calc.converter.sysref": [
        lambda: sysref(10e9, 2, 32),
        lambda: sysref(10e9, 2, 32, 7.8125e6, context="worst_case"),
        lambda: sysref(10e9, 2, 32, 10e6),
        lambda: sysref(10e9, 2, 32, 7.8125e6),
        lambda: sysref(10e9, 2, 32, 31.25e6),
        lambda: sysref(10e9, 2, 32, 15.625e6 / (2 - 1e-7)),
        lambda: sysref(16.896e9, f_sysref_hz=1e6, encoding="64b/66b", e=4, context="worst_case"),
    ],
}


def test_synthetic_w37_full_scale_settling():
    r = sar_rc(**SAR, r_ohm=18, context="worst_case")
    # A full-scale step to half LSB needs 17 ln(2) time constants for a 16-bit ADC.
    assert r.outputs["time_constants"].value == pytest.approx(11.78350207, abs=1e-8)
    assert r.outputs["tau_s"].value == pytest.approx(50.91864850e-9, abs=1e-17)
    assert r.outputs["r_max_ohm"].value == pytest.approx(18.85875870, abs=1e-8)
    assert r.outputs["bw_hz"].value == pytest.approx(3.125671002e6, abs=0.01)
    assert r.outputs["residual_v"].value == pytest.approx(5 * math.exp(-600e-9 / (18 * 2.7e-9)), rel=1e-12)
    assert r.verdict is Verdict.PASS


def test_sine_kickback_against_numerical_settling_root():
    r = sar_rc(**KICKBACK, r_ohm=18, c_ratio_min=20, context="worst_case")
    # Charge lost during conversion is the peak input slope times conversion time and Cdac.
    charge_c = (2 * math.pi * 100e3 * 2.5) * 700e-9 * 30e-12
    step_v = charge_c / (2.7e-9 + 30e-12)
    error_v = 5 / 131072
    resistance = brentq(lambda resistance: step_v * math.exp(-600e-9 / (resistance * 2.7e-9)) - error_v,
                        1, 1000, xtol=1e-12)
    assert r.outputs["step_v"].value == pytest.approx(step_v, rel=1e-12)
    assert r.outputs["r_max_ohm"].value == pytest.approx(resistance, rel=1e-10)
    assert r.outputs["c_ratio"].value == pytest.approx(90, abs=1e-12)
    assert r.verdict is Verdict.PASS


def test_sar_resistance_and_ratio_limits_are_independent():
    assert sar_rc(**SAR, r_ohm=22).verdict is Verdict.FAIL
    assert sar_rc(**SAR, r_ohm=18, c_dac_f=200e-12, c_ratio_min=20).verdict is Verdict.FAIL
    good = sar_rc(**SAR, r_ohm=18, c_dac_f=200e-12, context="worst_case")
    assert good.verdict is Verdict.PASS
    assert "No capacitance ratio limit" in good.summary
    assert "c_ratio_min" not in good.inputs
    assert sar_rc(**SAR).verdict is Verdict.INFO


def test_sar_at_the_calculated_boundary_and_already_within_half_lsb():
    boundary = 600e-9 / (17 * math.log(2) * 2.7e-9)
    r = sar_rc(**SAR, r_ohm=boundary, context="worst_case")
    assert r.verdict is Verdict.PASS
    tiny = sar_rc(**dict(KICKBACK, f_hz=1e-6), r_ohm=1000, context="worst_case")
    assert tiny.outputs["settling_s"].value == 0
    assert math.isinf(tiny.outputs["tau_s"].value)
    assert tiny.outputs["bw_hz"].value == 0
    assert tiny.verdict is Verdict.PASS


def test_sar_plot_ends_at_the_reported_error():
    r = sar_rc(**SAR, r_ohm=18)
    assert r.plots[0].series[0].y[-1] == pytest.approx(r.outputs["residual_v"].value, rel=1e-12)
    assert r.plots[0].markers[0].y == pytest.approx(5 / 131072, rel=1e-12)


@pytest.mark.parametrize("lanes,expected,verdict", [(2, 20e9, Verdict.FAIL), (4, 10e9, Verdict.PASS)])
def test_w38_jesd204b_explicit_revision_limit(lanes, expected, verdict):
    # Plan W38; JESD204B 12.5 Gb/s is supplied here, not inferred from encoding.
    r = jesd_lane_rate(2, 16, 1e9, lanes, "8b/10b", lane_max_bps=12.5e9, context="worst_case")
    assert r.outputs["lane_bps"].value == pytest.approx(expected, abs=1)
    assert r.verdict is verdict


def test_jesd64b66b_and_explicit_endpoint_bounds():
    r = jesd_lane_rate(2, 16, 1e9, 4, "64b/66b", lane_max_bps=8.25e9,
                       lane_min_bps=8.25e9, context="worst_case")
    assert r.outputs["lane_bps"].value == pytest.approx(8.25e9, abs=1)
    assert r.verdict is Verdict.PASS
    assert jesd_lane_rate(2, 16, 1e9, 4, "64b/66b", lane_min_bps=9e9).verdict is Verdict.FAIL


def test_jesd_no_hidden_encoding_maximum():
    assert jesd_lane_rate(2, 16, 1e9, 2, "8b/10b").verdict is Verdict.INFO
    r = jesd_lane_rate(2, 16, 1e9, 2, "8b/10b", lane_max_bps=25e9, context="worst_case")
    assert r.verdict is Verdict.PASS
    assert "lane_max_bps" not in jesd_lane_rate(2, 16, 1e9, 2, "8b/10b").inputs


@pytest.mark.parametrize("frequency,divider,verdict", [(7.8125e6, 2, Verdict.PASS), (10e6, 1.5625, Verdict.FAIL)])
def test_w39_sysref(frequency, divider, verdict):
    # SLYT628, AAJ 2Q 2015, p.16 eq.1, plan W39.
    r = sysref(10e9, 2, 32, frequency, context="worst_case")
    assert r.outputs["alignment_hz"].value == pytest.approx(15.625e6, abs=1e-8)
    assert r.outputs["n"].value == pytest.approx(divider, abs=1e-12)
    assert r.verdict is verdict


def test_sysref_lists_examples_and_does_not_limit_dividers():
    r = sysref(10e9, 2, 32, dividers=(1, 2, 8))
    assert r.verdict is Verdict.INFO
    assert [r.outputs[f"allowed_{n}_hz"].value for n in (1, 2, 8)] == \
        pytest.approx([15.625e6, 7.8125e6, 1.953125e6], abs=1e-8)
    assert sysref(10e9, 2, 32, 15.625e6 / 101, context="worst_case").verdict is Verdict.PASS
    assert sysref(10e9, 2, 32, 31.25e6).verdict is Verdict.FAIL
    assert sysref(10e9, 2, 32, 7.8125e6 * 1.0000001).verdict is Verdict.FAIL


def test_jesd204c_lemc_uses_e_not_f_and_k():
    # UG-1578 Rev 0 p.27 to 28: 32 blocks * 66 bits per multiblock, E = 4.
    r = sysref(16.896e9, f_sysref_hz=1e6, encoding="64b/66b", e=4, context="worst_case")
    assert r.outputs["alignment_hz"].value == pytest.approx(2e6, abs=1e-8)
    assert r.outputs["n"].value == pytest.approx(2, abs=1e-12)
    assert r.verdict is Verdict.PASS


CASES = [(name, i) for name, calls in SAMPLES.items() for i in range(len(calls))]


@pytest.mark.parametrize("name,i", CASES)
def test_plain_and_json_results(name, i):
    r = SAMPLES[name][i]()
    assert plain_problems(r) == []
    assert r.key and r.context and r.refs and r.assumptions
    json.dumps(r.to_dict(name), allow_nan=False)
    assert r.to_markdown()
    for plot in r.plots:
        assert plot.caption and plot.markers


@pytest.mark.parametrize("name", SAMPLES)
def test_each_verdict_branch_has_plain_samples(name):
    assert {make().verdict for make in SAMPLES[name]} == {Verdict.PASS, Verdict.FAIL, Verdict.INFO, Verdict.UNKNOWN}


@pytest.mark.parametrize("kwargs", [dict(n_bits=0), dict(n_bits=1.5), dict(n_bits=True), dict(v_ref_v=0),
                                   dict(c_ext_f=-1), dict(t_acq_s=math.nan), dict(r_ohm=math.inf),
                                   dict(t_conv_s=1e-6), dict(c_ratio_min=20), dict(context="typical")])
def test_sar_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        sar_rc(**(SAR | kwargs))


@pytest.mark.parametrize("kwargs", [dict(m=0), dict(np=16.5), dict(l=True), dict(fs_hz=math.nan),
                                   dict(encoding="unknown"), dict(lane_max_bps=0),
                                   dict(lane_min_bps=20e9, lane_max_bps=10e9)])
def test_jesd_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        jesd_lane_rate(**(dict(m=2, np=16, fs_hz=1e9, l=4, encoding="8b/10b") | kwargs))


@pytest.mark.parametrize("kwargs", [dict(lane_bps=0), dict(f=0), dict(k=1.5), dict(f_sysref_hz=0),
                                   dict(f_sysref_hz=math.inf), dict(dividers=(0,)), dict(f=None),
                                   dict(encoding="unknown"), dict(e=1), dict(encoding="64b/66b", e=1)])
def test_sysref_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        sysref(**(dict(lane_bps=10e9, f=2, k=32) | kwargs))
