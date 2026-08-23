"""CASTOR against the Perl calculators it was refactored from.

The point of these is not agreement. Both prototypes are superseded and one was
never finished, so a difference is expected; what is worth pinning is *which*
differences are structural, which of their numbers are safe to reuse, and which
look authoritative but are placeholders. See lulin_prototype.py for the sources.
"""
import math

import pytest

import lulin
import lulin_prototype as proto
from castor import physics


# ---------------------------------------------------------------------------
# What the 2011 tables actually are
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sdss,bessell", sorted(proto.SDSS_COPIED_FROM.items()))
def test_the_2011_sloan_tables_are_the_bessell_ones_shifted_one_slot(sdss, bessell):
    """The reason nothing Sloan from 2011 may be adopted as a source.

    Extinction and the whole five-column sky table are identical, value for
    value, for every one of the four pairs. Extinction differing by exactly
    nothing across four bands could be coincidence; twenty-four numbers cannot.
    They are Johnson BVRI wearing Sloan labels, and a future reader who finds
    `sdss_r => 0.13` in a document deserves to be told that before using it.
    """
    assert proto.EXTINCTION_2011[sdss] == proto.EXTINCTION_2011[bessell]
    assert proto.SKY_BRIGHTNESS_2011[sdss] == proto.SKY_BRIGHTNESS_2011[bessell]


def test_the_2011_z_bandwidth_is_a_copy_of_g_and_is_half_the_measured_one():
    """The same disease presets.json had, in the same band.

    Lulin's own published curve for z' integrates to 2780 A. Both this draft and
    presets.json-as-written gave it a width borrowed from another filter.
    """
    assert proto.FILTERS_2011["sdss_z"]["width_a"] == proto.FILTERS_2011["sdss_g"]["width_a"]
    measured_a = lulin.MEASURED_BANDPASS["Sloan_z"]["fwhm"] * 10.0
    assert proto.FILTERS_2011["sdss_z"]["width_a"] < 0.6 * measured_a


@pytest.mark.parametrize("band", ("sdss_g", "sdss_r", "sdss_i"))
def test_the_2011_griz_centres_and_widths_are_sound_where_they_were_not_copied(band):
    """Not everything in the draft is a placeholder, and saying so matters.

    Centres land within 1% of the transmission-weighted centroids measured off
    Lulin's curves, and widths within 6%. Only z' was copied. Blanket distrust
    of the file would throw away the parts somebody clearly did work on.
    """
    measured = lulin.MEASURED_BANDPASS[{"sdss_g": "Sloan_g", "sdss_r": "Sloan_r",
                                        "sdss_i": "Sloan_i"}[band]]
    assert proto.FILTERS_2011[band]["centre_nm"] == pytest.approx(measured["centroid"], rel=0.01)
    assert proto.FILTERS_2011[band]["width_a"] / 10.0 == pytest.approx(measured["fwhm"], rel=0.06)


# ---------------------------------------------------------------------------
# The throughput question
# ---------------------------------------------------------------------------

def test_the_2011_decomposition_is_the_one_the_atbd_specifies():
    """T_sys = R_optics * T_filter * QE, six years before CASTOR wrote it down.

    Worth asserting because presets.json is allowed to violate it: the VLT
    profile hides an optimistic optical throughput inside a filter transmission
    and is right in exactly one band. The form was never the disputed part.
    """
    expected = (proto.OPTICS_2011["sdss_r"]["m1"]
                * proto.OPTICS_2011["sdss_r"]["m2"]
                * proto.OPTICS_2011["sdss_r"]["glass"]
                * proto.FILTERS_2011["sdss_r"]["t_peak"]
                * proto.CAMERAS_2011["si1100"]["qe"]["sdss_r"])
    assert proto.throughput("si1100", "sdss_r") == pytest.approx(expected)


def test_the_2011_optics_are_flat_across_the_visible():
    """Half of why the measured r' excess is still unexplained.

    On this model the telescope is achromatic to 2.3% from g' to i' and under
    10% out to z'. Whatever makes r' outperform its neighbours by 81%, the
    observatory's own model says it is not the mirrors.
    """
    g, r, i, z = (proto.optics(f"sdss_{b}") for b in "griz")
    assert max(g, r, i) / min(g, r, i) == pytest.approx(1.0, abs=0.03)
    assert max(g, r, i, z) / min(g, r, i, z) < 1.10


@pytest.mark.parametrize("camera", sorted(proto.CAMERAS_2011))
def test_no_2011_camera_peaks_at_r_the_way_the_frames_do(camera):
    """The other half. Neither optics nor detector accounts for it.

    Measured on 14 photometric nights, T_sys(r')/T_sys(g') and T_sys(r')/T_sys(i')
    are both 1.81. Every camera the draft describes stays under 1.4 on both, and
    SOPHIA's own datasheet QE — a different detector again, but the one actually
    on the telescope — gives 1.07 and 1.13. Something outside both tables is
    doing this, which is why it is still an open question rather than a closed
    one about coatings.
    """
    qe = proto.CAMERAS_2011[camera]["qe"]
    if not all(f"sdss_{b}" in qe for b in "gri"):
        pytest.skip(f"{camera} has no Sloan quantum efficiencies; the draft left them blank")
    g, r, i = (proto.throughput(camera, f"sdss_{b}") for b in "gri")
    measured = lulin.MEASURED["r"]["throughput"] / lulin.MEASURED["g"]["throughput"]
    assert measured == pytest.approx(1.81, abs=0.01)
    assert max(r / g, r / i) < 1.4


