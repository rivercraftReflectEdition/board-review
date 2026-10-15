"""Waveform metrics from a run: steady state, ripple, tones, switching frequency, ring-down, loop margins, impedance."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import signal

from boardreview.calc.base import Key, Marker, Plot, Quantity, Result, Verdict, fmt, plot_from_arrays, si_text

MAX_POINTS = 1 << 22
_trapz = getattr(np, "trapezoid", None) or np.trapz


def window(t: np.ndarray, y: np.ndarray, t_start_s: float | None = None,
           t_end_s: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Samples with t_start_s <= t <= t_end_s."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y)
    m = np.ones(len(t), dtype=bool)
    if t_start_s is not None:
        m &= t >= t_start_s
    if t_end_s is not None:
        m &= t <= t_end_s
    if m.sum() < 2:
        raise ValueError(f"fewer than 2 samples between {t_start_s} and {t_end_s} s")
    return t[m], y[m]


def uniform(t: np.ndarray, y: np.ndarray, dt_s: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Resample a waveform with variable time step onto a uniform grid (linear interpolation)."""
    t, keep = np.unique(np.asarray(t, dtype=float), return_index=True)
    y = np.asarray(y)[keep]
    span = t[-1] - t[0]
    if dt_s is None:
        dt_s = float(np.median(np.diff(t)))
    n = int(min(MAX_POINTS, max(2, math.floor(span / dt_s) + 1)))
    tu = t[0] + np.arange(n) * (span / (n - 1))
    return tu, np.interp(tu, t, y)


def mean_value(t: np.ndarray, y: np.ndarray, t_start_s: float | None = None, t_end_s: float | None = None) -> float:
    """Time-weighted mean, correct for the variable time step of a SPICE transient."""
    t, y = window(t, y, t_start_s, t_end_s)
    return float(_trapz(y, t) / (t[-1] - t[0]))


def ripple_pkpk(t: np.ndarray, y: np.ndarray, t_start_s: float | None = None, t_end_s: float | None = None) -> float:
    """Peak-to-peak over the window."""
    _, y = window(t, y, t_start_s, t_end_s)
    return float(np.max(y) - np.min(y))


@dataclass(frozen=True)
class SteadyState:
    mean: float
    pkpk: float
    drift: float
    settled: bool


def steady_state(t: np.ndarray, y: np.ndarray, t_start_s: float, t_end_s: float | None = None,
                 drift_tol: float | None = None) -> SteadyState:
    """Mean and pk-pk over the window, and whether the two halves agree (drift below tolerance)."""
    t, y = window(t, y, t_start_s, t_end_s)
    mid = 0.5 * (t[0] + t[-1])
    drift = mean_value(t, y, mid, None) - mean_value(t, y, None, mid)
    pkpk = float(np.max(y) - np.min(y))
    tol = drift_tol if drift_tol is not None else max(0.1 * pkpk, 1e-3 * abs(mean_value(t, y)))
    return SteadyState(mean_value(t, y), pkpk, float(drift), abs(drift) <= tol)


@dataclass(frozen=True)
class Tone:
    f_hz: float
    amplitude: float
    bin_hz: float


def dominant_frequency(t: np.ndarray, y: np.ndarray, t_start_s: float | None = None, t_end_s: float | None = None,
                       f_min_hz: float | None = None, f_max_hz: float | None = None,
                       window_name: str = "hann", detrend: str = "linear", dt_s: float | None = None) -> Tone:
    """Strongest spectral line: uniform resample, detrend, window, FFT, parabolic peak interpolation."""
    t, y = window(t, y, t_start_s, t_end_s)
    tu, yu = uniform(t, y, dt_s)
    dt = tu[1] - tu[0]
    yu = signal.detrend(yu, type=detrend)
    w = signal.get_window(window_name, len(yu))
    spec = np.abs(np.fft.rfft(yu * w))
    f = np.fft.rfftfreq(len(yu), dt)
    band = f > 0
    if f_min_hz is not None:
        band &= f >= f_min_hz
    if f_max_hz is not None:
        band &= f <= f_max_hz
    idx = np.nonzero(band)[0]
    if len(idx) == 0:
        raise ValueError("no FFT bins in the requested band; lengthen the window")
    k = int(idx[np.argmax(spec[idx])])
    delta, peak = 0.0, spec[k]
    if 0 < k < len(spec) - 1 and spec[k - 1] > 0 and spec[k + 1] > 0:
        a, b, c = np.log(spec[k - 1]), np.log(spec[k]), np.log(spec[k + 1])
        den = a - 2 * b + c
        if den < 0:
            delta = 0.5 * (a - c) / den
            peak = math.exp(b - 0.25 * (a - c) * delta)
    df = f[1] - f[0]
    return Tone(f_hz=float((k + delta) * df), amplitude=float(2 * peak / np.sum(w)), bin_hz=float(df))


