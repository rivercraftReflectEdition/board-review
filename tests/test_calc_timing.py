import pytest

from boardreview.calc.base import Verdict
from boardreview.calc.i2c import i2c_rise_time
from boardreview.calc.timing import budget, imx900_exposure, imx900_line_time, rc_edge, smear_px, timestamp_error


def test_one_arcsec_at_3_deg_per_s():
    r = timestamp_error(1.0, 3.0)
    assert r.outputs["delta_t"].value == pytest.approx(92.59e-6, abs=0.005e-6)


def test_timestamp_budget_verdict():
    assert timestamp_error(1.0, 3.0, budget_s=50e-6).verdict is Verdict.PASS
    assert timestamp_error(1.0, 3.0, budget_s=100e-6).verdict is Verdict.FAIL


def test_imx900_line_time_hmax_2666():
    r = imx900_line_time(2666)
    assert r.outputs["t_h"].value == pytest.approx(35.906e-6, abs=0.0005e-6)
    assert imx900_line_time(2666, inck_hz=37.125e6).outputs["t_h"].value == r.outputs["t_h"].value
    assert imx900_line_time(864, inck_hz=24e6).outputs["t_h"].value == pytest.approx(36e-6)


def test_imx900_exposure_2785_2507_2666():
    r = imx900_exposure(2785, 2507, 2666, t_target_s=9.98334e-3, tol_s=5e-9)
    assert r.outputs["t_int"].value == pytest.approx(9.98334e-3, abs=5e-9)
    assert r.verdict is Verdict.PASS


def test_imx900_exposure_rejects_shs_past_vmax():
    assert imx900_exposure(2785, 2785, 2666).verdict is Verdict.FAIL


def test_smear_1_deg_per_s_50_ms():
    r = smear_px(1.0, 50e-3, 29.006, limit_px=5.0)
    assert r.outputs["length"].value == pytest.approx(6.21, abs=0.005)
    assert r.verdict is Verdict.FAIL


def test_budget_rmii_reference_clock_ppm():
    # RMII Specification Rev 1.2: REF_CLK 50 MHz +-50 ppm (page UNSURE, not fetched).
    r = budget({"initial": 10.0, "temperature": 20.0, "aging": 5.0}, 50.0, "ppm")
    assert r.outputs["total"].value == pytest.approx(35.0, abs=1e-9)
    assert r.outputs["spare"].value == pytest.approx(15.0, abs=1e-9)
    assert r.verdict is Verdict.PASS
    assert budget({"initial": 10.0, "temperature": 20.0, "aging": 15.0}, 50.0, "ppm").verdict is Verdict.MARGINAL
    assert budget({"initial": 30.0, "temperature": 25.0}, 50.0, "ppm").verdict is Verdict.FAIL


def test_rc_edge_30_to_70_matches_i2c_rise_time():
    # NXP UM10204 Rev 7.0 p. 50: tr = 0.8473 RC from 0.3 VDD to 0.7 VDD.
    r = rc_edge(4.7e3, 100e-12, 0.3, 0.7)
    assert r.outputs["t"].value == pytest.approx(i2c_rise_time(4.7e3, 100e-12).outputs["tr"].value, abs=0.05e-9)


def test_rc_edge_10_to_90_is_2_2_rc():
    r = rc_edge(10e3, 100e-12, limit_s=2e-6)
    assert r.outputs["t"].value == pytest.approx(2.1972e-6, abs=0.0001e-6)
    assert r.verdict is Verdict.FAIL
    assert rc_edge(10e3, 100e-12, limit_s=3e-6).verdict is Verdict.PASS
