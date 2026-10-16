"""Jitter plan W1 to W9, analytic integration checks, limits and plain-language results."""

import json
import math

import numpy as np
import pytest
from scipy.integrate import quad

from boardreview.calc import jitter
from boardreview.calc.base import Band, Plot, Verdict, plain_problems
from boardreview.report import plain, svgplot

PN = [(1e3, -120), (1e4, -130), (1e5, -135), (1e6, -145), (1e7, -150), (2e7, -150)]


def value(result, name):
    return result.outputs[name].value


def test_w1_jitter_snr_aperture_and_converter_loss():
    # MT-008 Rev A p.2; plan W1. SNR noise powers add, not their dB values.
    r = jitter.snr_jitter(100e6, 150e-15)
    assert value(r, "snr_j_db") == pytest.approx(80.51, abs=0.005)
    aperture = jitter.snr_jitter(100e6, 150e-15, 70e-15)
    assert value(aperture, "total_s") == pytest.approx(165.5e-15, abs=0.05e-15)
    assert value(aperture, "snr_j_db") == pytest.approx(79.66, abs=0.005)
    combined = jitter.snr_jitter(100e6, 150e-15, snr_adc_db=75, loss_limit_db=1,
                                loss_fail_db=3, context="worst_case")
    expected = -10 * math.log10(10 ** -7.5 + (2 * math.pi * 100e6 * 150e-15) ** 2)
    assert value(combined, "snr_total_db") == pytest.approx(expected, abs=1e-10)
    assert value(combined, "snr_total_db") == pytest.approx(73.92, abs=0.005)
    assert value(combined, "loss_db") == pytest.approx(1.08, abs=0.005)
    assert combined.verdict is Verdict.MARGINAL


def test_w2_snr_and_required_jitter():
    # MT-008 Rev A p.2; 70 dB means a noise amplitude ratio of 10^(-70/20).
    assert value(jitter.snr_jitter(1e9, 100e-15), "snr_j_db") == pytest.approx(64.0, abs=0.04)
    r = jitter.snr_jitter(200e6, 100e-15, snr_min_db=70)
    assert value(r, "jitter_allowed_s") == pytest.approx(251.6e-15, abs=0.05e-15)
    assert value(r, "jitter_allowed_s") == pytest.approx(10 ** -3.5 / (2 * math.pi * 200e6), rel=1e-12)


def test_w3_piecewise_phase_noise_matches_independent_quadrature():
    # Plan W3; quadrature on each log-frequency interval is independent of the analytic power-law integral.
    def density(log_f):
        f = math.exp(log_f)
        level = np.interp(log_f, np.log(np.array(PN)[:, 0]), np.array(PN)[:, 1])
        return 10 ** (level / 10) * f

    edges = [12e3, 100e3, 1e6, 10e6, 20e6]
    expected_area = sum(quad(density, math.log(a), math.log(b), epsabs=1e-20, epsrel=1e-11)[0]
                        for a, b in zip(edges[:-1], edges[1:]))
    r = jitter.pn_to_jitter(PN, 12e3, 20e6, 100e6)
    assert value(r, "area_dbc") == pytest.approx(10 * math.log10(expected_area), abs=1e-9)
    assert value(r, "area_dbc") == pytest.approx(-74.55, abs=0.005)
    assert value(r, "sigma_rad") == pytest.approx(265e-6, abs=0.2e-6)
    assert value(r, "jitter_s") == pytest.approx(421.6e-15, abs=0.1e-15)


@pytest.mark.parametrize("f0_hz,expected_s", [(100e6, 318.2e-15), (156.25e6, 203.7e-15)])
def test_w3_flat_phase_noise_closed_form(f0_hz, expected_s):
    # MT-008 Rev A p.4: flat SSB density integrated over 19.988 MHz.
    r = jitter.pn_to_jitter([(12e3, -150), (20e6, -150)], 12e3, 20e6, f0_hz)
    expected = math.sqrt(2 * 1e-15 * (20e6 - 12e3)) / (2 * math.pi * f0_hz)
    assert value(r, "jitter_s") == pytest.approx(expected, rel=1e-12)
    assert value(r, "jitter_s") == pytest.approx(expected_s, abs=0.05e-15)
    assert value(r, "area_dbc") == pytest.approx(-76.99, abs=0.005)


