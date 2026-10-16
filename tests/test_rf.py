"""RF worked examples W24 to W32 from the 2026-10-15 RF plan, plus independent checks."""

import cmath
import json
import math

import numpy as np
import pytest

from boardreview.calc import rf
from boardreview.calc.base import Verdict, plain_problems
from boardreview.calc.lc_tank import Cap

CHAIN = [rf.Stage(20, 1, 0), rf.Stage(-2, 2, 100), rf.Stage(-7, 7, 15), rf.Stage(15, 3, 10)]
CAPS = [Cap(22e-9, 0.02, 0.4e-9), Cap(100e-12, 0.1, 0.4e-9)]
MATCH = [rf.Element("L", l_h=50/(2*math.pi*100e6), tolerance_frac=0.1),
         rf.Element("C", c_f=1/(2*math.pi*100e6*100), tolerance_frac=0.1)]
MATCH_HZ = np.linspace(80e6, 120e6, 101)


def device(reverse=0.05):
    return np.array([[cmath.rect(0.6, math.radians(-60)), cmath.rect(reverse, math.radians(40))],
                     [cmath.rect(4, math.radians(100)), cmath.rect(0.5, math.radians(-30))]])


def value(result, key):
    return result.outputs[key].value


SAMPLES = {
    "calc.rf.element_impedance": [
        lambda: rf.element_impedance("C", [1e6, 1e9], c_f=22e-9, esr_ohm=0.02, esl_h=0.4e-9),
        lambda: rf.element_impedance("R", [1e6, 1e9], r_ohm=50, z_min_ohm=49, context="worst_case"),
        lambda: rf.element_impedance("R", [1e6, 1e9], r_ohm=50, z_max_ohm=40),
        lambda: rf.element_impedance("R", [1e6, 1e9], r_ohm=50, z_max_ohm=60),
    ],
    "calc.rf.match_sweep": [
        lambda: rf.match_sweep("L", MATCH, MATCH_HZ, 50, 100),
        lambda: rf.match_sweep("L", MATCH, MATCH_HZ, 50, 100, rl_min_db=10, context="worst_case"),
        lambda: rf.match_sweep("L", MATCH, MATCH_HZ, 50, 100, rl_min_db=40),
        lambda: rf.match_sweep("L", MATCH, MATCH_HZ, 50, 100, rl_min_db=10),
    ],
    "calc.rf.cascade": [
        lambda: rf.cascade(CHAIN),
        lambda: rf.cascade(CHAIN, nf_max_db=2, context="worst_case"),
        lambda: rf.cascade(CHAIN, nf_max_db=1, context="worst_case"),
        lambda: rf.cascade([rf.Stage(20)], nf_max_db=2),
    ],
    "calc.rf.mismatch": [lambda: rf.mismatch(rl_db=10), lambda: rf.mismatch(gamma=1),
                         lambda: rf.mismatch(gamma=0)],
    "calc.rf.shunt_c": [
        lambda: rf.shunt_c(0.2e-12, 2.45e9, 50),
        lambda: rf.shunt_c(0.2e-12, 2.45e9, 50, rl_min_db=20, il_max_db=0.1, context="worst_case"),
        lambda: rf.shunt_c(1e-12, 5.8e9, 50, rl_min_db=20, il_max_db=0.1),
        lambda: rf.shunt_c(0.2e-12, 2.45e9, 50, rl_min_db=20),
    ],
    "calc.rf.peak_voltage": [
        lambda: rf.peak_voltage(0.2, 50),
        lambda: rf.peak_voltage(0.2, 50, working_v=3.6),
        lambda: rf.peak_voltage(0.01, 50, working_v=3.6, context="worst_case"),
    ],
    "calc.rf.dc_block": [
        lambda: rf.dc_block(10e-9, 1e6, 50),
        lambda: rf.dc_block(100e-9, 1e6, 50, il_max_db=0.1, context="worst_case"),
        lambda: rf.dc_block(1e-9, 1e6, 50, il_max_db=0.1),
        lambda: rf.dc_block(100e-9, 1e6, 50, f_max_hz=2e6, il_max_db=0.1),
    ],
    "calc.rf.pad": [
        lambda: rf.pad(6, 50, p_in_w=1),
        lambda: rf.pad(6, 50, p_in_w=1, rl_min_db=20, context="worst_case"),
        lambda: rf.pad(6, 50, p_in_w=1, fitted_ohm=(100, 50, 100), rl_min_db=40),
        lambda: rf.pad(6, 50, p_in_w=1, ratings_w=(1, 1, 1)),
    ],
    "calc.rf.stability": [
        lambda: rf.stability(device(), 1e9),
        lambda: rf.stability(device(), 1e9, k_min=1, delta_max=1, context="worst_case"),
        lambda: rf.stability(device(0.1), 1e9, mu_min=1),
        lambda: rf.stability(np.stack([device(), device(0.1)]), [1e8, 1e9], k_min=1, delta_max=1),
    ],
    "calc.rf.cavity_modes": [
        lambda: rf.cavity_modes(0.03, 0.02, 0.005),
        lambda: rf.cavity_modes(0.03, 0.02, 0.005, f_max_hz=6e9, context="worst_case"),
        lambda: rf.cavity_modes(0.03, 0.02, 0.005, f_max_hz=10e9),
    ],
    "calc.rf.network_impedance": [
        lambda: rf.network_impedance(CAPS, 1e6, 2e9),
        lambda: rf.network_impedance(CAPS, 1e6, 2e9, z_max_ohm=20, context="worst_case"),
        lambda: rf.network_impedance(CAPS, 1e6, 2e9, forbidden_bands_hz=[(500e6, 600e6)]),
        lambda: rf.network_impedance(CAPS, 1e6, 2e9, forbidden_bands_hz=[(3e9, 4e9)]),
    ],
}


