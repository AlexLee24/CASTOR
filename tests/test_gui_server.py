import json

import pytest
from fastapi.responses import JSONResponse

from castorCLI import presets
from castorGUI import server

# ==========================================
# The presets route
# ==========================================
#
# Called as a plain function rather than through an HTTP client: the route takes no
# input, and what is under test is the document it hands the browser, not FastAPI.

@pytest.fixture(autouse=True)
def no_extra_presets(monkeypatch):
    monkeypatch.delenv(presets.PATH_VARIABLE, raising=False)

@pytest.fixture
def backyard(tmp_path):
    path = tmp_path / "backyard.json"
    path.write_text(json.dumps({"_comment": ["generated elsewhere"], "profiles": {"backyard": {
        "name": "Backyard rig",
        "telescopes": {"C8": {"telescope": {
            "primary_mirror_diameter": 0.203, "secondary_mirror_diameter": 0.07,
            "focal_length": 2.032, "optical_throughput": 0.8}}},
    }}}), encoding="utf-8")
    return path

def served():
    response = server.presets()
    return response.status_code, json.loads(response.body)

def test_the_shipped_file_is_served_exactly_as_before():
    """Byte for byte what the route sent before it could merge anything, so a
    browser that never sets the variable sees no change at all."""
    before = JSONResponse(json.loads(server.PRESETS_PATH.read_text(encoding="utf-8")))

    assert server.presets().body == before.body

def test_files_on_the_variable_are_served_after_the_shipped_one(monkeypatch, backyard):
    monkeypatch.setenv(presets.PATH_VARIABLE, str(backyard))

    status, document = served()

    assert status == 200
    assert list(document["profiles"]) == ["lulin", "vlt", "other", "backyard"]
    assert document["profiles"]["backyard"] == json.loads(backyard.read_text())["profiles"]["backyard"]
    assert document["_comment"][0].startswith("Hardware and site presets")

def test_a_file_the_cli_would_refuse_is_not_served(monkeypatch, tmp_path):
    """The form applies what it recognises and skips the rest without a word, so a
    broken file has to stop here rather than half-apply in the browser."""
    # Every shipped profile, defined a second time.
    monkeypatch.setenv(presets.PATH_VARIABLE, str(server.PRESETS_PATH))

    status, document = served()

    assert status == 500
    assert "'lulin' is defined in both" in document["error"]

def test_a_missing_file_on_the_variable_says_which(monkeypatch, tmp_path):
    monkeypatch.setenv(presets.PATH_VARIABLE, str(tmp_path / "nowhere.json"))

    status, document = served()

    assert status == 500
    assert "nowhere.json" in document["error"]

def test_a_malformed_file_on_the_variable_names_the_field(monkeypatch, tmp_path):
    path = tmp_path / "typo.json"
    path.write_text(json.dumps({"profiles": {"rig": {"telescopes": {"T": {"telescope": {
        "primary_mirror_diameter": 1.0, "secondary_mirror_diameter": 0.3,
        "focal_length": 8.0, "optical_thruput": 0.8}}}}}}), encoding="utf-8")
    monkeypatch.setenv(presets.PATH_VARIABLE, str(path))

    status, document = served()

    assert status == 500
    assert "optical_thruput" in document["error"]
