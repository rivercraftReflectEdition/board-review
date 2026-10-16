"""Loop gain from blocks: Bode arrays, crossovers, phase and gain margin, peaking, and the Cff lead helper."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol, Sequence

import numpy as np
from scipy.optimize import brentq

from boardreview.calc.base import Key, Marker, Plot, Quantity, Result, Verdict, fmt, plot_from_arrays, si_text

TWO_PI = 2.0 * math.pi


class Block(Protocol):
    def response(self, f_hz: np.ndarray) -> np.ndarray: ...

    def phase_deg(self, f_hz: np.ndarray) -> np.ndarray: ...

    def params(self) -> dict[str, Quantity]: ...

    def text(self) -> str: ...

    def tail_bounds(self, f_hz: float) -> tuple[float, float, float, float]: ...


@dataclass(frozen=True)
class Gain:
    k: float
    unit: str = ""

    def response(self, f_hz):
        return np.full(np.shape(f_hz), complex(self.k))

    def phase_deg(self, f_hz):
        return np.full(np.shape(f_hz), 0.0 if self.k >= 0 else -180.0)

    def params(self):
        return {"k": Quantity(self.k, self.unit, label="gain")}

    def text(self):
        return f"{self.k:g} {self.unit}".strip()

    def tail_bounds(self, f_hz):
        ph = 0.0 if self.k >= 0 else -180.0
        return ph, ph, abs(self.k), 0.0


@dataclass(frozen=True)
class Integrator:
    f_unity_hz: float

    def response(self, f_hz):
        return self.f_unity_hz / (1j * np.asarray(f_hz, dtype=float))

    def phase_deg(self, f_hz):
        return np.full(np.shape(f_hz), -90.0)

    def params(self):
        return {"f_unity": Quantity(self.f_unity_hz, "Hz", label="unity-gain frequency")}

    def text(self):
        return f"wi/s (fi = {self.f_unity_hz:g} Hz)"

    def tail_bounds(self, f_hz):
        return -90.0, -90.0, self.f_unity_hz / f_hz, -1.0


@dataclass(frozen=True)
class Pole:
    f_hz: float

    def response(self, f_hz):
        return 1.0 / (1.0 + 1j * np.asarray(f_hz, dtype=float) / self.f_hz)

    def phase_deg(self, f_hz):
        return -np.degrees(np.arctan(np.asarray(f_hz, dtype=float) / self.f_hz))

    def params(self):
        return {"fp": Quantity(self.f_hz, "Hz", label="pole frequency")}

    def text(self):
        return f"1/(1 + s/wp) (fp = {self.f_hz:g} Hz)"

    def tail_bounds(self, f_hz):
        ph = -math.degrees(math.atan(f_hz / self.f_hz))
        if f_hz >= self.f_hz:
            return -90.0, ph, self.f_hz / f_hz, -1.0
        return -90.0, ph, 1.0 / math.hypot(1.0, f_hz / self.f_hz), 0.0


@dataclass(frozen=True)
class Zero:
    f_hz: float
    rhp: bool = False

    def response(self, f_hz):
        sign = -1.0 if self.rhp else 1.0
        return 1.0 + sign * 1j * np.asarray(f_hz, dtype=float) / self.f_hz

    def phase_deg(self, f_hz):
        sign = -1.0 if self.rhp else 1.0
        return sign * np.degrees(np.arctan(np.asarray(f_hz, dtype=float) / self.f_hz))

    def params(self):
        return {"fz": Quantity(self.f_hz, "Hz", "RHP" if self.rhp else "",
                              label="right-half-plane zero frequency" if self.rhp else "zero frequency")}

    def text(self):
        return f"(1 {'-' if self.rhp else '+'} s/wz) (fz = {self.f_hz:g} Hz{', RHP' if self.rhp else ''})"

    def tail_bounds(self, f_hz):
        ph = math.degrees(math.atan(f_hz / self.f_hz))
        lo, hi = (-90.0, -ph) if self.rhp else (ph, 90.0)
        return lo, hi, math.hypot(1.0, f_hz / self.f_hz), 1.0


@dataclass(frozen=True)
class IntegratorZero:
    """Type-II compensator shape (1 + wz/s): integrator below fz, flat above."""

    f_hz: float

    def response(self, f_hz):
        return 1.0 + self.f_hz / (1j * np.asarray(f_hz, dtype=float))

    def phase_deg(self, f_hz):
        return -np.degrees(np.arctan(self.f_hz / np.asarray(f_hz, dtype=float)))

    def params(self):
        return {"fz": Quantity(self.f_hz, "Hz", label="integrator zero frequency")}

    def text(self):
        return f"(1 + wz/s) (fz = {self.f_hz:g} Hz)"

    def tail_bounds(self, f_hz):
        return -math.degrees(math.atan(self.f_hz / f_hz)), 0.0, math.hypot(1.0, self.f_hz / f_hz), 0.0


@dataclass(frozen=True)
class DoublePole:
    f_hz: float
    q: float

    def _parts(self, f_hz):
        x = np.asarray(f_hz, dtype=float) / self.f_hz
        return 1.0 - x * x, x / self.q

    def response(self, f_hz):
        re, im = self._parts(f_hz)
        return 1.0 / (re + 1j * im)

    def phase_deg(self, f_hz):
        re, im = self._parts(f_hz)
        return -np.degrees(np.arctan2(im, re))

    def params(self):
        return {"f0": Quantity(self.f_hz, "Hz", label="double-pole frequency"), "q": Quantity(self.q, "", label="double-pole Q")}

    def text(self):
        return f"1/(1 + s/(Q*w0) + s^2/w0^2) (f0 = {self.f_hz:g} Hz, Q = {self.q:g})"

    def tail_bounds(self, f_hz):
        x = f_hz / self.f_hz
        ph = -math.degrees(math.atan2(x / self.q, 1.0 - x * x))
        if x >= 2.0:
            return -180.0, ph, 1.0 / (x * x - 1.0), -2.0
        if self.q > math.sqrt(0.5) and x < math.sqrt(1.0 - 0.5 / self.q**2):
            return -180.0, ph, self.q / math.sqrt(1.0 - 0.25 / self.q**2), 0.0
        return -180.0, ph, 1.0 / math.hypot(1.0 - x * x, x / self.q), 0.0


@dataclass(frozen=True)
class Delay:
    t_s: float

    def response(self, f_hz):
        return np.exp(-1j * TWO_PI * np.asarray(f_hz, dtype=float) * self.t_s)

    def phase_deg(self, f_hz):
        return -360.0 * np.asarray(f_hz, dtype=float) * self.t_s

    def params(self):
        return {"td": Quantity(self.t_s, "s", label="delay")}

    def text(self):
        return f"exp(-s*Td) (Td = {self.t_s:g} s)"

    def tail_bounds(self, f_hz):
        return -math.inf, -360.0 * f_hz * self.t_s, 1.0, 0.0


@dataclass(frozen=True)
class Divider:
    """Feedback divider, top resistor optionally bypassed by Cff; include_dc=False keeps only the lead-lag."""

    r_top_ohm: float
    r_bot_ohm: float
    cff_f: float = 0.0
    include_dc: bool = True

    def _w(self):
        rp = self.r_top_ohm * self.r_bot_ohm / (self.r_top_ohm + self.r_bot_ohm)
        return self.r_top_ohm * self.cff_f, rp * self.cff_f

    def response(self, f_hz):
        s = 1j * TWO_PI * np.asarray(f_hz, dtype=float)
        tz, tp = self._w()
        dc = self.r_bot_ohm / (self.r_top_ohm + self.r_bot_ohm) if self.include_dc else 1.0
        return dc * (1.0 + s * tz) / (1.0 + s * tp)

    def phase_deg(self, f_hz):
        w = TWO_PI * np.asarray(f_hz, dtype=float)
        tz, tp = self._w()
        return np.degrees(np.arctan(w * tz) - np.arctan(w * tp))

    def params(self):
        return {
            "r_top": Quantity(self.r_top_ohm, "ohm", label="top resistor"),
            "r_bot": Quantity(self.r_bot_ohm, "ohm", label="bottom resistor"),
            "cff": Quantity(self.cff_f, "F", label="feed-forward capacitor"),
        }

    def text(self):
        dc = "R2/(R1+R2)*" if self.include_dc else ""
        return f"{dc}(1 + s*R1*Cff)/(1 + s*(R1||R2)*Cff) (R1 = {self.r_top_ohm:g}, R2 = {self.r_bot_ohm:g}, Cff = {self.cff_f:g})"

    def tail_bounds(self, f_hz):
        dc = self.r_bot_ohm / (self.r_top_ohm + self.r_bot_ohm) if self.include_dc else 1.0
        if self.cff_f == 0.0:
            return 0.0, 0.0, dc, 0.0
        tz, tp = self._w()
        return 0.0, 90.0, dc * tz / tp, 0.0


@dataclass(frozen=True)
class ParallelRC:
    """Output impedance R || (ESR + 1/sC), in ohms."""

    r_ohm: float
    c_f: float
    esr_ohm: float = 0.0

    def response(self, f_hz):
        s = 1j * TWO_PI * np.asarray(f_hz, dtype=float)
        return self.r_ohm * (1.0 + s * self.c_f * self.esr_ohm) / (1.0 + s * self.c_f * (self.r_ohm + self.esr_ohm))

    def phase_deg(self, f_hz):
        w = TWO_PI * np.asarray(f_hz, dtype=float)
        return np.degrees(np.arctan(w * self.c_f * self.esr_ohm) - np.arctan(w * self.c_f * (self.r_ohm + self.esr_ohm)))

    def params(self):
        return {"r": Quantity(self.r_ohm, "ohm", label="load resistance"), "c": Quantity(self.c_f, "F", label="capacitance"),
                "esr": Quantity(self.esr_ohm, "ohm", label="capacitor ESR")}

    def text(self):
        return f"R || (ESR + 1/sC) (R = {self.r_ohm:g} ohm, C = {self.c_f:g} F, ESR = {self.esr_ohm:g} ohm)"

    def tail_bounds(self, f_hz):
        if self.esr_ohm == 0.0 and TWO_PI * f_hz * self.r_ohm * self.c_f >= 1.0:
            return -90.0, 0.0, 1.0 / (TWO_PI * f_hz * self.c_f), -1.0
        return -90.0, 0.0, float(abs(self.response(np.array([f_hz]))[0])), 0.0


def loop_response(blocks: Sequence[Block], f_hz) -> tuple[np.ndarray, np.ndarray]:
    """Return |T| in dB and the continuous (unwrapped) phase of T in degrees."""
    f = np.atleast_1d(np.asarray(f_hz, dtype=float))
    t = np.ones_like(f, dtype=complex)
    ph = np.zeros_like(f)
    for b in blocks:
        t = t * b.response(f)
        ph = ph + b.phase_deg(f)
    return 20.0 * np.log10(np.abs(t)), ph


def bode(
    blocks: Sequence[Block], f_start_hz: float = 10.0, f_stop_hz: float = 10e6, points_per_decade: int = 200
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Frequency, magnitude in dB and unwrapped phase in degrees on a log grid."""
    n = int(round(math.log10(f_stop_hz / f_start_hz) * points_per_decade)) + 1
    f = np.logspace(math.log10(f_start_hz), math.log10(f_stop_hz), n)
    mag, ph = loop_response(blocks, f)
    return f, mag, ph