@pytest.mark.parametrize("name,make", [(name, make) for name, cases in SAMPLES.items() for make in cases])
def test_plain_results_and_strict_json(name, make):
    r = make()
    assert plain_problems(r) == [], (name, plain_problems(r))
    assert r.context and r.key and r.refs
    json.dumps(r.to_dict(), allow_nan=False)


def test_w24_cascade_and_independent_friis():
    r = rf.cascade(CHAIN)
    # W24 hand Friis, AN57-1 eq. 2-3 p.8; noise powers are referred to the input.
    factors = [10 ** (n / 10) for n in (1, 2, 7, 3)]
    expected_factor = factors[0] + (factors[1]-1)/100 + (factors[2]-1)/10**1.8 + (factors[3]-1)/10**1.1
    assert value(r, "gain_db") == pytest.approx(26, abs=1e-12)
    assert value(r, "nf_db") == pytest.approx(1.48422, abs=1e-5)
    assert value(r, "nf_db") == pytest.approx(10 * math.log10(expected_factor), abs=1e-12)
    assert value(r, "iip3_dbm") == pytest.approx(-6.28817, abs=1e-5)
    assert value(r, "oip3_dbm") == pytest.approx(19.71183, abs=1e-5)
    assert value(r, "stage3_ip3_contribution") == pytest.approx(10**1.8 / 10**(-1.5), rel=1e-12)


@pytest.mark.parametrize("limits,verdict", [({}, Verdict.INFO), ({"gain_min_db": 20}, Verdict.PASS),
    ({"gain_min_db": 27}, Verdict.FAIL), ({"gain_max_db": 25}, Verdict.FAIL),
    ({"nf_max_db": 2}, Verdict.PASS), ({"nf_max_db": 1}, Verdict.FAIL),
    ({"iip3_min_dbm": -7}, Verdict.PASS), ({"iip3_min_dbm": -6}, Verdict.FAIL),
    ({"oip3_min_dbm": 20}, Verdict.FAIL)])
def test_cascade_limits(limits, verdict):
    assert rf.cascade(CHAIN, context="worst_case", **limits).verdict is verdict


def test_cascade_loss_before_lna_and_missing_data():
    r = rf.cascade([rf.Stage(-3, 3, 100), rf.Stage(20, 1, 0)])
    assert value(r, "nf_db") == pytest.approx(4, abs=1e-12)
    assert rf.cascade([rf.Stage(20)], nf_max_db=2).verdict is Verdict.UNKNOWN
    r = rf.cascade([rf.Stage(20, 1)], nf_max_db=2, iip3_min_dbm=0)
    assert r.verdict is Verdict.UNKNOWN
    assert r.inputs["iip3_min"].value == 0
    r = rf.cascade([rf.Stage(20)], gain_max_db=10)
    assert r.verdict is Verdict.FAIL
    r = rf.cascade([rf.Stage(20, None, 10)])
    assert math.isnan(value(r, "nf_db"))
    assert value(r, "iip3_dbm") == pytest.approx(10, abs=1e-12)


def test_w25_mismatch():
    r = rf.mismatch(rl_db=10)
    assert value(r, "ml_db") == pytest.approx(0.457575, abs=1e-6)
    assert value(r, "gamma") == pytest.approx(math.sqrt(0.1), rel=1e-12)
    assert value(r, "vswr") == pytest.approx(1.92495059, abs=1e-8)
    assert rf.mismatch(gamma=-0.3j).outputs == rf.mismatch(gamma=0.3).outputs


def test_mismatch_perfect_and_total_reflection():
    assert value(rf.mismatch(rl_db=math.inf), "ml_db") == 0
    assert value(rf.mismatch(gamma=0), "vswr") == 1
    assert math.isinf(value(rf.mismatch(rl_db=0), "ml_db"))
    assert math.isinf(value(rf.mismatch(gamma=1j), "vswr"))