def test_w4_rss():
    # Plan W4: sqrt(300^2 + 100^2 + 80^2) fs.
    r = jitter.rss([300e-15, 100e-15, 80e-15])
    assert value(r, "total_s") == pytest.approx(math.sqrt(106400) * 1e-15, rel=1e-12)
    assert value(r, "total_s") == pytest.approx(326.2e-15, abs=0.05e-15)


@pytest.mark.parametrize("ratio,expected_db", [(100, -110), (0.01, -190), (1, -150)])
def test_w5_multiplication_and_division(ratio, expected_db):
    # SNAA106C printed p.1 and 12: ideal phase deviation scales by the frequency ratio.
    assert value(jitter.multiply(-150, ratio), "dbc_hz") == pytest.approx(expected_db, abs=1e-12)


def test_w6_pm_spur_pair_rms_jitter():
    # AN491 Rev 0.2 p.6 eq.1, one -70 dBc sideband of a symmetric PM pair.
    r = jitter.spur_to_jitter(-70, 100e6)
    assert value(r, "jitter_s") == pytest.approx(712e-15, abs=0.3e-15)
    # Each sideband amplitude is beta/2; sinusoidal phase RMS is beta/sqrt(2).
    beta = 2 * math.sqrt(1e-7)
    assert value(r, "jitter_s") == pytest.approx(beta / math.sqrt(2) / (2 * math.pi * 100e6), rel=1e-12)
    assert any("per sideband" in a for a in r.assumptions)


def test_w7_converter_spur_transfer():
    # AN-756 Rev 0 p.5 prints -66 dBc, 30.62 MHz and 78 MHz, giving -74.1 dBc.
    r = jitter.spur_transfer(-66, 30.62e6, 78e6)
    assert value(r, "spur_out_dbc") == pytest.approx(-74.1, abs=0.025)


@pytest.mark.parametrize("k_hz_per_v,fm_hz,expected_db", [(2e6, 1e6, -60), (1e6, 2e6, -72.04)])
def test_w8_supply_ripple_sidebands(k_hz_per_v, fm_hz, expected_db):
    # Plan W8, narrowband FM: beta = K * Vpeak / fm; each first sideband is beta/2.
    r = jitter.ripple_sideband(k_hz_per_v, 1e-3, fm_hz)
    assert value(r, "sideband_dbc") == pytest.approx(expected_db, abs=0.005)
    assert value(r, "small_angle_dbc") == pytest.approx(20 * math.log10(k_hz_per_v * 1e-3 / fm_hz / 2), abs=1e-12)


def test_large_modulation_uses_bessel_ratio():
    # Bessel power series at beta=1, independently summed without scipy.special.
    j0 = sum((-1) ** k * (0.5 ** (2 * k)) / math.factorial(k) ** 2 for k in range(15))
    j1 = sum((-1) ** k * (0.5 ** (2 * k + 1)) / (math.factorial(k) * math.factorial(k + 1)) for k in range(15))
    r = jitter.ripple_sideband(1e6, 1, 1e6)
    assert value(r, "sideband_dbc") == pytest.approx(20 * math.log10(j1 / j0), abs=1e-10)
    assert abs(value(r, "sideband_dbc") - value(r, "small_angle_dbc")) > 1


def test_w9_control_noise_conventions_and_ssc():
    # Wenzel VCXOs tutorial formula as transcribed in plan W9; one-sided phase PSD versus SSB L.
    r = jitter.vc_noise(10e6, 0.5e-6, 100e-9, 100)
    assert value(r, "s_phi_dbc_hz") == pytest.approx(-166.02, abs=0.005)
    assert value(r, "ssb_dbc_hz") == pytest.approx(-169.03, abs=0.005)
    assert value(r, "s_phi_dbc_hz") - value(r, "ssb_dbc_hz") == pytest.approx(10 * math.log10(2), abs=1e-12)
    assert r.outputs["s_phi_dbc_hz"].unit == "dB(rad^2/Hz)"
    # AN10005 Rev 1.2 p.5 and 7: estimated 14 dB, measured 13 dB.
    s = jitter.ssc_emi(0.02, 125e6, 100e3)
    assert value(s, "span_hz") == pytest.approx(2.5e6, abs=1e-6)
    assert value(s, "reduction_db") == pytest.approx(13.9794, abs=0.0001)


