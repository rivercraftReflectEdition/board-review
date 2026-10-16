"""Synthetic Touchstone files checked against circuit algebra and explicit format rules."""

import json

import numpy as np
import pytest

from boardreview.calc.base import Verdict, plain_problems
from boardreview.sim import touchstone as ts
from boardreview.report.plain import calc_block


def _write(tmp_path, f_hz, s, form="RI", unit="HZ", z0_ohm=50):
    path = tmp_path / "synthetic.s2p"
    lines = ["! Synthetic circuit, no manufacturer model", f"# {unit} S {form} R {z0_ohm}"]
    for frequency, matrix in zip(f_hz, s):
        numbers = [frequency / ts.UNITS[unit]]
        for value in matrix.flatten(order="F"):
            if form == "RI":
                numbers.extend([value.real, value.imag])
            else:
                magnitude = abs(value) if form == "MA" else 20 * np.log10(abs(value))
                numbers.extend([magnitude, np.degrees(np.angle(value))])
        lines.append(" ".join(f"{value:.17g}" for value in numbers) + " ! frequency record")
    path.write_text("\n".join(lines), encoding="utf-8")
    return ts.read_touchstone(path)


def _attenuator(tmp_path, amplitude=0.5, reflection=0):
    s = np.array([[[reflection, amplitude], [amplitude, reflection]]] * 2, dtype=complex)
    return _write(tmp_path, [1e6, 3e6], s)


def _series_cap(tmp_path, c_f=1e-9):
    f = np.array([1e6, 2e6, 4e6])
    impedance = 1 / (2j * np.pi * f * c_f)
    reflection = impedance / (100 + impedance)
    transmission = 100 / (100 + impedance)
    s = np.zeros((len(f), 2, 2), complex)
    s[:, 0, 0] = s[:, 1, 1] = reflection
    s[:, 0, 1] = s[:, 1, 0] = transmission
    return _write(tmp_path, f, s)


@pytest.mark.parametrize("unit", ["HZ", "KHZ", "MHZ", "GHZ"])
@pytest.mark.parametrize("form", ["RI", "MA", "DB"])
def test_units_formats_and_complex_phase(tmp_path, unit, form):
    original = np.array([[[0.1j, -0.2j], [0.3 + 0.4j, -0.25]]] * 2)
    network = _write(tmp_path, [1e6, 3e6], original, form, unit, 75)
    np.testing.assert_allclose(network.s, original, atol=1e-15, rtol=1e-14)
    np.testing.assert_array_equal(network.f_hz, [1e6, 3e6])
    np.testing.assert_array_equal(network.z0_ohm, [75, 75])
    assert network.source.endswith("synthetic.s2p")


def test_defaults_comments_later_option_and_continuations():
    network = ts.parse_touchstone("""! MA, GHz, 50 ohm defaults
#
1 .1 90 .2 -90
 .3 180 .4 0
# HZ Z RI R 75
2 .5 0 .6 0 .7 0 .8 0 ! retained first options
""", source="synthetic.s2p")
    np.testing.assert_allclose(network.s[0], [[0.1j, -0.3], [-0.2j, 0.4]], atol=1e-15)
    np.testing.assert_array_equal(network.f_hz, [1e9, 2e9])
    assert "ignored" in network.notes[0]


@pytest.mark.parametrize("ports", [1, 3, 4])
def test_legacy_port_count_and_row_major_order(ports):
    expected = np.arange(1, ports * ports + 1).reshape(ports, ports) / 20
    rows = [" ".join(f"{v} 0" for v in row) for row in expected]
    text = "# MHz S RI R 50\n1 " + "\n".join(rows)
    network = ts.parse_touchstone(text, source=f"synthetic.s{ports}p")
    np.testing.assert_allclose(network.s[0], expected, atol=1e-15)


@pytest.mark.parametrize("order,expected", [("21_12", [[.1, .3], [.2, .4]]),
                                            ("12_21", [[.1, .2], [.3, .4]])])
def test_v2_two_port_order_and_reference_continuation(order, expected):
    text = f"""[Version] 2.0
# MHz S RI R 50
[Number of Ports] 2
[Number of Frequencies] 1
[Reference] 50
75
[Two-Port Data Order] {order}
[Network Data]
1 .1 0 .2 0 .3 0 .4 0
[End]
"""
    network = ts.parse_touchstone(text)
    np.testing.assert_allclose(network.s[0], expected, atol=1e-15)
    np.testing.assert_array_equal(network.z0_ohm, [50, 75])