@pytest.mark.parametrize("c,f,rl,il", [(0.5e-12, 2.45e9, 14.47, 0.158),
    (0.2e-12, 2.45e9, 22.30, 0.026), (1e-12, 5.8e9, 3.43, 2.62)])
def test_w26_shunt_capacitance(c, f, rl, il):
    r = rf.shunt_c(c, f, 50)
    assert value(r, "rl_db") == pytest.approx(rl, abs=0.01)
    assert value(r, "il_db") == pytest.approx(il, abs=0.01)
    # A lossless two-port conserves incident power.
    assert 10**(-value(r, "rl_db")/10) + 10**(-value(r, "il_db")/10) == pytest.approx(1, abs=1e-12)


@pytest.mark.parametrize("c,rl,il,verdict", [(0.2e-12, 20, 0.1, Verdict.PASS),
    (0.5e-12, 20, None, Verdict.FAIL), (0.5e-12, None, 0.1, Verdict.FAIL),
    (0.5e-12, None, None, Verdict.INFO)])
def test_shunt_explicit_limits(c, rl, il, verdict):
    assert rf.shunt_c(c, 2.45e9, 50, rl_min_db=rl, il_max_db=il, context="worst_case").verdict is verdict


def test_zero_shunt():
    r = rf.shunt_c(0, 1e9, 50)
    assert value(r, "il_db") == 0
    assert math.isinf(value(r, "rl_db"))


def test_w27_peak_working_voltage_and_mismatch():
    # TI TPD1E0B04 SLVSDG9C section 7.2.2 gives 3.16 V RMS for 200 mW.
    r = rf.peak_voltage(0.2, 50, working_v=3.6, context="worst_case")
    assert value(r, "v_rms_v") == pytest.approx(3.16228, abs=1e-5)
    assert value(r, "v_pk_v") == pytest.approx(4.47214, abs=1e-5)
    assert r.verdict is Verdict.FAIL
    r = rf.peak_voltage(0.2, 50, gamma=0.6j)
    assert value(r, "v_pk_v") == pytest.approx(math.sqrt(20)*1.6, rel=1e-12)
    assert value(r, "v_max_rms_v") == pytest.approx(math.sqrt(10)*1.6, rel=1e-12)
    r = rf.peak_voltage(0, 50, working_v=3.6, context="worst_case")
    assert value(r, "v_pk_v") == 0 and r.verdict is Verdict.PASS


@pytest.mark.parametrize("c,loss,corner", [(1e-9, 5.481473, 1.591549e6),
    (10e-9, 0.108638, 159154.9), (100e-9, 0.001100, 15915.49)])
def test_w28_dc_block(c, loss, corner):
    r = rf.dc_block(c, 1e6, 50)
    assert value(r, "il_min_db") == pytest.approx(loss, abs=5e-5)
    assert value(r, "f_c_hz") == pytest.approx(corner, rel=1e-6)
    r = rf.dc_block(c, value(r, "f_c_hz"), 50)
    assert value(r, "il_min_db") == pytest.approx(10*math.log10(2), abs=1e-12)


def test_dc_block_sizing_and_real_series_rlc():
    r = rf.dc_block(10e-9, 1e6, 50, il_max_db=0.1)
    assert value(r, "c_needed_f") == pytest.approx(10.4281e-9, rel=1e-4)
    c = value(r, "c_needed_f")
    assert 10*math.log10(1 + (1/(2*math.pi*1e6*c*100))**2) == pytest.approx(0.1, abs=1e-12)
    # At series resonance the residual loss is set by ESR alone.
    r = rf.dc_block(100e-12, 1/(2*math.pi*math.sqrt(1e-9*100e-12)), 50, esl_h=1e-9, esr_ohm=2)
    assert value(r, "il_min_db") == pytest.approx(20*math.log10(102/100), abs=1e-12)
    assert value(r, "srf_hz") == pytest.approx(503.292121e6, rel=1e-9)


def test_dc_block_prf_and_high_frequency_inductive_loss():
    r = rf.dc_block(100e-9, 1e6, 50, f_max_hz=1e9, esl_h=10e-9, prf_hz=2e9,
                    il_max_db=0.1, context="worst_case")
    assert value(r, "il_worst_db") > 1
    assert r.verdict is Verdict.FAIL
    r = rf.dc_block(100e-9, 1e6, 50, f_max_hz=1e9, prf_hz=500e6, context="worst_case")
    assert r.verdict is Verdict.FAIL and value(r, "prf_in_band") == 1
    r = rf.dc_block(100e-9, 1e6, 50, f_max_hz=2e6, il_max_db=0.1, context="worst_case")
    assert r.verdict is Verdict.UNKNOWN
    r = rf.dc_block(100e-9, 1e6, 50, f_max_hz=2e6, prf_hz=3e6, il_max_db=0.1, context="worst_case")
    assert r.verdict is Verdict.PASS and r.plots


