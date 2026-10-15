"""Resistor dividers with resistor tolerance, reference tolerance and pin leakage, nominal and worst case."""

from __future__ import annotations

import numpy as np

from boardreview.calc.base import Marker, Plot, Quantity, Result, Verdict, plot_from_arrays


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
    return Result(
        name="divider output",
        formula="V = (VIN*R2 - I*R1*R2)/(R1 + R2), I = current into the pin; corners at R1, R2, VIN tolerance and I = +-Ileak",
        inputs={
            "vin": Quantity(vin_v, "V"),
            "r_top": Quantity(rt, "ohm"),
            "r_bot": Quantity(rb, "ohm"),
            "r_tol": Quantity(r_tol, ""),
            "vin_tol": Quantity(vin_tol, ""),
            "i_leak": Quantity(i_leak_a, "A"),
        },
        outputs={"v_nom": Quantity(nom, "V"), "v_min": Quantity(lo, "V"), "v_max": Quantity(hi, "V")},
        verdict=Verdict.INFO,
        refs=("Kirchhoff current law at the tap node",),
        assumptions=("tolerances are worst-case extremes, not statistical",),
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
    return Result(
        name="regulator output from feedback divider",
        formula="VOUT = VFB*(1 + R1/R2) + IFB*R1; high corner: VFB max, R1 high, R2 low, IFB into pin",
        inputs={
            "v_ref_min": Quantity(v_ref_min_v, "V"),
            "v_ref_typ": Quantity(v_ref_typ_v, "V"),
            "v_ref_max": Quantity(v_ref_max_v, "V"),
            "r_top": Quantity(r_top_ohm, "ohm"),
            "r_bot": Quantity(r_bot_ohm, "ohm"),
            "r_tol": Quantity(r_tol, ""),
            "i_fb": Quantity(i_fb_a, "A"),
            **({"v_out_max_allowed": Quantity(v_out_max_allowed_v, "V")} if v_out_max_allowed_v is not None else {}),
            **({"v_out_min_allowed": Quantity(v_out_min_allowed_v, "V")} if v_out_min_allowed_v is not None else {}),
        },
        outputs={"vout_nom": Quantity(nom, "V"), "vout_min": Quantity(lo, "V"), "vout_max": Quantity(hi, "V")},
        verdict=verdict,
        reason=reason,
        refs=("Kirchhoff current law at the FB node",) + tuple(refs),
        assumptions=("ripple, load and line regulation not included", "tolerances are worst-case extremes"),
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
        "v_rise": Quantity(v_rise_typ_v, "V", f"{v_rise_min_v:g} to {v_rise_max_v:g}"),
        "v_fall": Quantity(v_fall_typ_v, "V", f"{v_fall_min_v:g} to {v_fall_max_v:g}"),
        "r_top": Quantity(r_top_ohm, "ohm"),
        "r_bot": Quantity(r_bot_ohm, "ohm"),
        "r_tol": Quantity(r_tol, ""),
        "i_leak": Quantity(i_leak_a, "A", "either sign"),
    }
    if vin_min_v is not None:
        inputs["vin_min"] = Quantity(vin_min_v, "V")
        inputs["margin_min"] = Quantity(margin_frac, "", "fraction of VIN min")
    plot = enable_plot(v_rise_min_v, v_rise_max_v, r_top_ohm, r_bot_ohm, r_tol, i_leak_a, on_hi, vin_min_v)
    return Result(
        name="enable threshold from divider",
        formula="VIN_th = Vth*(1 + R1/R2) + I*R1; high corner: Vth max, R1 high, R2 low, I into pin",
        inputs=inputs,
        outputs={
            "enable_nom": Quantity(on_nom, "V"),
            "enable_min": Quantity(on_lo, "V"),
            "enable_max": Quantity(on_hi, "V"),
            "disable_nom": Quantity(off_nom, "V"),
            "disable_min": Quantity(off_lo, "V"),
            "disable_max": Quantity(off_hi, "V"),
            "hysteresis_nom": Quantity(on_nom - off_nom, "V"),
        },
        verdict=verdict,
        reason=reason,
        refs=("Kirchhoff current law at the RUN/EN node",) + tuple(refs),
        assumptions=("nominal values use zero leakage", "tolerances are worst-case extremes"),
        plots=(plot,),
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
    return plot_from_arrays("Enable pin against input voltage", "Input voltage", "V", vin, series, markers=marks)