@pytest.mark.parametrize("ports", [1, 2, 3, 4])
@pytest.mark.parametrize("matrix", ["Full", "Lower", "Upper"])
def test_v21_matrix_formats(ports, matrix):
    expected = np.array([[complex(i + j, i + j + 1) / 20 for j in range(ports)] for i in range(ports)])
    pairs = [(i, j) for i in range(ports) for j in range(ports)
             if matrix == "Full" or (matrix == "Lower" and i >= j) or (matrix == "Upper" and i <= j)]
    numbers = ["1"] + [str(v) for i, j in pairs for v in (expected[i, j].real, expected[i, j].imag)]
    text = f"""[Version] 2.1
# HZ S RI R 50
[Number of Ports] {ports}
[Matrix Format] {matrix}
[Begin Information]
Arbitrary manufacturer metadata, not numeric data.
[End Information]
[Network Data]
""" + "\n".join(numbers) + "\n[End]"
    network = ts.parse_touchstone(text)
    np.testing.assert_allclose(network.s[0], expected, atol=1e-15)


@pytest.mark.parametrize("version", ["1.0", "2.0"])
@pytest.mark.parametrize("parameter", ["Z", "Y", "H", "G"])
def test_parameter_types_against_series_and_shunt_resistors(version, parameter):
    # Z=diag(100 ohm) and Y=diag(.01 S) are two independent loads: gamma=(100-50)/(100+50).
    # H describes a series 50 ohm resistor; G describes a shunt .02 S resistor.
    legacy = version.startswith("1")
    matrices = {"Z": [[2 if legacy else 100, 0], [0, 2 if legacy else 100]],
                "Y": [[.5 if legacy else .01, 0], [0, .5 if legacy else .01]],
                "H": [[1 if legacy else 50, 1], [-1, 0]],
                "G": [[1 if legacy else .02, -1], [1, 0]]}
    expected = {"Z": [[1/3, 0], [0, 1/3]], "Y": [[1/3, 0], [0, 1/3]],
                "H": [[1/3, 2/3], [2/3, 1/3]], "G": [[-1/3, 2/3], [2/3, -1/3]]}[parameter]
    numbers = " ".join(f"{v} 0" for v in np.array(matrices[parameter]).flatten(order="F"))
    prefix = "" if legacy else "[Version] 2.0\n[Number of Ports] 2\n"
    body = "" if legacy else "[Network Data]\n"
    end = "" if legacy else "\n[End]"
    network = ts.parse_touchstone(prefix + f"# Hz {parameter} RI R 50\n" + body + "1 " + numbers + end, ports=2)
    np.testing.assert_allclose(network.s[0], expected, atol=1e-15)


def test_v2_unequal_references_z_conversion():
    text = """[Version] 2.0
[Number of Ports] 2
# Hz Z RI R 50
[Reference] 50 100
[Network Data]
1 100 0 0 0 0 0 200 0
[End]"""
    np.testing.assert_allclose(ts.parse_touchstone(text).s[0], np.eye(2) / 3, atol=1e-15)


@pytest.mark.parametrize("v2", [False, True])
def test_noise_blocks_skipped_with_note(v2):
    if v2:
        text = """[Version] 2.0
[Number of Ports] 2
[Number of Frequencies] 2
[Number of Noise Frequencies] 2
# Hz S RI R 50
[Network Data]
1 0 0 .5 0 .5 0 0 0
3 0 0 .5 0 .5 0 0 0
[Noise Data]
1 2 .2 30 .1
3 2 .2 30 .1
[End]"""
    else:
        text = "# Hz S RI R 50\n1 0 0 .5 0 .5 0 0 0\n3 0 0 .5 0 .5 0 0 0\n1 2 .2 30 .1\n3 2 .2 30 .1"
    network = ts.parse_touchstone(text, ports=2)
    np.testing.assert_array_equal(network.f_hz, [1, 3])
    assert any("Noise data skipped" in note for note in network.notes)
    result = ts.insertion_loss(network)
    assert any("Noise data skipped" in note for note in result.assumptions)


def test_interpolation_cartesian_and_no_extrapolation(tmp_path):
    original = np.array([[[0, 1], [1, 0]], [[0, -1j], [-1j, 0]]])
    network = _write(tmp_path, [1e6, 3e6], original)
    interpolated = ts.interpolate(network, [1e6, 2e6, 3e6])
    np.testing.assert_allclose(interpolated.s[1], [[0, .5-.5j], [.5-.5j, 0]], atol=1e-15)
    assert interpolated.notes and not network.notes
    for grid in ([0, 1e6], [3e6, 4e6], [], [2e6, 1e6], [1e6, 1e6], [np.nan]):
        with pytest.raises(ValueError):
            ts.interpolate(network, grid)