@pytest.mark.parametrize("attenuation,pi_r1,pi_r2,t_r1,t_r2", [
    (3, 292.4, 17.61, 8.55, 141.9), (6, 150.5, 37.35, 16.61, 66.93),
    (10, 96.25, 71.15, 25.97, 35.14), (20, 61.11, 247.5, 40.91, 10.10)])
def test_w29_pad_values(attenuation, pi_r1, pi_r2, t_r1, t_r2):
    for topology, expected1, expected2 in (("pi", pi_r1, pi_r2), ("t", t_r1, t_r2)):
        r = rf.pad(attenuation, 50, topology=topology, p_in_w=1)
        assert value(r, "r1_ideal_ohm") == pytest.approx(expected1, abs=0.06)
        assert value(r, "r2_ideal_ohm") == pytest.approx(expected2, abs=0.06)
        assert value(r, "loss_db") == pytest.approx(attenuation, abs=1e-12)
        assert value(r, "rl_worst_db") > 290


def test_w29_fitted_pad_and_one_watt_powers():
    r = rf.pad(6, 50, p_in_w=1, fitted_ohm=(150, 37.4, 150))
    assert value(r, "loss_db") == pytest.approx(6.012876, abs=1e-6)
    assert value(r, "rl_worst_db") == pytest.approx(67.03593, abs=1e-5)
    r = rf.pad(6, 50, p_in_w=1)
    for key, expected in (("p1_w", 0.332), ("p2_w", 0.333), ("p3_w", 0.083), ("p_out_w", 0.251)):
        assert value(r, key) == pytest.approx(expected, abs=0.001)


@pytest.mark.parametrize("topology,fitted", [("pi", (120, 40, 200)), ("t", (10, 60, 20))])
def test_pad_asymmetric_nodal_solution_and_power_conservation(topology, fitted):
    # Independent loaded nodal solve with a 2 V RMS Thevenin generator and 50 ohm source.
    r1, r2, r3 = fitted
    if topology == "pi":
        g = np.array([[1/50+1/r1+1/r2, -1/r2], [-1/r2, 1/r2+1/r3+1/50]])
        vin, vout = np.linalg.solve(g, [2/50, 0])
        powers = [vin**2/r1, (vin-vout)**2/r2, vout**2/r3]
    else:
        g = np.array([[1/50+1/r1, -1/r1, 0], [-1/r1, 1/r1+1/r2+1/r3, -1/r3], [0, -1/r3, 1/r3+1/50]])
        vin, vmid, vout = np.linalg.solve(g, [2/50, 0, 0])
        powers = [(vin-vmid)**2/r1, vmid**2/r2, (vmid-vout)**2/r3]
    r = rf.pad(6, 50, topology=topology, p_in_w=0.02, fitted_ohm=fitted)
    assert [value(r, f"p{i}_w") for i in (1, 2, 3)] == pytest.approx(powers, rel=1e-12)
    assert value(r, "p_out_w") == pytest.approx(vout**2/50, rel=1e-12)
    assert sum(powers) + value(r, "p_out_w") + value(r, "p_reflected_w") == pytest.approx(0.02, abs=1e-14)
    assert value(r, "rl_input_db") != value(r, "rl_output_db")


def test_pad_limits_power_and_missing_ratings():
    r = rf.pad(6, 50, p_in_w=1, loss_error_max_db=0.25, rl_min_db=20,
               ratings_w=(1, 1, 1), power_fraction_max=0.5, context="worst_case")
    assert r.verdict is Verdict.PASS
    r = rf.pad(6, 50, p_in_w=1, ratings_w=(0.25, 0.25, 0.25), power_fraction_max=0.5)
    assert r.verdict is Verdict.FAIL
    assert rf.pad(6, 50, p_in_w=1, power_fraction_max=0.5).verdict is Verdict.UNKNOWN
    r = rf.pad(6, 50, p_in_w=1, fitted_ohm=(100, 40, 100), loss_error_max_db=0.01)
    assert r.verdict is Verdict.FAIL


@pytest.mark.parametrize("reverse,k,delta,mu,verdict", [(0.05, 1.493, 0.455, 1.392, Verdict.PASS),
    (0.1, 0.993, 0.636, 0.988, Verdict.FAIL)])