def crossings(t: np.ndarray, y: np.ndarray, level: float, hysteresis: float = 0.0, rising: bool = True) -> np.ndarray:
    """Times where y crosses level (linear interpolation), with a Schmitt band so noise does not double count."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    state = np.full(len(y), np.nan)
    state[y > level + hysteresis / 2] = 1.0
    state[y < level - hysteresis / 2] = 0.0
    filled = _ffill(state)
    target = 1.0 if rising else 0.0
    change = np.nonzero((filled[1:] == target) & (filled[:-1] == 1.0 - target))[0] + 1
    side = (y <= level) if rising else (y >= level)
    before = np.nonzero(side)[0]
    out = []
    for i in change:
        pos = np.searchsorted(before, i) - 1
        if pos < 0:
            continue
        j = before[pos]
        if j + 1 >= len(y) or y[j + 1] == y[j]:
            out.append(t[j])
            continue
        out.append(t[j] + (level - y[j]) * (t[j + 1] - t[j]) / (y[j + 1] - y[j]))
    return np.asarray(out)


def _ffill(a: np.ndarray) -> np.ndarray:
    idx = np.where(~np.isnan(a), np.arange(len(a)), 0)
    np.maximum.accumulate(idx, out=idx)
    out = a[idx]
    return out


@dataclass(frozen=True)
class Switching:
    f_hz: float
    f_median_hz: float
    n_edges: int
    period_cv: float
    duty: float
    level: float

    @property
    def regular(self) -> bool:
        """False when periods vary more than 10 percent: pulse skipping, burst, or a limit cycle."""
        return self.period_cv < 0.10


def switching_frequency(t: np.ndarray, y: np.ndarray, t_start_s: float | None = None, t_end_s: float | None = None,
                        level: float | None = None, hysteresis_frac: float = 0.1) -> Switching:
    """Switching frequency from rising-edge crossings of a switch node (or a gate drive)."""
    t, y = window(t, y, t_start_s, t_end_s)
    lo, hi = np.percentile(y, [5, 95])
    lvl = 0.5 * (lo + hi) if level is None else level
    edges = crossings(t, y, lvl, hysteresis_frac * (hi - lo), rising=True)
    if len(edges) < 3:
        raise ValueError(f"only {len(edges)} rising edges through {lvl:.3g}; is this the switch node?")
    periods = np.diff(edges)
    tw, yw = window(t, y, edges[0], edges[-1])
    duty = float(_trapz((yw > lvl).astype(float), tw) / (tw[-1] - tw[0]))
    return Switching(
        f_hz=float((len(edges) - 1) / (edges[-1] - edges[0])),
        f_median_hz=float(1.0 / np.median(periods)),
        n_edges=int(len(edges)),
        period_cv=float(np.std(periods) / np.mean(periods)),
        duty=duty,
        level=float(lvl),
    )


def edge_timing_uncertainty(t: np.ndarray, y: np.ndarray, t_start_s: float | None = None,
                            max_edges: int = 400) -> tuple[float, float]:
    """Median edge timing uncertainty and the switching period, in seconds (0 when edges span 2+ samples)."""
    t, y = window(t, y, t_start_s, None)
    lo, hi = np.percentile(y, [5, 95])
    lvl, span = 0.5 * (lo + hi), hi - lo
    inside = (y > lo + 0.1 * span) & (y < lo + 0.9 * span)
    worst = []
    for rising in (True, False):
        edges = crossings(t, y, lvl, 0.1 * span, rising=rising)[-max_edges:]
        unc = []
        for te in edges:
            i = int(np.searchsorted(t, te))
            if i <= 0 or i >= len(t):
                continue
            a, b = i - 1, i
            while a >= 0 and inside[a]:
                a -= 1
            while b < len(t) and inside[b]:
                b += 1
            unc.append(0.0 if b - a - 1 >= 2 else t[i] - t[i - 1])
        if unc:
            worst.append(float(np.median(unc)))
    edges = crossings(t, y, lvl, 0.1 * span, rising=True)
    period = float(np.median(np.diff(edges))) if len(edges) > 2 else float("nan")
    return (max(worst) if worst else float("nan")), period


def box_average(t: np.ndarray, y: np.ndarray, period_s: float, points_per_period: int = 64,
                dt_s: float | None = None, max_points_per_period: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """Centered moving average over exactly one period (removes the switching frequency and its harmonics)."""
    t = np.asarray(t, dtype=float)
    native = float(np.median(np.diff(t))) if dt_s is None else dt_s
    m = max(points_per_period, min(max_points_per_period, int(math.ceil(period_s / native))))
    dt = period_s / m
    tu, yu = uniform(t, y, dt)
    dt_actual = tu[1] - tu[0]
    m = max(1, int(round(period_s / dt_actual)))
    c = np.concatenate([[0.0], np.cumsum(yu)])
    avg = (c[m:] - c[:-m]) / m
    tc = tu[: len(avg)] + 0.5 * (m - 1) * dt_actual
    return tc, avg


def lockin(t: np.ndarray, y: np.ndarray, f_hz: float, t_start_s: float | None = None,
           t_end_s: float | None = None, points_per_period: int = 256) -> complex:
    """Complex amplitude at f_hz (cosine reference) over the last whole periods; offset and linear drift fitted out."""
    t, y = window(t, y, t_start_s, t_end_s)
    n = int(math.floor((t[-1] - t[0]) * f_hz + 1e-9))
    if n < 1:
        raise ValueError(f"window shorter than one period at {f_hz:.4g} Hz")
    t0 = t[-1] - n / f_hz
    count = n * points_per_period
    tu = t0 + np.arange(count) * (1.0 / (f_hz * points_per_period))
    yu = np.interp(tu, t, y)
    w = 2 * np.pi * f_hz * tu
    x = (tu - tu.mean()) / (tu[-1] - tu[0])
    basis = np.column_stack([np.ones(count), x, np.cos(w), np.sin(w)])
    coef, *_ = np.linalg.lstsq(basis, yu, rcond=None)
    return complex(coef[2], -coef[3])


@dataclass(frozen=True)
class StepResponse:
    t_step_s: float
    initial: float
    final: float
    peak_dev: float
    t_peak_s: float
    overshoot_pct: float | None
    peaks: tuple[tuple[float, float], ...]
    decay_ratio: float | None
    ring_hz: float | None
    zeta: float | None
    pm_deg_est: float | None
    settle_s: float | None
    band: float


def zeta_from_decay_ratio(r: float) -> float:
    """Damping ratio from the ratio of successive same-sign peaks one ring period apart."""
    if not 0 < r < 1:
        raise ValueError("decay ratio must be between 0 and 1")
    ln = math.log(1.0 / r)
    return ln / math.sqrt(4 * math.pi ** 2 + ln ** 2)


PM_RULE_REF = ("Franklin, Powell, Emami-Naeini, Feedback Control of Dynamic Systems, section 6.4: zeta ~ PM/100 for "
               "the standard loop T = wn^2 / (s (s + 2 zeta wn)), PM below about 60 deg")


def pm_from_zeta(zeta: float) -> float:
    """Rule of thumb PM ~ 100 zeta deg; holds only for the standard second-order loop (PM_RULE_REF)."""
    return 100.0 * zeta


def step_response(t: np.ndarray, y: np.ndarray, t_step_s: float, t_end_s: float | None = None,
                  initial: float | None = None, final: float | None = None,
                  smooth_period_s: float | None = None, band: float | None = None,
                  min_peak_frac: float = 0.05, skip_first: bool = False) -> StepResponse:
    """Overshoot, ring frequency, decay ratio, zeta and the PM estimate after a step at t_step_s."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    if smooth_period_s:
        t, y = box_average(t, y, smooth_period_s)
    t_end = t[-1] if t_end_s is None else t_end_s
    if initial is None:
        initial = mean_value(t, y, t[0] + 0.5 * (t_step_s - t[0]), t_step_s)
    if final is None:
        final = mean_value(t, y, t_end - 0.2 * (t_end - t_step_s), t_end)
    tw, yw = window(t, y, t_step_s, t_end)
    e = yw - final
    k_peak = int(np.argmax(np.abs(e)))
    step = final - initial
    peak_abs = abs(e[k_peak])
    peaks = _alternating_peaks(tw, e, min_peak_frac * peak_abs)
    use = peaks[1:] if skip_first else peaks
    decay = ring = zeta = pm = None
    if len(use) >= 3 and use[0][1] != 0:
        r = use[2][1] / use[0][1]
        if r > 0:
            decay = float(r)
            ring = float(1.0 / (use[2][0] - use[0][0]))
        if 0 < r < 1:
            zeta = zeta_from_decay_ratio(r)
            pm = pm_from_zeta(zeta)
    overshoot = None
    if abs(step) > 1e-12 and abs(step) >= 0.2 * peak_abs:
        overshoot = float(max(0.0, np.max(np.sign(step) * e)) / abs(step) * 100.0)
    band_v = band if band is not None else (0.02 * abs(step) if overshoot is not None else 0.1 * peak_abs)
    outside = np.nonzero(np.abs(e) > band_v)[0]
    settle = None
    if len(outside) == 0:
        settle = 0.0
    elif outside[-1] < len(e) - 1 and t_end - tw[outside[-1] + 1] >= 0.2 * (t_end - t_step_s):
        settle = float(tw[outside[-1] + 1] - t_step_s)
    return StepResponse(
        t_step_s=float(t_step_s), initial=float(initial), final=float(final), peak_dev=float(e[k_peak]),
        t_peak_s=float(tw[k_peak]), overshoot_pct=overshoot, peaks=tuple(peaks), decay_ratio=decay,
        ring_hz=ring, zeta=zeta, pm_deg_est=pm, settle_s=settle, band=float(band_v),
    )


