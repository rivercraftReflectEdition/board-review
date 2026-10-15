"""Timing budgets: a sum of terms against a limit, RC edges, slew timestamp error, sensor line and exposure time, smear."""

from __future__ import annotations

import math

from boardreview.calc.base import Key, Quantity, Result, Verdict, fmt

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
    inputs = {k: Quantity(v, unit, label=_label(k)) for k, v in terms.items()}
    inputs.update(limit=Quantity(limit, unit, label="Limit"),
                  margin=Quantity(margin_frac, "", "required spare / limit", "Spare wanted, fraction of the limit"))
    text = [f"The {len(terms)} terms add up to {fmt(total, unit)} against a limit of {fmt(limit, unit)}."]
    if verdict is Verdict.FAIL:
        text.append("The budget does not close: the worst case runs over the limit.")
        key = (Key("total", f"{fmt(limit, unit)} or less"), Key("limit"))
    elif verdict is Verdict.MARGINAL:
        text.append(f"Only {fmt(spare, unit)} is left, under the {margin_frac:.0%} spare we want.")
        key = (Key("total", f"{fmt(limit, unit)} or less"), Key("spare", f"{fmt(margin_frac * limit, unit)} or more"))
    else:
        text.append(f"That leaves {fmt(spare, unit)} spare, {spare / limit:.0%} of the limit.")
        key = (Key("total", f"{fmt(limit, unit)} or less"), Key("spare", f"{fmt(margin_frac * limit, unit)} or more"))
    return Result(
        name=name,
        formula="total = sum(terms); spare = limit - total; pass when spare >= margin * limit",
        inputs=inputs,
        outputs={"total": Quantity(total, unit, label="Total"), "spare": Quantity(spare, unit, label="Spare")},
        verdict=verdict,
        reason=reason,
        refs=("worst-case stack: terms add linearly",) + tuple(refs),
        assumptions=("each term is its worst-case value, not a typical one",),
        summary=" ".join(text),
        key=key,
    )