def test_w30_stability(reverse, k, delta, mu, verdict):
    s = device(reverse)
    r = rf.stability(s, 1e9, k_min=1, delta_max=1, context="worst_case")
    assert value(r, "k_min") == pytest.approx(k, abs=0.0005)
    assert value(r, "delta_max") == pytest.approx(delta, abs=0.0005)
    assert value(r, "mu_min") == pytest.approx(mu, abs=0.0005)
    assert r.verdict is verdict
    assert rf.stability(s, 1e9, mu_min=1, context="worst_case").verdict is verdict
    # Determinant from independent matrix algebra guards the KS5072 p.3 typo.
    assert value(r, "delta_abs1") == pytest.approx(abs(np.linalg.det(s)), rel=1e-12)
    wrong_delta = s[0, 0]*s[1, 0] - s[0, 1]*s[1, 0]
    assert abs(value(r, "delta_abs1") - abs(wrong_delta)) > 1


def test_stability_sweep_limits_and_unilateral_device():
    s = np.stack([device(), device(0.1)])
    r = rf.stability(s, [1e8, 1e9], k_min=1, delta_max=1, context="worst_case")
    assert r.verdict is Verdict.FAIL and r.plots
    assert value(r, "f_worst_hz") == 1e9
    assert "s12_2_imag" in r.inputs
    assert rf.stability(device(), 1e9, k_min=1).verdict is Verdict.UNKNOWN
    r = rf.stability(np.array([[0.2, 0], [4, 0.3]]), 1e9, mu_min=1, context="worst_case")
    assert math.isinf(value(r, "k_min"))
    assert value(r, "mu_min") == pytest.approx(1/0.3, rel=1e-12)
    assert r.verdict is Verdict.PASS
    assert rf.stability(np.eye(2), 1e9, k_min=1, delta_max=1).verdict is Verdict.UNKNOWN


def test_stability_strict_boundary_and_alternate_criteria():
    r = rf.stability(device(), 1e9)
    assert rf.stability(device(), 1e9, mu_min=value(r, "mu_min"), context="worst_case").verdict is Verdict.FAIL
    assert rf.stability(device(), 1e9, k_min=2, delta_max=1, mu_min=1, context="worst_case").verdict is Verdict.PASS


@pytest.mark.parametrize("a,b,expected", [(0.03, 0.02, 9.007642e9), (0.05, 0.04, 4.799022e9)])
def test_w31_cavity_modes(a, b, expected):
    r = rf.cavity_modes(a, b, 0.005)
    assert value(r, "lowest_hz") == pytest.approx(expected, rel=2e-5)
    assert value(r, "lowest_hz") == pytest.approx(299792458/2 * math.hypot(1/a, 1/b), rel=1e-12)


def test_cavity_height_axis_permutations_and_fill():
    r = rf.cavity_modes(0.03, 0.02, 0.005)
    for dims in ((0.005, 0.03, 0.02), (0.02, 0.005, 0.03)):
        assert value(rf.cavity_modes(*dims), "lowest_hz") == pytest.approx(value(r, "lowest_hz"), rel=1e-12)
    assert value(rf.cavity_modes(0.03, 0.02, 0.005, epsilon_r=4), "lowest_hz") == pytest.approx(value(r, "lowest_hz")/2, rel=1e-12)
    assert rf.cavity_modes(0.03, 0.02, 0.005, f_max_hz=value(r, "lowest_hz"), context="worst_case").verdict is Verdict.FAIL
    modes = [value(r, f"mode{i}_hz") for i in range(1, 7)]
    assert modes == sorted(modes)


def test_w32_network_and_independent_two_branch_formula():
    r = rf.network_impedance(CAPS, 1e6, 2e9)
    assert value(r, "srf1_hz") == pytest.approx(53.65112e6, rel=1e-7)
    assert value(r, "srf2_hz") == pytest.approx(795.7747e6, rel=1e-7)
    assert value(r, "f_peak_hz") == pytest.approx(563.4748e6, rel=1e-6)
    assert value(r, "z_peak_ohm") == pytest.approx(16.49856, abs=1e-5)
    assert value(r, "peak_count") == 1
    w = 2*math.pi*value(r, "f_peak_hz")
    z1 = complex(0.02, w*0.4e-9 - 1/(w*22e-9))
    z2 = complex(0.1, w*0.4e-9 - 1/(w*100e-12))
    assert value(r, "z_peak_ohm") == pytest.approx(abs(z1*z2/(z1+z2)), rel=1e-12)
    assert abs(z1) == pytest.approx(1.4034, abs=0.001)
    assert r.plots and len(r.plots[0].series) == 3