def _alternating_peaks(t: np.ndarray, e: np.ndarray, min_height: float) -> list[tuple[float, float]]:
    hi, _ = signal.find_peaks(e, height=min_height, prominence=min_height)
    lo, _ = signal.find_peaks(-e, height=min_height, prominence=min_height)
    cand = sorted([(int(i), float(e[i])) for i in hi] + [(int(i), float(e[i])) for i in lo])
    out: list[tuple[int, float]] = []
    for i, v in cand:
        if out and np.sign(out[-1][1]) == np.sign(v):
            if abs(v) > abs(out[-1][1]):
                out[-1] = (i, v)
            continue
        out.append((i, v))
    return [(float(t[i]), v) for i, v in out]


def ring_result(sr: StepResponse, zeta_marginal: float = 0.42, zeta_fail: float = 0.27) -> Result:
    """Ring-down math; a light ring fails, a damped ring passes nothing, and the PM estimate is informational."""
    formula = "r = peak_3 / peak_1; zeta = ln(1/r) / sqrt(4 pi^2 + ln(1/r)^2)"
    p1 = sr.peaks[0][1] if sr.peaks else float("nan")
    inputs = {
        "peak_1": Quantity(p1, "V", "first deviation peak", "First deviation peak"),
        "peak_3": Quantity(sr.peaks[2][1] if len(sr.peaks) > 2 else float("nan"), "V", "next same-sign peak",
                           "Next same-sign peak"),
    }
    if sr.decay_ratio is None:
        first = f"The first deviation peak is {fmt(p1, 'V')}, but there is" if math.isfinite(p1) else "There is"
        return Result(name="ring-down after step", formula=formula, inputs=inputs, outputs={}, verdict=Verdict.INFO,
                      reason="no second same-sign peak above the noise: damped, or the window is too short; this "
                             "does not show margin, use the loop gain",
                      summary=f"{first} no second same-sign peak above the noise, so there is no ring to measure. "
                              "The output may be well damped or the window may end early; read the margins from the "
                              "loop gain.",
                      key=(Key("peak_1"),) if math.isfinite(p1) else ())
    outputs = {"r": Quantity(sr.decay_ratio, "", label="Decay ratio"),
               "f_ring": Quantity(sr.ring_hz, "Hz", label="Ring frequency")}
    r_s, f_s = fmt(sr.decay_ratio, ""), fmt(sr.ring_hz, "Hz")
    if sr.zeta is None:
        return Result(name="ring-down after step", formula=formula, inputs=inputs, outputs=outputs,
                      verdict=Verdict.FAIL, reason=f"the ring does not decay (r = {sr.decay_ratio:.2f}): sustained or "
                                                   "growing oscillation",
                      summary=f"The ring at {f_s} does not decay: each peak is {r_s} times the one a period before. "
                              "The output oscillates.",
                      key=(Key("r", "below 1"), Key("f_ring")))
    inputs["zeta_marginal"] = Quantity(zeta_marginal, "", "default 0.42, the standard loop's zeta at PM 45 deg",
                                       "Damping ratio wanted")
    inputs["zeta_fail"] = Quantity(zeta_fail, "", "default 0.27, the standard loop's zeta at PM 30 deg",
                                   "Damping ratio fail limit")
    outputs["zeta"] = Quantity(sr.zeta, "", "closed-loop damping of the ring", "Damping ratio")
    outputs["PM_est"] = Quantity(sr.pm_deg_est, "deg", "informational: standard second-order loop only",
                                 "Phase margin estimate")
    z_s = fmt(sr.zeta, "")
    first = f"The output rings at {f_s} with a damping ratio of {z_s}."
    if sr.zeta < zeta_fail:
        verdict, reason = Verdict.FAIL, f"lightly damped ring, zeta {sr.zeta:.2f} below {zeta_fail:.2f}"
        then = (f"That is below the {fmt(zeta_fail, '')} fail limit, so it rings for many cycles after each step "
                "and the loop is close to oscillating.")
    elif sr.zeta < zeta_marginal:
        verdict, reason = Verdict.MARGINAL, f"ring damping zeta {sr.zeta:.2f} below {zeta_marginal:.2f}"
        then = f"We want at least {fmt(zeta_marginal, '')}, so it rings for a few cycles after each step."
    else:
        verdict = Verdict.INFO
        reason = f"ring damping zeta {sr.zeta:.2f}; a damped ring does not show margin, use the loop gain"
        then = "A well damped ring does not prove margin; read the margins from the loop gain."
    return Result(
        name="ring-down after step",
        formula=formula + "; PM_est ~ 100 zeta deg",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(PM_RULE_REF,),
        assumptions=("the ring is one dominant second-order pair",
                     "PM_est holds only for T = wn^2 / (s (s + 2 zeta wn)); a loop zero or a third pole breaks it: "
                     "T = (0.9 - 100 s) / (s^2 + 101 s + 0.1) rings at zeta 0.5 with PM 9 deg"),
        summary=f"{first} {then}",
        key=(Key("zeta", f"{fmt(zeta_marginal, '')} or more"), Key("f_ring")),
    )