def _roots(fn, f: np.ndarray, y: np.ndarray) -> list[float]:
    out = []
    idx = np.nonzero(np.sign(y[:-1]) * np.sign(y[1:]) <= 0)[0]
    for i in idx:
        if y[i] == 0.0:
            out.append(float(f[i]))
            continue
        if y[i + 1] == 0.0:
            continue
        lf = brentq(lambda u: fn(10.0**u), math.log10(f[i]), math.log10(f[i + 1]), xtol=1e-12)
        out.append(10.0**lf)
    return out


def crossings(blocks: Sequence[Block], f_start_hz: float = 10.0, f_stop_hz: float = 10e6, points_per_decade: int = 200):
    """All gain crossovers (|T| = 0 dB) and phase crossovers (phase = -180 - k*360) in the range."""
    f, mag, ph = bode(blocks, f_start_hz, f_stop_hz, points_per_decade)

    def mag_at(x):
        return float(loop_response(blocks, x)[0][0])

    def ph_at(x):
        return float(loop_response(blocks, x)[1][0])

    gain_x = _roots(mag_at, f, mag)
    phase_x = []
    k_lo = math.floor((-180.0 - ph.max()) / 360.0)
    k_hi = math.ceil((-180.0 - ph.min()) / 360.0)
    for k in range(k_lo, k_hi + 1):
        level = -180.0 - 360.0 * k
        phase_x += _roots(lambda x, lv=level: ph_at(x) - lv, f, ph - level)
    phase_x = sorted(set(phase_x))
    gc = [(fc, 180.0 + ph_at(fc)) for fc in gain_x]
    pc = [(f180, -mag_at(f180)) for f180 in phase_x]
    return gc, pc


