"""Buck converter checks: duty, dropout, ripple, current slew, slew-limited swing, inrush, example envelope."""

from __future__ import annotations

import math
from dataclasses import dataclass

from boardreview.calc.base import Quantity, Result, Verdict

LTC3633A = "LTC3633A/LTC3633A-1 data sheet Rev B (3633a1fb)"


def duty_cycle(
    vin_v: float,
    vout_v: float,
    iout_a: float = 0.0,
    r_top_ohm: float = 0.0,
    r_bot_ohm: float = 0.0,
    r_l_ohm: float = 0.0,
) -> Result:
    """Steady-state CCM duty cycle, with optional switch and inductor conduction drops."""
    d_ideal = vout_v / vin_v
    d = (vout_v + iout_a * (r_bot_ohm + r_l_ohm)) / (vin_v - iout_a * (r_top_ohm - r_bot_ohm))
    verdict = Verdict.FAIL if d >= 1.0 else Verdict.INFO
    reason = "required duty reaches 100 %" if d >= 1.0 else ""
    return Result(
        name="buck duty cycle",
        formula="D = (VOUT + I*(Rbot + RL)) / (VIN - I*(Rtop - Rbot)); ideal D = VOUT/VIN",
        inputs={
            "vin": Quantity(vin_v, "V"),
            "vout": Quantity(vout_v, "V"),
            "iout": Quantity(iout_a, "A"),
            "r_top": Quantity(r_top_ohm, "ohm"),
            "r_bot": Quantity(r_bot_ohm, "ohm"),
            "r_l": Quantity(r_l_ohm, "ohm"),
        },
        outputs={"d": Quantity(d, ""), "d_ideal": Quantity(d_ideal, "")},
        verdict=verdict,
        reason=reason,
        refs=("volt-second balance on the switch node (CCM, synchronous rectifier)",),
        assumptions=("continuous conduction", "switching and dead-time losses ignored"),
    )


def dropout(
    vin_v: float,
    vout_v: float,
    f_hz: float,
    t_off_min_s: float,
    t_dead_s: float,
    dmax_measured: float | None = None,
    iout_a: float = 0.0,
    r_top_ohm: float = 0.0,
    r_bot_ohm: float = 0.0,
    r_l_ohm: float = 0.0,
    margin_frac: float = 0.05,
) -> Result:
    """Maximum duty from minimum off-time and dead time, and the minimum VIN that still regulates."""
    dmax_typ = 1.0 - f_hz * (t_off_min_s + 2.0 * t_dead_s)
    dmax = min(dmax_typ, dmax_measured) if dmax_measured is not None else dmax_typ
    num = vout_v + iout_a * (r_bot_ohm + r_l_ohm)
    drop = iout_a * (r_top_ohm - r_bot_ohm)
    d_req = num / (vin_v - drop)
    vin_min_typ = num / dmax_typ + drop
    vin_min = num / dmax + drop
    headroom = vin_v - vin_min
    if d_req > dmax:
        verdict, reason = Verdict.FAIL, f"needs D = {d_req:.3f} above Dmax = {dmax:.3f}; output drops out"
    elif headroom < margin_frac * vin_v:
        verdict, reason = Verdict.MARGINAL, f"VIN is {headroom:.3f} V above dropout, under {margin_frac:.0%} of VIN"
    else:
        verdict, reason = Verdict.PASS, f"VIN is {headroom:.3f} V above dropout"
    outputs = {
        "dmax_typ": Quantity(dmax_typ, ""),
        "dmax_used": Quantity(dmax, "", "lower of typical and measured" if dmax_measured is not None else ""),
        "d_required": Quantity(d_req, ""),
        "vin_min_typ": Quantity(vin_min_typ, "V"),
        "vin_min": Quantity(vin_min, "V"),
        "headroom": Quantity(headroom, "V"),
    }
    inputs = {
        "vin": Quantity(vin_v, "V"),
        "vout": Quantity(vout_v, "V"),
        "f": Quantity(f_hz, "Hz"),
        "t_off_min": Quantity(t_off_min_s, "s"),
        "t_dead": Quantity(t_dead_s, "s"),
        "iout": Quantity(iout_a, "A"),
    }
    if dmax_measured is not None:
        inputs["dmax_measured"] = Quantity(dmax_measured, "")
    return Result(
        name="buck dropout",
        formula="Dmax = 1 - f*(tOFFmin + 2*tdead); VINmin = (VOUT + I*(Rbot + RL))/Dmax + I*(Rtop - Rbot)",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(f"{LTC3633A} p. 15, Minimum Off-Time/On-Time Considerations (DC(MAX), VIN(MIN))",),
        assumptions=("tOFFmin and tdead are typical values unless a measured Dmax is given",),
    )


