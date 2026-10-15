"""Timing budgets: a sum of terms against a limit, RC edges, timestamp error from slew, sensor line and exposure time, smear."""

from __future__ import annotations

import math

from boardreview.calc.base import Quantity, Result, Verdict

SENSOR_REF = (
    "sensor data sheet: line-length register, the clock it counts and the integration formula; "
    "pass part, revision and page in refs"
)


def _budget(value: float, limit: float | None, what: str, unit_scale: float, unit: str) -> tuple[Verdict, str]:
    if limit is None:
        return Verdict.INFO, ""
    if value > limit:
        return Verdict.FAIL, f"{what} {value * unit_scale:.4g} {unit} exceeds {limit * unit_scale:.4g} {unit}"
    return Verdict.PASS, f"{what} {value * unit_scale:.4g} {unit} within {limit * unit_scale:.4g} {unit}"


def budget(terms: dict[str, float], limit: float, unit: str = "s", margin_frac: float = 0.2,
           name: str = "budget", refs: tuple[str, ...] = ()) -> Result:
    """Sum of worst-case terms that must fit inside a limit, with a required spare fraction."""
    total = sum(terms.values())
    spare = limit - total
    if total > limit:
        verdict, reason = Verdict.FAIL, f"total {total:.4g} {unit} exceeds the limit {limit:.4g} {unit}"
    elif spare < margin_frac * limit:
        verdict, reason = Verdict.MARGINAL, f"{spare:.4g} {unit} spare, under {margin_frac:.0%} of the limit"
    else:
        verdict, reason = Verdict.PASS, f"{spare:.4g} {unit} spare, {spare / limit:.0%} of the limit"
    inputs = {k: Quantity(v, unit) for k, v in terms.items()}
    inputs.update(limit=Quantity(limit, unit), margin=Quantity(margin_frac, "", "required spare / limit"))
    return Result(
        name=name,
        formula="total = sum(terms); spare = limit - total; pass when spare >= margin * limit",
        inputs=inputs,
        outputs={"total": Quantity(total, unit), "spare": Quantity(spare, unit)},
        verdict=verdict,
        reason=reason,
        refs=("worst-case stack: terms add linearly",) + tuple(refs),
        assumptions=("each term is its worst-case value, not a typical one",),
    )


def rc_edge(r_ohm: float, c_f: float, v_from_frac: float = 0.1, v_to_frac: float = 0.9,
            limit_s: float | None = None) -> Result:
    """Time a first-order RC step takes between two fractions of its final value."""
    t = r_ohm * c_f * math.log((1.0 - v_from_frac) / (1.0 - v_to_frac))
    verdict, reason = _budget(t, limit_s, "edge", 1e6, "us")
    inputs = {"r": Quantity(r_ohm, "ohm"), "c": Quantity(c_f, "F"), "from": Quantity(v_from_frac, "", "of final"),
              "to": Quantity(v_to_frac, "", "of final")}
    if limit_s is not None:
        inputs["limit"] = Quantity(limit_s, "s")
    return Result(
        name="RC edge time",
        formula="t = R*C*ln((1 - from)/(1 - to)); 10 to 90 % is 2.197 RC",
        inputs=inputs,
        outputs={"t": Quantity(t, "s")},
        verdict=verdict,
        reason=reason,
        refs=("first-order step response v(t) = V*(1 - exp(-t/(R*C)))",),
        assumptions=("one resistor charging one capacitor from a step; driver and input thresholds ideal",),
    )


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


def line_time(clocks_per_line: float, clock_hz: float, refs: tuple[str, ...] = ()) -> Result:
    """Image sensor line period (1H) from its line-length register and the clock that register counts."""
    t_h = clocks_per_line / clock_hz
    return Result(
        name="sensor line time",
        formula="1H = clocks per line / line clock",
        inputs={"clocks_per_line": Quantity(clocks_per_line, "clk"), "clock": Quantity(clock_hz, "Hz")},
        outputs={"t_h": Quantity(t_h, "s", f"{t_h * 1e6:.6g} us")},
        verdict=Verdict.INFO,
        refs=(SENSOR_REF,) + tuple(refs),
        assumptions=(
            "line-length register value from the readout mode in use",
            "clock is the one the line counter runs on, which can differ from the input clock",
        ),
    )


def exposure_time(
    integration_lines: float,
    t_line_s: float,
    offset_s: float = 0.0,
    t_target_s: float | None = None,
    tol_s: float = 0.0,
    refs: tuple[str, ...] = (),
) -> Result:
    """Integration time from the integration line count, the line period and the sensor's fixed offset."""
    t_int = integration_lines * t_line_s + offset_s
    if integration_lines <= 0:
        verdict, reason = Verdict.FAIL, "no integration lines: the shutter line is at or past the frame length"
    elif t_target_s is None:
        verdict, reason = Verdict.INFO, ""
    elif abs(t_int - t_target_s) > tol_s:
        verdict, reason = Verdict.FAIL, f"integration {t_int * 1e3:.6g} ms differs from target {t_target_s * 1e3:.6g} ms"
    else:
        verdict, reason = Verdict.PASS, f"integration {t_int * 1e3:.6g} ms matches target"
    inputs = {
        "integration_lines": Quantity(integration_lines, "lines", "for example frame lines minus shutter start line"),
        "t_line": Quantity(t_line_s, "s"),
        "offset": Quantity(offset_s, "s"),
    }
    if t_target_s is not None:
        inputs["t_target"] = Quantity(t_target_s, "s")
        inputs["tol"] = Quantity(tol_s, "s")
    return Result(
        name="sensor integration time",
        formula="t_int = integration lines * 1H + offset",
        inputs=inputs,
        outputs={"t_int": Quantity(t_int, "s", f"{t_int * 1e3:.6g} ms")},
        verdict=verdict,
        reason=reason,
        refs=(SENSOR_REF,) + tuple(refs),
        assumptions=("integration line count and offset from the sensor's shutter mode in use",),
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