def test_inverse_offset_power_law_and_nearby_slope():
    # A/f density: integral is A ln(f2/f1). This is the exponent=-1 integration branch.
    for last_db in [-150, -150 + 1e-10]:
        r = jitter.pn_to_jitter([(1e3, -120), (1e6, last_db)], 2e3, 7e5, 100e6)
        expected_area = 1e-9 * math.log(7e5 / 2e3)
        assert value(r, "area_dbc") == pytest.approx(10 * math.log10(expected_area), abs=1e-8)


def test_mask_squares_amplitude_and_includes_its_breakpoints():
    # Flat L=1e-12 with H proportional to f below 10 kHz, then H=1.
    # A = 1e-12 * [integral((f/1e4)^2, 1e3..1e4) + (1e5-1e4)].
    r = jitter.pn_to_jitter([(1e3, -120), (1e5, -120)], 1e3, 1e5, 100e6,
                            mask_points_db=[(1e3, -20), (1e4, 0), (1e5, 0)])
    area = 1e-12 * ((1e4 ** 3 - 1e3 ** 3) / (3 * 1e8) + 9e4)
    assert value(r, "area_dbc") == pytest.approx(10 * math.log10(area), abs=1e-10)
    assert "mask2_hz" in r.inputs
    assert len(r.plots[0].series) == 2


SAMPLES = {
    "calc.jitter.snr_jitter": [
        lambda: jitter.snr_jitter(100e6, 150e-15),
        lambda: jitter.snr_jitter(100e6, 150e-15, snr_adc_db=75, loss_limit_db=2, context="worst_case"),
        lambda: jitter.snr_jitter(100e6, 150e-15, snr_adc_db=75, loss_limit_db=1, loss_fail_db=3),
        lambda: jitter.snr_jitter(100e6, 150e-15, snr_adc_db=75, loss_limit_db=1),
        lambda: jitter.snr_jitter(100e6, 150e-15, snr_min_db=75),
        lambda: jitter.snr_jitter(100e6, 150e-15, snr_min_db=85),
        lambda: jitter.snr_jitter(100e6, 0, snr_adc_db=75, loss_limit_db=1),
        lambda: jitter.snr_jitter(100e6, 0),
        lambda: jitter.snr_jitter(100e6, 150e-15, snr_adc_db=75, snr_min_db=76),
    ],
}


def _samples():
    factories = {
        "pn_to_jitter": (lambda **kw: jitter.pn_to_jitter(PN, 12e3, 20e6, 100e6, **kw), "limit_s", 500e-15, 400e-15),
        "rss": (lambda **kw: jitter.rss([300e-15, 100e-15, 80e-15], **kw), "limit_s", 400e-15, 300e-15),
        "multiply": (lambda **kw: jitter.multiply(-150, 100, **kw), "limit_db", -100, -120),
        "spur_to_jitter": (lambda **kw: jitter.spur_to_jitter(-70, 100e6, **kw), "limit_s", 800e-15, 600e-15),
        "spur_transfer": (lambda **kw: jitter.spur_transfer(-66, 30.62e6, 78e6, **kw), "limit_db", -70, -80),
        "ripple_sideband": (lambda **kw: jitter.ripple_sideband(2e6, 1e-3, 1e6, **kw), "limit_db", -50, -70),
        "vc_noise": (lambda **kw: jitter.vc_noise(10e6, 0.5e-6, 100e-9, 100, **kw), "limit_db", -160, -180),
        "ssc_emi": (lambda **kw: jitter.ssc_emi(0.02, 125e6, 100e3, **kw), "min_reduction_db", 10, 20),
    }
    for name, (factory, arg, passing, failing) in factories.items():
        SAMPLES[f"calc.jitter.{name}"] = [
            lambda factory=factory: factory(),
            lambda factory=factory, arg=arg, passing=passing: factory(**{arg: passing}, context="worst_case"),
            lambda factory=factory, arg=arg, failing=failing: factory(**{arg: failing}),
            lambda factory=factory, arg=arg, passing=passing: factory(**{arg: passing}),
        ]
    SAMPLES["calc.jitter.rss"].append(lambda: jitter.rss([350e-15], 300e-15, marginal_limit_s=400e-15))
    SAMPLES["calc.jitter.pn_to_jitter"].append(
        lambda: jitter.pn_to_jitter(PN, 12e3, 20e6, 100e6, limit_s=400e-15, marginal_limit_s=500e-15))
    SAMPLES["calc.jitter.ripple_sideband"].append(
        lambda: jitter.ripple_sideband(2e6, 1e-3, 1e6, limit_db=-50, loop_bandwidth_hz=2e6))