def inductor_ripple(
    vin_v: float,
    vout_v: float,
    f_hz: float,
    l_h: float,
    iout_a: float,
    i_sat_a: float | None = None,
    i_valley_limit_a: float | None = None,
    i_neg_limit_a: float | None = None,
    iout_max_a: float | None = None,
) -> Result:
    """Inductor ripple, peak and valley current against saturation and current limits."""
    di = vout_v * (1.0 - vout_v / vin_v) / (f_hz * l_h)
    i_pk = iout_a + di / 2.0
    i_val = iout_a - di / 2.0
    problems: list[str] = []
    verdict = Verdict.PASS
    if i_sat_a is not None and i_pk > i_sat_a:
        problems.append(f"peak {i_pk:.3f} A above Isat {i_sat_a:.3f} A")
        verdict = Verdict.FAIL
    if i_valley_limit_a is not None and i_val > i_valley_limit_a:
        problems.append(f"valley {i_val:.3f} A above valley current limit {i_valley_limit_a:.3f} A")
        verdict = Verdict.FAIL
    if i_neg_limit_a is not None and -di / 2.0 < -abs(i_neg_limit_a):
        problems.append(f"no-load valley {-di / 2:.3f} A below negative limit -{abs(i_neg_limit_a):.3f} A")
        verdict = Verdict.FAIL
    outputs = {
        "di": Quantity(di, "A", "peak to peak"),
        "i_peak": Quantity(i_pk, "A"),
        "i_valley": Quantity(i_val, "A"),
    }
    if iout_max_a is not None:
        ratio = di / iout_max_a
        outputs["ripple_ratio"] = Quantity(ratio, "", "of IOUT(MAX)")
        if ratio > 0.6 and verdict is Verdict.PASS:
            problems.append(f"ripple is {ratio:.0%} of IOUT(MAX), above 60 %")
            verdict = Verdict.MARGINAL
    if i_valley_limit_a is not None:
        outputs["iout_limit"] = Quantity(i_valley_limit_a + di / 2.0, "A", "output current at valley limit")
    reason = "; ".join(problems) if problems else "within the given limits"
    if i_sat_a is None and i_valley_limit_a is None and i_neg_limit_a is None and iout_max_a is None:
        verdict, reason = Verdict.INFO, ""
    return Result(
        name="inductor ripple",
        formula="dI = VOUT*(1 - VOUT/VIN)/(f*L); Ipk = IOUT + dI/2; Ivalley = IOUT - dI/2",
        inputs={
            "vin": Quantity(vin_v, "V"),
            "vout": Quantity(vout_v, "V"),
            "f": Quantity(f_hz, "Hz"),
            "l": Quantity(l_h, "H"),
            "iout": Quantity(iout_a, "A"),
        },
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(
            f"{LTC3633A} p. 12, Inductor Selection (ripple equation)",
            f"{LTC3633A} p. 13, ripple above 60 % of IOUT(MAX) not recommended",
        ),
        assumptions=("continuous conduction", "inductance at operating current (derate for saturation)"),
    )


def current_slew(
    vin_v: float,
    vout_v: float,
    l_h: float,
    dmax: float,
    load_slew_a_per_s: float | None = None,
    asymmetry_limit: float = 5.0,
) -> Result:
    """Average inductor-current slew available at Dmax (up) and at zero duty (down)."""
    s_up = (vin_v * dmax - vout_v) / l_h
    s_down = vout_v / l_h
    asym = s_down / s_up if s_up > 0 else math.inf
    if s_up <= 0:
        verdict, reason = Verdict.FAIL, "VIN*Dmax is below VOUT; current cannot rise"
    elif load_slew_a_per_s is not None and load_slew_a_per_s > s_up:
        verdict = Verdict.MARGINAL
        reason = f"load step slews {load_slew_a_per_s / 1e6:.3f} A/us, faster than S_up {s_up / 1e6:.3f} A/us"
    elif asym > asymmetry_limit:
        verdict = Verdict.MARGINAL
        reason = f"up-slew is {asym:.1f}x slower than down-slew; large-signal response is slew limited"
    else:
        verdict, reason = Verdict.PASS, f"up/down slew ratio 1:{asym:.1f}"
    inputs = {
        "vin": Quantity(vin_v, "V"),
        "vout": Quantity(vout_v, "V"),
        "l": Quantity(l_h, "H"),
        "dmax": Quantity(dmax, ""),
    }
    if load_slew_a_per_s is not None:
        inputs["load_slew"] = Quantity(load_slew_a_per_s, "A/s")
    return Result(
        name="inductor current slew headroom",
        formula="S_up = (VIN*Dmax - VOUT)/L; S_down = VOUT/L",
        inputs=inputs,
        outputs={
            "s_up": Quantity(s_up, "A/s", f"{s_up / 1e6:.3f} A/us"),
            "s_down": Quantity(s_down, "A/s", f"{s_down / 1e6:.3f} A/us"),
            "down_over_up": Quantity(asym, ""),
        },
        verdict=verdict,
        reason=reason,
        refs=("inductor law V = L*dI/dt averaged over a switching cycle at the duty limits",),
        assumptions=("down-slew assumes the top switch can stay off for whole cycles",),
    )