def test_attenuator_analysis_and_cascade_closed_form(tmp_path):
    network = _attenuator(tmp_path)
    cascaded = ts.cascade(network, network)
    np.testing.assert_allclose(cascaded.s[:, 1, 0], .25, atol=1e-15)
    np.testing.assert_allclose(cascaded.s[:, 0, 0], 0, atol=1e-15)
    result = ts.insertion_loss(cascaded)
    assert result.outputs["worst"].value == pytest.approx(40 * np.log10(2), abs=1e-12)
    assert ts.vswr(network).outputs["worst"].value == pytest.approx(1, abs=1e-15)


@pytest.mark.parametrize("c_f,expected_db", [(1e-9, 5.48), (10e-9, .109), (100e-9, .0011)])
def test_w28_series_capacitor_closed_form(tmp_path, c_f, expected_db):
    # Plan W28: a series C between 50 ohm ports. Power ratio = 1/(1+(1/(2*pi*f*C*100))**2).
    network = _series_cap(tmp_path, c_f)
    result = ts.insertion_loss(network)
    independent_db = 10 * np.log10(1 + (1 / (2 * np.pi * 1e6 * c_f * 100)) ** 2)
    assert result.outputs["worst"].value == pytest.approx(independent_db, abs=1e-12)
    assert result.outputs["worst"].value == pytest.approx(expected_db, abs=.005)
    cascaded = ts.cascade(network, network)
    impedance = 2 / (2j * np.pi * network.f_hz * c_f)
    np.testing.assert_allclose(cascaded.s[:, 1, 0], 100 / (100 + impedance), atol=1e-14)
    np.testing.assert_allclose(cascaded.s[:, 0, 0], impedance / (100 + impedance), atol=1e-14)


def test_lossless_line_cascade_and_reference_change_closed_form(tmp_path):
    f, delay_s = np.array([1e6, 2e6, 3e6]), 25e-9
    phase = 2 * np.pi * f * delay_s
    original = np.zeros((3, 2, 2), complex)
    original[:, 0, 1] = original[:, 1, 0] = np.exp(-1j * phase)
    network = _write(tmp_path, f, original)
    cascaded = ts.cascade(network, network)
    np.testing.assert_allclose(cascaded.s[:, 1, 0], np.exp(-2j * phase), atol=1e-14)
    assert ts.insertion_loss(network).outputs["worst"].value == pytest.approx(0, abs=1e-14)
    changed = ts.renormalize(network, 75)
    # Lossless line ABCD: A=D=cos(theta), B=j*50*sin(theta), C=j*sin(theta)/50.
    den = 2 * np.cos(phase) + 1j * (50/75 + 75/50) * np.sin(phase)
    np.testing.assert_allclose(changed.s[:, 1, 0], 2 / den, atol=1e-14)
    np.testing.assert_allclose(changed.s[:, 0, 0], 1j * (50/75 - 75/50) * np.sin(phase) / den, atol=1e-14)
    assert ts.passivity(changed).outputs["worst"].value == pytest.approx(1, abs=1e-14)


def test_renormalize_unequal_ports_and_singular_impedance_models(tmp_path):
    thru = _attenuator(tmp_path, 1)
    changed = ts.renormalize(thru, [25, 100])
    # Direct junction between real references: S11=(R2-R1)/(R1+R2), S21=2*sqrt(R1*R2)/(R1+R2).
    np.testing.assert_allclose(changed.s[0], [[.6, .8], [.8, -.6]], atol=1e-15)
    open_short = ts.Network([1], [[[1, 0], [0, -1]]], [50, 50])
    np.testing.assert_allclose(ts.renormalize(open_short, [25, 100]).s, open_short.s, atol=1e-15)
    load = ts.Network([1], [[[0]]], [50])
    assert ts.renormalize(load, 75).s[0, 0, 0] == pytest.approx(-.2, abs=1e-15)


