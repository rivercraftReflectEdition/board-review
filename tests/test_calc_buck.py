import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.buck import (
    BuckPoint,
    current_slew,
    dropout,
    duty_cycle,
    example_envelope,
    inductor_ripple,
    slew_clamp_vpp,
    soft_start_inrush,
)

# Sauron rev1, LTC3633A channel 1: 4.03 V in, 3.32 V out, 1.185 MHz, 2.2 uH, 4 output caps 35.1 uF.
VIN, VOUT, FSW, L, COUT = 4.03, 3.32, 1.185e6, 2.2e-6, 35.1e-6
DS = "LTC3633A/LTC3633A-1 data sheet Rev B (3633a1fb)"

# Example circuits read off the LTC3633A Rev B schematics. fsw from RT: f = 3.2e11/RT (p. 12); RT tied to INTVCC is 2 MHz.
LTC3633A_EXAMPLES = [
    BuckPoint("p1 ch1", 6, 20, 3.3, 2.0e6, 1.0e-6, 22e-6, "internal", f"{DS} p. 1"),
    BuckPoint("p1 ch2", 6, 20, 5.0, 2.0e6, 1.5e-6, 22e-6, "internal", f"{DS} p. 1"),
    BuckPoint("fig8 ch1", 12, 13.2, 1.8, 3.2e11 / 162e3, 0.68e-6, 47e-6, "internal", f"{DS} p. 22"),
    BuckPoint("fig8 ch2", 12, 13.2, 3.3, 3.2e11 / 162e3, 1.0e-6, 22e-6, "internal", f"{DS} p. 22"),
    BuckPoint("4MHz ch1", 12, 12, 1.8, 3.2e11 / 80.6e3, 0.68e-6, 47e-6, "external", f"{DS} p. 24"),
    BuckPoint("4MHz ch2", 12, 12, 2.5, 3.2e11 / 80.6e3, 0.82e-6, 22e-6, "external", f"{DS} p. 24"),
    BuckPoint("seq ch1", 6, 20, 1.8, 3.2e11 / 162e3, 0.68e-6, 47e-6, "internal", f"{DS} p. 24"),
    BuckPoint("seq ch2", 6, 20, 3.3, 3.2e11 / 162e3, 1.0e-6, 22e-6, "internal", f"{DS} p. 24"),
    BuckPoint("track ch1", 6, 20, 1.8, 3.2e11 / 196e3, 0.68e-6, 47e-6, "internal", f"{DS} p. 25"),
    BuckPoint("track ch2", 6, 20, 1.2, 3.2e11 / 196e3, 0.47e-6, 68e-6, "internal", f"{DS} p. 25"),
    BuckPoint("dual phase", 3.6, 20, 1.5, 3.2e11 / 324e3, 1.0e-6, 94e-6, "external", f"{DS} p. 26"),
    BuckPoint("ldo ch1", 12, 12, 3.3, 3.2e11 / 162e3, 1.0e-6, 22e-6, "internal", f"{DS} p. 30"),
    BuckPoint("ldo ch2", 12, 12, 1.8, 3.2e11 / 162e3, 0.68e-6, 47e-6, "internal", f"{DS} p. 30"),
]


def test_duty_ideal_and_with_conduction_drops():
    assert duty_cycle(VIN, VOUT).outputs["d"].value == pytest.approx(3.32 / 4.03, rel=1e-12)
    # 1 A with RDS(on) 130/65 mohm (p. 3) and an assumed 50 mohm DCR.
    r = duty_cycle(VIN, VOUT, iout_a=1.0, r_top_ohm=0.130, r_bot_ohm=0.065, r_l_ohm=0.050)
    assert r.outputs["d"].value == pytest.approx(3.435 / 3.965, rel=1e-9)


def test_dmax_and_vin_min_ltc3633a_typical_and_measured():
    r = dropout(VIN, VOUT, FSW, 45e-9, 10e-9, dmax_measured=0.89)
    assert r.outputs["dmax_typ"].value == pytest.approx(0.922975, abs=1e-6)
    assert r.outputs["vin_min_typ"].value == pytest.approx(3.32 / 0.922975, rel=1e-9)
    assert r.outputs["vin_min_typ"].value == pytest.approx(3.597, abs=1e-3)
    assert r.outputs["vin_min"].value == pytest.approx(3.730, abs=1e-3)
    assert r.verdict is Verdict.PASS


def test_dropout_fails_when_conduction_drops_push_duty_past_measured_dmax():
    r = dropout(VIN, VOUT, FSW, 45e-9, 10e-9, dmax_measured=0.89, iout_a=2.0,
                r_top_ohm=0.130, r_bot_ohm=0.065, r_l_ohm=0.050)
    assert r.outputs["d_required"].value == pytest.approx(3.55 / 3.90, rel=1e-9)
    assert r.verdict is Verdict.FAIL


