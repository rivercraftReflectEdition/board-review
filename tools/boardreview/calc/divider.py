"""Resistor dividers with resistor tolerance, reference tolerance and pin leakage, nominal and worst case."""

from __future__ import annotations

import numpy as np

from boardreview.calc.base import Key, Marker, Plot, Quantity, Result, Verdict, fmt, plot_from_arrays


def _input_referred(v_pin_v: float, r_top_ohm: float, r_bot_ohm: float, i_in_a: float) -> float:
    return v_pin_v * (1.0 + r_top_ohm / r_bot_ohm) + i_in_a * r_top_ohm


def _corners(v_lo_v, v_hi_v, r_top_ohm, r_bot_ohm, r_tol, i_leak_a):
    lo = _input_referred(v_lo_v, r_top_ohm * (1 - r_tol), r_bot_ohm * (1 + r_tol), -abs(i_leak_a))
    hi = _input_referred(v_hi_v, r_top_ohm * (1 + r_tol), r_bot_ohm * (1 - r_tol), abs(i_leak_a))
    return lo, hi


def divider_output(
    vin_v: float,
    r_top_ohm: float,
    r_bot_ohm: float,
    r_tol: float = 0.01,
    vin_tol: float = 0.0,
    i_leak_a: float = 0.0,
) -> Result:
    """Tap voltage of an unloaded divider; leakage is current into the tap node's pin, either sign."""
    rt, rb = r_top_ohm, r_bot_ohm
    nom = vin_v * rb / (rt + rb)
    lo_rt, lo_rb = rt * (1 + r_tol), rb * (1 - r_tol)
    hi_rt, hi_rb = rt * (1 - r_tol), rb * (1 + r_tol)
    lo = (vin_v * (1 - vin_tol) * lo_rb - abs(i_leak_a) * lo_rt * lo_rb) / (lo_rt + lo_rb)
    hi = (vin_v * (1 + vin_tol) * hi_rb + abs(i_leak_a) * hi_rt * hi_rb) / (hi_rt + hi_rb)
    summary = (f"A {fmt(rt, 'ohm')} top and {fmt(rb, 'ohm')} bottom resistor divide {fmt(vin_v, 'V')} to "
               f"{fmt(nom, 'V')} at the tap. Across tolerance and leakage the tap sits between {fmt(lo, 'V')} and "
               f"{fmt(hi, 'V')}.")
    return Result(
        name="divider output",
        formula="V = (VIN*R2 - I*R1*R2)/(R1 + R2), I = current into the pin; corners at R1, R2, VIN tolerance and I = +-Ileak",
        inputs={
            "vin": Quantity(vin_v, "V", label="Input voltage"),
            "r_top": Quantity(rt, "ohm", label="Top resistor"),
            "r_bot": Quantity(rb, "ohm", label="Bottom resistor"),
            "r_tol": Quantity(r_tol, "", label="Resistor tolerance"),
            "vin_tol": Quantity(vin_tol, "", label="Input tolerance"),
            "i_leak": Quantity(i_leak_a, "A", label="Pin leakage"),
        },
        outputs={"v_nom": Quantity(nom, "V", label="Tap voltage, nominal"),
                 "v_min": Quantity(lo, "V", label="Tap voltage, low corner"),
                 "v_max": Quantity(hi, "V", label="Tap voltage, high corner")},
        verdict=Verdict.INFO,
        refs=("Kirchhoff current law at the tap node",),
        assumptions=("tolerances are worst-case extremes, not statistical",),
        summary=summary,
        key=(Key("v_nom"), Key("v_min"), Key("v_max")),
    )


