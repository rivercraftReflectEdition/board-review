import math

import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.crystal import STM32N6_HSE, drive_level, load_capacitance, oscillation_margin


def test_load_capacitance_12p_12p_3p():
    r = load_capacitance(12e-12, 12e-12, 3e-12, cl_spec_f=9e-12)
    assert r.outputs["cl"].value == pytest.approx(9e-12)
    assert r.verdict is Verdict.PASS


def test_load_capacitance_mismatch_and_pulling():
    r = load_capacitance(18e-12, 18e-12, 4e-12, cl_spec_f=8e-12, c0_f=2e-12, c_motional_f=5e-15)
    assert r.outputs["cl"].value == pytest.approx(13e-12)
    assert r.verdict is Verdict.FAIL
    # Heavier load pulls the frequency low: 5 fF/2 * (1/15 pF - 1/10 pF) = -83.3 ppm.
    assert r.outputs["pulling"].value == pytest.approx(-83.333, abs=1e-3)


def test_gm_crit_against_stm32n6_hse_gmcritmax():
    # 24 MHz, ESR 50 ohm, C0 3 pF, CL 9 pF: 4*50*(2*pi*24e6)^2*(12e-12)^2.
    r = oscillation_margin(50.0, 24e6, 3e-12, 9e-12, gm_crit_max_a_per_v=1.95e-3, refs=(STM32N6_HSE,))
    expected = 4 * 50 * (2 * math.pi * 24e6) ** 2 * (12e-12) ** 2
    assert r.outputs["gm_crit"].value == pytest.approx(expected, rel=1e-12)
    assert r.outputs["gm_crit"].value == pytest.approx(0.6549e-3, abs=1e-7)
    assert r.verdict is Verdict.PASS


def test_gain_margin_with_oscillator_gm():
    r = oscillation_margin(80.0, 48e6, 3e-12, 10e-12, gm_a_per_v=5e-3)
    assert r.outputs["gain_margin"].value == pytest.approx(5e-3 / (4 * 80 * (2 * math.pi * 48e6) ** 2 * (13e-12) ** 2))
    assert r.verdict is Verdict.FAIL


def test_no_gm_data_is_unknown():
    assert oscillation_margin(50.0, 24e6, 3e-12, 9e-12).verdict is Verdict.UNKNOWN


def test_drive_level_from_current_and_from_voltage():
    assert drive_level(50.0, 100e-6, i_rms_a=1e-3).outputs["dl"].value == pytest.approx(50e-6)
    r = drive_level(50.0, 100e-6, f_hz=24e6, c_tot_f=15e-12, v_pp_v=1.0)
    assert r.outputs["dl"].value == pytest.approx(50.0 * (math.pi * 24e6 * 15e-12 * 1.0) ** 2 / 2)
    assert r.verdict is Verdict.PASS
