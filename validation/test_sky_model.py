"""How CASTOR's moon model behaves as the filter changes.

Krisciunas & Schaefer (1991) is a V-band model. CASTOR applies it in whichever
band the caller selected, and these tests measure what that costs, using LCO's
measured new/half/full sky brightnesses as the reference for how much the moon
really contributes in each band.

The absolute size of the moon term depends on where the moon is, and LCO's table
is a three-row lookup rather than a geometry model, so nothing here compares
absolute brightnesses. What is comparable is the *shape* across bands, normalised
to V — that is a property of the model, not of the night.
"""
import inspect

import numpy as np
import pytest

import lco_etc
import skycalc
from castor import moon

#: One geometry, held fixed, so only the band can vary.
GEOMETRY = dict(rho_deg=60.0, z_moon_deg=30.0, z_target_deg=30.0)

FULL_MOON, HALF_MOON = 0.0, 90.0


def brightening(mu_dark, alpha_deg, k):
    """Magnitudes by which CASTOR says the moon brightens the sky."""
    b_moon = moon.krisciunas_schaefer_1991(alpha_deg, k_ext_v=k, **GEOMETRY)
    b_dark = 34.08 * 10.0 ** (0.4 * (22.5 - mu_dark))
    return float(2.5 * np.log10((b_moon + b_dark) / b_dark))


def test_the_filter_never_reaches_the_sky_model():
    """There is no band argument, in either direction.

    The only band-dependent quantity that gets in is the extinction coefficient,
    and it arrives through a parameter whose name says which band it is for.
    """
    parameters = inspect.signature(moon.calculate_sky_brightness).parameters
    assert not any("filter" in name or "wavelength" in name for name in parameters)
    assert "k_ext_v" in inspect.signature(moon.krisciunas_schaefer_1991).parameters
    assert inspect.signature(moon.krisciunas_schaefer_1991).parameters["k_ext_v"].default == 0.17


def test_the_photometry_inside_it_is_all_johnson_v():
    """The moon's brightness and the nanoLambert scale are hard-wired to V.

    Only the two atmospheric scattering terms respond to `k_ext_v`; the moon's
    own magnitude and the surface-brightness zero point do not, so the model has
    no representation of the moon having a colour.
    """
    source = inspect.getsource(moon.krisciunas_schaefer_1991)
    assert "-12.73" in source and "16.57" in source     # the moon's V magnitude
    assert "34.08" in inspect.getsource(moon.calculate_sky_brightness)   # V-band nL zero point


@pytest.mark.parametrize("alpha,phase", [(HALF_MOON, 1), (FULL_MOON, 2)])
def test_moon_contribution_is_too_blue_and_vanishes_in_the_red(alpha, phase):
    """The band shape, normalised to V, against LCO's measurements.

    Both ends are wrong and for the same reason. In the blue, extinction is large,
    so the scattering term is large and the model over-produces moonlight. In the
    near-infrared k is 0.03, the term (1 - 10^(-0.4·k·X)) collapses to about 0.014,
    and the moon all but disappears — when in reality it is a sunlit rock that is
    perfectly bright in Y, merely not Rayleigh-scattered. "Less scattering" is
    being read as "less moonlight".
    """
    v = lco_etc.FILTERS.index("V")
    measured_v = lco_etc.SKY_BRIGHTNESS[0][v] - lco_etc.SKY_BRIGHTNESS[phase][v]
    modelled_v = brightening(lco_etc.SKY_BRIGHTNESS[0][v], alpha, lco_etc.EXTINCTION[v])

    def shape(band):
        f = lco_etc.FILTERS.index(band)
        measured = lco_etc.SKY_BRIGHTNESS[0][f] - lco_etc.SKY_BRIGHTNESS[phase][f]
        modelled = brightening(lco_etc.SKY_BRIGHTNESS[0][f], alpha, lco_etc.EXTINCTION[f])
        return modelled / modelled_v - measured / measured_v

    assert shape("u") > 0.5      # far too much moon in the blue
    assert shape("Y") < -0.4     # almost none in the near-infrared
    assert abs(shape("g")) < 0.2  # and roughly right next door to V