def peaking_at_crossover(pm_deg: float) -> float:
    """Closed-loop |T/(1+T)| at fc: 1/(2 sin(PM/2)); inf when PM <= 0."""
    return 1.0 / (2.0 * math.sin(math.radians(pm_deg) / 2.0)) if pm_deg > 0 else math.inf


def peaking_at_f180(gm_db: float) -> float:
    """Sensitivity |1/(1+T)| at the phase crossover: 1/(1 - 10^(-GM/20)); inf when GM <= 0."""
    return 1.0 / (1.0 - 10.0 ** (-gm_db / 20.0)) if gm_db > 0 else math.inf


def _db(x: float) -> float:
    return 20.0 * math.log10(x) if math.isfinite(x) else math.inf


def bode_plot(
    blocks: Sequence[Block],
    f_start_hz: float = 10.0,
    f_stop_hz: float = 10e6,
    fc_hz: float | None = None,
    f180_hz: float | None = None,
    points_per_decade: int = 50,
    title: str = "Loop gain",
    caption: str = "",
) -> Plot:
    """Gain and phase of T on a log grid, with the crossover, PM, phase crossover and GM marked."""
    f, mag, ph = bode(blocks, f_start_hz, f_stop_hz, points_per_decade)
    markers = [Marker("-180°", y=-180.0, unit="deg")]
    if fc_hz is not None and math.isfinite(fc_hz):
        mag_c, ph_c = loop_response(blocks, fc_hz)
        markers += [Marker(f"fc {si_text(fc_hz, 'Hz')}", x=fc_hz),
                    Marker(f"PM {180.0 + float(ph_c[0]):.0f}°", x=fc_hz, y=float(ph_c[0]), unit="deg")]
    if f180_hz is not None and math.isfinite(f180_hz):
        mag_p, _ = loop_response(blocks, f180_hz)
        markers += [Marker(f"f180 {si_text(f180_hz, 'Hz')}", x=f180_hz),
                    Marker(f"GM {-float(mag_p[0]):.1f} dB", x=f180_hz, y=float(mag_p[0]), unit="dB")]
    return plot_from_arrays(title, "Frequency", "Hz", f, [("Gain", "dB", mag), ("Phase", "deg", ph)],
                            x_log=True, markers=markers, caption=caption)