def test_network_limits_peaks_endpoints_and_coverage():
    args = (CAPS, 1e6, 2e9)
    assert rf.network_impedance(*args, z_max_ohm=10).verdict is Verdict.FAIL
    assert rf.network_impedance(*args, z_max_ohm=20, context="worst_case").verdict is Verdict.PASS
    assert rf.network_impedance(*args, forbidden_bands_hz=[(1e9, 2e9)], context="worst_case").verdict is Verdict.PASS
    assert rf.network_impedance(*args, forbidden_bands_hz=[(2e9, 3e9)], context="worst_case").verdict is Verdict.UNKNOWN
    assert rf.network_impedance(*args, forbidden_bands_hz=[(500e6, 600e6)]).verdict is Verdict.FAIL
    assert rf.network_impedance(*args, forbidden_bands_hz=[], context="worst_case").verdict is Verdict.INFO
    r = rf.network_impedance([Cap(1e-9)], 1e6, 1e9)
    assert value(r, "peak_count") == 0
    assert value(r, "f_max_z_hz") == 1e6
    assert value(r, "z_max_ohm") == pytest.approx(1/(2*math.pi*1e6*1e-9), rel=1e-12)
    assert r.verdict is Verdict.INFO
    assert plain_problems(r) == []


def test_network_multiple_peaks_and_lossless_srf():
    caps = [Cap(22e-9, 0.02, 0.4e-9), Cap(1e-9, 0.04, 0.4e-9), Cap(100e-12, 0.1, 0.4e-9)]
    r = rf.network_impedance(caps, 1e6, 2e9)
    assert value(r, "peak_count") == 2
    r = rf.network_impedance([Cap(1e-9, 0, 1e-9)], 1e6, 1e9)
    assert value(r, "peak_count") == 0
    assert plain_problems(r) == []


@pytest.mark.parametrize("make", [lambda: rf.cascade(CHAIN, nf_max_db=2),
    lambda: rf.shunt_c(0.2e-12, 2.45e9, 50, il_max_db=0.1),
    lambda: rf.peak_voltage(0.01, 50, working_v=3.6),
    lambda: rf.dc_block(100e-9, 1e6, 50, il_max_db=0.1),
    lambda: rf.pad(6, 50, p_in_w=1, rl_min_db=20),
    lambda: rf.stability(device(), 1e9, mu_min=1),
    lambda: rf.cavity_modes(0.03, 0.02, 0.005, f_max_hz=6e9),
    lambda: rf.network_impedance(CAPS, 1e6, 2e9, z_max_ohm=20)])
def test_nominal_values_cannot_pass(make):
    r = make()
    assert r.verdict is Verdict.UNKNOWN
    assert plain_problems(r) == []


@pytest.mark.parametrize("make", [lambda: rf.cascade([]), lambda: rf.cascade([rf.Stage(math.nan)]),
    lambda: rf.cascade([rf.Stage(10, -1, 10)]), lambda: rf.cascade([rf.Stage(10, 1, math.inf)]),
    lambda: rf.cascade(CHAIN, nf_max_db=math.nan),
    lambda: rf.mismatch(), lambda: rf.mismatch(rl_db=10, gamma=0.1), lambda: rf.mismatch(rl_db=-10),
    lambda: rf.mismatch(gamma=1.1), lambda: rf.mismatch(gamma=complex(math.nan, 0)),
    lambda: rf.shunt_c(-1e-12, 1e9, 50), lambda: rf.shunt_c(1e-12, 0, 50),
    lambda: rf.shunt_c(1e-12, 1e9, 50, il_max_db=math.inf),
    lambda: rf.peak_voltage(-1, 50), lambda: rf.peak_voltage(1, 0), lambda: rf.peak_voltage(1, 50, working_v=0),
    lambda: rf.dc_block(0, 1e6, 50), lambda: rf.dc_block(1e-9, 1e6, 50, esl_h=-1),
    lambda: rf.dc_block(1e-9, 1e6, 50, f_max_hz=1e5), lambda: rf.dc_block(1e-9, 1e6, 50, il_max_db=0),
    lambda: rf.pad(0, 50, p_in_w=1), lambda: rf.pad(6, 50, p_in_w=1, topology="x"),
    lambda: rf.pad(6, 50, p_in_w=1, fitted_ohm=(1, 2)), lambda: rf.pad(6, 50, p_in_w=1, fitted_ohm=(1, 0, 1)),
    lambda: rf.pad(6, 50, p_in_w=1, ratings_w=(1,)), lambda: rf.pad(6, 50, p_in_w=1, ratings_w=(1, -1, 1)),
    lambda: rf.stability(device(), [1e9, 2e9]), lambda: rf.stability(np.zeros((2, 2, 2)), [1e9, 1e8]),
    lambda: rf.stability(device(), 1e9, mu_min=math.nan), lambda: rf.stability(np.full((2, 2), math.nan), 1e9),
    lambda: rf.cavity_modes(0, 0.02, 0.005), lambda: rf.cavity_modes(0.03, 0.02, 0.005, count=0),
    lambda: rf.network_impedance([], 1e6, 1e9), lambda: rf.network_impedance(CAPS, 1e9, 1e6),
    lambda: rf.network_impedance([Cap(0)], 1e6, 1e9), lambda: rf.network_impedance(CAPS, 1e6, 1e9, points_per_decade=1),
    lambda: rf.network_impedance(CAPS, 1e6, 1e9, forbidden_bands_hz=[(2e6, 1e6)])])