def test_the_near_infrared_moon_is_wrong_by_an_order_of_magnitude():
    """Full moon in Y: about +0.3 mag modelled against about +2.9 measured.

    Quoted as a flux ratio because that is what feeds the noise term.
    """
    f = lco_etc.FILTERS.index("Y")
    measured = lco_etc.SKY_BRIGHTNESS[0][f] - lco_etc.SKY_BRIGHTNESS[2][f]
    modelled = brightening(lco_etc.SKY_BRIGHTNESS[0][f], FULL_MOON, lco_etc.EXTINCTION[f])
    assert 10.0 ** (0.4 * (measured - modelled)) > 8.0


def test_mu_sky_leaves_the_model_in_one_system_and_is_read_in_another():
    """K&S 1991 is Vega-based Johnson V; calculator.py converts it as AB.

    Harmless in V, where the two systems differ by about 0.01 mag. Not harmless
    in u' or Y, and invisible either way because nothing records which system a
    mu_sky is in.
    """
    from castor import calculator

    source = inspect.getsource(calculator)
    assert "convert_ab_to_wavelength_flux(mu_sky" in source


# ==========================================
# What the sky is made of, along our sightline
# ==========================================

def test_half_the_g_band_dark_sky_never_touched_the_atmosphere():
    """The number that decides how questions 9 and 10 must be built.

    At the sightline all 123 frames look down, zodiacal light plus scattered
    starlight is 53% of a moonless g' sky, 35% of r' and 16% of i'. Every one of
    those photons is already inside the measured mu_dark, because mu_dark is a
    brightness someone measured from the ground.

    So computing zodiacal light from the pointing and adding it to mu_dark would
    count half the g' sky twice. That is the same shape of error the extinction
    term made, and the one the project's slides named "Hidden Errors (Two Wrongs
    Make a Right)". The safe construction subtracts before it adds.
    """
    share = skycalc.SIGHTLINE_STUDY["zodiacal_and_starlight_share"]
    assert share["g'"] > 0.5
    assert share["g'"] > share["r'"] > share["i'"]      # bluer sky, more zodiacal


def test_pointing_alone_moves_the_dark_sky_by_a_third_of_a_magnitude():
    """How wrong one site-wide mu_dark can be, and it is not small.

    From the ecliptic plane to the pole the g' sky darkens by 0.35 mag, r' by
    0.26 and i' by 0.12, saturating above about 60 degrees of ecliptic latitude.
    presets.json carries a single number per band, measured at +15.9, and has no
    way to say which direction it applies to.
    """
    table = skycalc.SIGHTLINE_STUDY["pointing_dmag"]
    swing = {b: table[90.0][b] - table[0.0][b] for b in ("g'", "r'", "i'")}
    assert swing["g'"] == pytest.approx(0.349, abs=0.005)
    assert swing["g'"] > swing["r'"] > swing["i'"]
    # It saturates: the last 30 degrees buy nothing.
    assert table[90.0]["g'"] == pytest.approx(table[60.0]["g'"], abs=0.001)


def test_the_sky_grows_with_airmass_at_a_rate_that_depends_on_the_band():
    """Why the xfail in test_eso.py cannot be closed with a scalar.

    From X=1.1 to X=2.0 the sky brightens by 23% in g' but 58% in i'. The cause
    is the component mix rather than anything about the filters: i' is mostly
    upper atmosphere and airglow, which are emitted inside the column and
    lengthen with it, while over half of g' is zodiacal light, which arrives from
    outside and is extinguished on the way in. One number fitted to one band
    would be wrong in every other.
    """
    growth = skycalc.SIGHTLINE_STUDY["growth_to_airmass_2"]
    assert growth["i'"] > 2.0 * growth["g'"]
    assert growth["u'"] < growth["g'"] < growth["r'"] < growth["i'"]


def test_the_component_shares_do_not_care_about_the_observatory_altitude():
    """Bounds one of the two ways standing in Paranal for Lulin could hurt.

    SkyCalc knows only ESO's sites. Lulin at 2862 m sits between La Silla at 2400
    and Armazones at 3060, and across that whole range the zodiacal-plus-
    starlight share of the g' sky moves by 0.1 percentage point.

    What this does *not* test is geography: all three are in northern Chile, and
    airglow amplitude varies with geomagnetic latitude, season and solar cycle.
    Lulin is at 23.5 N against Paranal's 24.6 S, comparable in magnitude and
    opposite in hemisphere, and nothing here checks that. The reason it is
    tolerable anyway is that no absolute brightness is taken from SkyCalc: the
    measured mu_dark stays the anchor and the model supplies only ratios.
    """
    sites = skycalc.SIGHTLINE_STUDY["site_insensitivity"]
    assert max(sites.values()) - min(sites.values()) < 0.002
