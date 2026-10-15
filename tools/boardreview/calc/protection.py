"""TVS checks: standoff against the worst-case rail, clamp voltage against the downstream absolute maximum."""

from __future__ import annotations

import numpy as np

from boardreview.calc.base import Key, Quantity, Result, Verdict, fmt


def tvs_standoff(
    v_rail_max_v: float,
    v_rwm_v: float,
    ripple_pp_v: float = 0.0,
    v_br_min_v: float | None = None,
    margin_frac: float = 0.05,
    refs: tuple[str, ...] = (),
) -> Result:
    """Worst-case rail peak (DC corner plus half the ripple) against the TVS reverse standoff voltage."""
    v_peak = v_rail_max_v + ripple_pp_v / 2.0
    margin = v_rwm_v - v_peak
    peak = f"The rail peaks at {fmt(v_peak, 'V')}"
    if ripple_pp_v:
        peak += f" ({fmt(v_rail_max_v, 'V')} plus half the {fmt(ripple_pp_v, 'V')} ripple)"
    standoff = fmt(v_rwm_v, "V")
    want = f"{fmt(v_rwm_v * (1 - margin_frac), 'V')} or less"
    if v_br_min_v is not None and v_peak >= v_br_min_v:
        verdict, reason = Verdict.FAIL, f"rail peak {v_peak:.3f} V reaches VBR(min) {v_br_min_v:g} V; the TVS conducts"
        summary = (f"{peak}, which reaches the TVS's {fmt(v_br_min_v, 'V')} minimum breakdown. The TVS conducts in "
                   "normal operation, heats up and loads the rail.")
        key = (Key("v_peak", want),)
    elif margin < 0:
        verdict = Verdict.FAIL
        reason = f"rail peak {v_peak:.3f} V above VRWM {v_rwm_v:g} V; leakage is no longer specified"
        summary = (f"{peak}, above the TVS standoff of {standoff}. Above standoff the leakage is not specified and the "
                   "TVS can start to conduct, more so when hot; use a part with a higher standoff.")
        key = (Key("v_peak", want),)
    elif margin < margin_frac * v_rwm_v:
        verdict = Verdict.MARGINAL
        reason = f"rail peak {v_peak:.3f} V is {margin * 1e3:.0f} mV ({margin / v_rwm_v:.1%}) under VRWM {v_rwm_v:g} V"
        summary = (f"{peak}, only {fmt(margin, 'V')} under the {standoff} standoff. Leakage rises near standoff, "
                   "more so when hot.")
        key = (Key("margin", f"{fmt(margin_frac * v_rwm_v, 'V')} or more"), Key("v_peak"))
    else:
        verdict, reason = Verdict.PASS, f"{margin * 1e3:.0f} mV under VRWM"
        summary = f"{peak}, {fmt(margin, 'V')} under the {standoff} standoff, so the TVS stays off in normal operation."
        key = (Key("margin", f"{fmt(margin_frac * v_rwm_v, 'V')} or more"), Key("v_peak"))
    inputs = {
        "v_rail_max": Quantity(v_rail_max_v, "V", "worst-case DC", label="Rail maximum"),
        "ripple_pp": Quantity(ripple_pp_v, "V", label="Ripple, peak to peak"),
        "v_rwm": Quantity(v_rwm_v, "V", label="TVS standoff voltage"),
        "margin_min": Quantity(margin_frac, "", "fraction of VRWM", label="Required margin under standoff"),
    }
    if v_br_min_v is not None:
        inputs["v_br_min"] = Quantity(v_br_min_v, "V", label="TVS minimum breakdown")
    return Result(
        name="TVS standoff vs worst-case rail",
        formula="Vpeak = Vrail_max + Vripple_pp/2; margin = VRWM - Vpeak",
        inputs=inputs,
        outputs={"v_peak": Quantity(v_peak, "V", label="Rail peak"),
                 "margin": Quantity(margin, "V", label="Margin under standoff")},
        verdict=verdict,
        reason=reason,
        refs=("TVS data sheet: VRWM, VBR(min) and IR at VRWM; pass the part, revision and page in refs",) + tuple(refs),
        assumptions=(
            f"MARGINAL below {margin_frac:.0%} of VRWM",
            "VRWM is the voltage at which the vendor specifies leakage; leakage rises with temperature",
        ),
        summary=summary,
        key=key,
    )


