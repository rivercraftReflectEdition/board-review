"""Loop gain from blocks: Bode arrays, crossovers, phase and gain margin, peaking, and the Cff lead helper."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np
from scipy.optimize import brentq

from boardreview.calc.base import Quantity, Result, Verdict

TWO_PI = 2.0 * math.pi


class Block(Protocol):
    def response(self, f_hz: np.ndarray) -> np.ndarray: ...

    def phase_deg(self, f_hz: np.ndarray) -> np.ndarray: ...

    def params(self) -> dict[str, Quantity]: ...

    def text(self) -> str: ...


@dataclass(frozen=True)
class Gain:
    k: float
    unit: str = ""

    def response(self, f_hz):
        return np.full(np.shape(f_hz), complex(self.k))

    def phase_deg(self, f_hz):
        return np.full(np.shape(f_hz), 0.0 if self.k >= 0 else -180.0)

    def params(self):
        return {"k": Quantity(self.k, self.unit)}

    def text(self):
        return f"{self.k:g} {self.unit}".strip()


@dataclass(frozen=True)
class Integrator:
    f_unity_hz: float

    def response(self, f_hz):
        return self.f_unity_hz / (1j * np.asarray(f_hz, dtype=float))

    def phase_deg(self, f_hz):
        return np.full(np.shape(f_hz), -90.0)

    def params(self):
        return {"f_unity": Quantity(self.f_unity_hz, "Hz")}

    def text(self):
        return f"wi/s (fi = {self.f_unity_hz:g} Hz)"


@dataclass(frozen=True)
class Pole:
    f_hz: float

    def response(self, f_hz):
        return 1.0 / (1.0 + 1j * np.asarray(f_hz, dtype=float) / self.f_hz)

    def phase_deg(self, f_hz):
        return -np.degrees(np.arctan(np.asarray(f_hz, dtype=float) / self.f_hz))

    def params(self):
        return {"fp": Quantity(self.f_hz, "Hz")}

    def text(self):
        return f"1/(1 + s/wp) (fp = {self.f_hz:g} Hz)"


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
        return {"fz": Quantity(self.f_hz, "Hz", "RHP" if self.rhp else "")}

    def text(self):
        return f"(1 {'-' if self.rhp else '+'} s/wz) (fz = {self.f_hz:g} Hz{', RHP' if self.rhp else ''})"


@dataclass(frozen=True)
class IntegratorZero:
    """Type-II compensator shape (1 + wz/s): integrator below fz, flat above."""

    f_hz: float

    def response(self, f_hz):
        return 1.0 + self.f_hz / (1j * np.asarray(f_hz, dtype=float))

    def phase_deg(self, f_hz):
        return -np.degrees(np.arctan(self.f_hz / np.asarray(f_hz, dtype=float)))

    def params(self):
        return {"fz": Quantity(self.f_hz, "Hz")}

    def text(self):
        return f"(1 + wz/s) (fz = {self.f_hz:g} Hz)"


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
        return {"f0": Quantity(self.f_hz, "Hz"), "q": Quantity(self.q, "")}

    def text(self):
        return f"1/(1 + s/(Q*w0) + s^2/w0^2) (f0 = {self.f_hz:g} Hz, Q = {self.q:g})"


@dataclass(frozen=True)
class Delay:
    t_s: float

    def response(self, f_hz):
        return np.exp(-1j * TWO_PI * np.asarray(f_hz, dtype=float) * self.t_s)

    def phase_deg(self, f_hz):
        return -360.0 * np.asarray(f_hz, dtype=float) * self.t_s

    def params(self):
        return {"td": Quantity(self.t_s, "s")}

    def text(self):
        return f"exp(-s*Td) (Td = {self.t_s:g} s)"


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
            "r_top": Quantity(self.r_top_ohm, "ohm"),
            "r_bot": Quantity(self.r_bot_ohm, "ohm"),
            "cff": Quantity(self.cff_f, "F"),
        }

    def text(self):
        dc = "R2/(R1+R2)*" if self.include_dc else ""
        return f"{dc}(1 + s*R1*Cff)/(1 + s*(R1||R2)*Cff) (R1 = {self.r_top_ohm:g}, R2 = {self.r_bot_ohm:g}, Cff = {self.cff_f:g})"


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
        return {"r": Quantity(self.r_ohm, "ohm"), "c": Quantity(self.c_f, "F"), "esr": Quantity(self.esr_ohm, "ohm")}

    def text(self):
        return f"R || (ESR + 1/sC) (R = {self.r_ohm:g} ohm, C = {self.c_f:g} F, ESR = {self.esr_ohm:g} ohm)"


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
) -> Result:
    """Crossover, phase margin, gain margin and peaking for a loop built from blocks."""
    gc, pc = crossings(blocks, f_start_hz, f_stop_hz)
    inputs = {f"b{i + 1}_{k}": q for i, b in enumerate(blocks) for k, q in b.params().items()}
    inputs["f_start"] = Quantity(f_start_hz, "Hz")
    inputs["f_stop"] = Quantity(f_stop_hz, "Hz")
    formula = (
        "T = " + " * ".join(f"[{b.text()}]" for b in blocks)
        + "; PM = 180 + arg T(fc); GM = -|T(f180)| dB; peak_fc = 1/(2 sin(PM/2)); peak_f180 = 1/(1 - 10^(-GM/20))"
    )
    base_refs = (
        "at |T| = 1, |1 + T| = 2 sin(PM/2), so |T/(1+T)| = 1/(2 sin(PM/2))",
        "at f180, |1 + T| = 1 - |T|, so |1/(1+T)| = 1/(1 - 10^(-GM/20))",
    ) + tuple(refs)
    if not gc:
        return Result(name, formula, inputs, {}, Verdict.UNKNOWN, "no 0 dB crossing in the swept range", base_refs)
    fc_min = min(f for f, _ in gc)
    fc_worst, pm = min(gc, key=lambda c: c[1])
    relevant = [(f, g) for f, g in pc if not (pm > 0 and f < fc_min and g < 0)]
    f180, gm = min(relevant, key=lambda c: c[1]) if relevant else (math.nan, math.inf)
    conditional = len(relevant) < len(pc)
    pk_fc = peaking_at_crossover(pm)
    pk_180 = peaking_at_f180(gm)
    outputs = {
        "fc": Quantity(fc_worst, "Hz", "crossover with the lowest PM"),
        "pm": Quantity(pm, "deg"),
        "f180": Quantity(f180, "Hz"),
        "gm": Quantity(gm, "dB"),
        "peak_fc": Quantity(pk_fc, "", f"{_db(pk_fc):.2f} dB"),
        "peak_f180": Quantity(pk_180, "", f"{_db(pk_180):.2f} dB"),
        "n_gain_crossings": Quantity(len(gc), "count"),
        "n_phase_crossings": Quantity(len(pc), "count"),
    }
    for i, (f, p) in enumerate(gc):
        outputs[f"fc_{i + 1}"] = Quantity(f, "Hz", f"PM {p:.2f} deg")
    for i, (f, g) in enumerate(pc):
        outputs[f"f180_{i + 1}"] = Quantity(f, "Hz", f"GM {g:.2f} dB")
    if pm <= 0 or gm <= 0:
        verdict, reason = Verdict.FAIL, f"unstable: PM {pm:.1f} deg, GM {gm:.1f} dB"
    elif pm < pm_fail_deg or gm < gm_fail_db:
        verdict, reason = Verdict.FAIL, f"PM {pm:.1f} deg or GM {gm:.1f} dB below {pm_fail_deg:g} deg / {gm_fail_db:g} dB"
    elif pm < pm_min_deg or gm < gm_min_db or conditional:
        verdict = Verdict.MARGINAL
        reason = f"PM {pm:.1f} deg, GM {gm:.1f} dB against {pm_min_deg:g} deg / {gm_min_db:g} dB"
        if conditional:
            reason += "; conditionally stable (phase crosses -180 below fc with gain above 0 dB)"
    else:
        verdict, reason = Verdict.PASS, f"PM {pm:.1f} deg at {fc_worst / 1e3:.1f} kHz, GM {gm:.1f} dB"
    if len(gc) > 1:
        reason += f"; {len(gc)} gain crossings"
    return Result(
        name=name,
        formula=formula,
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=base_refs,
        assumptions=("linear small-signal model", "phase is the sum of block phases, so it is continuous"),
    )


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
    return Result(
        name="feed-forward capacitor lead",
        formula=(
            "fz = 1/(2 pi R1 Cff); fp = 1/(2 pi (R1||R2) Cff); lead(f) = atan(f/fz) - atan(f/fp); "
            "max lead = asin((fp - fz)/(fp + fz)) at sqrt(fz*fp)"
        ),
        inputs={
            "r_top": Quantity(r_top_ohm, "ohm"),
            "r_bot": Quantity(r_bot_ohm, "ohm"),
            "cff": Quantity(cff_f, "F"),
            "f": Quantity(f_hz, "Hz"),
        },
        outputs={
            "fz": Quantity(fz, "Hz"),
            "fp": Quantity(fp, "Hz"),
            "lead_at_f": Quantity(lead, "deg"),
            "lead_max": Quantity(lead_max, "deg", "set by R1/R2 only"),
            "f_lead_max": Quantity(f_max, "Hz"),
            "cff_for_max_lead_at_f": Quantity(c_best, "F"),
            "hf_gain_boost": Quantity(gain_hf, "dB", "gain rise from below fz to above fp"),
        },
        verdict=Verdict.INFO,
        refs=(
            "LTC3633A/LTC3633A-1 data sheet Rev B (3633a1fb) p. 15 Figure 2 and p. 16 (CF adds phase lead)",
            "lead-lag network algebra: max of atan(f/fz) - atan(f/fp) is at the geometric mean",
        ),
        assumptions=("FB pin input impedance far above R1||R2",),
    )