_samples()


@pytest.mark.parametrize("name,index", [(name, i) for name, fns in SAMPLES.items() for i in range(len(fns))])
def test_all_verdicts_read_plainly_and_serialize(name, index):
    r = SAMPLES[name][index]()
    assert plain_problems(r) == [], r.summary
    assert r.context
    assert r.key and r.refs and r.reason
    json.dumps(r.to_dict(name), allow_nan=False)


@pytest.mark.parametrize("name", SAMPLES)
def test_no_limit_is_info_and_limits_reach_pass_fail_and_unknown(name):
    results = [make() for make in SAMPLES[name]]
    assert results[0].verdict is Verdict.INFO
    assert {Verdict.PASS, Verdict.FAIL, Verdict.UNKNOWN} <= {r.verdict for r in results}
    assert "limit" in results[0].summary or "minimum SNR" in results[0].summary


def test_snr_multiple_limits_aperture_budget_and_baseline_ceiling():
    r = jitter.snr_jitter(100e6, 150e-15, snr_adc_db=75, snr_min_db=73,
                          loss_limit_db=2, context="worst_case")
    assert r.verdict is Verdict.PASS
    assert value(r, "jitter_allowed_s") == pytest.approx(
        math.sqrt(10 ** -7.3 - 10 ** -7.5) / (2 * math.pi * 100e6), rel=1e-12)
    r = jitter.snr_jitter(100e6, 150e-15, snr_adc_db=75, snr_min_db=74,
                          loss_limit_db=2, context="worst_case")
    assert r.verdict is Verdict.FAIL
    assert plain_problems(r) == []
    assert r.inputs["limit"].value == 2 and r.inputs["snr_min_db"].value == 74
    r = jitter.snr_jitter(100e6, 0, snr_adc_db=75, snr_min_db=76)
    assert r.verdict is Verdict.FAIL and "jitter_allowed_s" not in r.outputs


def test_explicit_jitter_margin_is_not_a_hidden_default():
    assert jitter.rss([90e-15], 100e-15, context="worst_case").verdict is Verdict.PASS
    assert jitter.rss([90e-15], 80e-15, marginal_limit_s=100e-15).verdict is Verdict.MARGINAL
    assert jitter.rss([101e-15], 80e-15, marginal_limit_s=100e-15).verdict is Verdict.FAIL
    assert jitter.rss([100e-15], 100e-15, context="worst_case").verdict is Verdict.PASS


def test_negative_pushing_has_the_same_sideband_power_and_above_loop_is_allowed():
    r = jitter.ripple_sideband(-2e6, 1e-3, 1e6, limit_db=-50,
                              loop_bandwidth_hz=1e5, context="worst_case")
    assert r.verdict is Verdict.PASS
    assert value(r, "sideband_dbc") == pytest.approx(-60, abs=0.00001)
    assert plain_problems(r) == []


