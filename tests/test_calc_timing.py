import inspect

import pytest

from boardreview.calc import timing
from boardreview.calc.base import Verdict
from boardreview.calc.i2c import i2c_rise_time
from boardreview.calc.timing import budget, exposure_time, line_time, rc_edge, smear_px, timestamp_error

# Worked sensor example: Sony IMX900-AQR-C/AMR-C data sheet E24604D5Z.
# p. 168: 1H = HMAX / 74.25 MHz for INCK 37.125, 54 or 74.25 MHz; 1H = HMAX / 24 MHz for INCK 24 MHz.
# p. 173, 20.7.1 Global Shutter (Normal Mode): t_int = (VMAX - SHS) * 1H + 1.55 us.
IMX900 = "Sony IMX900-AQR-C/AMR-C data sheet E24604D5Z"
IMX900_HMAX = f"{IMX900} p. 168, HMAX [15:0] = number of INCK in 1H x 74.25/INCK (24 MHz: number of INCK)"
IMX900_TINT = f"{IMX900} p. 173, 20.7.1 Global Shutter (Normal Mode), integration time formula and tOFFSET 1.55 us"
IMX900_LINE_CLOCK_HZ = 74.25e6
IMX900_OFFSET_S = 1.55e-6


def test_one_arcsec_at_3_deg_per_s():
    r = timestamp_error(1.0, 3.0)
    assert r.outputs["delta_t"].value == pytest.approx(92.59e-6, abs=0.005e-6)


def test_timestamp_budget_verdict():
    assert timestamp_error(1.0, 3.0, budget_s=50e-6).verdict is Verdict.PASS
    assert timestamp_error(1.0, 3.0, budget_s=100e-6).verdict is Verdict.FAIL


def test_line_time_imx900_hmax_2666():
    r = line_time(2666, IMX900_LINE_CLOCK_HZ, refs=(IMX900_HMAX,))
    assert r.outputs["t_h"].value == pytest.approx(35.906e-6, abs=0.0005e-6)
    assert r.inputs["clocks_per_line"].value == 2666 and r.inputs["clock"].value == IMX900_LINE_CLOCK_HZ
    assert IMX900_HMAX in r.refs
    assert line_time(864, 24e6).outputs["t_h"].value == pytest.approx(36e-6)


def test_exposure_imx900_vmax_2785_shs_2507_hmax_2666():
    t_h = line_time(2666, IMX900_LINE_CLOCK_HZ).outputs["t_h"].value
    r = exposure_time(2785 - 2507, t_h, offset_s=IMX900_OFFSET_S, t_target_s=9.98334e-3, tol_s=5e-9, refs=(IMX900_TINT,))
    assert r.outputs["t_int"].value == pytest.approx(9.98334e-3, abs=5e-9)
    assert r.inputs["offset"].value == IMX900_OFFSET_S
    assert r.verdict is Verdict.PASS


def test_exposure_needs_positive_integration_lines():
    # Shutter line at or past the frame length (SHS >= VMAX on the IMX900) leaves no integration.
    assert exposure_time(2785 - 2785, 35.9e-6).verdict is Verdict.FAIL


def test_timing_module_is_vendor_neutral():
    names = [n for n in dir(timing) if not n.startswith("__")]
    assert not [n for n in names if "imx" in n.lower()]
    assert "IMX" not in inspect.getsource(timing)


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