def phase_caption(fc_hz: float, pm_deg: float) -> str:
    """Where to look on a Bode plot: the phase at the gain crossover, against -180°."""
    side = f"{fmt(pm_deg, 'deg')} above" if pm_deg >= 0 else f"{fmt(-pm_deg, 'deg')} below"
    return f"Read the phase where the gain crosses 0 dB (dashed line, {fmt(fc_hz, 'Hz')}): it is {side} -180°."


def margin_sentences(pm_deg: float, gm_db: float | None, verdict: Verdict, pm_min_deg: float, pm_fail_deg: float,
                     gm_min_db: float, gm_fail_db: float, conditional: bool = False) -> list[str]:
    """What the margins mean on the bench, in words that agree with the verdict."""
    pm_min, gm_min = fmt(pm_min_deg, "deg"), fmt(gm_min_db, "dB")
    gm_ok = gm_db is None or not math.isfinite(gm_db) or gm_db >= gm_min_db
    if verdict is Verdict.PASS:
        both = f"{pm_min} of phase margin and {gm_min} of gain margin" if gm_db is not None else f"{pm_min} of phase margin"
        return [f"We want at least {both}, and this loop has that, so the rail settles cleanly after load steps."]
    if verdict is Verdict.FAIL:
        if pm_deg <= 0 or (gm_db is not None and gm_db <= 0):
            return ["With no margin left the loop is unstable: the rail will oscillate."]
        if pm_deg < pm_fail_deg:
            return [f"That is below the {fmt(pm_fail_deg, 'deg')} fail limit, so the rail will ring hard after each "
                    "load step and is likely to oscillate."]
        return [f"The gain margin is below the {fmt(gm_fail_db, 'dB')} fail limit, so a small rise in loop gain from "
                "load, temperature or part tolerance makes it oscillate."]
    out = []
    if pm_deg < pm_min_deg:
        out.append(f"We want at least {pm_min}, so the rail will ring for a few cycles after each load step and may "
                   "oscillate at light load.")
    if not gm_ok:
        out.append(f"We want at least {gm_min} of gain margin, so a rise in loop gain from load, temperature or part "
                   "tolerance can push it into oscillation.")
    if conditional:
        out.append("The phase also passes -180° below the crossover while the gain is above 0 dB, so the loop is only "
                   "conditionally stable and can oscillate during start-up or overload.")
    return out


