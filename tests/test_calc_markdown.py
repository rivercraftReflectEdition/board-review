import pytest

from boardreview.calc import buck, crystal, divider, i2c, lc_tank, loop, mlcc_bias, protection, thermal, timing
from boardreview.calc.base import Result

CASES = [
    lambda: buck.duty_cycle(4.03, 3.32),
    lambda: buck.dropout(4.03, 3.32, 1.185e6, 45e-9, 10e-9),
    lambda: buck.inductor_ripple(4.03, 3.32, 1.185e6, 2.2e-6, 1.0),
    lambda: buck.current_slew(4.03, 3.32, 2.2e-6, 0.89),
    lambda: buck.slew_clamp_vpp(1.2e5, 125e3, 35.1e-6),
    lambda: buck.soft_start_inrush(35.1e-6, 3.32, 400e-6),
    lambda: buck.example_envelope(buck.BuckPoint("a", 4, 4, 3.3), [buck.BuckPoint("b", 6, 20, 3.3, source="x p. 1")]),
    lambda: loop.margins([loop.Integrator(1e4), loop.Pole(1e5), loop.Delay(1e-6)]),
    lambda: loop.cff_lead(54.9e3, 12.1e3, 22e-12, 100e3),
    lambda: lc_tank.lc_filter(lc_tank.bead_from_spec(120, 100e6, 0.045), lc_tank.Cap(100e-9), [1.19e6]),
    lambda: mlcc_bias.mlcc_effective(1e-6, "X7R", 0.1),
    lambda: divider.divider_output(3.3, 10e3, 10e3),
    lambda: divider.regulator_output(0.958, 0.97, 0.982, 12.7e3, 3.24e3),
    lambda: divider.enable_thresholds(1.18, 1.22, 1.26, 0.98, 1.01, 1.04, 57.6e3, 27.4e3),
    lambda: protection.tvs_standoff(4.909, 5.0),
    lambda: protection.tvs_clamp(4.0, 1.0, [(1.0, 5.5)]),
    lambda: timing.timestamp_error(1.0, 3.0),
    lambda: timing.imx900_exposure(2785, 2507, 2666),
    lambda: timing.smear_px(1.0, 0.05, 29.006),
    lambda: timing.budget({"initial": 10.0, "temperature": 20.0}, 50.0, "ppm"),
    lambda: timing.rc_edge(10e3, 100e-12),
    lambda: i2c.i2c_rise_time(2.2e3, 100e-12),
    lambda: i2c.i2c_pullup_range(3.3, 100e-12),
    lambda: crystal.load_capacitance(12e-12, 12e-12, 3e-12),
    lambda: crystal.oscillation_margin(50, 24e6, 3e-12, 9e-12, gm_crit_max_a_per_v=1.95e-3),
    lambda: crystal.drive_level(50, 100e-6, i_rms_a=1e-3),
    lambda: thermal.junction_temp(0.5, 43, 25, 125),
    lambda: thermal.buck_ic_dissipation(12, 1.8, 2, 0.145, 0.07, 2e6, 2.3e-9, 0.65e-3),
]


@pytest.mark.parametrize("make", CASES)
def test_every_result_shows_formula_inputs_outputs_and_a_reference(make):
    r = make()
    assert isinstance(r, Result)
    md = r.to_markdown()
    assert r.formula in md
    assert r.outputs and r.inputs
    assert r.refs
    assert "—" not in md and "–" not in md