# ---------------------------------------------------------------------------
# Structure shared with the modern calculators
# ---------------------------------------------------------------------------

def test_neither_prototype_extinguishes_the_sky():
    """The fourth independent source, and the one closest to home.

    CASTOR used to scale the sky by 10^(-0.4*k*X) and no longer does. LCO does
    not, ESO's sky grows the other way, and both of these — written for this
    telescope, by the author of the code CASTOR replaced — take only filter and
    moon phase. Asserted through the signature so a reintroduced parameter fails
    here rather than passing unnoticed.
    """
    import inspect
    params = inspect.signature(physics.calculate_sky_background_rate).parameters
    assert "airmass" not in params
    assert "extinction_coeff" not in params
    # And the prototypes' own sky tables carry no airmass axis to apply one to.
    assert set(proto.SKY_BRIGHTNESS_2005["V"]) == {0, 3, 7, 10, 14}
    assert set(proto.SKY_BRIGHTNESS_2011["sdss_r"]) == {0, 3, 7, 10, 14}


def test_the_2005_extinction_falls_towards_the_red_and_ours_does_not():
    """Why the measured coefficients were recorded but not adopted.

    2005 is monotonic, which is what extinction does. Our fit puts r' highest of
    the three, which it cannot be, because the frames span nights rather than
    airmass and night-to-night transparency is masquerading as an airmass term.
    Neither is good enough to overrule the other, so presets.json keeps its
    single site-wide value and test_lulin.py holds the question open.
    """
    k = [proto.EXTINCTION_2005[b] for b in proto.BESSELL]
    assert k == sorted(k, reverse=True)
    ours = [lulin.MEASURED[b]["k"] for b in ("g", "r", "i")]
    assert ours != sorted(ours, reverse=True)


@pytest.mark.parametrize("band,sloan_nm", (("g", 475.9), ("r", 627.8), ("i", 767.6)))
def test_the_2005_throughput_is_peaked_but_less_than_ours(band, sloan_nm):
    """What the 2005 file does and does not corroborate.

    Interpolated onto our band centres it gives 0.37 / 0.47 / 0.32 against a
    measured 0.265 / 0.480 / 0.265 — the same peak at r', but a shallower one,
    and r' is the only band the two agree on. Since the 2005 throughput is a
    total that includes an unnamed camera's quantum efficiency, the shape it
    shows may be that detector rather than the telescope. It narrows the
    question; it does not answer it.
    """
    interpolated = proto.interpolate_2005(proto.THROUGHPUT_2005, sloan_nm)
    measured = lulin.MEASURED[band]["throughput"]
    assert (measured / interpolated) == pytest.approx(
        {"g": 0.72, "r": 1.03, "i": 0.83}[band], abs=0.02)


# ---------------------------------------------------------------------------
# Tables presets.json has no source for
# ---------------------------------------------------------------------------

def test_read_noise_rises_steeply_with_readout_speed():
    """Context for the one camera number we measured and did not adopt.

    presets.json gives SOPHIA 7.0 e-, the datasheet's 1 MHz figure; a photon
    transfer curve over the frames gives 7.9. Every camera here spans a factor
    of two to twelve between its slowest and fastest port, so a 13% gap is
    unremarkable for a detector read at speed — and the measured value is the
    one describing this system, so that is the one presets.json now carries.
    """
    for camera in proto.CAMERAS_2011.values():
        speeds = camera["readout"]
        assert speeds[max(speeds)] / speeds[min(speeds)] >= 1.8
    assert lulin.MEASURED_READ_NOISE == 7.9


def test_dark_current_halves_every_four_to_six_degrees():
    """The shape behind QUESTIONS.md 6, and how wide it is.

    SOPHIA's datasheet quotes -90 C and the camera runs at -80, so the preset
    needs a scaling nobody has measured. The two cameras tabulated across that
    range fall by 33x and 100x between -50 and -80, which is a halving every
    5.9 C and every 4.5 C respectively. Even the sign of the correction is not
    in doubt, but a factor of three between two cameras in the same document is
    the reason a rule of thumb cannot replace a dark frame, and presets.json is
    unchanged.
    """
    halvings = {}
    for name in ("si1100", "ncucam1"):
        dark = proto.CAMERAS_2011[name]["dark"]
        ratio = dark[-50] / dark[-80]
        assert ratio >= 30.0
        halvings[name] = 30.0 / math.log2(ratio)
    assert halvings["si1100"] == pytest.approx(5.9, abs=0.1)
    assert halvings["ncucam1"] == pytest.approx(4.5, abs=0.1)