def test_invalid_inputs(make):
    with pytest.raises(ValueError):
        make()


@pytest.mark.parametrize("c_f,esr_ohm,expected_hz", [(22e-9, 0.02, 53.651e6), (100e-12, 0.1, 795.775e6)])
def test_element_w32_self_resonances(c_f, esr_ohm, expected_hz):
    # Plan W32, synthetic ESL 0.4 nH; independently solve wL = 1/(wC).
    r = rf.element_impedance("C", [1e6, 2e9], c_f=c_f, esr_ohm=esr_ohm, esl_h=0.4e-9)
    expected = 1 / (2 * math.pi * math.sqrt(0.4e-9 * c_f))
    assert value(r, "srf_hz") == pytest.approx(expected_hz, rel=2e-5)
    assert value(r, "srf_hz") == pytest.approx(expected, rel=1e-12)
    assert value(r, "z_min_ohm") == pytest.approx(esr_ohm, abs=1e-12)
    assert expected == pytest.approx(r.plots[0].markers[0].x, rel=1e-12)


@pytest.mark.parametrize("kind,params", [("R", dict(r_ohm=47)), ("L", dict(l_h=10e-9)),
                                       ("C", dict(c_f=100e-12))])
def test_element_complex_curve_against_series_parallel_equations(kind, params):
    f = np.array([10e6, 100e6, 1e9])
    r = rf.element_impedance(kind, f, **params, esr_ohm=0.2, esl_h=0.5e-9, c_parallel_f=0.3e-12)
    for i, frequency in enumerate(r.plots[0].x):
        w = 2 * math.pi * frequency
        z = params.get("r_ohm", 0) + 0.2 + 1j*w*(params.get("l_h", 0) + 0.5e-9)
        if "c_f" in params:
            z += 1/(1j*w*params["c_f"])
        z = 1 / (1/z + 1j*w*0.3e-12)
        assert r.plots[0].series[0].y[i] == pytest.approx(abs(z), rel=1e-12)
        assert r.plots[0].series[1].y[i] == pytest.approx(z.real, abs=1e-11)
        assert r.plots[0].series[2].y[i] == pytest.approx(z.imag, abs=1e-11)


def test_element_inductor_parallel_resonance_and_damping():
    r = rf.element_impedance("L", [1e6, 1e9], l_h=10e-9, esr_ohm=2, c_parallel_f=1e-12)
    expected = math.sqrt(1/(10e-9*1e-12) - (2/10e-9)**2) / (2*math.pi)
    assert value(r, "srf_hz") == pytest.approx(expected, rel=1e-12)
    damped = rf.element_impedance("L", [1e6, 1e9], l_h=10e-9, esr_ohm=200, c_parallel_f=1e-12)
    assert math.isinf(value(damped, "srf_hz"))
    assert value(damped, "resonance_count") == 0


@pytest.mark.parametrize("limits,context,verdict", [({}, "worst_case", Verdict.INFO),
    ({"z_min_ohm": 49, "z_max_ohm": 51}, "worst_case", Verdict.PASS),
    ({"z_min_ohm": 51}, "worst_case", Verdict.FAIL),
    ({"z_max_ohm": 49}, "worst_case", Verdict.FAIL),
    ({"z_min_ohm": 49}, "nominal", Verdict.UNKNOWN)])
def test_element_limits_and_context(limits, context, verdict):
    r = rf.element_impedance("R", [1e6, 1e9], r_ohm=50, context=context, **limits)
    assert r.verdict is verdict
    assert plain_problems(r) == []


def test_match_l_closed_form_conjugate_match_and_reverse():
    # Q=sqrt(100/50-1)=1; Xseries=Q*50; Xshunt=100/Q, at 100 MHz.
    parts = [rf.Element("L", l_h=50/(2*math.pi*100e6)), rf.Element("C", c_f=1/(2*math.pi*100e6*100))]
    forward = rf.match_sweep("L", parts, [100e6], 50, 100, rl_min_db=60, context="worst_case")
    reverse = rf.match_sweep("L", parts[::-1], [100e6], 100, 50, shunt_first=True, rl_min_db=60, context="worst_case")
    for r in (forward, reverse):
        assert value(r, "rl_min_db") > 300
        assert r.verdict is Verdict.PASS


