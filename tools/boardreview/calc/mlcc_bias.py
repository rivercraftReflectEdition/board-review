"""MLCC effective capacitance: tolerance, DC-bias curve, temperature characteristic band and aging."""

from __future__ import annotations

import re

import numpy as np

from boardreview.calc.base import Quantity, Result, Verdict
from boardreview.calc.curves import find_column, parse_csv_table, unit_scale

EIA_REF = "EIA-198-1 Class II temperature characteristic codes, from memory; page not checked (UNSURE)"
_LOW_T = {"X": -55.0, "Y": -30.0, "Z": 10.0}
_HIGH_T = {"2": 45.0, "4": 65.0, "5": 85.0, "6": 105.0, "7": 125.0, "8": 150.0, "9": 200.0}
_BAND = {
    "A": (-0.010, 0.010), "B": (-0.015, 0.015), "C": (-0.022, 0.022), "D": (-0.033, 0.033),
    "E": (-0.047, 0.047), "F": (-0.075, 0.075), "P": (-0.10, 0.10), "R": (-0.15, 0.15),
    "S": (-0.22, 0.22), "T": (-0.33, 0.22), "U": (-0.56, 0.22), "V": (-0.82, 0.22),
}
_CLASS1_PPM = {"C0G": 30.0, "NP0": 30.0}


def dielectric_band(code: str) -> tuple[float, float, float, float]:
    """(t_min_c, t_max_c, dc_low_frac, dc_high_frac) over the rated range for an EIA dielectric code."""
    c = code.strip().upper().replace("NPO", "NP0").replace("COG", "C0G")
    if c in _CLASS1_PPM:
        d = _CLASS1_PPM[c] * 1e-6 * 100.0
        return -55.0, 125.0, -d, d
    if len(c) == 3 and c[0] in _LOW_T and c[1] in _HIGH_T and c[2] in _BAND:
        lo, hi = _BAND[c[2]]
        return _LOW_T[c[0]], _HIGH_T[c[1]], lo, hi
    raise ValueError(f"unknown dielectric code {code!r}")


_PCT_CHANGE = re.compile(r"change|delta|Δ|δ|(?<![a-z])d\s*c\s*/\s*c", re.IGNORECASE)
_PCT_OF_NOM = re.compile(r"(?<![a-zΔδ])c\s*/\s*c|of\s*nom", re.IGNORECASE)


def percent_kind(header: str) -> str:
    """'change' or 'of_nominal' for a percent column header; ValueError when the header does not say which."""
    if _PCT_CHANGE.search(header):
        return "change"
    if _PCT_OF_NOM.search(header):
        return "of_nominal"
    raise ValueError(
        f"percent column {header!r} does not say change or percent of nominal; pass percent='change' or 'of_nominal'"
    )


