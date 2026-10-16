"""Every calculator labels its numbers and explains its result in plain words that agree with its verdict."""

import importlib
import inspect
from pathlib import Path

import pytest

from boardreview.calc.base import Key, Quantity, Result, Verdict, fmt, plain_problems

CALC = Path(__file__).resolve().parent.parent / "tools" / "boardreview" / "calc"
SAMPLE_MODULES = ("test_plain_power_io", "test_plain_passives", "test_plain_loop_sim", "test_jitter", "test_clock_term", "test_rf", "test_spur")


def calculators() -> list[str]:
    out = []
    for p in sorted(CALC.glob("*.py")):
        if p.stem in ("__init__", "base", "curves"):
            continue
        mod = importlib.import_module(f"boardreview.calc.{p.stem}")
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if fn.__module__ == mod.__name__ and not name.startswith("_") and \
                    inspect.signature(fn).return_annotation in (Result, "Result"):
                out.append(f"calc.{p.stem}.{name}")
    return out


def samples() -> dict:
    merged: dict = {}
    for m in SAMPLE_MODULES:
        merged.update(importlib.import_module(m).SAMPLES)
    return merged


def test_every_calculator_has_samples():
    assert len(calculators()) > 25
    assert sorted(set(calculators()) - set(samples())) == []


@pytest.mark.parametrize("name", calculators())
def test_calculator_reads_plainly(name):
    verdicts = set()
    for make in samples()[name]:
        r = make()
        assert plain_problems(r) == [], (name, plain_problems(r))
        assert r.summary and all(q.label for q in [*r.inputs.values(), *r.outputs.values()])
        verdicts.add(r.verdict)
    assert verdicts


def test_fmt_writes_numbers_the_normal_way():
    assert [fmt(64150, "Hz"), fmt(30.19, "deg"), fmt(0.0024, "V"), fmt(100e3, "ohm"), fmt(44e-6, "F")] == \
        ["64.2 kHz", "30.2°", "2.4 mV", "100 kΩ", "44 µF"]
    assert [fmt(85, "C"), fmt(27, "%"), fmt(3, "count"), fmt(6e7, "A/s"), fmt(999.96, "Hz"), fmt(None, "V")] == \
        ["85 °C", "27%", "3", "60 A/µs", "1 kHz", "n/a"]


def _result(summary: str, verdict: Verdict = Verdict.FAIL, label: str = "Phase margin") -> Result:
    return Result("loop", "PM = 180 + arg T", {"pm_min": Quantity(45, "deg", label="Phase margin target")},
                  {"pm": Quantity(30.19, "deg", label=label)}, verdict, summary=summary, key=(Key("pm", "45° or more"),))


def test_plain_problems_catches_what_a_reader_trips_on():
    good = "The loop has 30.2° of phase margin. We want 45°, so the rail rings after load steps."
    assert plain_problems(_result(good)) == []
    assert "no summary" in plain_problems(_result(""))
    assert any("does not state key" in p for p in plain_problems(_result("The margin is low.")))
    assert any("variable name pm_min" in p for p in plain_problems(_result(good + " Against pm_min.")))
    assert any("on a fail" in p for p in plain_problems(_result(good + " It passes.")))
    assert any("on a pass" in p for p in plain_problems(_result(good.replace("We want", "Too low against"),
                                                                 Verdict.PASS)))
    assert any("no label" in p for p in plain_problems(_result(good, label="")))
    assert any("dash" in p for p in plain_problems(_result(good + " \u2014 ringing.")))