def test_match_l_corners_against_independent_two_element_solution():
    r = rf.match_sweep("L", MATCH, MATCH_HZ, 50, 100)
    cases = []
    for lf in (0.9, 1, 1.1):
        for cf in (0.9, 1, 1.1):
            if (lf == 1) != (cf == 1):
                continue
            s = 2j*math.pi*MATCH_HZ
            zl = s*MATCH[0].l_h*lf
            yc = s*MATCH[1].c_f*cf
            zin = zl + 1/(1/100 + yc)
            zout = 1/(yc + 1/(50 + zl))
            with np.errstate(divide="ignore"):
                cases.append([-20*np.log10(abs((zin-50)/(zin+50))),
                              -20*np.log10(abs((zout-100)/(zout+100)))])
    curves = np.array(cases)
    assert value(r, "rl_min_db") == pytest.approx(float(curves.min()), abs=1e-10)
    corners = curves[[0, 1, 3, 4]]
    expected_spread = np.max(corners.max(axis=0) - corners.min(axis=0))
    assert value(r, "spread_max_db") == pytest.approx(expected_spread, abs=1e-9)
    assert value(r, "corner_count") == 4
    assert value(r, "worst_hz") in (80e6, 120e6)


@pytest.mark.parametrize("topology", ["pi", "T"])
def test_match_w29_six_db_resistor_pads(topology):
    # W29 values, independently synthesized from the attenuation voltage ratio K.
    k = 10**(6/20)
    vals = [50*(k+1)/(k-1), 50*(k*k-1)/(2*k), 50*(k+1)/(k-1)] if topology == "pi" else \
           [50*(k-1)/(k+1), 100*k/(k*k-1), 50*(k-1)/(k+1)]
    r = rf.match_sweep(topology, [rf.Element("R", r_ohm=x) for x in vals], [1e6, 1e9], 50, 50,
                       rl_min_db=60, context="worst_case")
    assert value(r, "rl_min_db") > 300
    assert value(r, "spread_max_db") == 0
    assert r.verdict is Verdict.PASS
    json.dumps(r.to_dict(), allow_nan=False)


def test_match_complex_source_and_load():
    parts = [rf.Element("L", l_h=10e-9), rf.Element("C", c_f=10e-12)]
    r = rf.match_sweep("L", parts, [100e6], 50+10j, 100-20j)
    w = 2*math.pi*100e6
    zin = 1j*w*10e-9 + 1/(1/(100-20j) + 1j*w*10e-12)
    zout = 1/(1j*w*10e-12 + 1/(50+10j+1j*w*10e-9))
    expected = min(-20*math.log10(abs((zin-(50-10j))/(zin+50+10j))),
                   -20*math.log10(abs((zout-(100+20j))/(zout+100-20j))))
    assert value(r, "rl_min_db") == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("limit,context,verdict", [(None, "worst_case", Verdict.INFO),
    (10, "worst_case", Verdict.PASS), (40, "worst_case", Verdict.FAIL), (10, "nominal", Verdict.UNKNOWN)])
def test_match_limits_and_context(limit, context, verdict):
    r = rf.match_sweep("L", MATCH, MATCH_HZ, 50, 100, rl_min_db=limit, context=context)
    assert r.verdict is verdict
    assert plain_problems(r) == []
    if limit is None:
        assert "board requirement or part datasheet" in r.summary


@pytest.mark.parametrize("make", [
    lambda: rf.element_impedance("X", [1e6], r_ohm=1),
    lambda: rf.element_impedance("C", [1e6], c_f=0),
    lambda: rf.element_impedance("R", [1e6], r_ohm=1, l_h=1),
    lambda: rf.element_impedance("L", [1e6], l_h=1, esr_ohm=-1),
    lambda: rf.element_impedance("R", [], r_ohm=1),
    lambda: rf.element_impedance("R", [1e6, 1e5], r_ohm=1),
    lambda: rf.element_impedance("R", [math.nan], r_ohm=1),
    lambda: rf.element_impedance("R", [0], r_ohm=1),
    lambda: rf.element_impedance("R", [1e6], r_ohm=1, z_min_ohm=2, z_max_ohm=1),
    lambda: rf.element_impedance("R", [1e6], r_ohm=1, z_max_ohm=-1),
    lambda: rf.match_sweep("X", MATCH, MATCH_HZ, 50, 100),
    lambda: rf.match_sweep("pi", MATCH, MATCH_HZ, 50, 100),
    lambda: rf.match_sweep("L", MATCH, MATCH_HZ, -50, 100),
    lambda: rf.match_sweep("L", MATCH, MATCH_HZ, 50, math.inf),
    lambda: rf.match_sweep("L", MATCH, MATCH_HZ, 50, 100, rl_min_db=math.nan),
    lambda: rf.match_sweep("L", [rf.Element("L", l_h=1, tolerance_frac=1), MATCH[1]], MATCH_HZ, 50, 100)])
def test_new_rf_invalid_inputs(make):
    with pytest.raises(ValueError):
        make()
