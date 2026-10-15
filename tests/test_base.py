from boardreview.calc.base import Quantity, Result, Verdict


def test_result_markdown_shows_formula_inputs_outputs():
    r = Result(
        name="divider",
        formula="vout = vin * r2 / (r1 + r2)",
        inputs={"vin": Quantity(3.3, "V"), "r1": Quantity(54.9e3, "ohm"), "r2": Quantity(12.1e3, "ohm")},
        outputs={"vout": Quantity(0.5960, "V")},
        verdict=Verdict.PASS,
    )
    md = r.to_markdown()
    assert "vout = vin * r2 / (r1 + r2)" in md
    assert "in  r1 = 54900 ohm" in md
    assert "out vout = 0.596 V" in md