def slew_clamp_vpp(slew_a_per_s: float, f_hz: float, c_f: float, limit_v: float | None = None) -> Result:
    """Largest sinusoidal output swing at f that a slew-limited inductor current can sustain on C."""
    w = 2.0 * math.pi * f_hz
    vpp = 2.0 * slew_a_per_s / (w * w * c_f)
    ipk = slew_a_per_s / w
    if limit_v is None:
        verdict, reason = Verdict.INFO, ""
    elif vpp > limit_v:
        verdict, reason = Verdict.FAIL, f"an oscillation at this frequency can reach {vpp * 1e3:.1f} mVpp"
    else:
        verdict, reason = Verdict.PASS, f"clamp {vpp * 1e3:.1f} mVpp is under {limit_v * 1e3:.1f} mVpp"
    inputs = {"slew": Quantity(slew_a_per_s, "A/s"), "f": Quantity(f_hz, "Hz"), "c": Quantity(c_f, "F")}
    if limit_v is not None:
        inputs["limit"] = Quantity(limit_v, "V")
    return Result(
        name="slew-limited oscillation clamp",
        formula="Vpp = 2*S/((2*pi*f)^2*C); Ipk = S/(2*pi*f)",
        inputs=inputs,
        outputs={"vpp": Quantity(vpp, "V"), "i_pk": Quantity(ipk, "A")},
        verdict=verdict,
        reason=reason,
        refs=("sinusoid of amplitude I has peak slope 2*pi*f*I; V on C is I/(2*pi*f*C)",),
        assumptions=("sinusoidal oscillation", "load current constant", "C is the effective output capacitance"),
    )


def soft_start_inrush(
    c_f: float,
    vout_v: float,
    t_ss_s: float,
    i_load_a: float = 0.0,
    i_limit_a: float | None = None,
) -> Result:
    """Capacitor charging current during a linear soft-start ramp, plus load."""
    i_cap = c_f * vout_v / t_ss_s
    i_tot = i_cap + i_load_a
    if i_limit_a is None:
        verdict, reason = Verdict.INFO, ""
    elif i_tot > i_limit_a:
        verdict, reason = Verdict.FAIL, f"inrush {i_tot:.3f} A exceeds limit {i_limit_a:.3f} A"
    elif i_tot > 0.8 * i_limit_a:
        verdict, reason = Verdict.MARGINAL, f"inrush {i_tot:.3f} A is over 80 % of {i_limit_a:.3f} A"
    else:
        verdict, reason = Verdict.PASS, f"inrush {i_tot:.3f} A under {i_limit_a:.3f} A"
    inputs = {
        "c": Quantity(c_f, "F"),
        "vout": Quantity(vout_v, "V"),
        "t_ss": Quantity(t_ss_s, "s"),
        "i_load": Quantity(i_load_a, "A"),
    }
    if i_limit_a is not None:
        inputs["i_limit"] = Quantity(i_limit_a, "A")
    return Result(
        name="soft-start inrush",
        formula="I = C*VOUT/tSS + Iload",
        inputs=inputs,
        outputs={"i_cap": Quantity(i_cap, "A"), "i_total": Quantity(i_tot, "A")},
        verdict=verdict,
        reason=reason,
        refs=("I = C*dV/dt for a linear ramp",),
        assumptions=("linear ramp from 0 to VOUT over tSS",),
    )


@dataclass(frozen=True)
class BuckPoint:
    """One buck operating point: ours, or a datasheet example circuit."""

    name: str
    vin_min_v: float
    vin_max_v: float
    vout_v: float
    fsw_hz: float | None = None
    l_h: float | None = None
    cout_f: float | None = None
    comp: str | None = None
    source: str = ""