def regulator_output(
    v_ref_min_v: float,
    v_ref_typ_v: float,
    v_ref_max_v: float,
    r_top_ohm: float,
    r_bot_ohm: float,
    r_tol: float = 0.01,
    i_fb_a: float = 0.0,
    v_out_max_allowed_v: float | None = None,
    v_out_min_allowed_v: float | None = None,
    refs: tuple[str, ...] = (),
) -> Result:
    """Regulated output set by a feedback divider, with reference, resistor and FB-current tolerance."""
    nom = _input_referred(v_ref_typ_v, r_top_ohm, r_bot_ohm, 0.0)
    lo, hi = _corners(v_ref_min_v, v_ref_max_v, r_top_ohm, r_bot_ohm, r_tol, i_fb_a)
    problems = []
    if v_out_max_allowed_v is not None and hi > v_out_max_allowed_v:
        problems.append(f"worst high {hi:.4f} V above {v_out_max_allowed_v:g} V")
    if v_out_min_allowed_v is not None and lo < v_out_min_allowed_v:
        problems.append(f"worst low {lo:.4f} V below {v_out_min_allowed_v:g} V")
    if problems:
        verdict, reason = Verdict.FAIL, "; ".join(problems)
    elif v_out_max_allowed_v is None and v_out_min_allowed_v is None:
        verdict, reason = Verdict.INFO, ""
    else:
        verdict, reason = Verdict.PASS, f"{lo:.4f} to {hi:.4f} V inside the allowed range"
    hi_ok, lo_ok = v_out_max_allowed_v, v_out_min_allowed_v
    text = [f"The feedback divider sets the output to {fmt(nom, 'V')} nominal, and {fmt(lo, 'V')} to {fmt(hi, 'V')} "
            "across reference, resistor and pin current tolerance."]
    if hi_ok is not None and hi > hi_ok:
        text.append(f"The high corner is above the {fmt(hi_ok, 'V')} the load allows.")
    if lo_ok is not None and lo < lo_ok:
        text.append(f"The low corner is below the {fmt(lo_ok, 'V')} the load needs.")
    if verdict is Verdict.PASS:
        if hi_ok is not None and lo_ok is not None:
            text.append(f"That stays inside the {fmt(lo_ok, 'V')} to {fmt(hi_ok, 'V')} the load allows.")
        elif hi_ok is not None:
            text.append(f"That stays at or under the {fmt(hi_ok, 'V')} the load allows.")
        else:
            text.append(f"That stays at or above the {fmt(lo_ok, 'V')} the load needs.")
    key = (Key("vout_nom"),
           Key("vout_min", f"{fmt(lo_ok, 'V')} or more" if lo_ok is not None else ""),
           Key("vout_max", f"{fmt(hi_ok, 'V')} or less" if hi_ok is not None else ""))
    return Result(
        name="regulator output from feedback divider",
        formula="VOUT = VFB*(1 + R1/R2) + IFB*R1; high corner: VFB max, R1 high, R2 low, IFB into pin",
        inputs={
            "v_ref_min": Quantity(v_ref_min_v, "V", label="Reference, minimum"),
            "v_ref_typ": Quantity(v_ref_typ_v, "V", label="Reference, typical"),
            "v_ref_max": Quantity(v_ref_max_v, "V", label="Reference, maximum"),
            "r_top": Quantity(r_top_ohm, "ohm", label="Top resistor"),
            "r_bot": Quantity(r_bot_ohm, "ohm", label="Bottom resistor"),
            "r_tol": Quantity(r_tol, "", label="Resistor tolerance"),
            "i_fb": Quantity(i_fb_a, "A", label="Feedback pin current"),
            **({"v_out_max_allowed": Quantity(v_out_max_allowed_v, "V", label="Highest output allowed")}
               if v_out_max_allowed_v is not None else {}),
            **({"v_out_min_allowed": Quantity(v_out_min_allowed_v, "V", label="Lowest output allowed")}
               if v_out_min_allowed_v is not None else {}),
        },
        outputs={"vout_nom": Quantity(nom, "V", label="Output, nominal"),
                 "vout_min": Quantity(lo, "V", label="Output, low corner"),
                 "vout_max": Quantity(hi, "V", label="Output, high corner")},
        verdict=verdict,
        reason=reason,
        refs=("Kirchhoff current law at the FB node",) + tuple(refs),
        assumptions=("ripple, load and line regulation not included", "tolerances are worst-case extremes"),
        summary=" ".join(text),
        key=key,
    )


