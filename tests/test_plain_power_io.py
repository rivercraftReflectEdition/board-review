"""Plain-language Results for calc.buck, calc.crystal, calc.i2c and calc.protection."""

import pytest

from boardreview.calc import buck, crystal, i2c, protection
from boardreview.calc.base import Verdict, fmt, plain_problems

VIN, VOUT, FSW, L = 4.03, 3.32, 1.185e6, 2.2e-6
OURS = buck.BuckPoint("ours", 5.0, 5.5, 3.3, 2e6, 2.2e-6, 44e-6, "internal")
EXAMPLE = buck.BuckPoint("Typical application 1", 4.5, 6.0, 3.3, 2e6, 2.2e-6, 44e-6, "internal", "synthetic p.20")
NO_COUT = buck.BuckPoint("ours", 5.0, 5.5, 3.3, 2e6, 2.2e-6, None, "internal")
BIG_L = buck.BuckPoint("ours", 5.0, 5.5, 3.3, 2e6, 4.7e-6, 44e-6, "internal")
CLAMP = [(1.0, 5.5), (10.0, 10.5)]

SAMPLES = {
    "calc.buck.duty_cycle": [
        lambda: buck.duty_cycle(VIN, VOUT),
        lambda: buck.duty_cycle(VIN, VOUT, 1.0, 0.1, 0.05, 0.03),
        lambda: buck.duty_cycle(3.3, VOUT),
    ],
    "calc.buck.dropout": [
        lambda: buck.dropout(VIN, VOUT, FSW, 45e-9, 10e-9),
        lambda: buck.dropout(3.7, VOUT, FSW, 45e-9, 10e-9),
        lambda: buck.dropout(3.5, VOUT, FSW, 45e-9, 10e-9, dmax_measured=0.9, iout_a=1.0, r_top_ohm=0.1,
                             r_bot_ohm=0.05, r_l_ohm=0.03),
    ],
    "calc.buck.inductor_ripple": [
        lambda: buck.inductor_ripple(VIN, VOUT, FSW, L, 1.0),
        lambda: buck.inductor_ripple(VIN, VOUT, FSW, L, 1.0, i_sat_a=3.0, i_valley_limit_a=2.6, i_neg_limit_a=1.0,
                                     iout_max_a=1.5),
        lambda: buck.inductor_ripple(VIN, VOUT, FSW, L, 1.0, i_sat_a=3.0, iout_max_a=0.3),
        lambda: buck.inductor_ripple(VIN, VOUT, FSW, L, 1.0, i_sat_a=1.0),
        lambda: buck.inductor_ripple(VIN, VOUT, FSW, L, 1.0, i_valley_limit_a=0.5),
        lambda: buck.inductor_ripple(VIN, VOUT, FSW, L, 1.0, i_neg_limit_a=0.05),
    ],
    "calc.buck.current_slew": [
        lambda: buck.current_slew(12.0, 3.3, L, 0.9),
        lambda: buck.current_slew(12.0, 3.3, L, 0.9, load_slew_a_per_s=1e6),
        lambda: buck.current_slew(12.0, 3.3, L, 0.9, load_slew_a_per_s=1e7),
        lambda: buck.current_slew(VIN, VOUT, L, 0.89),
        lambda: buck.current_slew(3.6, VOUT, L, 0.9),
    ],
    "calc.buck.slew_clamp_vpp": [
        lambda: buck.slew_clamp_vpp(1.2e5, 125e3, 35.1e-6),
        lambda: buck.slew_clamp_vpp(1.2e5, 125e3, 35.1e-6, 50e-3),
        lambda: buck.slew_clamp_vpp(1.2e5, 125e3, 35.1e-6, 5e-3),
    ],
    "calc.buck.soft_start_inrush": [
        lambda: buck.soft_start_inrush(35.1e-6, VOUT, 400e-6),
        lambda: buck.soft_start_inrush(35.1e-6, VOUT, 400e-6, 0.1, 1.0),
        lambda: buck.soft_start_inrush(35.1e-6, VOUT, 400e-6, i_limit_a=0.35),
        lambda: buck.soft_start_inrush(35.1e-6, VOUT, 400e-6, i_limit_a=0.25),
    ],
    "calc.buck.example_envelope": [
        lambda: buck.example_envelope(OURS, [EXAMPLE]),
        lambda: buck.example_envelope(NO_COUT, [EXAMPLE]),
        lambda: buck.example_envelope(BIG_L, [EXAMPLE]),
        lambda: buck.example_envelope(buck.BuckPoint("a", 4, 4, 3.3), [buck.BuckPoint("b", 6, 20, 3.3, source="x")]),
        lambda: buck.example_envelope(OURS, []),
    ],
    "calc.crystal.load_capacitance": [
        lambda: crystal.load_capacitance(12e-12, 12e-12, 3e-12),
        lambda: crystal.load_capacitance(12e-12, 12e-12, 3e-12, cl_spec_f=9e-12),
        lambda: crystal.load_capacitance(12e-12, 12e-12, 3e-12, 9.5e-12, c0_f=2e-12, c_motional_f=5e-15),
        lambda: crystal.load_capacitance(12e-12, 12e-12, 3e-12, cl_spec_f=12e-12, c0_f=2e-12, c_motional_f=5e-15),
    ],
    "calc.crystal.oscillation_margin": [
        lambda: crystal.oscillation_margin(50, 24e6, 3e-12, 9e-12),
        lambda: crystal.oscillation_margin(50, 24e6, 3e-12, 9e-12, gm_crit_max_a_per_v=1.95e-3),
        lambda: crystal.oscillation_margin(50, 24e6, 3e-12, 9e-12, gm_crit_max_a_per_v=0.75e-3),
        lambda: crystal.oscillation_margin(50, 24e6, 3e-12, 9e-12, gm_crit_max_a_per_v=0.5e-3),
        lambda: crystal.oscillation_margin(50, 24e6, 3e-12, 9e-12, gm_a_per_v=5e-3),
        lambda: crystal.oscillation_margin(50, 24e6, 3e-12, 9e-12, gm_a_per_v=2e-3),
        lambda: crystal.oscillation_margin(50, 24e6, 3e-12, 9e-12, gm_a_per_v=5e-3, gm_crit_max_a_per_v=0.75e-3),
    ],
    "calc.crystal.drive_level": [
        lambda: crystal.drive_level(50, 100e-6, i_rms_a=1e-3),
        lambda: crystal.drive_level(50, 100e-6, i_rms_a=1.3e-3),
        lambda: crystal.drive_level(50, 100e-6, i_rms_a=1.6e-3),
        lambda: crystal.drive_level(50, 100e-6, f_hz=24e6, c_tot_f=15e-12, v_pp_v=1.0),
    ],
    "calc.i2c.i2c_rise_time": [
        lambda: i2c.i2c_rise_time(2.2e3, 100e-12),
        lambda: i2c.i2c_rise_time(3.3e3, 100e-12),
        lambda: i2c.i2c_rise_time(4.7e3, 100e-12),
        lambda: i2c.i2c_rise_time(4.7e3, 100e-12, mode="standard"),
        lambda: i2c.i2c_rise_time(1e3, 150e-12, mode="fast_plus"),
    ],
    "calc.i2c.i2c_pullup_range": [
        lambda: i2c.i2c_pullup_range(3.3, 100e-12),
        lambda: i2c.i2c_pullup_range(3.3, 100e-12, r_pullup_ohm=2.2e3),
        lambda: i2c.i2c_pullup_range(3.3, 100e-12, r_pullup_ohm=470.0),
        lambda: i2c.i2c_pullup_range(3.3, 100e-12, r_pullup_ohm=10e3),
        lambda: i2c.i2c_pullup_range(3.3, 500e-12),
        lambda: i2c.i2c_pullup_range(3.3, 390e-12),
        lambda: i2c.i2c_pullup_range(1.8, 100e-12, mode="standard"),
    ],
    "calc.protection.tvs_standoff": [
        lambda: protection.tvs_standoff(3.465, 5.0),
        lambda: protection.tvs_standoff(4.909, 5.0),
        lambda: protection.tvs_standoff(26.4, 24.0),
        lambda: protection.tvs_standoff(5.0, 5.0, ripple_pp_v=0.2, v_br_min_v=5.05),
    ],
    "calc.protection.tvs_clamp": [
        lambda: protection.tvs_clamp(20.0, 1.0, CLAMP, i_pp_max_a=10.0),
        lambda: protection.tvs_clamp(6.0, 1.0, CLAMP, i_pp_max_a=10.0),
        lambda: protection.tvs_clamp(5.0, 1.0, CLAMP, i_pp_max_a=10.0),
        lambda: protection.tvs_clamp(20.0, 1.0, CLAMP),
        lambda: protection.tvs_clamp(20.0, 12.0, CLAMP, i_pp_max_a=10.0),
        lambda: protection.tvs_clamp(20.0, 1.0, CLAMP, p_pp_max_w=4.0),
        lambda: protection.tvs_clamp(8.0, 20.0, CLAMP),
        lambda: protection.tvs_clamp(20.0, 20.0, CLAMP),
        lambda: protection.tvs_clamp(4.0, 1.0, [(1.0, 5.5)]),
    ],
}

