"""Plain-language summaries, labels and key numbers for the divider, filter, MLCC, timing and thermal calculators."""

import numpy as np
import pytest

from boardreview.calc.base import Verdict, fmt, plain_problems
from boardreview.calc.divider import divider_output, enable_thresholds, regulator_output
from boardreview.calc.lc_tank import BeadRLC, Cap, bead_from_spec, damping_options, lc_filter, parse_bead_csv
from boardreview.calc.mlcc_bias import mlcc_effective
from boardreview.calc.thermal import buck_ic_dissipation, junction_temp, via_resistance
from boardreview.calc.timing import budget, exposure_time, line_time, rc_edge, smear_px, timestamp_error

KPZ = bead_from_spec(120.0, 100e6, 0.045, "synthetic bead")
C100N = Cap(100e-9, esr_ohm=0.02, esl_h=0.4e-9)
DAMPER = Cap(1e-6, esr_ohm=1.0, esl_h=0.4e-9)
CURVE_V = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.3])
CURVE_K = np.array([1.0, 0.85, 0.62, 0.45, 0.34, 0.27, 0.21])
# Synthetic bead table, RDC 45 mohm in series with 270 nH || 170 ohm (same construction as tests/test_calc_lc_tank.py).
BEAD_CSV = """Frequency [MHz],R [Ohm],X [Ohm]
0.1,0.0451693,0.169646
0.5,0.0492322,0.848209
0.9671,0.0608322,1.64049
1,0.0619276,1.69629
2,0.11269,3.39157
5,0.467181,8.46124
10,1.72123,16.7973
50,33.9317,67.9149
100,84.8678,84.9998
500,163.48,32.7553
1000,168.355,16.8661
"""
RUN = (1.18, 1.22, 1.26, 0.98, 1.01, 1.04, 57.6e3, 27.4e3)

