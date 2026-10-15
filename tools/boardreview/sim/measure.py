"""Waveform metrics from a run: steady state, ripple, tones, switching frequency, ring-down, loop margins, impedance."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import signal

from boardreview.calc.base import Quantity, Result, Verdict

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


def pm_from_zeta(zeta: float) -> float:
    """Second-order rule of thumb PM ~ 100 zeta degrees (fair below zeta 0.6)."""
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
        if 0 < r < 1:
            decay = float(r)
            ring = float(1.0 / (use[2][0] - use[0][0]))
            zeta = zeta_from_decay_ratio(r)
            pm = pm_from_zeta(zeta)
    overshoot = None
    if abs(step) > 1e-12 and abs(step) >= 0.2 * peak_abs:
        overshoot = float(max(0.0, np.max(np.sign(step) * e)) / abs(step) * 100.0)
    band_v = band if band is not None else (0.02 * abs(step) if overshoot is not None else 0.1 * peak_abs)
    outside = np.nonzero(np.abs(e) > band_v)[0]
    if len(outside) == 0:
        settle = 0.0
    elif outside[-1] < len(e) - 1:
        settle = float(tw[outside[-1] + 1] - t_step_s)
    else:
        settle = None
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


def ring_result(sr: StepResponse, pm_pass_deg: float = 45.0, pm_marginal_deg: float = 30.0) -> Result:
    """Show the ring-down math: r from same-sign peaks, zeta, PM estimate, with a verdict."""
    inputs = {
        "peak_1": Quantity(sr.peaks[0][1] if sr.peaks else float("nan"), "V", "first deviation peak"),
        "peak_3": Quantity(sr.peaks[2][1] if len(sr.peaks) > 2 else float("nan"), "V", "next same-sign peak"),
    }
    if sr.decay_ratio is None:
        return Result(
            name="ring-down after step", formula="r = peak_3 / peak_1; zeta = ln(1/r) / sqrt(4 pi^2 + ln(1/r)^2)",
            inputs=inputs, outputs={}, verdict=Verdict.UNKNOWN,
            reason="no second same-sign peak above the noise: overdamped, or the window is too short",
        )
    pm = sr.pm_deg_est
    verdict = Verdict.PASS if pm >= pm_pass_deg else Verdict.MARGINAL if pm >= pm_marginal_deg else Verdict.FAIL
    return Result(
        name="ring-down after step",
        formula="r = peak_3 / peak_1; zeta = ln(1/r) / sqrt(4 pi^2 + ln(1/r)^2); PM ~ 100 zeta deg",
        inputs=inputs,
        outputs={
            "r": Quantity(sr.decay_ratio, ""),
            "f_ring": Quantity(sr.ring_hz, "Hz"),
            "zeta": Quantity(sr.zeta, ""),
            "PM_est": Quantity(pm, "deg", "second-order estimate"),
        },
        verdict=verdict,
        reason=f"PM estimate {pm:.0f} deg against {pm_pass_deg:.0f} deg",
        assumptions=("the ring is one dominant second-order pair", "PM ~ 100 zeta holds below zeta 0.6"),
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


def margins_result(m: LoopMargins, pm_min_deg: float = 45.0, gm_min_db: float = 6.0, source: str = "") -> Result:
    """Loop margins as a Result with a verdict against the PM and GM targets."""
    outputs = {}
    if m.crossover_hz is not None:
        outputs["f_c"] = Quantity(m.crossover_hz, "Hz", "|T| = 0 dB")
        outputs["PM"] = Quantity(m.phase_margin_deg, "deg", "180 + angle(T) at f_c")
    if m.gain_margin_db is not None:
        outputs["f_180"] = Quantity(m.phase_crossover_hz, "Hz", "angle(T) = -180 deg")
        outputs["GM"] = Quantity(m.gain_margin_db, "dB", "-|T| at f_180")
    if m.crossover_hz is None:
        verdict, reason = Verdict.UNKNOWN, "no 0 dB crossing inside the sweep; widen it"
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
    return Result(
        name="loop margins",
        formula="T = -V(b)/V(a); f_c at |T| = 1; PM = 180 + angle T(f_c); GM = -20 log|T(f_180)|",
        inputs={},
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(source,) if source else (),
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