CASES = [(name, i, fn) for name, fns in SAMPLES.items() for i, fn in enumerate(fns)]


@pytest.mark.parametrize("name,i,fn", CASES, ids=[f"{n}[{i}]" for n, i, _ in CASES])
def test_result_reads_plainly(name, i, fn):
    r = fn()
    assert plain_problems(r) == [], (r.verdict, r.summary)


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_samples_reach_more_than_one_verdict(name):
    assert len({fn().verdict for fn in SAMPLES[name]}) > 1


def test_samples_cover_the_verdicts_each_function_can_give():
    seen = {name: {fn().verdict for fn in fns} for name, fns in SAMPLES.items()}
    assert {Verdict.PASS, Verdict.MARGINAL, Verdict.FAIL} <= seen["calc.buck.dropout"]
    assert {Verdict.INFO, Verdict.PASS, Verdict.MARGINAL, Verdict.FAIL} <= seen["calc.buck.inductor_ripple"]
    assert {Verdict.PASS, Verdict.MARGINAL, Verdict.FAIL} <= seen["calc.buck.current_slew"]
    assert {Verdict.PASS, Verdict.MARGINAL, Verdict.UNKNOWN} <= seen["calc.buck.example_envelope"]
    assert {Verdict.UNKNOWN, Verdict.PASS, Verdict.MARGINAL, Verdict.FAIL} <= seen["calc.crystal.oscillation_margin"]
    assert {Verdict.INFO, Verdict.PASS, Verdict.FAIL} <= seen["calc.i2c.i2c_pullup_range"]
    assert {Verdict.PASS, Verdict.MARGINAL, Verdict.FAIL, Verdict.UNKNOWN} <= seen["calc.protection.tvs_clamp"]


def test_summaries_carry_the_real_numbers():
    r = buck.dropout(3.7, VOUT, FSW, 45e-9, 10e-9)
    assert r.verdict is Verdict.MARGINAL
    assert fmt(r.outputs["headroom"].value, "V") in r.summary and "3.7 V" in r.summary
    r = protection.tvs_standoff(26.4, 24.0)
    assert r.summary.startswith("The rail peaks at 26.4 V, above the TVS standoff of 24 V.")
    assert r.key_line()[0]["label"] == "Rail peak" and r.key_line()[0]["want"] == "22.8 V or less"
    r = i2c.i2c_rise_time(4.7e3, 100e-12)
    assert "398 ns" in r.summary and "300 ns" in r.summary
    r = crystal.oscillation_margin(80.0, 8e6, 2e-12, 8e-12, gm_crit_max_a_per_v=1.5e-3)
    assert r.plots[0].caption.startswith("The dot is this design:") and "Gmcritmax" in r.plots[0].caption
    assert r.plots[0].series[0].label == "Critical gm"
