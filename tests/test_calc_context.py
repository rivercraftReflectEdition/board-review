"""Finite JSON, input context (nominal, worst case, example, ideal), CCM negative current and true LC damping Q."""

import json
import math
from pathlib import Path

import pytest

from boardreview.__main__ import main
from boardreview.calc import buck, loop
from boardreview.calc.base import Quantity, Verdict, plain_problems
from boardreview.calc.lc_tank import BeadRLC, Cap, lc_filter
from boardreview.report import plain


def _finite(d: dict) -> str:
    return json.dumps(d, allow_nan=False)


def test_non_finite_quantities_serialize_as_null_with_a_note():
    d = Quantity(math.inf, "dB", label="Gain margin").to_dict()
    assert d["value"] is None and "infinite" in d["note"] and d["label"] == "Gain margin"
    assert Quantity(math.nan, "Hz", "from the sweep").to_dict()["note"].startswith("from the sweep; ")


def test_loop_and_filter_results_are_finite_json():
    no_phase_crossing = loop.margins([loop.Integrator(10e3)], 10, 1e6)
    open_load = lc_filter(BeadRLC(1e-6, 0.05), Cap(1e-6, 0.01), [500e3])
    for r in (no_phase_crossing, open_load):
        _finite(r.to_dict("calc.x"))


def test_current_slew_below_vout_is_an_explicit_not_regulating_result():
    r = buck.current_slew(2.7, 3.3, 2.2e-6, 1.0)
    text = _finite(r.to_dict("calc.buck.current_slew"))
    assert "Infinity" not in text and "NaN" not in text
    assert "not regulating" in r.summary and "dropout" in r.summary
    assert "s_up" not in r.outputs and "down_over_up" not in r.outputs
    assert r.outputs["vin_x_dmax"].value == pytest.approx(2.7)
    assert plain_problems(r) == []


@pytest.mark.parametrize("context", ["nominal", "example", "ideal"])
def test_a_pass_from_nominal_example_or_ideal_inputs_is_not_a_pass(context):
    r = buck.current_slew(12.0, 3.3, 2.2e-6, 0.9, context=context)
    assert r.verdict is Verdict.UNKNOWN and r.context == context
    assert context.replace("_", " ") in r.summary and "worst case" in r.summary
    assert plain_problems(r) == []
    assert r.to_dict("calc.buck.current_slew")["context"] == context
    good = loop.margins([loop.Integrator(10e3), loop.Pole(200e3)], context=context)
    assert good.verdict is Verdict.UNKNOWN and plain_problems(good) == []


def test_worst_case_inputs_keep_the_pass_and_failures_stay_failures():
    assert buck.current_slew(12.0, 3.3, 2.2e-6, 0.9, context="worst_case").verdict is Verdict.PASS
    assert buck.current_slew(3.4, 3.3, 2.2e-6, 0.9, context="nominal").verdict is Verdict.FAIL
    with pytest.raises(ValueError):
        buck.current_slew(12.0, 3.3, 2.2e-6, 0.9, context="typical")


def test_a_passing_check_on_nominal_calculations_is_flagged():
    calc = buck.current_slew(12.0, 3.3, 2.2e-6, 0.9, context="nominal").to_dict("calc.buck.current_slew")
    check = {"id": "U2.BR-4", "verdict": "pass", "summary": "Slew is fine.", "results": [calc]}
    problems = plain.check_problems(check)
    assert problems and "nominal" in problems[0]


def test_ccm_ripple_with_negative_valley_names_pfm_and_zero_current_detection():
    r = buck.inductor_ripple(5.0, 3.3, 2e6, 2.2e-6, 0.0)
    assert r.outputs["i_valley"].value < 0
    assert "PFM" in r.summary and "zero-current" in r.summary
    assert any("negative" in a for a in r.assumptions)
    assert plain_problems(r) == []
    assert "PFM" not in buck.inductor_ripple(5.0, 3.3, 2e6, 2.2e-6, 1.0).summary


def test_lc_damping_q_is_sqrt_l_over_c_over_r_total_and_peak_gain_is_renamed():
    # Interior sweep value from a review: L puts f0 at 2.1 MHz on 20.1 uF, 30 mohm bead, 10 mohm ESR, open load.
    c = 20.1e-6
    l = 1 / ((2 * math.pi * 2.1e6) ** 2 * c)
    r = lc_filter(BeadRLC(l, 0.03, 1e12, assumed=True), Cap(c, 0.01), [2e6, 2.1e6], r_load_ohm=1e12)
    assert "q" not in r.outputs
    assert r.outputs["q_damping"].value == pytest.approx(math.sqrt(l / c) / 0.04, rel=1e-3)
    assert r.outputs["q_damping"].value == pytest.approx(0.0943, abs=5e-4)
    assert r.outputs["peak_gain_linear"].value == pytest.approx(1.0, abs=0.02)
    assert "0.0943" in r.summary
    assert plain_problems(r) == []


def test_lc_verdict_follows_the_true_q_not_the_peak_gain():
    # Series RLC, open load: Q = 1/0.5128 = 1.95 under the 2.0 (6 dB) limit, but the peak gain is 6.09 dB.
    r = lc_filter(BeadRLC(1e-6, 1 / 1.95), Cap(1e-6), [])
    assert r.outputs["peak"].value > 6.0
    assert r.outputs["q_damping"].value == pytest.approx(1.95, rel=1e-3)
    assert r.verdict is Verdict.PASS
    r = lc_filter(BeadRLC(1e-6, 1 / 2.2), Cap(1e-6), [])
    assert r.verdict is Verdict.MARGINAL and "needs damping" in r.summary


def test_lc_q_with_a_load_or_damper_is_an_upper_bound():
    r = lc_filter(BeadRLC(1e-6, 0.05), Cap(1e-6), [], r_load_ohm=2.0)
    assert "upper bound" in r.outputs["q_damping"].note


def test_report_writes_findings_as_finite_json(tmp_path):
    board = Path(__file__).parent / "fixtures" / "report"
    assert main(["prep", str(board / "board.kicad.xml"), "--out", str(tmp_path / "facts")]) == 0
    calc = buck.current_slew(12.0, 3.3, 2.2e-6, 0.9).to_dict("calc.buck.current_slew")
    calc["outputs"]["s_up"]["value"] = math.inf
    f = {"id": "F-001", "title": "U2 slew headroom", "severity": "minor", "block": "buck_regulator",
         "failure_mode": "other", "claim": "A synthetic claim long enough.", "evidence": [{"kind": "bom", "ref": "L2"}],
         "fix": "None.", "verification": {"status": "CONFIRMED"}, "calculations": [calc]}
    (tmp_path / "findings.json").write_text(json.dumps([f]), encoding="utf-8")
    assert main(["report", "--findings", str(tmp_path / "findings.json"), "--facts", str(tmp_path / "facts"),
                 "--out", str(tmp_path / "out")]) == 0
    text = (tmp_path / "out" / "findings.json").read_text(encoding="utf-8")
    assert "Infinity" not in text
    assert json.loads(text)[0]["calculations"][0]["outputs"]["s_up"]["value"] is None
