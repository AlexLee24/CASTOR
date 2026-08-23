"""Local override of pyinstaller-hooks-contrib's hook-astropy.py.

The upstream hook does `hiddenimports = collect_submodules('astropy')`, which
imports every astropy submodule to discover it — including
astropy.visualization.wcsaxes, whose __init__.py calls
`pytest.importorskip("matplotlib")` at module level. CASTOR never imports
astropy.visualization (see moon.py: only astropy.time, .coordinates, .units),
and matplotlib is deliberately not installed — see pyproject.toml.

`on_error="ignore"` does not help here: pytest's Skipped exception subclasses
BaseException directly rather than Exception, specifically so libraries with a
bare `except Exception` — which is exactly what collect_submodules' internals
use — do not accidentally swallow it. So the fix has to stop the import from
happening at all, via `filter`, which decides whether a submodule is even
queued for the (isolated-subprocess) __import__ that discovers it.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, \
    copy_metadata, is_module_satisfies

datas = collect_data_files('astropy')
hiddenimports = collect_submodules(
    'astropy', filter=lambda name: not name.startswith('astropy.visualization'))

ply_files = []
for path, target in collect_data_files('astropy', include_py_files=True):
    if path.endswith(('_parsetab.py', '_lextab.py')):
        ply_files.append((path, target))
datas += ply_files

if is_module_satisfies('astropy >= 5.0'):
    datas += copy_metadata('astropy')
    datas += copy_metadata('numpy')

hiddenimports += ['numpy.lib.recfunctions']
