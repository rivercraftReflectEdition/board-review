import math

import numpy as np
import pytest

from boardreview.calc.base import Result
from boardreview.calc.buck import BuckPoint, current_slew, dropout, example_envelope, inductor_ripple
from boardreview.calc.crystal import load_capacitance, oscillation_margin
from boardreview.calc.divider import enable_thresholds, regulator_output
from boardreview.calc.i2c import i2c_rise_time
from boardreview.calc.lc_tank import BeadRLC, Cap, damping_options, lc_filter
from boardreview.calc.loop import Integrator, margins
from boardreview.calc.mlcc_bias import mlcc_effective
from boardreview.calc.protection import tvs_clamp, tvs_standoff
from boardreview.calc.thermal import junction_temp

POINT = BuckPoint("a", 5, 5, 1.8, 1e6, 1e-6, 1e-5, "internal")

# Every value a calculator uses for its math or its verdict must be in Result.inputs.
CASES = {
    "dropout": (
        lambda: dropout(4.03, 3.32, 1.185e6, 45e-9, 10e-9, iout_a=2.0, r_top_ohm=0.13, r_bot_ohm=0.065, r_l_ohm=0.05),
        ["r_top", "r_bot", "r_l", "margin_min"],
    ),
    "inductor_ripple": (
        lambda: inductor_ripple(
            4.03, 3.32, 1.185e6, 2.2e-6, 1.0, i_sat_a=4.0, i_valley_limit_a=2.6, i_neg_limit_a=1.2, iout_max_a=3.0
        ),
        ["i_sat", "i_valley_limit", "i_neg_limit", "iout_max"],
    ),
    "current_slew": (lambda: current_slew(4.03, 3.32, 2.2e-6, 0.89), ["asymmetry_limit"]),
    "example_envelope": (
        lambda: example_envelope(POINT, [POINT]),
        ["tol_vin", "tol_vout", "tol_fsw", "tol_l", "tol_cout"],
    ),
    "tvs_standoff": (lambda: tvs_standoff(3.3, 5.0), ["margin_min"]),
    "tvs_clamp": (lambda: tvs_clamp(12.0, 4.0, [(1.0, 5.5), (10.0, 10.5)], i_pp_max_a=25.0), ["margin_min"]),
    "mlcc_effective": (
        lambda: mlcc_effective(100e-9, "X7R", 0.1, 3.3, np.array([0.0, 5.0]), np.array([1.0, 0.6]), -40, 85),
        ["t_min", "t_max", "curve_v_lo", "curve_k_lo", "curve_v_hi", "curve_k_hi"],
    ),
    "load_capacitance": (lambda: load_capacitance(12e-12, 12e-12, 3e-12, cl_spec_f=9e-12), ["tol"]),
    "oscillation_margin": (lambda: oscillation_margin(50.0, 24e6, 3e-12, 9e-12, gm_a_per_v=25e-3), ["min_gain_margin"]),
    "regulator_output": (
        lambda: regulator_output(0.958, 0.97, 0.982, 12.7e3, 3.24e3, v_out_max_allowed_v=5.0, v_out_min_allowed_v=3.0),
        ["v_out_max_allowed", "v_out_min_allowed"],
    ),
    "enable_thresholds": (
        lambda: enable_thresholds(1.1, 1.2, 1.3, 1.0, 1.1, 1.2, 100e3, 20e3, vin_min_v=10.0),
        ["margin_min"],
    ),
    "i2c_rise_time": (lambda: i2c_rise_time(2.2e3, 100e-12), ["margin_min"]),
    "junction_temp": (lambda: junction_temp(0.5, 40.0, 25.0, 125.0), ["margin_min"]),
    "margins": (lambda: margins([Integrator(1e3)], 10, 1e6), ["pm_min", "pm_fail", "gm_min", "gm_fail"]),
    "lc_filter": (
        lambda: lc_filter(BeadRLC(270e-9, 0.045), Cap(100e-9), [1.19e6], dampers=[Cap(1e-6, 1.0, 0.4e-9)]),
        ["harmonics", "window", "f_min", "f_max", "bead_l", "bead_rdc", "damper1_esl"],
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_result_carries_every_parameter(name):
    make, keys = CASES[name]
    r = make()
    assert isinstance(r, Result)
    missing = [k for k in keys if k not in r.inputs]
    assert not missing, f"{name} omits {missing}"


def test_dropout_reproduces_from_its_inputs():
    r = dropout(4.03, 3.32, 1.185e6, 45e-9, 10e-9, 0.89, iout_a=2.0, r_top_ohm=0.13, r_bot_ohm=0.065, r_l_ohm=0.05)
    q = {k: v.value for k, v in r.inputs.items()}
    dmax = min(1 - q["f"] * (q["t_off_min"] + 2 * q["t_dead"]), q["dmax_measured"])
    vin_min = (q["vout"] + q["iout"] * (q["r_bot"] + q["r_l"])) / dmax + q["iout"] * (q["r_top"] - q["r_bot"])
    assert r.outputs["vin_min"].value == pytest.approx(vin_min, rel=1e-12)


def test_damping_options_is_a_result():
    r = damping_options(0.25e-6, 100e-9)
    assert isinstance(r, Result)
    assert r.inputs["l"].value == 0.25e-6 and r.inputs["c"].value == 100e-9 and r.inputs["n"].value == 4.0
    assert r.outputs["r0"].value == pytest.approx(math.sqrt(2.5))
    assert r.outputs["r0"].unit == "ohm" and r.outputs["cd"].unit == "F"
    assert r.refs
