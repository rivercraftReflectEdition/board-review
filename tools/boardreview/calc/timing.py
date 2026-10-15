"""Timing budgets for a star tracker: timestamp error from slew, IMX900 line and exposure time, smear."""

from __future__ import annotations

from boardreview.calc.base import Quantity, Result, Verdict

IMX900 = "Sony IMX900-AQR-C/AMR-C data sheet E24604D5Z"
HMAX_CLOCK_HZ = 74.25e6
INTEGRATION_OFFSET_S = 1.55e-6


def _budget(value: float, limit: float | None, what: str, unit_scale: float, unit: str) -> tuple[Verdict, str]:
    if limit is None:
        return Verdict.INFO, ""
    if value > limit:
        return Verdict.FAIL, f"{what} {value * unit_scale:.4g} {unit} exceeds {limit * unit_scale:.4g} {unit}"
    return Verdict.PASS, f"{what} {value * unit_scale:.4g} {unit} within {limit * unit_scale:.4g} {unit}"


def timestamp_error(
    delta_theta_arcsec: float, omega_deg_s: float, budget_s: float | None = None
) -> Result:
    """Time error that produces a given attitude error at a given body rate."""
    dt = (delta_theta_arcsec / 3600.0) / omega_deg_s
    if budget_s is None:
        verdict, reason = Verdict.INFO, ""
    elif budget_s <= dt:
        verdict = Verdict.PASS
        reason = f"timing error {budget_s * 1e6:.4g} us keeps attitude error within {delta_theta_arcsec:g} arcsec"
    else:
        verdict = Verdict.FAIL
        reason = f"timing error {budget_s * 1e6:.4g} us exceeds the {dt * 1e6:.4g} us that {delta_theta_arcsec:g} arcsec allows"
    inputs = {"delta_theta": Quantity(delta_theta_arcsec, "arcsec"), "omega": Quantity(omega_deg_s, "deg/s")}
    if budget_s is not None:
        inputs["timing_error"] = Quantity(budget_s, "s")
    return Result(
        name="timestamp error budget",
        formula="delta_t = delta_theta/omega (delta_theta in deg = arcsec/3600)",
        inputs=inputs,
        outputs={"delta_t": Quantity(dt, "s", f"{dt * 1e6:.4g} us")},
        verdict=verdict,
        reason=reason,
        refs=("rigid-body rotation at constant rate: theta = omega*t",),
        assumptions=("constant body rate over the interval",),
    )


def imx900_line_time(hmax: int, inck_hz: float = 74.25e6) -> Result:
    """IMX900 1H period from the HMAX register."""
    clock = inck_hz if abs(inck_hz - 24e6) < 1.0 else HMAX_CLOCK_HZ
    t_h = hmax / clock
    return Result(
        name="IMX900 line time",
        formula="1H = HMAX / 74.25 MHz (INCK 37.125, 54 or 74.25 MHz); 1H = HMAX / 24 MHz (INCK 24 MHz)",
        inputs={"hmax": Quantity(hmax, "clk"), "inck": Quantity(inck_hz, "Hz")},
        outputs={"t_h": Quantity(t_h, "s", f"{t_h * 1e6:.6g} us")},
        verdict=Verdict.INFO,
        refs=(f"{IMX900} p. 168, HMAX [15:0] = number of INCK in 1H x 74.25/INCK (24 MHz: number of INCK)",),
        assumptions=("HMAX taken from the register list of the readout mode in use",),
    )


def imx900_exposure(
    vmax: int, shs: int, hmax: int, inck_hz: float = 74.25e6, t_target_s: float | None = None, tol_s: float = 0.0
) -> Result:
    """IMX900 global-shutter integration time in normal mode from VMAX, SHS and HMAX."""
    t_h = imx900_line_time(hmax, inck_hz).outputs["t_h"].value
    t_int = (vmax - shs) * t_h + INTEGRATION_OFFSET_S
    if shs >= vmax:
        verdict, reason = Verdict.FAIL, "SHS must be below the number of lines per frame"
    elif t_target_s is None:
        verdict, reason = Verdict.INFO, ""
    elif abs(t_int - t_target_s) > tol_s:
        verdict, reason = Verdict.FAIL, f"integration {t_int * 1e3:.6g} ms differs from target {t_target_s * 1e3:.6g} ms"
    else:
        verdict, reason = Verdict.PASS, f"integration {t_int * 1e3:.6g} ms matches target"
    return Result(
        name="IMX900 integration time",
        formula="t_int = (VMAX - SHS) * 1H + 1.55 us",
        inputs={
            "vmax": Quantity(vmax, "lines"),
            "shs": Quantity(shs, "lines"),
            "hmax": Quantity(hmax, "clk"),
            "inck": Quantity(inck_hz, "Hz"),
        },
        outputs={"t_h": Quantity(t_h, "s"), "t_int": Quantity(t_int, "s", f"{t_int * 1e3:.6g} ms")},
        verdict=verdict,
        reason=reason,
        refs=(f"{IMX900} p. 173, 20.7.1 Global Shutter (Normal Mode), integration time formula and tOFFSET 1.55 us",),
        assumptions=("master mode, so lines per frame = VMAX",),
    )


def smear_px(
    omega_deg_s: float, t_exp_s: float, plate_scale_arcsec_px: float, limit_px: float | None = None
) -> Result:
    """Star streak length on the detector during one exposure."""
    length = 3600.0 * omega_deg_s * t_exp_s / plate_scale_arcsec_px
    verdict, reason = _budget(length, limit_px, "smear", 1.0, "px")
    inputs = {
        "omega": Quantity(omega_deg_s, "deg/s"),
        "t_exp": Quantity(t_exp_s, "s"),
        "plate_scale": Quantity(plate_scale_arcsec_px, "arcsec/px"),
    }
    if limit_px is not None:
        inputs["limit"] = Quantity(limit_px, "px")
    return Result(
        name="exposure smear",
        formula="L_px = 3600 * omega * t / plate_scale",
        inputs=inputs,
        outputs={"length": Quantity(length, "px")},
        verdict=verdict,
        reason=reason,
        refs=("angle swept = omega*t, converted to arcsec and divided by the plate scale",),
        assumptions=("rotation about an axis perpendicular to the boresight; roll about boresight smears less",),
    )