def bias_curve_from_csv(
    text: str, c_nom_f: float | None = None, percent: str | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """DC bias in volts and C/Cnom from a vendor DC-bias export (percent change, percent of nominal, or farads)."""
    headers, data = parse_csv_table(text)
    iv = find_column(headers, "bias", "volt", "[v]", "(v)", "vdc")
    ic = find_column(headers, "cap", "%", "c/c")
    v = data[:, iv] * unit_scale(headers[iv], "V")
    y = data[:, ic]
    order = np.argsort(v)
    v, y = v[order], y[order]
    if "%" in headers[ic] or percent is not None:
        kind = percent or percent_kind(headers[ic])
        if kind not in ("change", "of_nominal"):
            raise ValueError(f"percent must be 'change' or 'of_nominal', not {kind!r}")
        ratio = 1.0 + y / 100.0 if kind == "change" else y / 100.0
        if np.any(ratio <= 0.0) or np.any(ratio > 1.5):
            raise ValueError(
                f"reading {headers[ic]!r} as percent {kind} gives C/Cnom from {ratio.min():.3g} to {ratio.max():.3g}; "
                "check the column semantics"
            )
    else:
        c = y * unit_scale(headers[ic], "F")
        if c_nom_f is None and v[0] != 0.0:
            raise ValueError(f"absolute curve starts at {v[0]:g} V, not 0 V; pass c_nom_f")
        ratio = c / (c_nom_f if c_nom_f is not None else c[0])
    return v, ratio


def mlcc_effective(
    c_nom_f: float,
    dielectric: str,
    tol_frac: float,
    v_bias_v: float = 0.0,
    curve_v: np.ndarray | None = None,
    curve_ratio: np.ndarray | None = None,
    t_min_c: float | None = None,
    t_max_c: float | None = None,
    aging_frac: float = 0.0,
    c_required_f: float | None = None,
    refs: tuple[str, ...] = (),
) -> Result:
    """Worst-case low and high capacitance of one MLCC at its DC bias over temperature."""
    t_lo_rated, t_hi_rated, dc_lo, dc_hi = dielectric_band(dielectric)
    class1 = dielectric.strip().upper() in ("C0G", "NP0", "COG", "NPO")
    t_lo = t_lo_rated if t_min_c is None else t_min_c
    t_hi = t_hi_rated if t_max_c is None else t_max_c
    if class1:
        d = _CLASS1_PPM["C0G"] * 1e-6 * max(abs(t_lo - 25.0), abs(t_hi - 25.0))
        dc_lo, dc_hi = -d, d
    notes: list[str] = []
    if curve_v is not None and curve_ratio is not None:
        ratio = float(np.interp(v_bias_v, curve_v, curve_ratio))
        if v_bias_v > float(np.max(curve_v)):
            notes.append(f"bias {v_bias_v:g} V beyond the curve ({np.max(curve_v):g} V)")
        bias_note = "from vendor DC-bias curve"
    else:
        ratio = 1.0
        bias_note = "no curve given"
        if not class1 and v_bias_v > 0:
            notes.append("class II part with no DC-bias curve; effective C is overstated")
    c_lo = c_nom_f * (1 - tol_frac) * ratio * (1 + dc_lo) * (1 - aging_frac)
    c_hi = c_nom_f * (1 + tol_frac) * ratio * (1 + dc_hi)
    out_of_range = t_lo < t_lo_rated or t_hi > t_hi_rated
    if out_of_range:
        verdict = Verdict.FAIL
        reason = f"operating {t_lo:g} to {t_hi:g} C exceeds {dielectric} rating {t_lo_rated:g} to {t_hi_rated:g} C"
    elif notes:
        verdict, reason = Verdict.UNKNOWN, "; ".join(notes)
    elif c_required_f is None:
        verdict, reason = Verdict.INFO, ""
    elif c_lo < c_required_f:
        verdict, reason = Verdict.FAIL, f"worst-case {c_lo * 1e9:.4g} nF below required {c_required_f * 1e9:.4g} nF"
    else:
        verdict, reason = Verdict.PASS, f"worst-case {c_lo * 1e9:.4g} nF meets {c_required_f * 1e9:.4g} nF"
    inputs = {
        "c_nom": Quantity(c_nom_f, "F"),
        "dc_temp_low": Quantity(dc_lo, "", f"{dielectric}, rated {t_lo_rated:g} to {t_hi_rated:g} C"),
        "dc_temp_high": Quantity(dc_hi, ""),
        "tol": Quantity(tol_frac, ""),
        "v_bias": Quantity(v_bias_v, "V"),
        "aging": Quantity(aging_frac, ""),
    }
    if c_required_f is not None:
        inputs["c_required"] = Quantity(c_required_f, "F")
    return Result(
        name="MLCC effective capacitance",
        formula="C_low = Cnom*(1 - tol)*k_bias(V)*(1 + dC_T,low)*(1 - aging); C_high = Cnom*(1 + tol)*k_bias(V)*(1 + dC_T,high)",
        inputs=inputs,
        outputs={
            "k_bias": Quantity(ratio, "", bias_note),
            "c_low": Quantity(c_lo, "F"),
            "c_high": Quantity(c_hi, "F"),
            "c_at_bias_nom": Quantity(c_nom_f * ratio, "F", "25 C, nominal part"),
        },
        verdict=verdict,
        reason=reason,
        refs=(EIA_REF,) + tuple(refs),
        assumptions=(
            "bias and temperature effects multiplied as independent factors",
            "class II band applied in full over the operating range (conservative inside the rated range)",
            "C0G: 30 ppm/C from 25 C",
        ),
    )
