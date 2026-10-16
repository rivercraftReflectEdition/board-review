"""Frequency screening and supply-coupled spur estimates."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from boardreview.calc.base import Key, Marker, Plot, Quantity, Result, Series, Verdict, fmt


MT002 = "ADI MT-002 Rev A, October 2008, p.5 (Nyquist folding)"
M1838 = "Maxim AN1838, March 2003, p.2 to 3 (mixer image and half-IF)"
MS2210 = "ADI MS-2210, February 2012, p.3 (supply ripple and PSRR)"


def _finite(value: float, name: str, positive: bool = False) -> float:
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return value


def _interval(value, name: str, positive: bool = False) -> tuple[float, float]:
    pair = (value, value) if isinstance(value, (int, float)) else tuple(value)
    if len(pair) != 2:
        raise ValueError(f"{name} needs a frequency or a pair of edges")
    lo, hi = (_finite(v, name, positive) for v in pair)
    if lo < 0 or hi < lo:
        raise ValueError(f"{name} needs nonnegative, ordered edges")
    return lo, hi


def _fold(f_hz: float, fs_hz: float) -> float:
    remainder = f_hz % fs_hz
    return min(remainder, fs_hz - remainder)


def _fold_interval(lo_hz: float, hi_hz: float, fs_hz: float) -> tuple[float, float]:
    a, b = _fold(lo_hz, fs_hz), _fold(hi_hz, fs_hz)
    low, high = min(a, b), max(a, b)
    if math.ceil(lo_hz / fs_hz) <= math.floor(hi_hz / fs_hz):
        low = 0.0
    if math.ceil(lo_hz / fs_hz - 0.5) <= math.floor(hi_hz / fs_hz - 0.5):
        high = fs_hz / 2
    return low, high


def alias(f_hz: float, fs_hz: float, context: str = "nominal") -> Result:
    """Fold a real tone, including negative frequency, into the first Nyquist zone."""
    f_hz = _finite(f_hz, "tone frequency")
    fs_hz = _finite(fs_hz, "sample rate", True)
    folded = _fold(f_hz, fs_hz)
    return Result(
        "tone alias", "f_alias = abs(f - fs round(f/fs))",
        {"f_hz": Quantity(f_hz, "Hz", label="Tone frequency"),
         "fs_hz": Quantity(fs_hz, "Hz", label="Sample rate")},
        {"f_alias_hz": Quantity(folded, "Hz", label="Aliased frequency")},
        refs=(MT002,), assumptions=("real sampling; no attenuation or amplitude estimate",),
        summary=f"A {fmt(f_hz, 'Hz')} tone sampled at {fmt(fs_hz, 'Hz')} folds to {fmt(folded, 'Hz')}. "
                "Compare that location with the wanted band and its spur requirement.",
        key=(Key("f_alias_hz"),),
    ).in_context(context)


def search(
    aggressors_hz: Mapping[str, float | tuple[float, float]] | Sequence[float],
    bands: Mapping[str, tuple[float, float]],
    n_max: int,
    lo_hz: Sequence[float] = (),
    m_max: int = 1,
    fs_hz: float | None = None,
    limit_dbfs: float | None = None,
    levels_dbfs: Mapping[str, float] | None = None,
    context: str = "nominal",
) -> Result:
    """Screen harmonics, LO products and their aliases; source levels bound every destination product."""
    for value, name in ((n_max, "aggressor order"), (m_max, "LO order")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    sources = dict(aggressors_hz) if isinstance(aggressors_hz, Mapping) else {
        f"source {i + 1}": f for i, f in enumerate(aggressors_hz)}
    if not sources or not bands or any(not str(k).strip() for k in (*sources, *bands)):
        raise ValueError("named aggressors and bands must be nonempty")
    sources = {str(k): _interval(v, str(k), True) for k, v in sources.items()}
    bands = {str(k): _interval(v, str(k)) for k, v in bands.items()}
    los = tuple(_finite(f, "LO frequency", True) for f in lo_hz)
    if fs_hz is not None:
        fs_hz = _finite(fs_hz, "sample rate", True)
    if limit_dbfs is not None:
        limit_dbfs = _finite(limit_dbfs, "spur limit")
    levels = {k: _finite(v, "destination level bound") for k, v in (levels_dbfs or {}).items()}
    if set(levels) - sources.keys():
        raise ValueError("level bounds must name an aggressor")
    inputs = {"n_max": Quantity(n_max, "count", label="Highest aggressor harmonic"),
              "m_max": Quantity(m_max, "count", label="Highest LO harmonic")}
    for i, (source, (low, high)) in enumerate(sources.items(), 1):
        label = source.replace("_", " ")
        inputs[f"source_{i}_low_hz"] = Quantity(low, "Hz", label=f"{label} lower frequency")
        inputs[f"source_{i}_high_hz"] = Quantity(high, "Hz", label=f"{label} upper frequency")
        if source in levels:
            inputs[f"source_{i}_level_dbfs"] = Quantity(levels[source], "dBFS", label=f"{label} destination level bound")
    for i, (band, (low, high)) in enumerate(bands.items(), 1):
        label = band.replace("_", " ")
        inputs[f"band_{i}_low_hz"] = Quantity(low, "Hz", label=f"{label} lower edge")
        inputs[f"band_{i}_high_hz"] = Quantity(high, "Hz", label=f"{label} upper edge")
    for i, f in enumerate(los, 1):
        inputs[f"lo_{i}_hz"] = Quantity(f, "Hz", label=f"LO {i} frequency")
    if fs_hz is not None:
        inputs["fs_hz"] = Quantity(fs_hz, "Hz", label="Sample rate")
    if limit_dbfs is not None:
        inputs["limit_dbfs"] = Quantity(limit_dbfs, "dBFS", label="Largest allowed spur")
    outputs = {}
    markers = []
    harmonic_edges = []
    hit_count = missing = excessive = 0
    for source, (low, high) in sources.items():
        for n in range(1, n_max + 1):
            harmonic_edges.extend((n * low, n * high))
            markers.append(Marker(f"{source} harmonic {n}: {fmt(n * low, 'Hz')} to {fmt(n * high, 'Hz')}",
                                  n * (low + high) / 2, 0))
            products = [(n * low, n * high, 0, 0, "+")]
            for j, lo in enumerate(los, 1):
                for m in range(1, m_max + 1):
                    a, b = m * lo - n * high, m * lo - n * low
                    products += [(m * lo + n * low, m * lo + n * high, m, j, "+"),
                                 (0.0 if a <= 0 <= b else min(abs(a), abs(b)),
                                  max(abs(a), abs(b)), m, j, "-")]
            for a, b, m, j, sign in products:
                kinds = [("harmonic" if m == 0 else "mix", a, b)]
                if fs_hz is not None:
                    kinds.append(("alias", *_fold_interval(a, b, fs_hz)))
                for kind, left, right in kinds:
                    for row, (band, (start, stop)) in enumerate(bands.items(), 1):
                        if right < start or left > stop:
                            continue
                        hit_count += 1
                        missing += source not in levels
                        excessive += limit_dbfs is not None and source in levels and levels[source] > limit_dbfs
                        prefix = f"hit_{hit_count}"
                        detail = f"source={source}; band={band}; kind={kind}; n={n}; m={m}; LO={j}; sign={sign}"
                        outputs[f"{prefix}_frequency_hz"] = Quantity(max(left, start), "Hz", detail,
                                                                        f"Hit {hit_count} first overlap frequency")
                        outputs[f"{prefix}_low_hz"] = Quantity(left, "Hz", detail, f"Hit {hit_count} product lower edge")
                        outputs[f"{prefix}_high_hz"] = Quantity(right, "Hz", detail, f"Hit {hit_count} product upper edge")
                        outputs[f"{prefix}_n"] = Quantity(n, "count", detail, f"Hit {hit_count} aggressor order")
                        outputs[f"{prefix}_m"] = Quantity(m, "count", detail, f"Hit {hit_count} LO order")
                        markers.append(Marker(f"{source} n={n} m={m} {kind} in {band}", max(left, start), row))
    outputs["hit_count"] = Quantity(hit_count, "count", label="Band overlaps")
    outputs["unbounded_count"] = Quantity(missing, "count", label="Overlaps without level bounds")
    verdict = Verdict.INFO if limit_dbfs is None or not hit_count else (
        Verdict.FAIL if excessive else Verdict.UNKNOWN if missing else Verdict.INFO)
    summary = f"The search found {fmt(hit_count, 'count')} band overlaps through aggressor order {fmt(n_max, 'count')}. "
    key = (Key("hit_count"),)
    if hit_count:
        summary += f"The first listed overlap starts at {fmt(outputs['hit_1_frequency_hz'].value, 'Hz')}. "
        key += (Key("hit_1_frequency_hz"),)
    if limit_dbfs is None:
        summary += "Supply a spur limit from the board requirement or converter datasheet to judge their levels."
    elif excessive:
        summary += f"At least one destination level bound exceeds {fmt(limit_dbfs, 'dBFS')}; measure or reduce that spur."
    elif missing:
        summary += f"Destination level bounds are missing for comparison with {fmt(limit_dbfs, 'dBFS')}; measure the overlaps."
    else:
        summary += f"No screened product exceeds the {fmt(limit_dbfs, 'dBFS')} limit on the supplied bounds; higher orders remain unchecked."
    x = tuple(sorted({*harmonic_edges, *(edge for pair in bands.values() for edge in pair)}))
    if len(x) == 1:
        x = (max(0.0, x[0] - 1), x[0] + 1)
    series = (Series("Aggressor harmonics", "", tuple(0.0 for _ in x)),) + tuple(
        Series(f"{band} band", "", tuple(float(row) if a <= f <= b else math.nan for f in x))
        for row, (band, (a, b)) in enumerate(bands.items(), 1))
    plot = Plot("Aggressor products over named bands", "Frequency", "Hz", x, series, markers=tuple(markers),
                caption="The bottom row marks every aggressor harmonic; each band is a horizontal segment. "
                        "Markers on bands show overlapping harmonics, LO products and aliases. "
                        "For a frequency range, the marker is its first overlap with that band, not its center.")
    return Result(
        "spur frequency search", "f = n fa; f_mix = abs(m fLO +/- n fa); f_alias = abs(f - fs round(f/fs))",
        inputs, outputs, verdict, summary, (MT002, M1838, "ADI MT-003 Rev A, October 2008, p.2"),
        assumptions=("band edges are inclusive; frequency ranges include every frequency between their edges",
                     "each source level is a conservative bound for every harmonic, mixed product and alias at the destination",
                     "frequency overlap alone does not predict coupling amplitude; different product paths are counted separately",
                     "no products between different aggressors; orders above the supplied limits are unchecked"),
        plots=(plot,), summary=summary, key=key,
    ).in_context(context)


def frequency_plan(
    rf_hz: float, f_if_hz: float, lo_side: str,
    min_rejection_db: float | None = None,
    image_rejection_db: float | None = None,
    half_if_rejection_db: float | None = None,
    context: str = "nominal",
) -> Result:
    """Locate the image and the half-IF response on the desired RF side of the LO."""
    rf_hz = _finite(rf_hz, "RF frequency", True)
    f_if_hz = _finite(f_if_hz, "IF frequency")
    if f_if_hz < 0 or lo_side not in ("high", "low"):
        raise ValueError("IF must be nonnegative and LO side must be 'high' or 'low'")
    sign = 1 if lo_side == "high" else -1
    lo = rf_hz + sign * f_if_hz
    if lo <= 0:
        raise ValueError("low-side LO must be positive")
    image, half = abs(rf_hz + sign * 2 * f_if_hz), lo - sign * f_if_hz / 2
    inputs = {"rf_hz": Quantity(rf_hz, "Hz", label="Wanted RF frequency"),
              "f_if_hz": Quantity(f_if_hz, "Hz", label="Intermediate frequency"),
              "lo_side": Quantity(sign, "", "+1 high; -1 low", "LO side")}
    for key, value, label in (("min_rejection_db", min_rejection_db, "Required rejection"),
                              ("image_rejection_db", image_rejection_db, "Image rejection"),
                              ("half_if_rejection_db", half_if_rejection_db, "Half-IF rejection")):
        if value is not None:
            value = _finite(value, label)
            if value < 0:
                raise ValueError(f"{label} must be nonnegative")
            inputs[key] = Quantity(value, "dB", label=label)
    rejects = (image_rejection_db, half_if_rejection_db)
    verdict = Verdict.INFO if min_rejection_db is None else (
        Verdict.FAIL if any(v is not None and v < min_rejection_db for v in rejects) else
        Verdict.UNKNOWN if any(v is None for v in rejects) else Verdict.PASS)
    summary = f"The {lo_side}-side LO is {fmt(lo, 'Hz')}; the image is {fmt(image, 'Hz')} and the half-IF response is {fmt(half, 'Hz')}. "
    if min_rejection_db is None:
        summary += "Supply the rejection limit from the receiver requirement and filter rejection at both frequencies."
    else:
        image_text = "not supplied" if image_rejection_db is None else fmt(image_rejection_db, "dB")
        half_text = "not supplied" if half_if_rejection_db is None else fmt(half_if_rejection_db, "dB")
        summary += f"Image rejection is {image_text} and half-IF rejection is {half_text} against {fmt(min_rejection_db, 'dB')} required; "
        summary += ("a supplied rejection is below it." if verdict is Verdict.FAIL else
                    "filter data at one or both frequencies are missing." if verdict is Verdict.UNKNOWN else
                    "both supplied rejections are at least this value.")
    return Result(
        "mixer frequency plan", "fLO = fRF +/- fIF; image = abs(fRF +/- 2 fIF); half_IF = fLO -/+ fIF/2",
        inputs, {"lo_hz": Quantity(lo, "Hz", label="Local oscillator frequency"),
                 "image_hz": Quantity(image, "Hz", label="Image frequency"),
                 "half_if_hz": Quantity(half, "Hz", label="Half-IF response frequency")},
        verdict, summary, (M1838, "Keysight AN150, 5952-0292, August 4 2014, p.11 to 12"),
        assumptions=("one tuning setting; repeat across the tuning range and every switched filter state",
                     "half-IF is the 2 RF by 2 LO response on the desired RF side; other mixer products need search",
                     "supplied rejection includes all filtering and mixer response needed by the requirement"),
        summary=summary, key=(Key("lo_hz"), Key("image_hz"), Key("half_if_hz")),
    ).in_context(context)


def supply_spur(
    ripple_v_pp: float, full_scale_v_pp: float, psrr_db: float,
    limit_dbfs: float | None = None, context: str = "nominal",
) -> Result:
    """Estimate a supply tone in dBFS using signed output-to-supply voltage transfer in dB."""
    ripple_v_pp = _finite(ripple_v_pp, "ripple amplitude", True)
    full_scale_v_pp = _finite(full_scale_v_pp, "full scale", True)
    psrr_db = _finite(psrr_db, "signed supply transfer")
    spur = 20 * (math.log10(ripple_v_pp) - math.log10(full_scale_v_pp)) + psrr_db
    inputs = {"ripple_v_pp": Quantity(ripple_v_pp, "V", "peak to peak", "Supply ripple"),
              "full_scale_v_pp": Quantity(full_scale_v_pp, "V", "peak to peak", "Converter full scale"),
              "psrr_db": Quantity(psrr_db, "dB", "signed output/supply voltage transfer; negate positive rejection", "Supply transfer")}
    if limit_dbfs is not None:
        limit_dbfs = _finite(limit_dbfs, "spur limit")
        inputs["limit_dbfs"] = Quantity(limit_dbfs, "dBFS", label="Largest allowed spur")
    verdict = Verdict.INFO if limit_dbfs is None else Verdict.PASS if spur <= limit_dbfs else Verdict.FAIL
    summary = f"Supply ripple of {fmt(ripple_v_pp, 'V')} peak to peak predicts a {fmt(spur, 'dBFS')} spur with {fmt(psrr_db, 'dB')} supply transfer. "
    summary += ("Supply the spur limit from the board requirement or converter datasheet to judge it." if limit_dbfs is None else
                f"That is {'at or below' if verdict is Verdict.PASS else 'above'} the {fmt(limit_dbfs, 'dBFS')} limit; verify the transfer at the ripple frequency.")
    return Result(
        "supply ripple spur", "spur_dBFS = 20 log10(ripple_Vpp / full_scale_Vpp) + signed_PSRR_dB",
        inputs, {"spur_dbfs": Quantity(spur, "dBFS", label="Predicted supply spur")}, verdict, summary, (MS2210,),
        assumptions=("sinusoidal ripple and full scale use the same peak-to-peak convention",
                     "PSRR is signed voltage transfer at the ripple frequency, rail, bias and operating mode",
                     "direct supply feedthrough only; oscillator FM needs pushing or PSMR instead"),
        summary=summary, key=(Key("spur_dbfs", "a stated limit" if limit_dbfs is None else f"{fmt(limit_dbfs, 'dBFS')} or less"),),
    ).in_context(context)