def settling_result(sr: StepResponse, settle_max_s: float | None = None) -> Result:
    """Settling time after a step against an optional limit; still outside the band at the window end fails."""
    band_s = fmt(sr.band, "V")
    lim_s = fmt(settle_max_s, "s") if settle_max_s is not None else ""
    key: tuple[Key, ...] = (Key("t_settle", f"{lim_s} or less" if lim_s else ""),)
    if sr.settle_s is None:
        verdict = Verdict.FAIL
        reason = "not inside the band for the last 20 percent of the window: the ring has not decayed (lengthen " \
                 "the window if it is still decaying)"
        summary = (f"The output is still outside {band_s} of its final value at the end of the window, so the ring "
                   "has not decayed. Lengthen the window if it is still decaying.")
        key = ()
    else:
        t_s = fmt(sr.settle_s, "s")
        said = f"The output settles inside {band_s} of its final value {t_s} after the step."
        if settle_max_s is None:
            verdict, reason = Verdict.INFO, f"settles in {sr.settle_s * 1e6:.1f} us; no limit given"
            summary = f"{said} No settling limit was given."
        else:
            verdict = Verdict.PASS if sr.settle_s <= settle_max_s else Verdict.FAIL
            reason = f"{sr.settle_s * 1e6:.1f} us against {settle_max_s * 1e6:.1f} us"
            summary = (f"{said} That is within the {lim_s} limit." if verdict is Verdict.PASS else
                       f"{said} The limit is {lim_s}, so loads see the rail off its value for longer than budgeted.")
    return Result(
        name="settling after step",
        formula="t_settle = last time |V - V_final| > band, after the step",
        inputs={"band": Quantity(sr.band, "V", label="Settling band"),
                "t_settle_max": Quantity(settle_max_s if settle_max_s is not None else float("nan"), "s",
                                         label="Settling time limit")},
        outputs={"t_settle": Quantity(sr.settle_s if sr.settle_s is not None else float("nan"), "s",
                                      label="Settling time")},
        verdict=verdict,
        reason=reason,
        summary=summary,
        key=key,
    )