def _label(name: str) -> str:
    text = name.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def rc_edge(r_ohm: float, c_f: float, v_from_frac: float = 0.1, v_to_frac: float = 0.9,
            limit_s: float | None = None) -> Result:
    """Time a first-order RC step takes between two fractions of its final value."""
    t = r_ohm * c_f * math.log((1.0 - v_from_frac) / (1.0 - v_to_frac))
    verdict, reason = _budget(t, limit_s, "edge", 1e6, "us")
    inputs = {"r": Quantity(r_ohm, "ohm", label="Resistance"), "c": Quantity(c_f, "F", label="Capacitance"),
              "from": Quantity(v_from_frac, "", "of final", "Start, fraction of the final value"),
              "to": Quantity(v_to_frac, "", "of final", "End, fraction of the final value")}
    if limit_s is not None:
        inputs["limit"] = Quantity(limit_s, "s", label="Limit")
    text = [f"{fmt(r_ohm, 'ohm')} charging {fmt(c_f, 'F')} takes {fmt(t, 's')} to go from {v_from_frac:.0%} to "
            f"{v_to_frac:.0%} of its final value."]
    if verdict is Verdict.FAIL:
        text.append(f"The limit is {fmt(limit_s, 's')}, so the edge is too slow.")
    elif verdict is Verdict.PASS:
        text.append(f"That is inside the {fmt(limit_s, 's')} limit.")
    return Result(
        name="RC edge time",
        formula="t = R*C*ln((1 - from)/(1 - to)); 10 to 90 % is 2.197 RC",
        inputs=inputs,
        outputs={"t": Quantity(t, "s", label="Edge time")},
        verdict=verdict,
        reason=reason,
        refs=("first-order step response v(t) = V*(1 - exp(-t/(R*C)))",),
        assumptions=("one resistor charging one capacitor from a step; driver and input thresholds ideal",),
        summary=" ".join(text),
        key=(Key("t", f"{fmt(limit_s, 's')} or less" if limit_s is not None else ""),),
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
    inputs = {"delta_theta": Quantity(delta_theta_arcsec, "arcsec", label="Attitude error allowed"),
              "omega": Quantity(omega_deg_s, "deg/s", label="Body rate")}
    if budget_s is not None:
        inputs["timing_error"] = Quantity(budget_s, "s", label="Timing error")
    text = [f"At {fmt(omega_deg_s, 'deg/s')} the body turns {fmt(delta_theta_arcsec, 'arcsec')} in {fmt(dt, 's')}, so "
            f"timestamps must be good to {fmt(dt, 's')} to hold that attitude error."]
    if verdict is Verdict.FAIL:
        text.append(f"The timing error is {fmt(budget_s, 's')}, more than that, so the attitude error grows past "
                    f"{fmt(delta_theta_arcsec, 'arcsec')}.")
    elif verdict is Verdict.PASS:
        text.append(f"The timing error is {fmt(budget_s, 's')}, inside that.")
    key = (Key("delta_t"),) + ((Key("timing_error", f"{fmt(dt, 's')} or less"),) if budget_s is not None else ())
    return Result(
        name="timestamp error budget",
        formula="delta_t = delta_theta/omega (delta_theta in deg = arcsec/3600)",
        inputs=inputs,
        outputs={"delta_t": Quantity(dt, "s", f"{dt * 1e6:.4g} us", "Time error allowed")},
        verdict=verdict,
        reason=reason,
        refs=("rigid-body rotation at constant rate: theta = omega*t",),
        assumptions=("constant body rate over the interval",),
        summary=" ".join(text),
        key=key,
    )


def line_time(clocks_per_line: float, clock_hz: float, refs: tuple[str, ...] = ()) -> Result:
    """Image sensor line period (1H) from its line-length register and the clock that register counts."""
    t_h = clocks_per_line / clock_hz
    summary = (f"{clocks_per_line:g} clocks per line at {fmt(clock_hz, 'Hz')} make a line time of {fmt(t_h, 's')}. "
               "Integration and frame times are counted in these lines.")
    return Result(
        name="sensor line time",
        formula="1H = clocks per line / line clock",
        inputs={"clocks_per_line": Quantity(clocks_per_line, "clk", label="Clocks per line"),
                "clock": Quantity(clock_hz, "Hz", label="Line clock")},
        outputs={"t_h": Quantity(t_h, "s", f"{t_h * 1e6:.6g} us", "Line time")},
        verdict=Verdict.INFO,
        refs=(SENSOR_REF,) + tuple(refs),
        assumptions=(
            "line-length register value from the readout mode in use",
            "clock is the one the line counter runs on, which can differ from the input clock",
        ),
        summary=summary,
        key=(Key("t_h"),),
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
        "integration_lines": Quantity(integration_lines, "lines", "for example frame lines minus shutter start line",
                                      "Integration lines"),
        "t_line": Quantity(t_line_s, "s", label="Line time"),
        "offset": Quantity(offset_s, "s", label="Fixed offset"),
    }
    if t_target_s is not None:
        inputs["t_target"] = Quantity(t_target_s, "s", label="Target integration time")
        inputs["tol"] = Quantity(tol_s, "s", label="Tolerance")
    offset = f" plus a {fmt(offset_s, 's')} offset" if offset_s else ""
    text = [f"{integration_lines:g} lines of {fmt(t_line_s, 's')}{offset} give {fmt(t_int, 's')} of integration."]
    if integration_lines <= 0:
        text.append("There are no integration lines: the shutter line is at or past the frame length, so the "
                    "sensor does not integrate.")
    elif verdict is Verdict.FAIL:
        text.append(f"The target is {fmt(t_target_s, 's')}, so the exposure is off by "
                    f"{fmt(abs(t_int - t_target_s), 's')}, more than the {fmt(tol_s, 's')} allowed.")
    elif verdict is Verdict.PASS:
        text.append(f"That matches the {fmt(t_target_s, 's')} target"
                    + (f" within {fmt(tol_s, 's')}." if tol_s else "."))
    key = [Key("t_int", f"{fmt(t_target_s, 's')}" + (f" within {fmt(tol_s, 's')}" if tol_s else "")
               if t_target_s is not None and integration_lines > 0 else "")]
    if t_target_s is not None and integration_lines > 0:
        key.append(Key("t_target"))
    return Result(
        name="sensor integration time",
        formula="t_int = integration lines * 1H + offset",
        inputs=inputs,
        outputs={"t_int": Quantity(t_int, "s", f"{t_int * 1e3:.6g} ms", "Integration time")},
        verdict=verdict,
        reason=reason,
        refs=(SENSOR_REF,) + tuple(refs),
        assumptions=("integration line count and offset from the sensor's shutter mode in use",),
        summary=" ".join(text),
        key=tuple(key),
    )


def smear_px(
    omega_deg_s: float, t_exp_s: float, plate_scale_arcsec_px: float, limit_px: float | None = None
) -> Result:
    """Star streak length on the detector during one exposure."""
    length = 3600.0 * omega_deg_s * t_exp_s / plate_scale_arcsec_px
    verdict, reason = _budget(length, limit_px, "smear", 1.0, "px")
    inputs = {
        "omega": Quantity(omega_deg_s, "deg/s", label="Body rate"),
        "t_exp": Quantity(t_exp_s, "s", label="Exposure time"),
        "plate_scale": Quantity(plate_scale_arcsec_px, "arcsec/px", label="Plate scale"),
    }
    if limit_px is not None:
        inputs["limit"] = Quantity(limit_px, "px", label="Limit")
    text = [f"At {fmt(omega_deg_s, 'deg/s')} for {fmt(t_exp_s, 's')} a star moves {fmt(length, 'px')} across the "
            f"detector at {fmt(plate_scale_arcsec_px, 'arcsec/px')}."]
    if verdict is Verdict.FAIL:
        text.append(f"The limit is {fmt(limit_px, 'px')}, so stars smear too much to centroid as planned.")
    elif verdict is Verdict.PASS:
        text.append(f"That is inside the {fmt(limit_px, 'px')} limit.")
    return Result(
        name="exposure smear",
        formula="L_px = 3600 * omega * t / plate_scale",
        inputs=inputs,
        outputs={"length": Quantity(length, "px", label="Streak length")},
        verdict=verdict,
        reason=reason,
        refs=("angle swept = omega*t, converted to arcsec and divided by the plate scale",),
        assumptions=("rotation about an axis perpendicular to the boresight; roll about boresight smears less",),
        summary=" ".join(text),
        key=(Key("length", f"{fmt(limit_px, 'px')} or less" if limit_px is not None else ""),),
    )
