"""Worked examples W33 to W36 and bounded frequency screening."""

import json
import math

import pytest

from boardreview.calc.base import Verdict, plain_problems
from boardreview.calc.spur import alias, frequency_plan, search, supply_spur
from boardreview.report.svgplot import plot_svg


SAMPLES = {
    "calc.spur.alias": [lambda: alias(50e6, 61.44e6)],
    "calc.spur.search": [
        lambda: search({"buck": 2.2e6}, {"RF": (98e6, 102e6)}, 60),
        lambda: search({"clock": 25e6}, {"RF": (98e6, 102e6)}, 4, limit_dbfs=-90),
        lambda: search({"clock": 25e6}, {"RF": (98e6, 102e6)}, 4,
                       limit_dbfs=-90, levels_dbfs={"clock": -80}),
        lambda: search({"clock": 25e6}, {"RF": (98e6, 102e6)}, 4,
                       limit_dbfs=-90, levels_dbfs={"clock": -100}),
        lambda: search([1e6], {"RF": (98e6, 102e6)}, 2, limit_dbfs=-90),
    ],
    "calc.spur.frequency_plan": [
        lambda: frequency_plan(100e6, 10.7e6, "high"),
        lambda: frequency_plan(100e6, 10.7e6, "high", 40),
        lambda: frequency_plan(100e6, 10.7e6, "high", 40, 39, 50),
        lambda: frequency_plan(100e6, 10.7e6, "high", 40, 50, 39),
        lambda: frequency_plan(100e6, 10.7e6, "high", 40, 40, 40, context="worst_case"),
        lambda: frequency_plan(100e6, 10.7e6, "high", 40, 40, 40),
    ],
    "calc.spur.supply_spur": [
        lambda: supply_spur(0.01, 2, -60),
        lambda: supply_spur(0.01, 2, -60, -100, context="worst_case"),
        lambda: supply_spur(0.01, 2, -60, -110),
        lambda: supply_spur(0.01, 2, -60, -100),
    ],
}


def _hits(result):
    return [(dict(part.split("=", 1) for part in q.note.split("; ")), q.value)
            for key, q in result.outputs.items() if key.startswith("hit_") and key.endswith("_frequency_hz")]


def test_w33_aggressor_harmonics_and_lo_difference():
    # Plan W33, enumerated integer products: 45*2.2, 46*2.2, 4*25 and 110.7-4*25 MHz.
    result = search({"buck": 2.2e6, "clock": 25e6}, {"RF": (98e6, 102e6), "IF": (10.6e6, 10.8e6)},
                    60, lo_hz=[110.7e6])
    direct = [(h["source"], int(h["n"]), f) for h, f in _hits(result) if h["band"] == "RF" and h["m"] == "0"]
    assert [(s, n) for s, n, _ in direct] == [("buck", 45), ("buck", 46), ("clock", 4)]
    assert [f for _, _, f in direct] == pytest.approx([99e6, 101.2e6, 100e6], abs=1e-7)
    mixed = [f for h, f in _hits(result) if h["source"] == "clock" and h["band"] == "IF"
             and h["n"] == "4" and h["m"] == "1" and h["sign"] == "-"]
    assert mixed == pytest.approx([10.7e6], abs=1e-7)
    assert result.verdict is Verdict.INFO
    assert "spur limit" in result.summary


@pytest.mark.parametrize("tone_hz,expected_hz", [(50e6, 11.44e6), (75e6, 13.56e6),
                                               (99e6, 23.88e6), (59.4e6, 2.04e6)])
def test_w34_aliases(tone_hz, expected_hz):
    # Plan W34, MT-002 Rev A p.5. Values are distances from 61.44 or 122.88 MHz.
    result = alias(tone_hz, 61.44e6)
    assert result.outputs["f_alias_hz"].value == pytest.approx(expected_hz, abs=1e-7)
    assert result.verdict is Verdict.INFO


def test_w34_harmonic_alias_in_search():
    result = search({"buck": 2.2e6}, {"baseband": (2.03e6, 2.05e6)}, 27, fs_hz=61.44e6)
    matches = [(h, f) for h, f in _hits(result) if h["kind"] == "alias" and h["n"] == "27"]
    assert len(matches) == 1
    assert matches[0][1] == pytest.approx(2.04e6, abs=1e-7)


@pytest.mark.parametrize("rf_hz,if_hz,side,lo_hz,image_hz,half_hz", [
    (100e6, 10.7e6, "high", 110.7e6, 121.4e6, 105.35e6),
    (1950e6, 200e6, "low", 1750e6, 1550e6, 1850e6),
])
def test_w35_frequency_plan(rf_hz, if_hz, side, lo_hz, image_hz, half_hz):
    # W35. AN1838 March 2003 p.2 to 3 prints the 1950/1750/1850 MHz half-IF example.
    result = frequency_plan(rf_hz, if_hz, side)
    assert result.outputs["lo_hz"].value == pytest.approx(lo_hz, abs=1e-6)
    assert result.outputs["image_hz"].value == pytest.approx(image_hz, abs=1e-6)
    assert result.outputs["half_if_hz"].value == pytest.approx(half_hz, abs=1e-6)
    assert result.verdict is Verdict.INFO