def enable_thresholds(
    v_rise_min_v: float,
    v_rise_typ_v: float,
    v_rise_max_v: float,
    v_fall_min_v: float,
    v_fall_typ_v: float,
    v_fall_max_v: float,
    r_top_ohm: float,
    r_bot_ohm: float,
    r_tol: float = 0.01,
    i_leak_a: float = 0.0,
    vin_min_v: float | None = None,
    margin_frac: float = 0.03,
    refs: tuple[str, ...] = (),
) -> Result:
    """Input voltage at which a divider-driven RUN/EN pin turns a part on and off."""
    on_nom = _input_referred(v_rise_typ_v, r_top_ohm, r_bot_ohm, 0.0)
    off_nom = _input_referred(v_fall_typ_v, r_top_ohm, r_bot_ohm, 0.0)
    on_lo, on_hi = _corners(v_rise_min_v, v_rise_max_v, r_top_ohm, r_bot_ohm, r_tol, i_leak_a)
    off_lo, off_hi = _corners(v_fall_min_v, v_fall_max_v, r_top_ohm, r_bot_ohm, r_tol, i_leak_a)
    if vin_min_v is None:
        verdict, reason = Verdict.INFO, ""
    elif on_hi > vin_min_v:
        verdict = Verdict.FAIL
        reason = f"worst-case enable {on_hi:.3f} V is above the minimum supply {vin_min_v:g} V; the part may never turn on"
    elif on_hi > vin_min_v * (1 - margin_frac):
        verdict = Verdict.MARGINAL
        reason = f"worst-case enable {on_hi:.3f} V is within {margin_frac:.0%} of the minimum supply {vin_min_v:g} V"
    else:
        verdict, reason = Verdict.PASS, f"worst-case enable {on_hi:.3f} V below {vin_min_v:g} V"
    inputs = {
        "v_rise": Quantity(v_rise_typ_v, "V", f"{v_rise_min_v:g} to {v_rise_max_v:g}", "Rising threshold, typical"),
        "v_fall": Quantity(v_fall_typ_v, "V", f"{v_fall_min_v:g} to {v_fall_max_v:g}", "Falling threshold, typical"),
        "r_top": Quantity(r_top_ohm, "ohm", label="Top resistor"),
        "r_bot": Quantity(r_bot_ohm, "ohm", label="Bottom resistor"),
        "r_tol": Quantity(r_tol, "", label="Resistor tolerance"),
        "i_leak": Quantity(i_leak_a, "A", "either sign", "Pin leakage"),
    }
    if vin_min_v is not None:
        inputs["vin_min"] = Quantity(vin_min_v, "V", label="Lowest supply")
        inputs["margin_min"] = Quantity(margin_frac, "", "fraction of VIN min", "Margin wanted below the lowest supply")
    text = [f"The enable pin turns the part on between {fmt(v_rise_min_v, 'V')} and {fmt(v_rise_max_v, 'V')}.",
            f"With a {fmt(r_top_ohm, 'ohm')} top and {fmt(r_bot_ohm, 'ohm')} bottom resistor the input turns it on at "
            f"{fmt(on_nom, 'V')} nominal and {fmt(on_hi, 'V')} in the worst case."]
    if vin_min_v is None:
        text.append("No supply range was given to compare against.")
    elif verdict is Verdict.FAIL and on_nom > vin_min_v:
        pin = vin_min_v * r_bot_ohm / (r_top_ohm + r_bot_ohm)
        text.append(f"At the lowest supply of {fmt(vin_min_v, 'V')} the pin sees only {fmt(pin, 'V')}, so the part "
                    "may never turn on.")
    elif verdict is Verdict.FAIL:
        text.append(f"The lowest supply is {fmt(vin_min_v, 'V')}, below the worst case, so with tolerance and pin "
                    "leakage some boards will not turn on at low input.")
    elif verdict is Verdict.MARGINAL:
        text.append(f"That is within {margin_frac:.0%} of the lowest supply of {fmt(vin_min_v, 'V')}, so a low supply "
                    "or a hot board may keep it off.")
    else:
        text.append(f"The lowest supply is {fmt(vin_min_v, 'V')}, so it turns on with {fmt(vin_min_v - on_hi, 'V')} "
                    "to spare.")
    key = (Key("enable_max", f"under {fmt(vin_min_v, 'V')}" if vin_min_v is not None else ""),
           Key("vin_min") if vin_min_v is not None else Key("enable_nom"))
    plot = enable_plot(v_rise_min_v, v_rise_max_v, r_top_ohm, r_bot_ohm, r_tol, i_leak_a, on_hi, vin_min_v)
    return Result(
        name="enable threshold from divider",
        formula="VIN_th = Vth*(1 + R1/R2) + I*R1; high corner: Vth max, R1 high, R2 low, I into pin",
        inputs=inputs,
        outputs={
            "enable_nom": Quantity(on_nom, "V", label="Turn-on, nominal"),
            "enable_min": Quantity(on_lo, "V", label="Turn-on, lowest"),
            "enable_max": Quantity(on_hi, "V", label="Turn-on, worst case"),
            "disable_nom": Quantity(off_nom, "V", label="Turn-off, nominal"),
            "disable_min": Quantity(off_lo, "V", label="Turn-off, lowest"),
            "disable_max": Quantity(off_hi, "V", label="Turn-off, highest"),
            "hysteresis_nom": Quantity(on_nom - off_nom, "V", label="Hysteresis, nominal"),
        },
        verdict=verdict,
        reason=reason,
        refs=("Kirchhoff current law at the RUN/EN node",) + tuple(refs),
        assumptions=("nominal values use zero leakage", "tolerances are worst-case extremes"),
        plots=(plot,),
        summary=" ".join(text),
        key=key,
    )


