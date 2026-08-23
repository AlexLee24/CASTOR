"""Everything under validation/ is a comparison against an outside reference.

These are not unit tests. A unit test says CASTOR does what we specified; these
say what CASTOR's answers are worth next to somebody else's measurements, and a
failure here is usually a finding rather than a regression. `pytest` on its own
runs tests/ only — reach for these deliberately:

    pytest validation
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker("validation")