def test_w36_supply_spur_and_signed_psrr():
    # MS-2210 February 2012 p.3 rule: 10 mV / 2 V is -46.0206 dB; add -60 dB.
    result = supply_spur(0.01, 2, -60)
    expected_dbfs = -46.020599913279625 - 60
    assert result.outputs["spur_dbfs"].value == pytest.approx(expected_dbfs, abs=1e-10)
    assert result.outputs["spur_dbfs"].value == pytest.approx(-106, abs=0.03)
    assert result.verdict is Verdict.INFO
    assert "spur limit" in result.summary


@pytest.mark.parametrize("f_hz,expected_hz", [(0, 0), (5, 5), (10, 0), (15, 5), (-17, 3), (37, 3)])
def test_alias_dc_nyquist_negative_and_high_zones(f_hz, expected_hz):
    assert alias(f_hz, 10).outputs["f_alias_hz"].value == pytest.approx(expected_hz, abs=1e-12)


def test_mixing_orders_multiple_los_sum_and_absolute_difference():
    result = search({"source": 3}, {"all": (0, 100)}, 2, lo_hz=[5, 7], m_max=3)
    hits = _hits(result)
    # Explicit small integer table, independent of the implementation's interval arithmetic.
    expected = [(n * 3, n, 0, 0, "+") for n in (1, 2)]
    expected += [(abs(m * lo + sign * n * 3), n, m, j, "+" if sign == 1 else "-")
                 for n in (1, 2) for j, lo in ((1, 5), (2, 7)) for m in (1, 2, 3) for sign in (1, -1)]
    actual = [(f, int(h["n"]), int(h["m"]), int(h["LO"]), h["sign"]) for h, f in hits]
    assert sorted(actual) == sorted(expected)
    assert result.outputs["hit_count"].value == 26


def test_spread_interval_interior_and_inclusive_edges():
    result = search({"spread": (9, 11)}, {"RF": (29, 31), "edge": (33, 33)}, 3)
    matches = {(h["band"], h["n"]): f for h, f in _hits(result)}
    assert matches == {("RF", "3"): 29, ("edge", "3"): 33}
    assert result.outputs["hit_1_low_hz"].value == pytest.approx(27, abs=1e-12)
    assert result.outputs["hit_1_high_hz"].value == pytest.approx(33, abs=1e-12)


@pytest.mark.parametrize("source_hz,expected_low_hz,expected_high_hz", [
    ((9, 11), 0, 1), ((4, 6), 4, 5), ((10, 20), 0, 5), ((2, 3), 2, 3),
])
def test_alias_interval_preserves_internal_fold_extrema(source_hz, expected_low_hz, expected_high_hz):
    result = search({"spread": source_hz}, {"baseband": (0, 5)}, 1, fs_hz=10)
    alias_hits = [i for i in range(1, int(result.outputs["hit_count"].value) + 1)
                  if "kind=alias" in result.outputs[f"hit_{i}_frequency_hz"].note]
    assert len(alias_hits) == 1
    i = alias_hits[0]
    assert result.outputs[f"hit_{i}_low_hz"].value == pytest.approx(expected_low_hz, abs=1e-12)
    assert result.outputs[f"hit_{i}_high_hz"].value == pytest.approx(expected_high_hz, abs=1e-12)


def test_mixing_interval_crossing_zero_has_internal_minimum():
    result = search({"spread": (9, 11)}, {"baseband": (0, 0.1)}, 1, lo_hz=[10])
    assert len(_hits(result)) == 1
    assert result.outputs["hit_1_low_hz"].value == pytest.approx(0, abs=1e-12)
    assert result.outputs["hit_1_high_hz"].value == pytest.approx(1, abs=1e-12)


def test_aliases_of_lo_products_are_searched():
    # 110.7 + 100 = 210.7 MHz; its distance from 3*61.44 = 184.32 MHz is 26.38 MHz.
    result = search({"clock": 25e6}, {"baseband": (26.37e6, 26.39e6)}, 4, lo_hz=[110.7e6], fs_hz=61.44e6)
    assert any(h["kind"] == "alias" and h["m"] == "1" and h["n"] == "4" and h["sign"] == "+"
               and f == pytest.approx(26.38e6, abs=1e-7) for h, f in _hits(result))


@pytest.mark.parametrize("limit_dbfs,levels_dbfs,expected", [
    (None, None, Verdict.INFO), (None, {"clock": -20}, Verdict.INFO),
    (-90, None, Verdict.UNKNOWN), (-90, {"clock": -80}, Verdict.FAIL),
    (-90, {"clock": -90}, Verdict.INFO), (-90, {"clock": -100}, Verdict.INFO),
])
def test_search_verdicts(limit_dbfs, levels_dbfs, expected):
    result = search({"clock": 25e6}, {"RF": (99e6, 101e6)}, 4,
                    limit_dbfs=limit_dbfs, levels_dbfs=levels_dbfs)
    assert result.verdict is expected