def deviation_result(sr: StepResponse, dev_max_v: float | None = None) -> Result:
    """Peak deviation from the final value after a step against an optional limit."""
    peak = abs(sr.peak_dev)
    said = f"The peak deviation after the step is {fmt(sr.peak_dev, 'V')}, {fmt(sr.t_peak_s - sr.t_step_s, 's')} " \
           "after the edge."
    lim_s = fmt(dev_max_v, "V") if dev_max_v is not None else ""
    if dev_max_v is None:
        verdict, reason = Verdict.INFO, f"{peak * 1e3:.1f} mV; no limit given"
        summary = f"{said} No limit was given."
    else:
        verdict = Verdict.PASS if peak <= dev_max_v else Verdict.FAIL
        reason = f"{peak * 1e3:.1f} mV against {dev_max_v * 1e3:.1f} mV"
        summary = (f"{said} That is within the {lim_s} limit." if verdict is Verdict.PASS else
                   f"{said} It goes past the {lim_s} limit, so loads on this rail see a bigger dip than budgeted.")
    return Result(
        name="peak deviation after step",
        formula="dV = max |V - V_final| after the step",
        inputs={"dV_max": Quantity(dev_max_v if dev_max_v is not None else float("nan"), "V",
                                   label="Deviation limit")},
        outputs={"dV": Quantity(sr.peak_dev, "V", label="Peak deviation"),
                 "t_peak": Quantity(sr.t_peak_s, "s", label="Time of the peak")},
        verdict=verdict,
        reason=reason,
        summary=summary,
        key=(Key("dV", f"within {lim_s}" if lim_s else ""),),
    )


@dataclass(frozen=True)
class LoopMargins:
    crossover_hz: float | None
    phase_margin_deg: float | None
    phase_crossover_hz: float | None
    gain_margin_db: float | None
    crossovers_hz: tuple[float, ...]
    phase_margins_deg: tuple[float, ...]


