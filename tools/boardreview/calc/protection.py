"""TVS checks: standoff against the worst-case rail, clamp voltage against the downstream absolute maximum."""

from __future__ import annotations

import numpy as np

from boardreview.calc.base import Quantity, Result, Verdict


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
    if v_br_min_v is not None and v_peak >= v_br_min_v:
        verdict, reason = Verdict.FAIL, f"rail peak {v_peak:.3f} V reaches VBR(min) {v_br_min_v:g} V; the TVS conducts"
    elif margin < 0:
        verdict, reason = Verdict.FAIL, f"rail peak {v_peak:.3f} V above VRWM {v_rwm_v:g} V; leakage is no longer specified"
    elif margin < margin_frac * v_rwm_v:
        verdict = Verdict.MARGINAL
        reason = f"rail peak {v_peak:.3f} V is {margin * 1e3:.0f} mV ({margin / v_rwm_v:.1%}) under VRWM {v_rwm_v:g} V"
    else:
        verdict, reason = Verdict.PASS, f"{margin * 1e3:.0f} mV under VRWM"
    inputs = {
        "v_rail_max": Quantity(v_rail_max_v, "V", "worst-case DC"),
        "ripple_pp": Quantity(ripple_pp_v, "V"),
        "v_rwm": Quantity(v_rwm_v, "V"),
    }
    if v_br_min_v is not None:
        inputs["v_br_min"] = Quantity(v_br_min_v, "V")
    return Result(
        name="TVS standoff vs worst-case rail",
        formula="Vpeak = Vrail_max + Vripple_pp/2; margin = VRWM - Vpeak",
        inputs=inputs,
        outputs={"v_peak": Quantity(v_peak, "V"), "margin": Quantity(margin, "V")},
        verdict=verdict,
        reason=reason,
        refs=("TVS data sheet: VRWM, VBR(min) and IR at VRWM; pass the part, revision and page in refs",) + tuple(refs),
        assumptions=(
            f"MARGINAL below {margin_frac:.0%} of VRWM",
            "VRWM is the voltage at which the vendor specifies leakage; leakage rises with temperature",
        ),
    )


def tvs_clamp(
    v_abs_max_v: float,
    i_surge_a: float,
    clamp_points: list[tuple[float, float]],
    margin_frac: float = 0.10,
    refs: tuple[str, ...] = (),
) -> Result:
    """Clamp voltage at the expected surge current, interpolated from (Ipp, Vc) points, against the downstream abs max."""
    pts = sorted(clamp_points)
    i = np.array([p[0] for p in pts])
    v = np.array([p[1] for p in pts])
    if len(pts) == 1:
        vc, r_dyn = float(v[0]), float("nan")
    else:
        k = int(np.clip(np.searchsorted(i, i_surge_a), 1, len(i) - 1))
        r_dyn = float((v[k] - v[k - 1]) / (i[k] - i[k - 1]))
        # Below the first point keep the first Vc rather than extrapolating down.
        vc = float(v[k - 1] + r_dyn * (max(i_surge_a, i[0]) - i[k - 1]))
    margin = v_abs_max_v - vc
    if margin < 0:
        verdict, reason = Verdict.FAIL, f"clamps at {vc:.2f} V, above the downstream abs max {v_abs_max_v:g} V"
    elif margin < margin_frac * v_abs_max_v:
        verdict, reason = Verdict.MARGINAL, f"clamps at {vc:.2f} V, within {margin_frac:.0%} of {v_abs_max_v:g} V"
    else:
        verdict, reason = Verdict.PASS, f"clamps at {vc:.2f} V, {margin:.2f} V under abs max"
    return Result(
        name="TVS clamp vs downstream abs max",
        formula="Vc(I) linear between datasheet (Ipp, Vc) points, extrapolated with the last slope; margin = Vabsmax - Vc",
        inputs={
            "v_abs_max": Quantity(v_abs_max_v, "V"),
            "i_surge": Quantity(i_surge_a, "A"),
            **{f"vc_at_{p[0]:g}A": Quantity(p[1], "V") for p in pts},
        },
        outputs={"v_clamp": Quantity(vc, "V"), "r_dyn": Quantity(r_dyn, "ohm"), "margin": Quantity(margin, "V")},
        verdict=verdict,
        reason=reason,
        refs=("TVS data sheet: VC at IPP for the stated pulse; pass the part, revision and page in refs",) + tuple(refs),
        assumptions=(
            "trace inductance between TVS and the protected pin adds L*di/dt on top of Vc",
            "clamp points are for the same pulse shape as the expected surge",
        ),
    )