def _pin_v(vin: np.ndarray, r_top_ohm: float, r_bot_ohm: float, i_in_a: float) -> np.ndarray:
    return np.maximum((vin - i_in_a * r_top_ohm) * r_bot_ohm / (r_top_ohm + r_bot_ohm), 0.0)


def enable_plot(v_rise_min_v: float, v_rise_max_v: float, r_top_ohm: float, r_bot_ohm: float, r_tol: float,
                i_leak_a: float, enable_max_v: float, vin_min_v: float | None = None) -> Plot:
    """Pin voltage against input voltage at nominal and both corners, with the rising threshold band marked."""
    span = max(enable_max_v, vin_min_v or 0.0) * 1.25 or 1.0
    vin = np.linspace(0.0, span, 241)
    i = abs(i_leak_a)
    series = [
        ("pin, nominal", "V", _pin_v(vin, r_top_ohm, r_bot_ohm, 0.0)),
        ("pin, low corner", "V", _pin_v(vin, r_top_ohm * (1 + r_tol), r_bot_ohm * (1 - r_tol), i)),
        ("pin, high corner", "V", _pin_v(vin, r_top_ohm * (1 - r_tol), r_bot_ohm * (1 + r_tol), -i)),
    ]
    marks = [Marker(f"rising max {v_rise_max_v:g} V", y=v_rise_max_v, unit="V"),
             Marker(f"rising min {v_rise_min_v:g} V", y=v_rise_min_v, unit="V"),
             Marker(f"enable worst {enable_max_v:.3f} V", x=enable_max_v, y=v_rise_max_v, unit="V")]
    if vin_min_v is not None:
        marks.append(Marker(f"VIN min {vin_min_v:g} V", x=vin_min_v))
    caption = (f"The part turns on where a pin line crosses the dashed threshold at {fmt(v_rise_max_v, 'V')}; the worst "
               f"case crosses at {fmt(enable_max_v, 'V')}"
               + (f", against a lowest supply of {fmt(vin_min_v, 'V')}." if vin_min_v is not None else "."))
    return plot_from_arrays("Enable pin against input voltage", "Input voltage", "V", vin, series, markers=marks,
                            caption=caption)