def test_cascade_matches_internal_references_and_keeps_external_references(tmp_path):
    first = _series_cap(tmp_path)
    second = ts.renormalize(first, [75, 100])
    expected = ts.renormalize(ts.cascade(first, first), [50, 100])
    actual = ts.cascade(first, second)
    np.testing.assert_allclose(actual.s, expected.s, atol=1e-14)
    np.testing.assert_array_equal(actual.z0_ohm, [50, 100])
    sparse = ts.interpolate(first, [1e6, 4e6])
    with pytest.raises(ValueError, match="grids must match"):
        ts.cascade(first, sparse)
    assert len(ts.cascade(first, sparse, [1e6, 4e6]).f_hz) == 2


def test_zero_transmission_cascade_and_singular_connection(tmp_path):
    blocked = _attenuator(tmp_path, 0, .25)
    result = ts.cascade(blocked, _attenuator(tmp_path))
    np.testing.assert_allclose(result.s[:, 0, 0], .25, atol=1e-15)
    np.testing.assert_allclose(result.s[:, 1, 0], 0, atol=1e-15)
    with pytest.raises(ValueError, match="connection is singular"):
        ts.cascade(_attenuator(tmp_path, 0, 1), _attenuator(tmp_path, 0, 1))


@pytest.mark.parametrize("analysis,kwargs,expected,unit", [
    (ts.return_loss, {"min_return_loss_db": 10}, 20, "dB"),
    (ts.insertion_loss, {"max_insertion_loss_db": 7}, 20*np.log10(2), "dB"),
    (ts.vswr, {"max_vswr": 1.3}, 1.1/.9, ""),
    (ts.passivity, {"max_singular_value": 1}, .6, ""),
])
def test_analysis_verdicts_and_plain_results(tmp_path, analysis, kwargs, expected, unit):
    network = _attenuator(tmp_path, .5, .1)
    results = [analysis(network), analysis(network, **kwargs), analysis(network, **kwargs, context="worst_case")]
    failing = dict(kwargs)
    failing[next(iter(kwargs))] = 30 if analysis is ts.return_loss else 1.1 if analysis is ts.vswr else .2
    results.append(analysis(network, **failing, context="worst_case"))
    assert [r.verdict for r in results] == [Verdict.INFO, Verdict.UNKNOWN, Verdict.PASS, Verdict.FAIL]
    for r in results:
        assert r.outputs["worst"].value == pytest.approx(expected, abs=1e-12)
        assert r.outputs["worst"].unit == unit
        assert plain_problems(r) == []
        assert r.context and r.key and r.plots
        assert "<svg" in calc_block(r.to_dict(), "synthetic")
        json.dumps(r.to_dict(), allow_nan=False)
    assert "requirement" in results[0].summary
    with pytest.raises(ValueError, match="limit must be finite"):
        analysis(network, **{next(iter(kwargs)): np.nan})


def test_passivity_uses_singular_values_instead_of_individual_entries():
    # Identical rows have singular values 1.2 and 0, though each row's squared norm is only .72.
    network = ts.Network([1, 2], [[[.6, .6], [.6, .6]]] * 2, [50, 50])
    result = ts.passivity(network, 1, context="worst_case")
    assert result.outputs["worst"].value == pytest.approx(1.2, abs=1e-14)
    assert result.verdict is Verdict.FAIL
    assert plain_problems(result) == []


def test_perfect_match_is_infinite_return_loss_and_unity_vswr(tmp_path):
    network = _attenuator(tmp_path)
    result = ts.return_loss(network, min_return_loss_db=20, context="worst_case")
    assert result.verdict is Verdict.PASS
    assert np.isinf(result.outputs["worst"].value)
    assert ts.vswr(network).outputs["worst"].value == 1
    assert plain_problems(result) == []
    assert "<svg" in calc_block(result.to_dict(), "infinite-return-loss")
    json.dumps(result.to_dict(), allow_nan=False)


@pytest.mark.parametrize("reflection,expected", [(1, Verdict.FAIL), (1.1, Verdict.UNKNOWN)])
def test_vswr_total_and_active_reflection(tmp_path, reflection, expected):
    network = _attenuator(tmp_path, 0, reflection)
    result = ts.vswr(network, max_vswr=2, context="worst_case")
    assert result.verdict is expected
    assert (np.isinf if reflection == 1 else np.isnan)(result.outputs["worst"].value)
    if reflection > 1:
        assert "1.1" in result.summary and "undefined" in result.outputs["worst"].note
        without_limit = ts.vswr(network)
        assert without_limit.verdict is Verdict.UNKNOWN
        assert "Supply a vswr limit" in without_limit.summary
        assert plain_problems(without_limit) == []
    assert plain_problems(result) == []
    assert "<svg" in calc_block(result.to_dict(), "infinite-vswr")
    result = ts.insertion_loss(network, max_insertion_loss_db=1, context="worst_case")
    assert result.verdict is Verdict.FAIL
    assert np.isinf(result.outputs["worst"].value)
    assert plain_problems(result) == []