def _gm_above(blocks: Sequence[Block], f_hz: float) -> float:
    """Lowest GM any phase crossing above f_hz can have, from per-block phase and gain bounds; -inf when unbounded."""
    lo = hi = n = 0.0
    c = 1.0
    for b in blocks:
        bounds = getattr(b, "tail_bounds", None)
        if bounds is None:
            return -math.inf
        a, z, cb, nb = bounds(f_hz)
        lo, hi, c, n = lo + a, hi + z, c * cb, n + nb
    if math.isfinite(lo) and math.ceil((-180.0 - hi) / 360.0) > math.floor((-180.0 - lo) / 360.0):
        return math.inf
    if n > 0 or not math.isfinite(c):
        return -math.inf
    return -20.0 * math.log10(c) if c > 0 else math.inf


def _grade(pm, gm, conditional, pm_min, pm_fail, gm_min, gm_fail):
    if pm <= 0 or gm <= 0:
        return Verdict.FAIL, f"unstable: PM {pm:.1f} deg, GM {gm:.1f} dB"
    if pm < pm_fail or gm < gm_fail:
        return Verdict.FAIL, f"PM {pm:.1f} deg or GM {gm:.1f} dB below {pm_fail:g} deg / {gm_fail:g} dB"
    if pm < pm_min or gm < gm_min or conditional:
        reason = f"PM {pm:.1f} deg, GM {gm:.1f} dB against {pm_min:g} deg / {gm_min:g} dB"
        if conditional:
            reason += "; conditionally stable (phase crosses -180 below fc with gain above 0 dB)"
        return Verdict.MARGINAL, reason
    return Verdict.PASS, ""