def loop_margins(f_hz: np.ndarray, t_loop: np.ndarray) -> LoopMargins:
    """Crossover, PM and GM of a loop gain T (closed loop 1/(1+T)); log-frequency interpolation between points."""
    f = np.asarray(f_hz, dtype=float)
    order = np.argsort(f)
    f = f[order]
    tl = np.asarray(t_loop, dtype=complex)[order]
    lf = np.log(f)
    mag = 20 * np.log10(np.abs(tl))
    ph = np.degrees(np.unwrap(np.angle(tl)))
    ph -= 360.0 * np.round(ph[0] / 360.0)
    xs, pms = [], []
    for i in np.nonzero(np.sign(mag[:-1]) != np.sign(mag[1:]))[0]:
        a = mag[i] / (mag[i] - mag[i + 1])
        lfc = lf[i] + a * (lf[i + 1] - lf[i])
        xs.append(float(math.exp(lfc)))
        pms.append(float(_wrap180(180.0 + ph[i] + a * (ph[i + 1] - ph[i]))))
    fc = xs[0] if xs else None
    pm = pms[0] if pms else None
    fp = gm = None
    shifted = ph + 180.0
    for i in np.nonzero(np.sign(shifted[:-1]) != np.sign(shifted[1:]))[0]:
        a = shifted[i] / (shifted[i] - shifted[i + 1])
        f180 = math.exp(lf[i] + a * (lf[i + 1] - lf[i]))
        if fc is None or f180 >= fc * 0.999:
            fp = float(f180)
            gm = float(-(mag[i] + a * (mag[i + 1] - mag[i])))
            break
    return LoopMargins(fc, pm, fp, gm, tuple(xs), tuple(pms))


def _wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def loop_gain_plot(f_hz: np.ndarray, t_loop: np.ndarray, m: LoopMargins | None = None,
                   title: str = "Measured loop gain") -> Plot:
    """Gain and phase of measured T with the crossover, PM, phase crossover and GM marked."""
    f = np.asarray(f_hz, dtype=float)
    order = np.argsort(f)
    f = f[order]
    tl = np.asarray(t_loop, dtype=complex)[order]
    mag = 20 * np.log10(np.abs(tl))
    ph = np.degrees(np.unwrap(np.angle(tl)))
    ph -= 360.0 * np.round(ph[0] / 360.0)
    lf = np.log(f)
    marks = [Marker("-180°", y=-180.0, unit="deg")]
    caption = "The measured gain never crosses 0 dB in this sweep."
    if m is not None and m.crossover_hz is not None:
        fc = m.crossover_hz
        marks += [Marker(f"fc {si_text(fc, 'Hz')}", x=fc),
                  Marker(f"PM {m.phase_margin_deg:.0f}°", x=fc, y=float(np.interp(math.log(fc), lf, ph)),
                         unit="deg")]
        side = (f"{fmt(m.phase_margin_deg, 'deg')} above" if m.phase_margin_deg >= 0
                else f"{fmt(-m.phase_margin_deg, 'deg')} below")
        caption = f"Read the phase where the gain crosses 0 dB (dashed line, {fmt(fc, 'Hz')}): it is {side} -180°."
    if m is not None and m.phase_crossover_hz is not None and m.gain_margin_db is not None:
        marks += [Marker(f"f180 {si_text(m.phase_crossover_hz, 'Hz')}", x=m.phase_crossover_hz),
                  Marker(f"GM {m.gain_margin_db:.1f} dB", x=m.phase_crossover_hz, y=-m.gain_margin_db, unit="dB")]
    return plot_from_arrays(title, "Frequency", "Hz", f, [("Gain", "dB", mag), ("Phase", "deg", ph)], x_log=True,
                            markers=marks, caption=caption)


