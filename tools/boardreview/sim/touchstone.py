"""Touchstone networks, real-reference transforms and frequency-domain checks using numpy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from boardreview.calc.base import Key, Marker, Quantity, Result, Verdict, fmt, plot_from_arrays

TS = "IBIS Touchstone File Format Specification Version 2.1, 2024-01-26, pp.4, 6 to 18, 24 to 29"
WAVES = "Frickey, IEEE T-MTT 42(2), 1994-02, pp.205 to 211, Tables I and VI; positive real references only"
PASSIVITY = "Shlepnev, Quality metrics for S-parameter models, 2010-02-04, slides 6 to 14"
UNITS = {"HZ": 1.0, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}


def _frequencies(f_hz) -> np.ndarray:
    f = np.asarray(f_hz, dtype=float)
    if f.ndim != 1 or not f.size or not np.all(np.isfinite(f)) or np.any(f < 0) or np.any(np.diff(f) <= 0):
        raise ValueError("frequencies must be a nonempty, finite, nonnegative, strictly increasing grid")
    return f


def _references(z0_ohm, ports: int) -> np.ndarray:
    if np.iscomplexobj(z0_ohm):
        raise ValueError("only positive real reference impedances are supported")
    z = np.asarray(z0_ohm, dtype=float)
    if z.ndim == 0:
        z = np.full(ports, z.item())
    if z.shape != (ports,) or not np.all(np.isfinite(z)) or np.any(z <= 0):
        raise ValueError("provide one positive real reference impedance per port, or a scalar")
    return z


@dataclass(frozen=True)
class Network:
    """S matrices indexed by frequency, receiving port and driven port; ports in file order."""

    f_hz: np.ndarray
    s: np.ndarray
    z0_ohm: np.ndarray
    source: str = ""
    notes: tuple[str, ...] = ()

    def __post_init__(self):
        f = _frequencies(self.f_hz).copy()
        s = np.asarray(self.s, dtype=complex).copy()
        if s.ndim != 3 or s.shape[0] != f.size or s.shape[1] != s.shape[2] or not 1 <= s.shape[1] <= 4:
            raise ValueError("S must have shape (frequencies, ports, ports) with 1 to 4 ports")
        if not np.all(np.isfinite(s)):
            raise ValueError("S parameters must be finite")
        z = _references(self.z0_ohm, s.shape[1]).copy()
        for a in (f, s, z):
            a.setflags(write=False)
        object.__setattr__(self, "f_hz", f)
        object.__setattr__(self, "s", s)
        object.__setattr__(self, "z0_ohm", z)
        object.__setattr__(self, "notes", tuple(self.notes))

    @property
    def ports(self) -> int:
        return self.s.shape[1]


def _numbers(text: str) -> list[float]:
    return [float(t.replace("D", "E").replace("d", "e")) for t in text.split()]


def _options(text: str) -> tuple[str, str, str, float]:
    fields = text.upper().split()
    unit, parameter, form, resistance = "GHZ", "S", "MA", 50.0
    if "R" in fields:
        k = fields.index("R")
        if k != len(fields) - 2:
            raise ValueError("option R must be followed by one reference resistance")
        resistance = float(fields[-1])
        fields = fields[:k]
    if len(fields) > 3:
        raise ValueError("too many option fields")
    if fields:
        unit = fields[0]
    if len(fields) > 1:
        parameter = fields[1]
    if len(fields) > 2:
        form = fields[2]
    if unit not in UNITS or parameter not in ("S", "Y", "Z", "H", "G") or form not in ("RI", "MA", "DB"):
        raise ValueError("unsupported frequency unit, parameter type or numeric format")
    _references(resistance, 1)
    return unit, parameter, form, resistance


def _positions(ports: int, matrix: str, order: str) -> list[tuple[int, int]]:
    if matrix == "FULL" and ports == 2 and order == "21_12":
        return [(0, 0), (1, 0), (0, 1), (1, 1)]
    return [(i, j) for i in range(ports) for j in range(ports)
            if matrix == "FULL" or (matrix == "LOWER" and j <= i) or (matrix == "UPPER" and j >= i)]


def _to_s(data: np.ndarray, parameter: str, z0_ohm: np.ndarray, legacy: bool) -> np.ndarray:
    if parameter == "S":
        return data
    n = len(z0_ohm)
    eye = np.broadcast_to(np.eye(n), data.shape)
    if parameter in ("Z", "Y"):
        if legacy:
            data = data * (z0_ohm[0] if parameter == "Z" else 1 / z0_ohm[0])
        a, b = (eye, data) if parameter == "Z" else (data, eye)
    else:
        if n != 2:
            raise ValueError("H and G parameters require two ports")
        data = data.copy()
        if legacy:
            scale = z0_ohm[0] if parameter == "H" else 1 / z0_ohm[0]
            data[:, 0, 0] *= scale
            data[:, 1, 1] /= scale
        a, b = np.zeros_like(data), np.zeros_like(data)
        if parameter == "H":
            a[:, 0, 0], a[:, 0, 1], a[:, 1, 1] = 1, -data[:, 0, 1], -data[:, 1, 1]
            b[:, 0, 0], b[:, 1, 0], b[:, 1, 1] = data[:, 0, 0], data[:, 1, 0], -1
        else:
            a[:, 0, 0], a[:, 1, 0], a[:, 1, 1] = -data[:, 0, 0], -data[:, 1, 0], 1
            b[:, 0, 0], b[:, 0, 1], b[:, 1, 1] = -1, data[:, 0, 1], data[:, 1, 1]
    av, bi = a * np.sqrt(z0_ohm), b / np.sqrt(z0_ohm)
    try:
        return np.linalg.solve(av + bi, bi - av)
    except np.linalg.LinAlgError as exc:
        raise ValueError("parameter conversion is singular at a supplied frequency") from exc


def parse_touchstone(text: str, ports: int | None = None, source: str = "") -> Network:
    """Read Touchstone text; 1.x requires a port count or an .s1p to .s4p source name."""
    suffix = re.search(r"\.s([1-4])p$", source, re.I)
    if ports is not None and suffix and ports != int(suffix.group(1)):
        raise ValueError("port count disagrees with source extension")
    if ports is None and suffix:
        ports = int(suffix.group(1))
    version, matrix, order = "1.0", "FULL", "21_12"
    unit, parameter, form, resistance = "GHZ", "S", "MA", 50.0
    references, rows, notes = [], [], []
    state, option_seen, ended = "header", False, False
    declared_count, declared_ports, reference_seen = None, None, False
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].strip()
        if not line:
            continue
        if ended:
            raise ValueError("data after [End]")
        if state == "information" and not line.lower().startswith("[end information]"):
            continue
        if line.startswith("#"):
            if not option_seen:
                unit, parameter, form, resistance = _options(line[1:])
                option_seen = True
            else:
                notes.append("Later option line ignored under Touchstone rules.")
            continue
        if line.startswith("["):
            match = re.fullmatch(r"\[([^]]+)\]\s*(.*)", line)
            if not match:
                raise ValueError(f"invalid keyword: {line}")
            key, value = match.group(1).lower(), match.group(2).strip()
            state = "header"
            if key == "version":
                if value not in ("1.0", "1.1", "2.0", "2.1"):
                    raise ValueError("supported Touchstone versions are 1.x, 2.0 and 2.1")
                version = value
            elif key == "number of ports":
                declared_ports = int(value)
                if ports is not None and declared_ports != ports:
                    raise ValueError("port count disagrees with source extension or argument")
                ports = declared_ports
            elif key == "reference":
                reference_seen = True
                references = _numbers(value)
                state = "reference"
            elif key == "matrix format":
                matrix = value.upper()
                if matrix not in ("FULL", "LOWER", "UPPER"):
                    raise ValueError("unsupported matrix format")
            elif key == "two-port data order":
                order = value.upper()
                if order not in ("21_12", "12_21"):
                    raise ValueError("unsupported two-port data order")
            elif key == "number of frequencies":
                declared_count = int(value)
                if declared_count < 1:
                    raise ValueError("number of frequencies must be positive")
            elif key == "network data":
                state = "network"
            elif key == "noise data":
                state = "noise"
                notes.append("Noise data skipped; no noise figure or optimum source match was analyzed.")
            elif key == "number of noise frequencies":
                if int(value) < 0:
                    raise ValueError("number of noise frequencies must be nonnegative")
            elif key == "begin information":
                state = "information"
            elif key == "end information":
                pass
            elif key == "end":
                ended = True
            else:
                raise ValueError(f"unsupported Touchstone keyword [{key}]")
            continue
        if state == "noise":
            continue
        values = _numbers(line)
        if state == "reference":
            references.extend(values)
        elif state == "network" or not version.startswith("2"):
            rows.append(values)
        else:
            raise ValueError("2.x numeric network data must follow [Network Data]")
    if ports not in (1, 2, 3, 4):
        raise ValueError("supply a port count from 1 to 4")
    if version.startswith("2") and (declared_ports is None or not ended):
        raise ValueError("2.x requires [Number of Ports] and [End]")
    if parameter in ("H", "G") and ports != 2:
        raise ValueError("H and G parameters require two ports")
    if reference_seen and len(references) != ports:
        raise ValueError("[Reference] requires one resistance per port")
    if ports != 2 and any("Noise data skipped" in note for note in notes):
        raise ValueError("noise data is supported only for two-port files")
    z0 = _references(references if references else resistance, ports)
    positions = _positions(ports, matrix, order)
    width, buffer, records = 1 + 2 * len(positions), [], []
    for values in rows:
        if not version.startswith("2") and ports == 2 and not buffer and records and len(values) == 5 \
                and values[0] <= records[-1][0]:
            notes.append("Noise data skipped; no noise figure or optimum source match was analyzed.")
            break
        buffer.extend(values)
        while len(buffer) >= width:
            records.append(buffer[:width])
            del buffer[:width]
    if buffer or not records:
        raise ValueError("incomplete or empty network data")
    if declared_count is not None and declared_count != len(records):
        raise ValueError("network data count disagrees with [Number of Frequencies]")
    table = np.asarray(records)
    if not np.all(np.isfinite(table)):
        raise ValueError("network data must be finite")
    pairs = table[:, 1:].reshape(len(records), -1, 2)
    if form == "RI":
        values = pairs[:, :, 0] + 1j * pairs[:, :, 1]
    else:
        magnitude = pairs[:, :, 0]
        if form == "DB":
            with np.errstate(over="ignore"):
                magnitude = 10.0 ** (magnitude / 20.0)
        elif np.any(magnitude < 0):
            raise ValueError("MA magnitudes must be nonnegative")
        if not np.all(np.isfinite(magnitude)):
            raise ValueError("converted magnitudes must be finite")
        values = magnitude * np.exp(1j * np.radians(pairs[:, :, 1]))
    data = np.zeros((len(records), ports, ports), dtype=complex)
    for k, (i, j) in enumerate(positions):
        data[:, i, j] = values[:, k]
        if matrix != "FULL":
            data[:, j, i] = values[:, k]
    s = _to_s(data, parameter, z0, not version.startswith("2"))
    return Network(table[:, 0] * UNITS[unit], s, z0, source, tuple(notes))


def read_touchstone(path: str | Path) -> Network:
    """Read a local manufacturer or synthetic Touchstone file without modifying it."""
    path = Path(path)
    return parse_touchstone(path.read_text(encoding="utf-8-sig"), source=str(path))


def interpolate(network: Network, f_hz) -> Network:
    """Interpolate real and imaginary parts linearly in frequency, without extrapolation."""
    f = _frequencies(f_hz)
    if f[0] < network.f_hz[0] or f[-1] > network.f_hz[-1]:
        raise ValueError("requested frequencies lie outside the model range; extrapolation is refused")
    flat = network.s.reshape(len(network.f_hz), -1)
    out = np.empty((len(f), flat.shape[1]), dtype=complex)
    for k in range(flat.shape[1]):
        out[:, k] = np.interp(f, network.f_hz, flat[:, k].real) + 1j * np.interp(f, network.f_hz, flat[:, k].imag)
    return Network(f, out.reshape(len(f), network.ports, network.ports), network.z0_ohm, network.source,
                   network.notes + ("Real and imaginary parts interpolated linearly; narrow features may be missed.",))


def _right_solve(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    try:
        return np.linalg.solve(denominator.swapaxes(-1, -2), numerator.swapaxes(-1, -2)).swapaxes(-1, -2)
    except np.linalg.LinAlgError as exc:
        raise ValueError("network transform is singular at a supplied frequency") from exc


def renormalize(network: Network, z0_ohm) -> Network:
    """Change positive real power-wave references without an intermediate impedance matrix."""
    z = _references(z0_ohm, network.ports)
    ratio = np.sqrt(network.z0_ohm / z)
    p, q = np.diag((ratio + 1 / ratio) / 2), np.diag((ratio - 1 / ratio) / 2)
    s = _right_solve(q + p @ network.s, p + q @ network.s)
    note = "Renormalized to " + ", ".join(fmt(v, "ohm") for v in z) + " in file port order."
    return Network(network.f_hz, s, z, network.source, network.notes + (note,))


def _chain(s: np.ndarray) -> np.ndarray:
    out = np.empty_like(s)
    out[:, 0, 0] = 1 / s[:, 1, 0]
    out[:, 0, 1] = -s[:, 1, 1] / s[:, 1, 0]
    out[:, 1, 0] = s[:, 0, 0] / s[:, 1, 0]
    out[:, 1, 1] = s[:, 0, 1] - s[:, 0, 0] * s[:, 1, 1] / s[:, 1, 0]
    return out


def cascade(first: Network, second: Network, f_hz=None) -> Network:
    """Connect first port 2 to second port 1 using wave-chain matrices at matched references."""
    if first.ports != 2 or second.ports != 2:
        raise ValueError("cascade requires two two-port networks")
    if f_hz is not None:
        first, second = interpolate(first, f_hz), interpolate(second, f_hz)
    if not np.array_equal(first.f_hz, second.f_hz):
        raise ValueError("cascade grids must match; supply a common frequency grid explicitly")
    second = renormalize(second, [first.z0_ohm[1], second.z0_ohm[1]])
    a, b = first.s, second.s
    den = 1 - a[:, 1, 1] * b[:, 0, 0]
    if np.any(den == 0):
        raise ValueError("cascade connection is singular at a supplied frequency")
    s = np.empty_like(a)
    regular = (a[:, 1, 0] != 0) & (b[:, 1, 0] != 0)
    t = _chain(a[regular]) @ _chain(b[regular])
    s[regular, 0, 0] = t[:, 1, 0] / t[:, 0, 0]
    s[regular, 1, 0] = 1 / t[:, 0, 0]
    s[regular, 1, 1] = -t[:, 0, 1] / t[:, 0, 0]
    s[:, 0, 1] = a[:, 0, 1] * b[:, 0, 1] / den
    k = ~regular
    s[k, 0, 0] = a[k, 0, 0] + a[k, 0, 1] * b[k, 0, 0] * a[k, 1, 0] / den[k]
    s[k, 1, 0] = b[k, 1, 0] * a[k, 1, 0] / den[k]
    s[k, 1, 1] = b[k, 1, 1] + b[k, 1, 0] * a[k, 1, 1] * b[k, 0, 1] / den[k]
    return Network(first.f_hz, s, [first.z0_ohm[0], second.z0_ohm[1]],
                   f"{first.source or 'first network'} then {second.source or 'second network'}",
                   first.notes + second.notes + ("Port 2 connected to port 1; wave-chain cascade with isolation fallback.",))


def _port(network: Network, port: int) -> int:
    if not isinstance(port, int) or not 1 <= port <= network.ports:
        raise ValueError(f"port must be an integer from 1 to {network.ports}")
    return port - 1


def _analysis(network, values, label, unit, formula, limit, minimum, context, refs, extra_inputs=None,
              undefined=False) -> Result:
    if limit is not None and not np.isfinite(limit):
        raise ValueError("limit must be finite when supplied")
    k = int(np.argmin(values) if minimum else np.argmax(values))
    value, frequency = float(values[k]), float(network.f_hz[k])
    if undefined:
        value = float("nan")
    side = "at least" if minimum else "at most"
    wanted = f"{side} {fmt(limit, unit)}" if limit is not None else "supply a limit"
    inputs = {"f_start": Quantity(network.f_hz[0], "Hz", label="First model frequency"),
              "f_stop": Quantity(network.f_hz[-1], "Hz", label="Last model frequency"),
              **{f"reference_{i + 1}": Quantity(z, "ohm", label=f"Port {i + 1} reference resistance")
                 for i, z in enumerate(network.z0_ohm)}, **(extra_inputs or {})}
    if limit is not None:
        inputs["limit"] = Quantity(limit, unit, label=f"{label} limit")
    verdict, reason = Verdict.INFO, "no limit supplied"
    summary = f"The worst {label.lower()} is {fmt(value, unit)} at {fmt(frequency, 'Hz')}."
    if np.isinf(value):
        explanation = {"Return loss": "a perfect match", "Insertion loss": "zero transmission",
                       "VSWR": "total or greater reflection"}[label]
        summary += f" This is infinite because the model has {explanation}; the display uses n/a for infinity."
    if undefined:
        verdict, reason = Verdict.UNKNOWN, "VSWR is undefined when the reflection magnitude exceeds 1"
        peak = extra_inputs["reflection_peak"].value
        summary += (f" Reflection magnitude reaches {fmt(peak)}, above 1, so passive VSWR does not describe this "
                    "port; check the model and bias.")
    if limit is None:
        summary += f" Supply a {label.lower()} limit from the board requirement, datasheet or stated engineering judgment."
    elif not undefined:
        good = value >= limit if minimum else value <= limit
        verdict = Verdict.PASS if good else Verdict.FAIL
        reason = f"{fmt(value, unit)} against {wanted}"
        summary += f" We want {wanted}; this model {'is within' if good else 'is outside'} that limit at the sampled frequencies."
    markers = [Marker("Worst sample", x=frequency, y=value, unit=unit)]
    if limit is not None:
        markers.append(Marker("Supplied limit", y=limit, unit=unit))
    return Result(
        name=f"Touchstone {label.lower()}", formula=formula, inputs=inputs,
        outputs={"worst": Quantity(value, unit, "undefined for reflection above 1" if undefined else "",
                                    label=f"Worst {label.lower()}"),
                 "f_worst": Quantity(frequency, "Hz", label="Frequency of worst sample")},
        verdict=verdict, reason=reason, refs=refs,
        assumptions=((f"Source: {network.source}" if network.source else "Source provenance must be recorded by the reviewer"),
                     "Other ports terminated in their listed reference resistances; sampled frequencies only",
                     "Model bias, temperature, port order and reference plane require reviewer verification") + network.notes,
        plots=(plot_from_arrays(label, "Frequency", "Hz", network.f_hz, [(label, unit, values)],
                                x_log=bool(network.f_hz[0] > 0), markers=markers, caption=summary),),
        summary=summary, key=(Key("worst", wanted), Key("f_worst")),
    ).in_context(context)


def return_loss(network: Network, port: int = 1, min_return_loss_db: float | None = None,
                context: str = "nominal") -> Result:
    """Minimum return loss across the model grid with the other ports matched."""
    i = _port(network, port)
    with np.errstate(divide="ignore"):
        values = -20 * np.log10(np.abs(network.s[:, i, i]))
    return _analysis(network, values, "Return loss", "dB", "RL = -20 log10(abs(Sii))", min_return_loss_db,
                     True, context, (TS, WAVES), {"port": Quantity(port, "count", label="Port checked")})


def insertion_loss(network: Network, input_port: int = 1, output_port: int = 2,
                   max_insertion_loss_db: float | None = None, context: str = "nominal") -> Result:
    """Maximum matched-port insertion loss; negative loss denotes gain."""
    i, j = _port(network, input_port), _port(network, output_port)
    if i == j:
        raise ValueError("insertion loss requires different input and output ports")
    with np.errstate(divide="ignore"):
        values = -20 * np.log10(np.abs(network.s[:, j, i]))
    return _analysis(network, values, "Insertion loss", "dB", "IL = -20 log10(abs(Sout,in))",
                     max_insertion_loss_db, False, context, (TS, WAVES),
                     {"input_port": Quantity(input_port, "count", label="Driven port"),
                      "output_port": Quantity(output_port, "count", label="Receiving port")})


def vswr(network: Network, port: int = 1, max_vswr: float | None = None, context: str = "nominal") -> Result:
    """Maximum passive voltage standing wave ratio; reflection above unity is unknown."""
    if max_vswr is not None and max_vswr < 1:
        raise ValueError("VSWR limit must be at least 1")
    i = _port(network, port)
    magnitude = np.abs(network.s[:, i, i])
    with np.errstate(divide="ignore"):
        values = np.where(magnitude <= 1, (1 + magnitude) / (1 - magnitude), np.inf)
    return _analysis(network, values, "VSWR", "", "VSWR = (1 + abs(Sii))/(1 - abs(Sii)), abs(Sii) <= 1",
                     max_vswr, False, context, (WAVES,),
                     {"port": Quantity(port, "count", label="Port checked"),
                      "reflection_peak": Quantity(float(np.max(magnitude)), "", label="Largest reflection magnitude")},
                     undefined=bool(np.any(magnitude > 1)))


def passivity(network: Network, max_singular_value: float | None = None, context: str = "nominal") -> Result:
    """Maximum singular value of S; supply 1 for the mathematical passive boundary."""
    if max_singular_value is not None and max_singular_value < 0:
        raise ValueError("singular value limit must be nonnegative")
    values = np.linalg.svd(network.s, compute_uv=False)[:, 0]
    return _analysis(network, values, "Singular value", "", "sigma_max(S) <= supplied limit; passive boundary = 1",
                     max_singular_value, False, context, (PASSIVITY, WAVES))