def tvs_clamp(
    v_abs_max_v: float,
    i_surge_a: float,
    clamp_points: list[tuple[float, float]],
    margin_frac: float = 0.10,
    refs: tuple[str, ...] = (),
    i_pp_max_a: float | None = None,
    p_pp_max_w: float | None = None,
) -> Result:
    """Clamp voltage at the surge current from (Ipp, Vc) points against the downstream abs max and the pulse rating."""
    pts = sorted(clamp_points)
    i = np.array([p[0] for p in pts])
    v = np.array([p[1] for p in pts])
    i_char = float(i[-1])
    beyond = i_surge_a > i_char
    if len(pts) == 1:
        vc, r_dyn = float(v[0]), float("nan")
    else:
        k = int(np.clip(np.searchsorted(i, i_surge_a), 1, len(i) - 1))
        r_dyn = float((v[k] - v[k - 1]) / (i[k] - i[k - 1]))
        # Below the first point keep the first Vc rather than extrapolating down.
        vc = float(v[k - 1] + r_dyn * (max(i_surge_a, i[0]) - i[k - 1]))
    margin = v_abs_max_v - vc
    missing = []
    if i_pp_max_a is None and p_pp_max_w is None:
        missing.append("the rated peak pulse current or power for this pulse shape")
    if beyond:
        missing.append(f"Vc at {i_surge_a:g} A or above (characterized to {i_char:g} A)")
    surge, absmax = fmt(i_surge_a, "A"), fmt(v_abs_max_v, "V")
    clamp = f"At {surge} the TVS clamps at {fmt(vc, 'V')}"
    want_vc = f"{fmt(v_abs_max_v * (1 - margin_frac), 'V')} or less"
    last = f"vc_at_{pts[-1][0]:g}A"
    if i_pp_max_a is not None and i_surge_a > i_pp_max_a:
        verdict, reason = Verdict.FAIL, f"surge {i_surge_a:g} A above the rated {i_pp_max_a:g} A peak pulse current"
        summary = (f"The {surge} surge is above the TVS's {fmt(i_pp_max_a, 'A')} peak pulse rating, so the TVS can "
                   "fail short or open on that surge; use a larger part.")
        key = (Key("i_surge", f"{fmt(i_pp_max_a, 'A')} or less"),)
    elif p_pp_max_w is not None and vc * i_surge_a > p_pp_max_w:
        verdict = Verdict.FAIL
        reason = f"surge {vc * i_surge_a:.4g} W (Vc*I) above the rated {p_pp_max_w:g} W peak pulse power"
        summary = (f"{clamp} and absorbs {fmt(vc * i_surge_a, 'W')}, above its {fmt(p_pp_max_w, 'W')} pulse rating. "
                   "The TVS can fail on that surge; use a larger part.")
        key = (Key("p_pulse", f"{fmt(p_pp_max_w, 'W')} or less"),)
    elif beyond and float(v[-1]) > v_abs_max_v:
        verdict = Verdict.FAIL
        reason = f"Vc is already {v[-1]:g} V at {i_char:g} A, above the downstream abs max {v_abs_max_v:g} V"
        summary = (f"The TVS already clamps at {fmt(float(v[-1]), 'V')} at {fmt(i_char, 'A')}, above the {absmax} "
                   f"abs max of the part it protects, and the {surge} surge is larger still. The surge reaches "
                   "that part.")
        key = (Key(last, f"under {absmax}"),)
    elif not beyond and margin < 0:
        verdict, reason = Verdict.FAIL, f"clamps at {vc:.2f} V, above the downstream abs max {v_abs_max_v:g} V"
        summary = f"{clamp}, above the {absmax} abs max of the part it protects, so the surge reaches that part."
        key = (Key("v_clamp", want_vc),)
    elif missing:
        verdict = Verdict.UNKNOWN
        reason = f"clamp {vc:.2f} V{' extrapolated' if beyond else ''} against {v_abs_max_v:g} V; give {' and '.join(missing)}"
        gaps = []
        if i_pp_max_a is None and p_pp_max_w is None:
            gaps.append("the peak pulse rating for this pulse shape")
        if beyond:
            gaps.append(f"the clamp voltage at {surge}, since the datasheet stops at {fmt(i_char, 'A')}")
        summary = (f"{clamp}{' by extrapolation' if beyond else ''}, against a {absmax} abs max. This cannot be "
                   f"settled without {' and '.join(gaps)}.")
        key = (Key("v_clamp", want_vc),)
    elif margin < margin_frac * v_abs_max_v:
        verdict, reason = Verdict.MARGINAL, f"clamps at {vc:.2f} V, within {margin_frac:.0%} of {v_abs_max_v:g} V"
        summary = (f"{clamp}, only {fmt(margin, 'V')} under the {absmax} abs max. Trace inductance adds to that, so "
                   "the protected pin can see more.")
        key = (Key("margin", f"{fmt(margin_frac * v_abs_max_v, 'V')} or more"), Key("v_clamp"))
    else:
        verdict, reason = Verdict.PASS, f"clamps at {vc:.2f} V, {margin:.2f} V under abs max"
        summary = f"{clamp}, {fmt(margin, 'V')} under the {absmax} abs max of the part it protects."
        key = (Key("margin", f"{fmt(margin_frac * v_abs_max_v, 'V')} or more"), Key("v_clamp"))
    inputs = {
        "v_abs_max": Quantity(v_abs_max_v, "V", label="Protected part's abs max"),
        "i_surge": Quantity(i_surge_a, "A", label="Surge current"),
        **{f"vc_at_{p[0]:g}A": Quantity(p[1], "V", label=f"Clamp voltage at {fmt(p[0], 'A')}") for p in pts},
        "margin_min": Quantity(margin_frac, "", "fraction of the abs max", label="Required margin under abs max"),
    }
    if i_pp_max_a is not None:
        inputs["i_pp_max"] = Quantity(i_pp_max_a, "A", label="Rated peak pulse current")
    if p_pp_max_w is not None:
        inputs["p_pp_max"] = Quantity(p_pp_max_w, "W", label="Rated peak pulse power")
    return Result(
        name="TVS clamp vs downstream abs max",
        formula=(
            "Vc(I) linear between datasheet (Ipp, Vc) points, Vc(first point) below them; margin = Vabsmax - Vc; "
            "I <= IPP(max); Vc*I <= PPP(max)"
        ),
        inputs=inputs,
        outputs={
            "v_clamp": Quantity(vc, "V", "extrapolated with the last slope" if beyond else "", label="Clamp voltage"),
            "r_dyn": Quantity(r_dyn, "ohm", label="Dynamic resistance"),
            "margin": Quantity(margin, "V", label="Margin under abs max"),
            "p_pulse": Quantity(vc * i_surge_a, "W", "Vc*I at the surge peak", label="Pulse power"),
        },
        verdict=verdict,
        reason=reason,
        refs=(
            "TVS data sheet: VC at IPP and the IPP or PPP rating for the stated pulse; pass the part, revision and page in refs",
        )
        + tuple(refs),
        assumptions=(
            "trace inductance between TVS and the protected pin adds L*di/dt on top of Vc",
            "clamp points and ratings are for the same pulse shape as the expected surge",
            "Vc rises with current, so Vc at the first point bounds lower currents",
        ),
        summary=summary,
        key=key,
    )