SAMPLES = {
    "calc.divider.divider_output": [
        lambda: divider_output(3.3, 10e3, 10e3),
        lambda: divider_output(12.0, 100e3, 10e3, vin_tol=0.05, i_leak_a=1e-6),
    ],
    "calc.divider.regulator_output": [
        lambda: regulator_output(0.958, 0.970, 0.982, 12.7e3, 3.24e3, i_fb_a=20e-9, v_out_max_allowed_v=5.0,
                                 v_out_min_allowed_v=4.5),
        lambda: regulator_output(0.958, 0.970, 0.982, 12.7e3, 3.24e3, v_out_max_allowed_v=4.7),
        lambda: regulator_output(0.958, 0.970, 0.982, 12.7e3, 3.24e3, v_out_min_allowed_v=4.8),
        lambda: regulator_output(0.958, 0.970, 0.982, 12.7e3, 3.24e3, v_out_max_allowed_v=5.0),
        lambda: regulator_output(0.958, 0.970, 0.982, 12.7e3, 3.24e3),
    ],
    "calc.divider.enable_thresholds": [
        lambda: enable_thresholds(1.15, 1.20, 1.25, 1.05, 1.10, 1.15, 100e3, 10.0, r_tol=0.01, i_leak_a=1e-6,
                                  vin_min_v=21.6),
        lambda: enable_thresholds(*RUN, r_tol=0.01, i_leak_a=3e-6, vin_min_v=4.03),
        lambda: enable_thresholds(*RUN, r_tol=0.01, i_leak_a=3e-6, vin_min_v=4.2),
        lambda: enable_thresholds(*RUN, vin_min_v=6.0),
        lambda: enable_thresholds(*RUN),
    ],
    "calc.lc_tank.damping_options": [lambda: damping_options(1e-6, 100e-9)],
    "calc.lc_tank.lc_filter": [
        lambda: lc_filter(KPZ, C100N, [1.19e6]),
        lambda: lc_filter(KPZ, C100N, [5e6], harmonics=1),
        lambda: lc_filter(KPZ, C100N, [1.19e6], dampers=[DAMPER]),
        lambda: lc_filter(parse_bead_csv(BEAD_CSV, rdc_ohm=0.045), C100N, [1.19e6], dampers=[DAMPER]),
        lambda: lc_filter(BeadRLC(1.2e-6, 0.15, 600.0), Cap(1e-6, 0.01, 0.4e-9)),
    ],
    "calc.mlcc_bias.mlcc_effective": [
        lambda: mlcc_effective(22e-6, "X5R", 0.2, v_bias_v=5.0, curve_v=CURVE_V, curve_ratio=CURVE_K,
                               c_required_f=10e-6),
        lambda: mlcc_effective(22e-6, "X5R", 0.2, v_bias_v=1.0, curve_v=CURVE_V, curve_ratio=CURVE_K,
                               c_required_f=10e-6),
        lambda: mlcc_effective(100e-9, "X7R", 0.1, v_bias_v=3.3),
        lambda: mlcc_effective(22e-6, "X5R", 0.2, v_bias_v=7.0, curve_v=CURVE_V, curve_ratio=CURVE_K),
        lambda: mlcc_effective(1e-6, "X5R", 0.1, t_min_c=-40.0, t_max_c=105.0),
        lambda: mlcc_effective(10e-12, "C0G", 0.05, t_min_c=-40.0, t_max_c=90.0),
    ],
    "calc.timing.budget": [
        lambda: budget({"t_setup": 2e-6, "t_prop": 3e-6}, 10e-6),
        lambda: budget({"t_setup": 4e-6, "t_prop": 4.5e-6}, 10e-6),
        lambda: budget({"t_setup": 6e-6, "t_prop": 5e-6}, 10e-6),
    ],
    "calc.timing.rc_edge": [
        lambda: rc_edge(2.2e3, 100e-12, limit_s=1e-6),
        lambda: rc_edge(10e3, 400e-12, limit_s=1e-6),
        lambda: rc_edge(10e3, 1e-6),
    ],
    "calc.timing.timestamp_error": [
        lambda: timestamp_error(1.0, 3.0, budget_s=50e-6),
        lambda: timestamp_error(1.0, 3.0, budget_s=200e-6),
        lambda: timestamp_error(1.0, 3.0),
    ],
    "calc.timing.line_time": [lambda: line_time(2666, 74.25e6)],
    "calc.timing.exposure_time": [
        lambda: exposure_time(278, 35.906e-6, offset_s=1e-6, t_target_s=10e-3, tol_s=0.1e-3),
        lambda: exposure_time(278, 35.906e-6, t_target_s=20e-3, tol_s=0.1e-3),
        lambda: exposure_time(0, 35.906e-6),
        lambda: exposure_time(278, 35.906e-6),
    ],
    "calc.timing.smear_px": [
        lambda: smear_px(0.1, 10e-3, 20.0, limit_px=0.5),
        lambda: smear_px(1.0, 50e-3, 20.0, limit_px=0.5),
        lambda: smear_px(1.0, 50e-3, 20.0),
    ],
    "calc.thermal.junction_temp": [
        lambda: junction_temp(0.5, 40.0, 25.0, 125.0),
        lambda: junction_temp(1.5, 40.0, 50.0, 125.0),
        lambda: junction_temp(2.5, 40.0, 50.0, 125.0),
    ],
    "calc.thermal.buck_ic_dissipation": [lambda: buck_ic_dissipation(5.0, 3.3, 2.0, 0.1, 0.07, 2e6, 6e-9, 500e-6)],
    "calc.thermal.via_resistance": [lambda: via_resistance(9, 0.3e-3, 25e-6, 1.6e-3)],
}

CASES = [(name, i) for name, calls in SAMPLES.items() for i in range(len(calls))]


@pytest.mark.parametrize("name,i", CASES, ids=[f"{n}[{i}]" for n, i in CASES])
def test_result_reads_plainly(name, i):
    r = SAMPLES[name][i]()
    assert plain_problems(r) == [], (r.verdict.value, r.summary)
    assert r.key, "no key numbers"


INFO_ONLY = {"calc.divider.divider_output"}


@pytest.mark.parametrize("name", [n for n, calls in SAMPLES.items() if len(calls) > 1 and n not in INFO_ONLY])
def test_samples_reach_more_than_one_verdict(name):
    assert len({f().verdict for f in SAMPLES[name]}) > 1


def test_every_plot_has_a_caption_with_numbers():
    for calls in SAMPLES.values():
        for f in calls:
            for p in f().plots:
                assert p.caption and any(ch.isdigit() for ch in p.caption), p.title


def test_enable_summary_reads_like_the_bench():
    r = SAMPLES["calc.divider.enable_thresholds"][0]()
    assert r.verdict is Verdict.FAIL
    assert "12.8 kV" in r.summary and "1.25 V" in r.summary and "may never turn on" in r.summary
    assert [k["label"] for k in r.key_line()] == ["Turn-on, worst case", "Lowest supply"]
    assert r.key_line()[0]["want"] == f"under {fmt(21.6, 'V')}"


def test_an_undamped_peak_away_from_the_switcher_does_not_read_as_fine():
    r = SAMPLES["calc.lc_tank.lc_filter"][4]()
    assert r.verdict is Verdict.MARGINAL and r.outputs["peak"].value > 6.0
    assert "needs damping" in r.summary
