"""Buck converter checks: duty, dropout, ripple, current slew, slew-limited swing, inrush, example envelope."""

from __future__ import annotations

import math
from dataclasses import dataclass

from boardreview.calc.base import Key, Quantity, Result, Verdict, fmt

LTC3633A = "LTC3633A/LTC3633A-1 data sheet Rev B (3633a1fb)"


def _pct(frac: float) -> str:
    return fmt(100.0 * frac, "%")


def _drops(iout_a: float, r_top_ohm: float, r_bot_ohm: float, r_l_ohm: float) -> dict[str, Quantity]:
    return {
        "iout": Quantity(iout_a, "A", label="Output current"),
        "r_top": Quantity(r_top_ohm, "ohm", label="High-side switch resistance"),
        "r_bot": Quantity(r_bot_ohm, "ohm", label="Low-side switch resistance"),
        "r_l": Quantity(r_l_ohm, "ohm", label="Inductor resistance"),
    }


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
    load = f" at {fmt(iout_a, 'A')}" if iout_a else ""
    head = f"To make {fmt(vout_v, 'V')} from {fmt(vin_v, 'V')}{load} the converter needs a duty cycle of {fmt(d)}"
    lossless = f" ({fmt(d_ideal)} with no losses)" if fmt(d_ideal) != fmt(d) else ""
    if d >= 1.0:
        summary = (f"{head}{lossless}. A buck cannot keep its switch on for the whole cycle, so the output sags "
                   f"below {fmt(vout_v, 'V')} at this input.")
    else:
        summary = (f"{head}{lossless}. The dropout check compares this with the longest on-time the controller "
                   "allows.")
    return Result(
        name="buck duty cycle",
        formula="D = (VOUT + I*(Rbot + RL)) / (VIN - I*(Rtop - Rbot)); ideal D = VOUT/VIN",
        inputs={
            "vin": Quantity(vin_v, "V", label="Input voltage"),
            "vout": Quantity(vout_v, "V", label="Output voltage"),
            **_drops(iout_a, r_top_ohm, r_bot_ohm, r_l_ohm),
        },
        outputs={"d": Quantity(d, "", label="Duty cycle"), "d_ideal": Quantity(d_ideal, "", label="Ideal duty cycle")},
        verdict=verdict,
        reason=reason,
        refs=("volt-second balance on the switch node (CCM, synchronous rectifier)",),
        assumptions=("continuous conduction", "switching and dead-time losses ignored"),
        summary=summary,
        key=(Key("d", "under 1"),),
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
    want = margin_frac * vin_v
    if d_req > dmax:
        verdict, reason = Verdict.FAIL, f"needs D = {d_req:.3f} above Dmax = {dmax:.3f}; output drops out"
        summary = (f"At {fmt(vin_v, 'V')} input the converter needs a duty cycle of {fmt(d_req)}, above the "
                   f"{fmt(dmax)} it can reach. It regulates only above {fmt(vin_min, 'V')}, so {fmt(vout_v, 'V')} "
                   "sags at this input.")
        key = (Key("vin_min", f"under {fmt(vin_v - want, 'V')}"), Key("d_required", f"under {fmt(dmax)}"))
    elif headroom < want:
        verdict, reason = Verdict.MARGINAL, f"VIN is {headroom:.3f} V above dropout, under {margin_frac:.0%} of VIN"
        summary = (f"The converter regulates down to {fmt(vin_min, 'V')} input. At {fmt(vin_v, 'V')} that leaves "
                   f"{fmt(headroom, 'V')} of headroom, less than the {fmt(want, 'V')} we want, so a small input droop "
                   "or a hot switch can make it drop out.")
        key = (Key("headroom", f"{fmt(want, 'V')} or more"), Key("vin_min"))
    else:
        verdict, reason = Verdict.PASS, f"VIN is {headroom:.3f} V above dropout"
        summary = (f"The converter regulates down to {fmt(vin_min, 'V')} input. At {fmt(vin_v, 'V')} it has "
                   f"{fmt(headroom, 'V')} of headroom, more than the {fmt(want, 'V')} we want.")
        key = (Key("headroom", f"{fmt(want, 'V')} or more"), Key("vin_min"))
    outputs = {
        "dmax_typ": Quantity(dmax_typ, "", label="Maximum duty, typical"),
        "dmax_used": Quantity(dmax, "", "lower of typical and measured" if dmax_measured is not None else "",
                              label="Maximum duty used"),
        "d_required": Quantity(d_req, "", label="Required duty"),
        "vin_min_typ": Quantity(vin_min_typ, "V", label="Lowest input that regulates, typical"),
        "vin_min": Quantity(vin_min, "V", label="Lowest input that regulates"),
        "headroom": Quantity(headroom, "V", label="Headroom above dropout"),
    }
    inputs = {
        "vin": Quantity(vin_v, "V", label="Input voltage"),
        "vout": Quantity(vout_v, "V", label="Output voltage"),
        "f": Quantity(f_hz, "Hz", label="Switching frequency"),
        "t_off_min": Quantity(t_off_min_s, "s", label="Minimum off-time"),
        "t_dead": Quantity(t_dead_s, "s", label="Dead time"),
        **_drops(iout_a, r_top_ohm, r_bot_ohm, r_l_ohm),
        "margin_min": Quantity(margin_frac, "", "headroom as a fraction of VIN", label="Required headroom"),
    }
    if dmax_measured is not None:
        inputs["dmax_measured"] = Quantity(dmax_measured, "", label="Maximum duty, measured")
    return Result(
        name="buck dropout",
        formula="Dmax = 1 - f*(tOFFmin + 2*tdead); VINmin = (VOUT + I*(Rbot + RL))/Dmax + I*(Rtop - Rbot)",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(f"{LTC3633A} p. 15, Minimum Off-Time/On-Time Considerations (DC(MAX), VIN(MIN))",),
        assumptions=("tOFFmin and tdead are typical values unless a measured Dmax is given",),
        summary=summary,
        key=key,
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
    said: list[str] = []
    verdict = Verdict.PASS
    if i_sat_a is not None and i_pk > i_sat_a:
        problems.append(f"peak {i_pk:.3f} A above Isat {i_sat_a:.3f} A")
        said.append(f"That is above the {fmt(i_sat_a, 'A')} saturation current, so the inductance collapses at the "
                    "peak and the current spikes.")
        verdict = Verdict.FAIL
    if i_valley_limit_a is not None and i_val > i_valley_limit_a:
        problems.append(f"valley {i_val:.3f} A above valley current limit {i_valley_limit_a:.3f} A")
        said.append(f"The valley of {fmt(i_val, 'A')} is above the {fmt(i_valley_limit_a, 'A')} valley current "
                    "limit, so the converter limits current before it reaches this load.")
        verdict = Verdict.FAIL
    if i_neg_limit_a is not None and -di / 2.0 < -abs(i_neg_limit_a):
        problems.append(f"no-load valley {-di / 2:.3f} A below negative limit -{abs(i_neg_limit_a):.3f} A")
        said.append(f"At no load the current swings down to {fmt(-di / 2.0, 'A')}, past the "
                    f"{fmt(-abs(i_neg_limit_a), 'A')} negative current limit.")
        verdict = Verdict.FAIL
    outputs = {
        "di": Quantity(di, "A", "peak to peak", label="Ripple current"),
        "i_peak": Quantity(i_pk, "A", label="Peak inductor current"),
        "i_valley": Quantity(i_val, "A", label="Valley inductor current"),
    }
    key: list[Key] = []
    if i_sat_a is not None:
        key.append(Key("i_peak", f"under {fmt(i_sat_a, 'A')}"))
    if i_valley_limit_a is not None:
        key.append(Key("i_valley", f"under {fmt(i_valley_limit_a, 'A')}"))
    if iout_max_a is not None:
        ratio = di / iout_max_a
        outputs["ripple_ratio"] = Quantity(ratio, "", "of IOUT(MAX)", label="Ripple over the maximum load")
        key.append(Key("di", f"{fmt(0.6 * iout_max_a, 'A')} or less"))
        if ratio > 0.6 and verdict is Verdict.PASS:
            problems.append(f"ripple is {ratio:.0%} of IOUT(MAX), above 60 %")
            said.append(f"That ripple is {_pct(ratio)} of the {fmt(iout_max_a, 'A')} maximum load, above the 60% "
                        "the datasheet recommends, so output ripple and core loss run high.")
            verdict = Verdict.MARGINAL
    else:
        key.append(Key("di"))
    if i_valley_limit_a is not None:
        outputs["iout_limit"] = Quantity(i_valley_limit_a + di / 2.0, "A", "output current at valley limit",
                                         label="Output current at the valley limit")
    reason = "; ".join(problems) if problems else "within the given limits"
    head = (f"The inductor current ripples {fmt(di, 'A')} peak to peak around the {fmt(iout_a, 'A')} load, so it "
            f"peaks at {fmt(i_pk, 'A')} and falls to {fmt(i_val, 'A')}.")
    if i_sat_a is None and i_valley_limit_a is None and i_neg_limit_a is None and iout_max_a is None:
        verdict, reason = Verdict.INFO, ""
        said = ["No saturation or current limits were given to compare with."]
    elif verdict is Verdict.PASS:
        limits = [f"the peak stays under the {fmt(i_sat_a, 'A')} saturation current" if i_sat_a is not None else "",
                  f"the valley stays under the {fmt(i_valley_limit_a, 'A')} valley current limit"
                  if i_valley_limit_a is not None else "",
                  f"at no load the current stays above the {fmt(-abs(i_neg_limit_a), 'A')} negative limit"
                  if i_neg_limit_a is not None else "",
                  f"the ripple is {_pct(di / iout_max_a)} of the {fmt(iout_max_a, 'A')} maximum load, within the 60% "
                  "the datasheet recommends" if iout_max_a is not None else ""]
        text = "; ".join(x for x in limits if x)
        said = [text[:1].upper() + text[1:] + "."]
    inputs = {
        "vin": Quantity(vin_v, "V", label="Input voltage"),
        "vout": Quantity(vout_v, "V", label="Output voltage"),
        "f": Quantity(f_hz, "Hz", label="Switching frequency"),
        "l": Quantity(l_h, "H", label="Inductance"),
        "iout": Quantity(iout_a, "A", label="Output current"),
    }
    for name, value, label in (
        ("i_sat", i_sat_a, "Saturation current"), ("i_valley_limit", i_valley_limit_a, "Valley current limit"),
        ("i_neg_limit", i_neg_limit_a, "Negative current limit"), ("iout_max", iout_max_a, "Maximum load current"),
    ):
        if value is not None:
            inputs[name] = Quantity(value, "A", label=label)
    return Result(
        name="inductor ripple",
        formula="dI = VOUT*(1 - VOUT/VIN)/(f*L); Ipk = IOUT + dI/2; Ivalley = IOUT - dI/2",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(
            f"{LTC3633A} p. 12, Inductor Selection (ripple equation)",
            f"{LTC3633A} p. 13, ripple above 60 % of IOUT(MAX) not recommended",
        ),
        assumptions=("continuous conduction", "inductance at operating current (derate for saturation)"),
        summary=" ".join([head, *said]),
        key=tuple(key[:3]),
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
    rates = f"The inductor current can rise at {fmt(s_up, 'A/s')} and fall at {fmt(s_down, 'A/s')}"
    if s_up <= 0:
        verdict, reason = Verdict.FAIL, "VIN*Dmax is below VOUT; current cannot rise"
        summary = (f"{rates}: at {fmt(vin_v, 'V')} and a maximum duty of {fmt(dmax)} the switch node averages less "
                   f"than {fmt(vout_v, 'V')}, so the current cannot rise at all. A load step pulls the output down "
                   "until the input recovers.")
        key = (Key("s_up", "above 0"),)
    elif load_slew_a_per_s is not None and load_slew_a_per_s > s_up:
        verdict = Verdict.MARGINAL
        reason = f"load step slews {load_slew_a_per_s / 1e6:.3f} A/us, faster than S_up {s_up / 1e6:.3f} A/us"
        summary = (f"{rates}. The load steps at {fmt(load_slew_a_per_s, 'A/s')}, faster than the current can rise, "
                   "so the output dips until the inductor catches up, deeper than the loop alone would allow.")
        key = (Key("s_up", f"{fmt(load_slew_a_per_s, 'A/s')} or more"), Key("load_slew"))
    elif asym > asymmetry_limit:
        verdict = Verdict.MARGINAL
        reason = f"up-slew is {asym:.1f}x slower than down-slew; large-signal response is slew limited"
        summary = (f"{rates}, so it falls {fmt(asym)} times as fast as it rises. We allow up to "
                   f"{fmt(asymmetry_limit)} times; beyond that a large load step is slew limited and the output "
                   "recovers slower than the loop bandwidth suggests.")
        key = (Key("down_over_up", f"{fmt(asymmetry_limit)} or less"), Key("s_up"))
    else:
        verdict, reason = Verdict.PASS, f"up/down slew ratio 1:{asym:.1f}"
        summary = (f"{rates}, so it falls {fmt(asym)} times as fast as it rises. We allow up to "
                   f"{fmt(asymmetry_limit)} times, so large load steps are not badly slew limited.")
        key = (Key("down_over_up", f"{fmt(asymmetry_limit)} or less"), Key("s_up"))
        if load_slew_a_per_s is not None:
            summary += f" The load steps at {fmt(load_slew_a_per_s, 'A/s')}, slower than the current can rise."
    inputs = {
        "vin": Quantity(vin_v, "V", label="Input voltage"),
        "vout": Quantity(vout_v, "V", label="Output voltage"),
        "l": Quantity(l_h, "H", label="Inductance"),
        "dmax": Quantity(dmax, "", label="Maximum duty"),
        "asymmetry_limit": Quantity(asymmetry_limit, "", "MARGINAL above this down/up slew ratio",
                                    label="Largest down to up slew ratio allowed"),
    }
    if load_slew_a_per_s is not None:
        inputs["load_slew"] = Quantity(load_slew_a_per_s, "A/s", label="Load step slew")
    return Result(
        name="inductor current slew headroom",
        formula="S_up = (VIN*Dmax - VOUT)/L; S_down = VOUT/L",
        inputs=inputs,
        outputs={
            "s_up": Quantity(s_up, "A/s", f"{s_up / 1e6:.3f} A/us", label="Current slew, rising"),
            "s_down": Quantity(s_down, "A/s", f"{s_down / 1e6:.3f} A/us", label="Current slew, falling"),
            "down_over_up": Quantity(asym, "", label="Falling over rising slew"),
        },
        verdict=verdict,
        reason=reason,
        refs=("inductor law V = L*dI/dt averaged over a switching cycle at the duty limits",),
        assumptions=("down-slew assumes the top switch can stay off for whole cycles",),
        summary=summary,
        key=key,
    )


def slew_clamp_vpp(slew_a_per_s: float, f_hz: float, c_f: float, limit_v: float | None = None) -> Result:
    """Largest sinusoidal output swing at f that a slew-limited inductor current can sustain on C."""
    w = 2.0 * math.pi * f_hz
    vpp = 2.0 * slew_a_per_s / (w * w * c_f)
    ipk = slew_a_per_s / w
    head = (f"With the inductor current slewing at most {fmt(slew_a_per_s, 'A/s')}, an oscillation at "
            f"{fmt(f_hz, 'Hz')} on {fmt(c_f, 'F')} can grow to {fmt(vpp, 'V')} peak to peak")
    if limit_v is None:
        verdict, reason = Verdict.INFO, ""
        summary = f"{head}. That is the largest swing the slew limit allows."
        key = (Key("vpp"),)
    elif vpp > limit_v:
        verdict, reason = Verdict.FAIL, f"an oscillation at this frequency can reach {vpp * 1e3:.1f} mVpp"
        summary = (f"{head}, more than the {fmt(limit_v, 'V')} allowed. The slew limit does not keep an oscillation "
                   "small, so the loop itself has to be stable.")
        key = (Key("vpp", f"under {fmt(limit_v, 'V')}"),)
    else:
        verdict, reason = Verdict.PASS, f"clamp {vpp * 1e3:.1f} mVpp is under {limit_v * 1e3:.1f} mVpp"
        summary = (f"{head}, under the {fmt(limit_v, 'V')} allowed. Even if the loop rang at this frequency, the "
                   "slew limit keeps the swing small.")
        key = (Key("vpp", f"under {fmt(limit_v, 'V')}"),)
    inputs = {"slew": Quantity(slew_a_per_s, "A/s", label="Inductor current slew"),
              "f": Quantity(f_hz, "Hz", label="Oscillation frequency"),
              "c": Quantity(c_f, "F", label="Output capacitance")}
    if limit_v is not None:
        inputs["limit"] = Quantity(limit_v, "V", label="Allowed swing")
    return Result(
        name="slew-limited oscillation clamp",
        formula="Vpp = 2*S/((2*pi*f)^2*C); Ipk = S/(2*pi*f)",
        inputs=inputs,
        outputs={"vpp": Quantity(vpp, "V", label="Largest swing, peak to peak"),
                 "i_pk": Quantity(ipk, "A", label="Inductor current amplitude")},
        verdict=verdict,
        reason=reason,
        refs=("sinusoid of amplitude I has peak slope 2*pi*f*I; V on C is I/(2*pi*f*C)",),
        assumptions=("sinusoidal oscillation", "load current constant", "C is the effective output capacitance"),
        summary=summary,
        key=key,
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
    head = f"Charging {fmt(c_f, 'F')} to {fmt(vout_v, 'V')} in {fmt(t_ss_s, 's')} takes {fmt(i_cap, 'A')}"
    head += f", {fmt(i_tot, 'A')} with the {fmt(i_load_a, 'A')} load." if i_load_a else "."
    if i_limit_a is None:
        verdict, reason = Verdict.INFO, ""
        summary = f"{head} No current limit was given to compare with."
        key = (Key("i_total"),)
    else:
        want = f"{fmt(0.8 * i_limit_a, 'A')} or less"
        key = (Key("i_total", want),)
        if i_tot > i_limit_a:
            verdict, reason = Verdict.FAIL, f"inrush {i_tot:.3f} A exceeds limit {i_limit_a:.3f} A"
            summary = (f"{head} That is above the {fmt(i_limit_a, 'A')} current limit, so start-up runs into the "
                       "limit: the ramp stretches or the converter hiccups.")
        elif i_tot > 0.8 * i_limit_a:
            verdict, reason = Verdict.MARGINAL, f"inrush {i_tot:.3f} A is over 80 % of {i_limit_a:.3f} A"
            summary = (f"{head} That is over 80% of the {fmt(i_limit_a, 'A')} current limit, so a part at the low "
                       "end of its limit or a heavier start-up load can trip it.")
        else:
            verdict, reason = Verdict.PASS, f"inrush {i_tot:.3f} A under {i_limit_a:.3f} A"
            summary = f"{head} That is under 80% of the {fmt(i_limit_a, 'A')} current limit, so start-up stays clear of it."
    inputs = {
        "c": Quantity(c_f, "F", label="Output capacitance"),
        "vout": Quantity(vout_v, "V", label="Output voltage"),
        "t_ss": Quantity(t_ss_s, "s", label="Soft-start time"),
        "i_load": Quantity(i_load_a, "A", label="Load during start-up"),
    }
    if i_limit_a is not None:
        inputs["i_limit"] = Quantity(i_limit_a, "A", label="Current limit")
    return Result(
        name="soft-start inrush",
        formula="I = C*VOUT/tSS + Iload",
        inputs=inputs,
        outputs={"i_cap": Quantity(i_cap, "A", label="Capacitor charging current"),
                 "i_total": Quantity(i_tot, "A", label="Start-up current")},
        verdict=verdict,
        reason=reason,
        refs=("I = C*dV/dt for a linear ramp",),
        assumptions=("linear ramp from 0 to VOUT over tSS",),
        summary=summary,
        key=key,
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
_DIMS = (("vout", "vout_v", "V"), ("fsw", "fsw_hz", "Hz"), ("l", "l_h", "H"), ("cout", "cout_f", "F"))
_WORDS = {"vout": "output", "fsw": "frequency", "l": "inductor", "cout": "output capacitance", "comp": "compensation"}
_TOL_LABEL = {"vin": "input range", "vout": "output voltage", "fsw": "frequency", "l": "inductor",
              "cout": "output capacitance"}


def _missing(p: BuckPoint) -> list[str]:
    return [k for k, attr, _ in _DIMS if getattr(p, attr) is None] + ([] if p.comp else ["comp"])


def _mismatches(ours: BuckPoint, ex: BuckPoint, tol: dict[str, float]) -> list[str]:
    out: list[str] = []
    if ours.comp and ex.comp and ours.comp != ex.comp:
        out.append(f"comp {ours.comp} vs {ex.comp}")
    lo, hi = ex.vin_min_v * (1 - tol["vin"]), ex.vin_max_v * (1 + tol["vin"])
    if ours.vin_min_v < lo or ours.vin_max_v > hi:
        out.append(f"VIN {ours.vin_min_v:g}-{ours.vin_max_v:g} V vs {ex.vin_min_v:g}-{ex.vin_max_v:g} V")
    for key, attr, unit in _DIMS:
        a, b = getattr(ours, attr), getattr(ex, attr)
        if a is None or b is None:
            continue
        if max(a / b, b / a) > 1.0 + tol[key]:
            out.append(f"{key} {a:.4g} vs {b:.4g} {unit}")
    return out


def _plain_mismatches(ours: BuckPoint, ex: BuckPoint, tol: dict[str, float]) -> list[str]:
    """The same mismatches as _mismatches, in words: 'inductor 4.7 µH against 2.2 µH'."""
    out: list[str] = []
    if ours.comp and ex.comp and ours.comp != ex.comp:
        out.append(f"compensation {ours.comp} against {ex.comp}")
    lo, hi = ex.vin_min_v * (1 - tol["vin"]), ex.vin_max_v * (1 + tol["vin"])
    if ours.vin_min_v < lo or ours.vin_max_v > hi:
        out.append(f"input {fmt(ours.vin_min_v)} to {fmt(ours.vin_max_v, 'V')} against "
                   f"{fmt(ex.vin_min_v)} to {fmt(ex.vin_max_v, 'V')}")
    for key, attr, unit in _DIMS:
        a, b = getattr(ours, attr), getattr(ex, attr)
        if a is not None and b is not None and max(a / b, b / a) > 1.0 + tol[key]:
            out.append(f"{_WORDS[key]} {fmt(a, unit)} against {fmt(b, unit)}")
    return out


def example_envelope(
    ours: BuckPoint,
    examples: list[BuckPoint],
    tol: dict[str, float] | None = None,
) -> Result:
    """Flag a design that sits outside every datasheet example circuit; pass only when every field is known."""
    t = {**DEFAULT_TOL, **(tol or {})}
    if not examples:
        return Result(
            name="operating envelope vs datasheet examples",
            formula="covered if one example matches comp mode and contains VIN, VOUT, fsw, L, COUT within tolerance",
            inputs={},
            outputs={},
            verdict=Verdict.UNKNOWN,
            reason="no examples given",
            summary=("No datasheet example circuits were given, so this design cannot be compared with them. "
                     "Give the examples with their pages to settle it."),
        )
    ours_missing = _missing(ours)
    checks = [(ex, _mismatches(ours, ex, t)) for ex in examples]
    consistent = [ex for ex, m in checks if not m]
    covered = [ex for ex in consistent if not ours_missing and not _missing(ex)]
    open_ = [ex for ex in consistent if ours_missing or _missing(ex)]
    same_comp = [ex for ex in examples if not (ours.comp and ex.comp and ex.comp != ours.comp)]
    outputs: dict[str, Quantity] = {
        "examples": Quantity(len(examples), "count", label="Example circuits"),
        "covering": Quantity(len(covered), "count", label="Examples that cover this design"),
    }
    if same_comp:
        outputs["vin_lo_same_comp"] = Quantity(min(e.vin_min_v for e in same_comp), "V", "lowest example VIN",
                                               label="Lowest example input, same compensation")
        outputs["vin_hi_same_comp"] = Quantity(max(e.vin_max_v for e in same_comp), "V", "highest example VIN",
                                               label="Highest example input, same compensation")
        ls = [e.l_h for e in same_comp if e.l_h is not None]
        if ls:
            outputs["l_hi_same_comp"] = Quantity(max(ls), "H", "largest example L",
                                                 label="Largest example inductor, same compensation")
    for ex, m in checks:
        if m:
            note = "; ".join(m)
        elif ex in open_:
            note = "matches the given values; missing " + ", ".join(ours_missing + [f"example {k}" for k in _missing(ex)])
        else:
            note = "covers our point"
        outputs[f"miss[{ex.name}]"] = Quantity(len(m), "count", note, label=f"Mismatches with {ex.name}")
    n, here = len(examples), (f"This design ({fmt(ours.vin_min_v)} to {fmt(ours.vin_max_v, 'V')} in, "
                              f"{fmt(ours.vout_v, 'V')} out)")
    if covered:
        verdict = Verdict.PASS
        reason = "inside " + ", ".join(e.name for e in covered)
        summary = (f"{here} sits inside {', '.join(e.name for e in covered)}: {fmt(len(covered), 'count')} of {n} "
                   "datasheet example circuits cover it. The vendor shows the loop working at this operating point.")
    elif open_:
        parts = [f"ours: {', '.join(ours_missing)}"] if ours_missing else []
        parts += [f"{e.name}: {', '.join(_missing(e))}" for e in open_ if _missing(e)]
        verdict = Verdict.UNKNOWN
        reason = (
            f"consistent with {', '.join(e.name for e in open_)} on the values given, but missing "
            f"{'; '.join(parts)}. Give these to settle coverage"
        )
        gaps = ([f"this design's {', '.join(_WORDS.get(k, k) for k in ours_missing)}"] if ours_missing else []) + [
            f"{e.name}'s {', '.join(_WORDS.get(k, k) for k in _missing(e))}" for e in open_ if _missing(e)]
        summary = (f"{here} agrees with {', '.join(e.name for e in open_)} on the values given. Still missing: "
                   f"{'; '.join(gaps)}. So far {fmt(len(covered), 'count')} of {n} examples confirm coverage; give "
                   "the missing values to settle it.")
    else:
        nearest, miss = min(checks, key=lambda c: len(c[1]))
        verdict = Verdict.MARGINAL
        reason = (
            f"outside every datasheet example; nearest is {nearest.name} ({'; '.join(miss)}). "
            "Loop behavior here is not shown by the vendor: measure it"
        )
        where = "the one datasheet example circuit" if n == 1 else f"all {n} datasheet example circuits"
        summary = (f"{here} sits outside {where}: {fmt(len(covered), 'count')} of {n} cover it. The nearest is "
                   f"{nearest.name}, with {'; '.join(_plain_mismatches(ours, nearest, t))}. The vendor does not show "
                   "the loop at this point, so measure it.")
    inputs = {
        "vin_min": Quantity(ours.vin_min_v, "V", label="Lowest input voltage"),
        "vin_max": Quantity(ours.vin_max_v, "V", label="Highest input voltage"),
        "vout": Quantity(ours.vout_v, "V", label="Output voltage"),
    }
    for key, attr, unit, label in (("fsw", "fsw_hz", "Hz", "Switching frequency"), ("l", "l_h", "H", "Inductor"),
                                   ("cout", "cout_f", "F", "Output capacitance")):
        if getattr(ours, attr) is not None:
            inputs[key] = Quantity(getattr(ours, attr), unit, label=label)
    for key in ("vin", "vout", "fsw", "l", "cout"):
        inputs[f"tol_{key}"] = Quantity(t[key], "", "screening tolerance",
                                        label=f"Screening tolerance on {_TOL_LABEL[key]}")
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
            "tolerances are screening heuristics, not vendor stability guarantees",
            "a value missing on our side or the example's blocks a pass",
        ),
        summary=summary,
        key=(Key("covering", "1 or more"),),
    )