def margins(
    blocks: Sequence[Block],
    f_start_hz: float = 10.0,
    f_stop_hz: float = 10e6,
    pm_min_deg: float = 45.0,
    pm_fail_deg: float = 30.0,
    gm_min_db: float = 10.0,
    gm_fail_db: float = 6.0,
    name: str = "loop margins",
    refs: tuple[str, ...] = (),
    context: str = "",
) -> Result:
    """Crossover, phase margin, gain margin and peaking for a loop built from blocks; context marks the inputs."""
    gc, pc = crossings(blocks, f_start_hz, f_stop_hz)
    inputs = {f"b{i + 1}_{k}": replace(q, label=f"Block {i + 1} {q.label or k.replace('_', ' ')}")
              for i, b in enumerate(blocks) for k, q in b.params().items()}
    inputs["f_start"] = Quantity(f_start_hz, "Hz", label="Sweep start")
    inputs["f_stop"] = Quantity(f_stop_hz, "Hz", label="Sweep stop")
    inputs["pm_min"] = Quantity(pm_min_deg, "deg", label="Phase margin wanted")
    inputs["pm_fail"] = Quantity(pm_fail_deg, "deg", label="Phase margin fail limit")
    inputs["gm_min"] = Quantity(gm_min_db, "dB", label="Gain margin wanted")
    inputs["gm_fail"] = Quantity(gm_fail_db, "dB", label="Gain margin fail limit")
    formula = (
        "T = " + " * ".join(f"[{b.text()}]" for b in blocks)
        + "; PM = 180 + arg T(fc); GM = -|T(f180)| dB; peak_fc = 1/(2 sin(PM/2)); peak_f180 = 1/(1 - 10^(-GM/20))"
    )
    base_refs = (
        "at |T| = 1, |1 + T| = 2 sin(PM/2), so |T/(1+T)| = 1/(2 sin(PM/2))",
        "at f180, |1 + T| = 1 - |T|, so |1/(1+T)| = 1/(1 - 10^(-GM/20))",
    ) + tuple(refs)
    if not gc:
        summary = (f"The loop gain never crosses 0 dB between {fmt(f_start_hz, 'Hz')} and {fmt(f_stop_hz, 'Hz')}, so "
                   "there is no crossover to read the margins at. Widen the sweep or check the blocks.")
        return Result(name, formula, inputs, {}, Verdict.UNKNOWN, "no 0 dB crossing in the swept range", base_refs,
                      plots=(bode_plot(blocks, f_start_hz, f_stop_hz,
                                       caption="The gain never crosses 0 dB in this sweep."),),
                      summary=summary).in_context(context)
    fc_min = min(f for f, _ in gc)
    fc_worst, pm = min(gc, key=lambda c: c[1])
    relevant = [(f, g) for f, g in pc if not (pm > 0 and f < fc_min and g < 0)]
    f180, gm_swept = min(relevant, key=lambda c: c[1]) if relevant else (math.nan, math.inf)
    conditional = len(relevant) < len(pc)
    gm_above = _gm_above(blocks, f_stop_hz)
    known = gm_above >= gm_swept
    gm = gm_swept if known else gm_above
    limits = (pm_min_deg, pm_fail_deg, gm_min_db, gm_fail_db)
    verdict, reason = _grade(pm, gm_swept, conditional, *limits)
    if not known and verdict is not Verdict.FAIL:
        low, _ = _grade(pm, gm_above, conditional, *limits)
        if low is not verdict:
            bound = f"at least {gm_above:.1f} dB" if math.isfinite(gm_above) else "unbounded by the model"
            verdict = Verdict.UNKNOWN
            reason = (
                f"PM {pm:.1f} deg; phase may reach -180 deg above f_stop = {f_stop_hz:g} Hz, where GM is {bound}; "
                "extend f_stop past the phase crossing"
            )
    if verdict is Verdict.PASS:
        reason = f"PM {pm:.1f} deg at {fc_worst / 1e3:.1f} kHz, GM {'at least ' if not known else ''}{gm:.1f} dB"
    pk_fc = peaking_at_crossover(pm)
    pk_180 = peaking_at_f180(gm)
    outputs = {
        "fc": Quantity(fc_worst, "Hz", "crossover with the lowest PM", "Crossover frequency"),
        "pm": Quantity(pm, "deg", label="Phase margin"),
        "f180": Quantity(f180 if known else math.nan, "Hz", label="Phase crossover frequency"),
        "gm": Quantity(gm, "dB", "" if known else "lower bound: phase may cross -180 above f_stop",
                       "Gain margin" if known else "Gain margin, lower bound"),
        "gm_above_f_stop": Quantity(gm_above, "dB", "lowest GM any phase crossing above f_stop can have",
                                    "Lowest gain margin above the sweep"),
        "peak_fc": Quantity(pk_fc, "", f"{_db(pk_fc):.2f} dB", "Closed-loop peaking at crossover"),
        "peak_f180": Quantity(pk_180, "", f"{_db(pk_180):.2f} dB" + ("" if known else ", upper bound"),
                              "Peaking at the phase crossover"),
        "n_gain_crossings": Quantity(len(gc), "count", label="Gain crossings"),
        "n_phase_crossings": Quantity(len(pc), "count", label="Phase crossings"),
    }
    for i, (f, p) in enumerate(gc):
        outputs[f"fc_{i + 1}"] = Quantity(f, "Hz", f"PM {p:.2f} deg", f"Gain crossing {i + 1}")
    for i, (f, g) in enumerate(pc):
        outputs[f"f180_{i + 1}"] = Quantity(f, "Hz", f"GM {g:.2f} dB", f"Phase crossing {i + 1}")
    if len(gc) > 1:
        reason += f"; {len(gc)} gain crossings"
    fc_s, pm_s, gm_s = fmt(fc_worst, "Hz"), fmt(pm, "deg"), fmt(gm, "dB")
    text = [f"The loop crosses over at {fc_s} with {pm_s} of phase margin." if len(gc) == 1 else
            f"The gain crosses 0 dB {len(gc)} times; the worst crossing is at {fc_s} with {pm_s} of phase margin."]
    gm_finite = math.isfinite(gm)
    if known and gm_finite:
        text.append(f"The phase reaches -180° at {fmt(f180, 'Hz')}, where the gain margin is {gm_s}.")
    elif known:
        text.append("The phase never reaches -180°, so the gain margin is not limited.")
    elif gm_finite:
        text.append(f"The phase may reach -180° above the {fmt(f_stop_hz, 'Hz')} sweep, where the gain margin could "
                    f"be as low as {gm_s}.")
    else:
        text.append(f"The phase may reach -180° above the {fmt(f_stop_hz, 'Hz')} sweep, and nothing in the model "
                    "bounds the gain margin there.")
    if verdict is Verdict.UNKNOWN:
        text.append("Extend the sweep past the phase crossing to settle it.")
    else:
        text += margin_sentences(pm, gm_swept if math.isfinite(gm_swept) else None, verdict, *limits,
                                 conditional=conditional)
    key = [Key("pm", f"{fmt(pm_min_deg, 'deg')} or more")]
    if gm_finite:
        key.append(Key("gm", f"{fmt(gm_min_db, 'dB')} or more"))
    key.append(Key("fc"))
    return Result(
        name=name,
        formula=formula,
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=base_refs,
        assumptions=(
            "linear small-signal model",
            "phase is the sum of block phases, so it is continuous",
            "above f_stop, phase and gain are bounded from each block's limits, not swept",
        ),
        plots=(bode_plot(blocks, f_start_hz, f_stop_hz, fc_worst, f180 if known else None,
                         caption=phase_caption(fc_worst, pm)),),
        summary=" ".join(text),
        key=tuple(key),
    ).in_context(context)