DEFAULT_TOL = {"vin": 0.05, "vout": 0.15, "fsw": 0.25, "l": 0.5, "cout": 0.5}


def _mismatches(ours: BuckPoint, ex: BuckPoint, tol: dict[str, float]) -> list[str]:
    out: list[str] = []
    if ours.comp and ex.comp and ours.comp != ex.comp:
        out.append(f"comp {ours.comp} vs {ex.comp}")
    lo, hi = ex.vin_min_v * (1 - tol["vin"]), ex.vin_max_v * (1 + tol["vin"])
    if ours.vin_min_v < lo or ours.vin_max_v > hi:
        out.append(f"VIN {ours.vin_min_v:g}-{ours.vin_max_v:g} V vs {ex.vin_min_v:g}-{ex.vin_max_v:g} V")
    for key, attr, unit in (("vout", "vout_v", "V"), ("fsw", "fsw_hz", "Hz"), ("l", "l_h", "H"), ("cout", "cout_f", "F")):
        a, b = getattr(ours, attr), getattr(ex, attr)
        if a is None or b is None:
            continue
        if max(a / b, b / a) > 1.0 + tol[key]:
            out.append(f"{key} {a:.4g} vs {b:.4g} {unit}")
    return out


def example_envelope(
    ours: BuckPoint,
    examples: list[BuckPoint],
    tol: dict[str, float] | None = None,
) -> Result:
    """Flag a design that sits outside every datasheet example circuit."""
    t = {**DEFAULT_TOL, **(tol or {})}
    if not examples:
        return Result(
            name="operating envelope vs datasheet examples",
            formula="covered if one example matches comp mode and contains VIN, VOUT, fsw, L, COUT within tolerance",
            inputs={},
            outputs={},
            verdict=Verdict.UNKNOWN,
            reason="no examples given",
        )
    checks = [(ex, _mismatches(ours, ex, t)) for ex in examples]
    covered = [ex for ex, m in checks if not m]
    same_comp = [ex for ex in examples if not (ours.comp and ex.comp and ex.comp != ours.comp)]
    outputs: dict[str, Quantity] = {
        "examples": Quantity(len(examples), "count"),
        "covering": Quantity(len(covered), "count"),
    }
    if same_comp:
        outputs["vin_lo_same_comp"] = Quantity(min(e.vin_min_v for e in same_comp), "V", "lowest example VIN")
        outputs["vin_hi_same_comp"] = Quantity(max(e.vin_max_v for e in same_comp), "V", "highest example VIN")
        ls = [e.l_h for e in same_comp if e.l_h is not None]
        if ls:
            outputs["l_hi_same_comp"] = Quantity(max(ls), "H", "largest example L")
    for ex, m in checks:
        outputs[f"miss[{ex.name}]"] = Quantity(len(m), "count", "; ".join(m) if m else "covers our point")
    if covered:
        verdict = Verdict.PASS
        reason = "inside " + ", ".join(e.name for e in covered)
    else:
        nearest, miss = min(checks, key=lambda c: len(c[1]))
        verdict = Verdict.MARGINAL
        reason = (
            f"outside every datasheet example; nearest is {nearest.name} ({'; '.join(miss)}). "
            "Loop behavior here is not shown by the vendor: measure it"
        )
    inputs = {
        "vin_min": Quantity(ours.vin_min_v, "V"),
        "vin_max": Quantity(ours.vin_max_v, "V"),
        "vout": Quantity(ours.vout_v, "V"),
    }
    for key, attr, unit in (("fsw", "fsw_hz", "Hz"), ("l", "l_h", "H"), ("cout", "cout_f", "F")):
        if getattr(ours, attr) is not None:
            inputs[key] = Quantity(getattr(ours, attr), unit)
    refs = tuple(dict.fromkeys(e.source for e in examples if e.source))
    factors = ", ".join(f"{k} x{1 + t[k]:g}" for k in ("vout", "fsw", "l", "cout"))
    return Result(
        name="operating envelope vs datasheet examples",
        formula="covered if one example matches comp mode and contains VIN, VOUT, fsw, L, COUT within tolerance",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=refs,
        assumptions=(
            f"our compensation: {ours.comp or 'not stated'}",
            f"VIN range may exceed the example range by {t['vin']:.0%}; other values within a factor ({factors})",
            "example values not stated on the page are not compared",
        ),
    )