def test_plot_band_shades_svg_and_snr_curve_has_expected_slope():
    r = jitter.pn_to_jitter(PN, 12e3, 20e6, 100e6)
    p = r.plots[0]
    assert p.bands == (Band("Integrated offset band", 12e3, 20e6),)
    assert p.to_dict()["bands"][0]["x_min"] == 12e3
    svg = svgplot.plot_svg(p)
    assert 'class="pl-band"' in svg and 'opacity:0.12' in svg
    assert svg.index('class="pl-band"') < svg.index('class="pl-series"')
    assert 'class="pl-band"' in plain.calc_block(r.to_dict(), "jitter")
    assert "bands" not in Plot("Empty", "Offset", "Hz", (), ()).to_dict()
    snr_plot = jitter.snr_jitter(100e6, 150e-15, snr_adc_db=75).plots[0]
    f, y = np.array(snr_plot.x), np.array(snr_plot.series[0].y)
    assert np.interp(math.log10(1e9), np.log10(f), y) - np.interp(math.log10(100e6), np.log10(f), y) == pytest.approx(-20, abs=1e-10)
    assert len(snr_plot.series) == 2 and snr_plot.caption.endswith(".")


@pytest.mark.parametrize("make", [
    lambda: jitter.snr_jitter(100e6, 0),
    lambda: jitter.snr_jitter(100e6, 0, snr_adc_db=75),
    lambda: jitter.rss([0]),
    lambda: jitter.ripple_sideband(2e6, 0, 1e6),
    lambda: jitter.vc_noise(10e6, 0.5e-6, 0, 100),
    lambda: jitter.ssc_emi(0, 125e6, 100e3),
    lambda: jitter.ssc_emi(1e-6, 125e6, 100e3),
])
def test_zero_noise_and_unresolved_spread(make):
    r = make()
    assert plain_problems(r) == []
    json.dumps(r.to_dict(), allow_nan=False)
    if "reduction_db" in r.outputs:
        assert value(r, "reduction_db") == 0


@pytest.mark.parametrize("make", [
    lambda: jitter.snr_jitter(0, 100e-15),
    lambda: jitter.snr_jitter(1e8, -1e-15),
    lambda: jitter.snr_jitter(1e8, 1e-15, loss_limit_db=1),
    lambda: jitter.snr_jitter(1e8, 1e-15, snr_adc_db=75, loss_fail_db=3),
    lambda: jitter.snr_jitter(1e8, 1e-15, snr_adc_db=75, loss_limit_db=-1),
    lambda: jitter.pn_to_jitter([(1e3, -150)], 1e3, 1e4, 1e8),
    lambda: jitter.pn_to_jitter([(1e3, -150), (1e3, -140)], 1e3, 1e4, 1e8),
    lambda: jitter.pn_to_jitter([(1e4, -140), (1e3, -150)], 1e3, 1e4, 1e8),
    lambda: jitter.pn_to_jitter([(1e3, math.nan), (1e4, -150)], 1e3, 1e4, 1e8),
    lambda: jitter.pn_to_jitter([(1e3, -150), (1e4, -150)], 100, 1e4, 1e8),
    lambda: jitter.pn_to_jitter(PN, 1e4, 1e4, 1e8),
    lambda: jitter.pn_to_jitter(PN, 1e4, 1e6, 1e8, mask_points_db=[(1e5, 0), (1e6, 0)]),
    lambda: jitter.rss([]),
    lambda: jitter.rss([-1]),
    lambda: jitter.rss([math.inf]),
    lambda: jitter.rss([1e-12], -1),
    lambda: jitter.rss([1e-12], marginal_limit_s=1e-12),
    lambda: jitter.rss([1e-12], 1e-12, marginal_limit_s=0.5e-12),
    lambda: jitter.multiply(-150, 0),
    lambda: jitter.multiply(-150, 2, limit_db=math.nan),
    lambda: jitter.spur_to_jitter(-70, 0),
    lambda: jitter.spur_to_jitter(0, 1e8),
    lambda: jitter.spur_transfer(-66, 0, 1e8),
    lambda: jitter.ripple_sideband(2e6, -1e-3, 1e6),
    lambda: jitter.ripple_sideband(2e6, 1e-3, 0),
    lambda: jitter.vc_noise(1e7, 0.5e-6, -100e-9, 100),
    lambda: jitter.ssc_emi(-0.02, 125e6, 100e3),
    lambda: jitter.ssc_emi(1, 125e6, 100e3),
    lambda: jitter.ssc_emi(0.02, 125e6, 0),
    lambda: jitter.rss([1e-12], context="typical"),
])
def test_invalid_inputs_are_rejected(make):
    with pytest.raises(ValueError):
        make()