def test_known_excess_takes_precedence_over_missing_levels():
    result = search({"clock": 25, "buck": 20}, {"RF": (100, 100)}, 5,
                    limit_dbfs=-90, levels_dbfs={"clock": -80})
    assert result.verdict is Verdict.FAIL
    assert result.outputs["unbounded_count"].value == 1


def test_no_hit_is_information_not_a_board_pass():
    result = search([1], {"RF": (100, 101)}, 2, limit_dbfs=-90)
    assert result.verdict is Verdict.INFO
    assert result.outputs["hit_count"].value == 0


@pytest.mark.parametrize("image_db,half_db,expected", [
    (None, None, Verdict.UNKNOWN), (50, None, Verdict.UNKNOWN), (None, 50, Verdict.UNKNOWN),
    (39, None, Verdict.FAIL), (None, 39, Verdict.FAIL), (40, 40, Verdict.PASS),
    (39, 50, Verdict.FAIL), (50, 39, Verdict.FAIL),
])
def test_frequency_plan_verdicts(image_db, half_db, expected):
    result = frequency_plan(100e6, 10.7e6, "high", 40, image_db, half_db, context="worst_case")
    assert result.verdict is expected


@pytest.mark.parametrize("limit_dbfs,expected", [(None, Verdict.INFO), (-100, Verdict.PASS), (-110, Verdict.FAIL)])
def test_supply_spur_verdicts(limit_dbfs, expected):
    assert supply_spur(0.01, 2, -60, limit_dbfs, context="worst_case").verdict is expected


def test_supply_spur_limit_equality_and_positive_transfer():
    assert supply_spur(0.1, 1, -60, -80, context="worst_case").verdict is Verdict.PASS
    assert supply_spur(0.1, 1, 6).outputs["spur_dbfs"].value == pytest.approx(-14, abs=1e-12)


@pytest.mark.parametrize("context", ["nominal", "example", "ideal"])
def test_nominal_rejection_or_transfer_cannot_pass(context):
    assert frequency_plan(100, 10, "high", 40, 50, 50, context=context).verdict is Verdict.UNKNOWN
    assert supply_spur(0.01, 2, -60, -100, context=context).verdict is Verdict.UNKNOWN


@pytest.mark.parametrize("name", SAMPLES)
def test_every_branch_reads_plainly_and_serializes(name):
    for make in SAMPLES[name]:
        result = make()
        assert plain_problems(result) == []
        assert result.context
        assert result.refs and result.assumptions and result.key
        json.dumps(result.to_dict(name), allow_nan=False)


def test_plot_contains_every_harmonic_and_named_bands():
    result = search({"clock": 25}, {"RF": (98, 102), "IF": (10, 11)}, 4, lo_hz=[110.7])
    plot = result.plots[0]
    assert {s.label for s in plot.series} == {"Aggressor harmonics", "RF band", "IF band"}
    harmonic_markers = [m for m in plot.markers if "harmonic" in m.label and m.y == 0]
    assert [m.x for m in harmonic_markers] == pytest.approx([25, 50, 75, 100], abs=1e-12)
    rendered = plot_svg(plot.to_dict(), "spur-example")
    assert "<svg" in rendered and "RF band" in rendered
    assert "nan" not in rendered.lower()


def test_net_names_with_underscores_keep_plain_labels():
    result = search({"U1_SW": 25}, {"RF_band": (98, 102)}, 4)
    assert plain_problems(result) == []
    assert any(h["source"] == "U1_SW" and h["band"] == "RF_band" for h, _ in _hits(result))


@pytest.mark.parametrize("make", [
    lambda: alias(math.nan, 1), lambda: alias(1, 0), lambda: alias(1, math.inf),
    lambda: search({}, {"RF": (1, 2)}, 1), lambda: search([1], {}, 1),
    lambda: search([1], {"RF": (2, 1)}, 1), lambda: search([0], {"RF": (1, 2)}, 1),
    lambda: search([1], {"RF": (1, 2)}, 0), lambda: search([1], {"RF": (1, 2)}, 1.5),
    lambda: search([1], {"RF": (1, 2)}, True), lambda: search([1], {"RF": (1, 2)}, 1, m_max=0),
    lambda: search([1], {"RF": (1, 2)}, 1, lo_hz=[0]),
    lambda: search([1], {"RF": (1, 2)}, 1, fs_hz=-1),
    lambda: search([1], {"RF": (1, 2)}, 1, limit_dbfs=math.inf),
    lambda: search([1], {"RF": (1, 2)}, 1, levels_dbfs={"wrong source": -90}),
    lambda: search({"a": (1, 2, 3)}, {"RF": (1, 2)}, 1),
    lambda: frequency_plan(100, -1, "high"), lambda: frequency_plan(100, 10, "wrong"),
    lambda: frequency_plan(10, 10, "low"), lambda: frequency_plan(100, 10, "high", -1),
    lambda: frequency_plan(100, 10, "high", 10, math.nan),
    lambda: supply_spur(0, 2, -60), lambda: supply_spur(0.01, 0, -60),
    lambda: supply_spur(0.01, 2, math.nan), lambda: supply_spur(0.01, 2, -60, math.inf),
])
def test_invalid_inputs_raise(make):
    with pytest.raises(ValueError):
        make()