def test_slew_headroom_sauron_ch1():
    typ = current_slew(VIN, VOUT, L, 0.923)
    meas = current_slew(VIN, VOUT, L, 0.89)
    assert typ.outputs["s_up"].value / 1e6 == pytest.approx(0.1817, abs=5e-4)
    assert meas.outputs["s_up"].value / 1e6 == pytest.approx(0.1212, abs=5e-4)
    assert meas.outputs["s_down"].value / 1e6 == pytest.approx(1.509, abs=1e-3)
    assert meas.verdict is Verdict.MARGINAL


def test_slew_headroom_flags_fast_load_step():
    r = current_slew(VIN, VOUT, L, 0.89, load_slew_a_per_s=1e6, asymmetry_limit=100)
    assert r.verdict is Verdict.MARGINAL
    assert "faster than S_up" in r.reason


def test_slew_clamp_vpp_worked():
    r = slew_clamp_vpp(0.121227e6, 125e3, COUT, limit_v=0.010)
    assert r.outputs["vpp"].value == pytest.approx(2 * 0.121227e6 / ((2 * 3.141592653589793 * 125e3) ** 2 * COUT), rel=1e-12)
    assert r.outputs["vpp"].value == pytest.approx(11.20e-3, abs=0.02e-3)
    assert r.verdict is Verdict.FAIL


def test_ripple_and_valley_limit_ltc3633a():
    r = inductor_ripple(VIN, VOUT, FSW, L, iout_a=1.0, i_valley_limit_a=2.6, i_neg_limit_a=1.2, iout_max_a=3.0)
    assert r.outputs["di"].value == pytest.approx(0.22436, abs=1e-5)
    assert r.outputs["iout_limit"].value == pytest.approx(2.6 + 0.22436 / 2, abs=1e-5)
    assert r.verdict is Verdict.PASS


def test_soft_start_inrush_internal_ramp():
    # LTC3633A minimum internal soft-start is 400 us (p. 17).
    r = soft_start_inrush(COUT, VOUT, 400e-6, i_load_a=0.0, i_limit_a=2.6)
    assert r.outputs["i_cap"].value == pytest.approx(0.29133, abs=1e-5)
    assert r.verdict is Verdict.PASS


def test_envelope_flags_4v_input_outside_every_internal_comp_example():
    ours = BuckPoint("Sauron ch1", VIN, VIN, VOUT, FSW, L, COUT, "internal")
    r = example_envelope(ours, LTC3633A_EXAMPLES)
    assert r.verdict is Verdict.MARGINAL
    assert r.outputs["covering"].value == 0
    assert r.outputs["vin_lo_same_comp"].value == 6
    assert r.outputs["vin_hi_same_comp"].value == 20
    for ex in LTC3633A_EXAMPLES:
        if ex.comp == "internal":
            assert "VIN" in r.outputs[f"miss[{ex.name}]"].note
    assert any("p. 30" in ref for ref in r.refs) and any("p. 1" in ref for ref in r.refs)


def test_envelope_passes_a_copy_of_the_p30_circuit():
    ours = BuckPoint("copy", 11.5, 12.5, 3.3, 2.0e6, 1.0e-6, 22e-6, "internal")
    r = example_envelope(ours, LTC3633A_EXAMPLES)
    assert r.verdict is Verdict.PASS
    assert "ldo ch1" in r.reason


def test_envelope_with_our_values_missing_is_unknown():
    ours = BuckPoint("vin and vout only", 11.5, 12.5, 3.3)
    r = example_envelope(ours, LTC3633A_EXAMPLES)
    assert r.verdict is Verdict.UNKNOWN
    assert all(k in r.reason for k in ("fsw", "l", "cout", "comp"))


def test_envelope_with_unknown_compensation_is_unknown():
    ours = BuckPoint("comp unknown", 11.5, 12.5, 3.3, 2.0e6, 1.0e-6, 22e-6)
    r = example_envelope(ours, LTC3633A_EXAMPLES)
    assert r.verdict is Verdict.UNKNOWN
    assert "comp" in r.reason


def test_envelope_with_example_values_missing_is_unknown():
    ours = BuckPoint("ours", 11.5, 12.5, 3.3, 2.0e6, 1.0e-6, 22e-6, "internal")
    ex = BuckPoint("p1 values only", 6, 20, 3.3, source=f"{DS} p. 1")
    r = example_envelope(ours, [ex])
    assert r.verdict is Verdict.UNKNOWN
    assert "p1 values only" in r.reason and "fsw" in r.reason


def test_envelope_tolerances_are_screening_heuristics():
    ours = BuckPoint("copy", 11.5, 12.5, 3.3, 2.0e6, 1.0e-6, 22e-6, "internal")
    r = example_envelope(ours, LTC3633A_EXAMPLES)
    assert any("screening" in a for a in r.assumptions)


def test_envelope_without_examples_is_unknown():
    ours = BuckPoint("x", 5, 5, 1.8)
    assert example_envelope(ours, []).verdict is Verdict.UNKNOWN
