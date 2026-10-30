"""The browser form's preset rules, pinned to the ones castorCLI/presets.py follows.

The browser cannot run Python, so frontend/js/etc.js holds a second copy of the
resolution rules, and a second copy drifts without a word unless a test holds it to
the first (docs/LESSONS.md, "The same physics implemented twice will drift,
silently"). These tests run etc.js under Node against the controls etc_body.html
defines (tests/etc_form_harness.js), drive its selectors, and compare the request it
would POST with what PresetFile.resolve() makes of the same selection — the request
`castor calc` would build.

Skipped where Node is not installed; GitHub's ubuntu-latest runners have it.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from castorCLI import presets

NODE = shutil.which("node")
HARNESS = Path(__file__).with_name("etc_form_harness.js")

pytestmark = pytest.mark.skipif(NODE is None, reason="runs etc.js under Node.js, which is not installed")

# ==========================================
# Helpers
# ==========================================

def drive(document, steps=()):
    """The request the form sends on opening, then the one it sends after each step."""
    result = subprocess.run(
        [NODE, str(HARNESS)],
        input=json.dumps({"presets": document, "steps": list(steps)}),
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)

def select(selector, value):
    return {"select": f"select-{selector}", "value": value}

def _flat(fragment, prefix=""):
    flat = {}
    for key, value in fragment.items():
        if isinstance(value, dict):
            flat.update(_flat(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat

#: Every environment field a preset can set. All are compared, so a field the form
#: sends and the CLI would not (a band's zodiacal share left behind) is a mismatch.
SKY = ("location", "mu_dark", "extinction_coeff", "zodiacal_share")

def assert_sent_as_resolved(request, fragment, context=None):
    """The request carries exactly the preset values resolve() gives for it.

    Only the hardware sections resolve() fills are compared: a catalogue the site
    leaves empty ("other" lists no filters) leaves the form's own fields standing,
    as Custom, where the CLI would ask for them instead.
    """
    environment = request["environment"]
    sent = _flat({
        "environment": {key: environment[key] for key in SKY if key in environment},
        "instrument": {key: request["instrument"][key] for key in fragment["instrument"]},
    })
    # Approximate only because percentages travel through the form as text: 77.1 / 100
    # is 0.7709999999999999 in IEEE 754.
    assert sent == pytest.approx(_flat(fragment)), context

@pytest.fixture
def shipped():
    return presets.load()

@pytest.fixture
def with_family():
    """The shipped file and, after it, a hardware family of the kind a host generates
    for itself (OWL's files are nothing else): no environment, and a filter whose
    throughput was measured on the family's own telescope."""
    family = {"profiles": {"backyard": {
        "name": "Backyard rig",
        "telescopes": {"C8": {"telescope": {
            "primary_mirror_diameter": 0.203, "secondary_mirror_diameter": 0.07,
            "focal_length": 2.032, "optical_throughput": 0.8}}},
        "cameras": {"Mono": {"camera": {
            "pixel_pitch": 3.76, "quantum_efficiency": 0.8, "dark_current_rate": 0.002,
            "readout_noise": 1.5, "full_well_capacity": 50000}}},
        "filters": {"V": {
            "optic_filter": {"central_wavelength": 550.0, "filter_bandwidth": 88.0,
                             "filter_transmission": 0.95},
            "telescope": {"C8": {"optical_throughput": 0.7}}}},
    }}}
    document = presets.document()
    document["profiles"].update(family["profiles"])
    return document, presets.PresetFile.model_validate(document)

FAMILY = dict(telescope="backyard/C8", camera="backyard/Mono", optic_filter="backyard/V")

# ==========================================
# Every shipped configuration
# ==========================================

def test_the_form_opens_on_what_the_cli_resolves(shipped):
    opening, = drive(presets.document())

    assert_sent_as_resolved(opening, shipped.resolve(next(iter(shipped.profiles))))

def test_every_shipped_configuration_is_sent_as_the_cli_resolves_it(shipped):
    """Each site, then each filter under each of its telescopes, then each camera.

    Walking them in sequence is the point: each selection lands on whatever the one
    before it left, which is where a band's correction outstaying its filter shows —
    and a new telescope arrives under the filter the last one was left with, whose
    throughput measured on it must come along."""
    steps, expected = [], []
    for site, profile in shipped.profiles.items():
        steps.append(select("profile", site))
        expected.append(shipped.resolve(site))
        telescope = optic_filter = None
        for telescope in profile.telescopes:
            steps.append(select("telescope", telescope))
            expected.append(shipped.resolve(site, telescope, None, optic_filter))
            for optic_filter in profile.filters:
                steps.append(select("filter", optic_filter))
                expected.append(shipped.resolve(site, telescope, None, optic_filter))
        for camera in profile.cameras:
            steps.append(select("camera", camera))
            expected.append(shipped.resolve(site, telescope, camera, optic_filter))

    sent = drive(presets.document(), steps)[1:]

    for step, request, fragment in zip(steps, sent, expected):
        if fragment is not None:
            assert_sent_as_resolved(request, fragment, step)

def test_a_bands_sky_does_not_follow_into_another_site(shipped):
    """Lulin's r' sky carries a zodiacal share no site-wide sky does. Moving to
    another site re-applied that site's mu_dark and left the share standing."""
    moves = [(site, optic_filter, other)
             for site, profile in shipped.profiles.items()
             for optic_filter in profile.filters
             for other in shipped.profiles if other != site]
    steps = [step for site, optic_filter, other in moves
             for step in (select("profile", site), select("filter", optic_filter),
                          select("profile", other))]

    sent = drive(presets.document(), steps)[1:]

    for index, move in enumerate(moves):
        assert_sent_as_resolved(sent[3 * index + 2], shipped.resolve(move[2]), move)

# ==========================================
# A hardware family from another file
# ==========================================
#
# A family has no sky, so the form keeps the one it holds. What it must not keep is
# the correction the previous filter laid over that sky: that was the sky through
# another band, measured at another filter's site. What is left is exactly what the
# CLI uses when the family's hardware is named under the same site.

@pytest.mark.parametrize("site, optic_filter", [
    ("lulin", "Sloan_r"),    # the opening configuration; r' carries mu_dark and a share
    ("lulin", "Sloan_u"),    # a band with no correction of its own
    ("vlt", None),
])
def test_a_family_runs_under_the_last_sites_own_sky(with_family, site, optic_filter):
    document, catalogue = with_family
    steps = [select("profile", site)]
    if optic_filter:
        steps.append(select("filter", optic_filter))
    steps.append(select("profile", "backyard"))

    request = drive(document, steps)[-1]

    assert_sent_as_resolved(request, catalogue.resolve(site, **FAMILY))
    assert "zodiacal_share" not in request["environment"]
    assert request["instrument"]["telescope"]["optical_throughput"] == pytest.approx(0.7)

def test_a_sky_typed_by_hand_stays_when_a_family_is_chosen(with_family):
    """The number typed is the reader's. The band's zodiacal share, untouched, is still
    the band's, and goes with it."""
    document, _ = with_family

    request = drive(document, [{"edit": "environment.mu_dark", "value": "22.0"},
                               select("profile", "backyard")])[-1]

    assert request["environment"]["mu_dark"] == 22.0
    assert "zodiacal_share" not in request["environment"]

def test_a_loaded_sky_stays_when_a_family_is_chosen(with_family):
    """LOAD puts the reader's own numbers in the form, even ones equal to a band's."""
    document, _ = with_family
    opening, = drive(document)

    request = drive(document, [{"load": opening}, select("profile", "backyard")])[-1]

    assert request["environment"]["mu_dark"] == opening["environment"]["mu_dark"] == 21.26
    assert request["environment"]["zodiacal_share"] == 0.267