@pytest.mark.parametrize("text,ports", [
    ("# THZ S RI R 50\n1 0 0", 1), ("# Hz A RI R 50\n1 0 0", 1),
    ("# Hz S XY R 50\n1 0 0", 1), ("# Hz S RI R -50\n1 0 0", 1),
    ("# Hz S RI R 50 75\n1 0 0", 1), ("# Hz S RI\n1 0", 1),
    ("# Hz S RI\n1 nan 0", 1), ("# Hz S MA\n1 -1 0", 1),
    ("# Hz S DB\n1 99999 0", 1), ("# Hz S RI\n2 0 0\n1 0 0", 1),
    ("# Hz S RI\n1 0 0\n1 0 0", 1), ("", 2), ("# Hz S RI\n1 0 0", None),
    ("# Hz H RI\n1 0 0", 1), ("# Hz Z RI\n1 -1 0", 1),
    ("[Version] 3.0", 1), ("[Version] 2.0\n[Number of Ports] 3", 2),
    ("[Version] 2.0\n[Number of Ports] 2\n[Matrix Format] Other", 2),
    ("[Version] 2.0\n[Number of Ports] 2\n[Mixed-Mode Order] D1,2", 2),
    ("[Version] 2.0\n[Number of Ports] 2\n[Two-Port Data Order] 22_11", 2),
    ("[Version] 2.0\n[Number of Ports] 1\n[Reference] 50 75\n[End]", 1),
    ("[Version] 2.0\n[Number of Ports] 1\n1 0 0\n[End]", 1),
    ("[Version] 2.0\n[Number of Ports] 1\n[Network Data]\n1 0 0", 1),
    ("[Version] 2.0\n[Network Data]\n1 0 0\n[End]", 1),
    ("[Version] 2.0\n[Number of Ports] 1\n[Number of Frequencies] 2\n[Network Data]\n1 0 0\n[End]", 1),
])
def test_reader_rejects_malformed_or_unsupported_data(text, ports):
    with pytest.raises(ValueError):
        ts.parse_touchstone(text, ports=ports)


def test_bad_references_ports_and_network_shapes(tmp_path):
    network = _attenuator(tmp_path)
    for references in ([50, -50], [50, np.inf], [50], [50+1j, 50], [[50, 50]]):
        with pytest.raises(ValueError):
            ts.renormalize(network, references)
    for port in (0, 3, 1.5):
        with pytest.raises(ValueError):
            ts.return_loss(network, port=port)
    with pytest.raises(ValueError):
        ts.insertion_loss(network, output_port=1)
    with pytest.raises(ValueError):
        ts.Network([1, 2], [[[0]]], [50])
    with pytest.raises(ValueError):
        ts.Network([1], [[[np.nan]]], [50])
    one_port = ts.Network([1], [[[0]]], [50])
    with pytest.raises(ValueError):
        ts.cascade(one_port, network)
    with pytest.raises(ValueError):
        ts.passivity(network, -1)
    with pytest.raises(ValueError):
        ts.vswr(network, max_vswr=.5)
    with pytest.raises(ValueError):
        network.s[0, 0, 0] = .5


def test_invalid_reference_keyword_noise_ports_and_extension_conflict():
    with pytest.raises(ValueError, match="source extension"):
        ts.parse_touchstone("# Hz S RI R 50\n1 0 0", ports=1, source="synthetic.s2p")
    for extra in ("[Reference]\n", "[Noise Data]\n1 2 .1 0 .1\n"):
        with pytest.raises(ValueError):
            ts.parse_touchstone("[Version] 2.0\n[Number of Ports] 1\n# Hz S RI R 50\n"
                               "[Network Data]\n1 0 0\n" + extra + "[End]")


def test_reverse_isolation_is_preserved_during_cascade():
    # An exact zero reverse path must remain zero even with large reflected terms in the chain matrix.
    network = ts.Network([1], [[[.9, 0], [.001, .9]]], [50, 50])
    actual = ts.cascade(network, network)
    assert actual.s[0, 0, 1] == 0
    assert actual.s[0, 1, 0] == pytest.approx(1e-6 / (1 - .9**2), rel=1e-14)