def step_plot(t: np.ndarray, y: np.ndarray, sr: StepResponse, t_end_s: float | None = None,
              smooth_period_s: float | None = None, title: str = "Load step") -> Plot:
    """Output around one step: raw and one-period average, with the step, the peak and the settling band marked."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    t_end = float(t[-1]) if t_end_s is None else t_end_s
    t0 = max(float(t[0]), sr.t_step_s - 0.25 * (t_end - sr.t_step_s))
    tw, yw = window(t, y, t0, t_end)
    marks = [Marker("step", x=sr.t_step_s),
             Marker(f"peak {sr.peak_dev * 1e3:+.1f} mV", x=sr.t_peak_s, y=sr.final + sr.peak_dev, unit="V"),
             Marker(f"band +{sr.band * 1e3:.3g} mV", y=sr.final + sr.band, unit="V"),
             Marker(f"band -{sr.band * 1e3:.3g} mV", y=sr.final - sr.band, unit="V")]
    if sr.settle_s:
        marks.append(Marker(f"settled {si_text(sr.settle_s, 's')}", x=sr.t_step_s + sr.settle_s))
    caption = (f"Read how far the output moves after the step ({fmt(sr.peak_dev, 'V')} at the peak) and when it "
               "stays inside the dashed band.")
    if smooth_period_s:
        ta, ya = box_average(t, y, smooth_period_s)
        ta, ya = window(ta, ya, t0, t_end)
        raw = np.interp(ta, tw, yw)
        series = [("one-period average", "V", ya), ("raw", "V", raw)]
        return plot_from_arrays(title, "Time", "s", ta, series, markers=marks, caption=caption)
    return plot_from_arrays(title, "Time", "s", tw, [("output", "V", yw)], markers=marks, caption=caption)


def margins_result(m: LoopMargins, pm_min_deg: float = 45.0, gm_min_db: float = 10.0, source: str = "",
                   f_hz: np.ndarray | None = None, t_loop: np.ndarray | None = None) -> Result:
    """Loop margins as a Result with a verdict against the PM and GM targets; T, when given, adds the Bode plot."""
    inputs = {"pm_min": Quantity(pm_min_deg, "deg", label="Phase margin wanted"),
              "gm_min": Quantity(gm_min_db, "dB", label="Gain margin wanted")}
    outputs = {}
    if m.crossover_hz is not None:
        outputs["f_c"] = Quantity(m.crossover_hz, "Hz", "|T| = 0 dB", "Crossover frequency")
        outputs["PM"] = Quantity(m.phase_margin_deg, "deg", "180 + angle(T) at f_c", "Phase margin")
    if m.gain_margin_db is not None:
        outputs["f_180"] = Quantity(m.phase_crossover_hz, "Hz", "angle(T) = -180 deg", "Phase crossover frequency")
        outputs["GM"] = Quantity(m.gain_margin_db, "dB", "-|T| at f_180", "Gain margin")
    pm_min_s, gm_min_s = fmt(pm_min_deg, "deg"), fmt(gm_min_db, "dB")
    key: list[Key] = []
    if m.crossover_hz is None:
        verdict, reason = Verdict.UNKNOWN, "no 0 dB crossing inside the sweep; widen it"
        text = ["The measured loop gain never crosses 0 dB inside the sweep, so there is no crossover to read the "
                "margins at. Widen the sweep."]
    else:
        worst_pm = min(m.phase_margins_deg)
        gm_ok = m.gain_margin_db is None or m.gain_margin_db >= gm_min_db
        if worst_pm >= pm_min_deg and gm_ok:
            verdict = Verdict.PASS
        elif worst_pm > 0 and (m.gain_margin_db is None or m.gain_margin_db > 0):
            verdict = Verdict.MARGINAL
        else:
            verdict = Verdict.FAIL
        reason = f"PM {worst_pm:.0f} deg (target {pm_min_deg:.0f})"
        reason += f", GM {m.gain_margin_db:.1f} dB (target {gm_min_db:.0f})" if m.gain_margin_db is not None else \
            ", GM not measured (no -180 deg crossing in the sweep)"
        if len(m.crossovers_hz) > 1:
            reason += f", {len(m.crossovers_hz)} crossovers"
        text = [f"The measured loop crosses over at {fmt(m.crossover_hz, 'Hz')} with "
                f"{fmt(m.phase_margin_deg, 'deg')} of phase margin."]
        pm_key = "PM"
        if len(m.crossovers_hz) > 1:
            outputs["PM_worst"] = Quantity(worst_pm, "deg", f"lowest of {len(m.crossovers_hz)} crossings",
                                           "Worst phase margin")
            text.append(f"It crosses 0 dB {len(m.crossovers_hz)} times; the worst crossing has "
                        f"{fmt(worst_pm, 'deg')}.")
            pm_key = "PM_worst"
        key.append(Key(pm_key, f"{pm_min_s} or more"))
        if m.gain_margin_db is not None:
            text.append(f"The phase reaches -180° at {fmt(m.phase_crossover_hz, 'Hz')}, where the gain margin is "
                        f"{fmt(m.gain_margin_db, 'dB')}.")
            key.append(Key("GM", f"{gm_min_s} or more"))
        else:
            text.append("The phase does not reach -180° inside the sweep, so the gain margin was not measured.")
        key.append(Key("f_c"))
        if verdict is Verdict.PASS:
            both = f"{pm_min_s} of phase margin" + (f" and {gm_min_s} of gain margin" if m.gain_margin_db is not None
                                                     else "")
            text.append(f"We want at least {both}, and the loop has that, so the rail settles cleanly after load "
                        "steps.")
        elif verdict is Verdict.FAIL:
            text.append("With no margin left the loop is unstable: the rail will oscillate.")
        else:
            if worst_pm < pm_min_deg:
                text.append(f"We want at least {pm_min_s}, so the rail will ring for a few cycles after each load "
                            "step and may oscillate at light load.")
            if not gm_ok:
                text.append(f"We want at least {gm_min_s} of gain margin, so a rise in loop gain from load, "
                            "temperature or part tolerance can push it into oscillation.")
    return Result(
        name="loop margins",
        formula="T = -V(b)/V(a); f_c at |T| = 1; PM = 180 + angle T(f_c); GM = -20 log|T(f_180)|",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(source,) if source else (),
        plots=(loop_gain_plot(f_hz, t_loop, m),) if f_hz is not None and t_loop is not None and len(f_hz) > 1 else (),
        summary=" ".join(text),
        key=tuple(key),
    )


@dataclass(frozen=True)
class ImpedancePeak:
    f_hz: float
    z_ohm: float
    q: float | None


@dataclass(frozen=True)
class ImpedanceSummary:
    max_z_ohm: float
    f_at_max_hz: float
    peaks: tuple[ImpedancePeak, ...]
    z_target_ohm: float | None
    bands_over_target_hz: tuple[tuple[float, float], ...]


def impedance(v: np.ndarray, i_inj_a: complex | np.ndarray = 1.0) -> np.ndarray:
    """Z = V/I from an AC current-injection sweep (default AC 1 A, so Z equals the node voltage)."""
    return np.asarray(v, dtype=complex) / i_inj_a


def impedance_summary(f_hz: np.ndarray, z: np.ndarray, z_target_ohm: float | None = None,
                      min_prominence_db: float = 1.0) -> ImpedanceSummary:
    """Peaks of |Z| with Q from the half-power width, and the bands where |Z| exceeds the target."""
    f = np.asarray(f_hz, dtype=float)
    mag = np.abs(np.asarray(z))
    db = 20 * np.log10(mag)
    idx, _ = signal.find_peaks(db, prominence=min_prominence_db)
    peaks = tuple(ImpedancePeak(float(f[i]), float(mag[i]), _half_power_q(f, mag, int(i))) for i in idx)
    k = int(np.argmax(mag))
    bands = []
    if z_target_ohm is not None:
        d = np.diff(np.concatenate([[0], (mag > z_target_ohm).astype(int), [0]]))
        starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1
        bands = [(float(f[a]), float(f[b])) for a, b in zip(starts, ends)]
    return ImpedanceSummary(float(mag[k]), float(f[k]), peaks, z_target_ohm, tuple(bands))


def impedance_plot(f_hz: np.ndarray, z: np.ndarray, summary: ImpedanceSummary | None = None,
                   title: str = "Rail impedance") -> Plot:
    """|Z| against frequency on log axes, with the target line and the three largest peaks marked."""
    f = np.asarray(f_hz, dtype=float)
    mag = np.abs(np.asarray(z))
    marks = []
    if summary is not None:
        if summary.z_target_ohm is not None:
            marks.append(Marker(f"target {si_text(summary.z_target_ohm, 'ohm')}", y=summary.z_target_ohm, unit="ohm"))
        for p in sorted(summary.peaks, key=lambda p: -p.z_ohm)[:3]:
            marks.append(Marker(f"peak {si_text(p.z_ohm, 'ohm')}", x=p.f_hz, y=p.z_ohm, unit="ohm"))
    k = int(np.argmax(mag)) if len(mag) else 0
    caption = (f"Read the highest point of |Z|: {fmt(float(mag[k]), 'ohm')} at {fmt(float(f[k]), 'Hz')}"
               if len(mag) else "No impedance data.")
    if len(mag) and summary is not None and summary.z_target_ohm is not None:
        caption += f", against the dashed target at {fmt(summary.z_target_ohm, 'ohm')}."
    elif len(mag):
        caption += "."
    return plot_from_arrays(title, "Frequency", "Hz", f, [("|Z|", "ohm", mag)], x_log=True, y_log=True, markers=marks,
                            caption=caption)


def _half_power_q(f: np.ndarray, mag: np.ndarray, i: int) -> float | None:
    level = mag[i] / math.sqrt(2)
    lo = i
    while lo > 0 and mag[lo] > level:
        lo -= 1
    hi = i
    while hi < len(mag) - 1 and mag[hi] > level:
        hi += 1
    if mag[lo] > level or mag[hi] > level:
        return None
    f_lo = _interp_log(f[lo], f[lo + 1], mag[lo], mag[lo + 1], level)
    f_hi = _interp_log(f[hi - 1], f[hi], mag[hi - 1], mag[hi], level)
    return float(f[i] / (f_hi - f_lo)) if f_hi > f_lo else None


def _interp_log(f1: float, f2: float, m1: float, m2: float, level: float) -> float:
    if m2 == m1:
        return f1
    a = (level - m1) / (m2 - m1)
    return math.exp(math.log(f1) + a * (math.log(f2) - math.log(f1)))