def cff_lead(r_top_ohm: float, r_bot_ohm: float, cff_f: float, f_hz: float) -> Result:
    """Zero, pole and phase lead of a feed-forward capacitor across the top divider resistor."""
    rp = r_top_ohm * r_bot_ohm / (r_top_ohm + r_bot_ohm)
    fz = 1.0 / (TWO_PI * r_top_ohm * cff_f)
    fp = 1.0 / (TWO_PI * rp * cff_f)
    lead = math.degrees(math.atan(f_hz / fz) - math.atan(f_hz / fp))
    lead_max = math.degrees(math.asin((fp - fz) / (fp + fz)))
    f_max = math.sqrt(fz * fp)
    c_best = 1.0 / (TWO_PI * f_hz * math.sqrt(r_top_ohm * rp))
    gain_hf = 20.0 * math.log10((r_top_ohm + r_bot_ohm) / r_bot_ohm)
    summary = (f"A {fmt(cff_f, 'F')} capacitor across the {fmt(r_top_ohm, 'ohm')} top resistor puts a zero at "
               f"{fmt(fz, 'Hz')} and a pole at {fmt(fp, 'Hz')}. At {fmt(f_hz, 'Hz')} it adds {fmt(lead, 'deg')} of "
               f"phase lead. The most it can add is {fmt(lead_max, 'deg')}, at {fmt(f_max, 'Hz')}; "
               f"{fmt(c_best, 'F')} would put that peak at {fmt(f_hz, 'Hz')}.")
    return Result(
        name="feed-forward capacitor lead",
        formula=(
            "fz = 1/(2 pi R1 Cff); fp = 1/(2 pi (R1||R2) Cff); lead(f) = atan(f/fz) - atan(f/fp); "
            "max lead = asin((fp - fz)/(fp + fz)) at sqrt(fz*fp)"
        ),
        inputs={
            "r_top": Quantity(r_top_ohm, "ohm", label="Top resistor"),
            "r_bot": Quantity(r_bot_ohm, "ohm", label="Bottom resistor"),
            "cff": Quantity(cff_f, "F", label="Feed-forward capacitor"),
            "f": Quantity(f_hz, "Hz", label="Frequency of interest"),
        },
        outputs={
            "fz": Quantity(fz, "Hz", label="Zero frequency"),
            "fp": Quantity(fp, "Hz", label="Pole frequency"),
            "lead_at_f": Quantity(lead, "deg", label="Phase lead at that frequency"),
            "lead_max": Quantity(lead_max, "deg", "set by R1/R2 only", "Most phase lead"),
            "f_lead_max": Quantity(f_max, "Hz", label="Frequency of the most lead"),
            "cff_for_max_lead_at_f": Quantity(c_best, "F", label="Capacitor for the most lead there"),
            "hf_gain_boost": Quantity(gain_hf, "dB", "gain rise from below fz to above fp", "High-frequency gain rise"),
        },
        verdict=Verdict.INFO,
        refs=(
            "LTC3633A/LTC3633A-1 data sheet Rev B (3633a1fb) p. 15 Figure 2 and p. 16 (CF adds phase lead)",
            "lead-lag network algebra: max of atan(f/fz) - atan(f/fp) is at the geometric mean",
        ),
        assumptions=("FB pin input impedance far above R1||R2",),
        summary=summary,
        key=(Key("lead_at_f"), Key("lead_max"), Key("cff_for_max_lead_at_f")),
    )
