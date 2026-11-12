# CASTOR ETC — web frontend

The canonical HTML/CSS/JS for the exposure time calculator UI. It exists so the
calculator's interface is written once and mounted in more than one place,
instead of each host keeping its own copy that quietly drifts from the others.

```
frontend/
├── etc_body.html      # Advanced mode — a plain HTML fragment, shared by every host
├── etc_simple_body.html # Simple mode — the same kind of fragment
├── css/etc.css        # Advanced styling, scoped under .castor-etc
├── css/etc_simple.css # Simple mode and the mode switch
├── css/kinder_shim.css # Kinder's kw-* components, for a host that is not Kinder
├── js/etc.js          # Advanced controller — talks to the engine over HTTP
├── js/etc_simple.js   # Simple controller and the Simple / Advanced switch
├── js/plotly.min.js   # vendored charting library (standalone build only)
├── img/               # logo and icons, generated from assets/ — do not hand-edit
└── index.html         # standalone page shell (see server.py)
```

## The host contract

A host page mounts the calculator by doing three things:

1. **Include `etc_body.html`** somewhere in its body. It is deliberately free of
   `<html>`/`<head>`/`<body>` wrappers and of any template syntax, so it drops
   into a Jinja template, a static page, or anything else unchanged.
2. **Set `window.CASTOR_ETC_CONFIG`** before `etc.js` runs, naming the three
   routes it should call:
   ```js
   window.CASTOR_ETC_CONFIG = {
       apiUrl:     '/api/exposure_time_calculator',
       batchUrl:   '/api/exposure_time_calculator/batch',
       presetsUrl: '/api/exposure_time_calculator/presets'
   };
   ```
3. **Load `css/etc.css`, a Plotly build, and `js/etc.js`.** Providing Plotly is
   the host's call — `etc.js` only ever reads `window.Plotly`, and says so in the
   chart area rather than throwing if it isn't there. The standalone build serves
   the vendored copy so it works offline; a host already pulling Plotly from a
   CDN should keep doing that rather than loading it twice.

Those routes must accept and return exactly what `castor.schema` defines:
`ObservationRequest` → `ObservationResponse`, `BatchObservationRequest` →
`BatchObservationResponse`, and `{"error": "..."}` with a 4xx on failure.
`server.py` is the reference implementation, and is small on purpose — the
contract is the schema, not the server.

### Simple mode

A host that also offers Simple mode (hardware names, a target and an SNR in; a
frame length and count out) does three more things:

1. **Include `etc_simple_body.html` too**, and put both fragments under a
   `[data-etc-mode]` tab bar, each in its own `[data-etc-mode-panel]` wrapper:
   ```html
   <div class="etc-page">
     <div class="etc-mode-bar">
       <div class="kw-tabbar" role="tablist">
         <button type="button" class="kw-tab is-on" data-etc-mode="simple">Simple</button>
         <button type="button" class="kw-tab" data-etc-mode="advanced">Advanced</button>
       </div>
     </div>
     <!-- etc_simple_body.html: it is the "simple" panel itself -->
     <div class="etc-advanced" data-etc-mode-panel="advanced" hidden><!-- etc_body.html --></div>
   </div>
   ```
   `index.html` is a working example, and Kinder's template is another.
2. **Add `quickUrl`** to `window.CASTOR_ETC_CONFIG`, a route taking
   `{site, telescope, camera, filter, ra, dec, mag, target_snr, fwhm,
   observing_time_utc}` and answering with `castorCLI.plan.compute_plan()`'s
   result (`server.py`'s `calculate_quick` is the reference). Kinder's template
   names it `window.KINDER_ETC_QUICK_URL` instead, which is still read.
3. **Load `css/etc_simple.css` and `js/etc_simple.js`.** Simple mode is built on
   Kinder's site components (`kw-panel`, `kw-field`, `kw-btn`, …): Kinder's own
   theme supplies them, and any other host loads `css/kinder_shim.css` before
   `etc_simple.css`.

The presets route returns the preset document with its key order intact, since
the first entry in each catalogue is the default. A Python host can serve what
`server.py` serves with
`castorCLI.presets.document(*castorCLI.presets.search_path())`: the shipped
file, then any files on `CASTOR_PRESETS_PATH`, validated, and as written. A
host whose copy of the shipped file lives elsewhere passes that path to
`search_path()`.

Everything the CSS touches lives under `.castor-etc`, and the page background,
fonts, outer padding and page title are left to the host — the partial starts
straight at the two panels, so a host with its own nav bar and heading above the
content area doesn't end up showing two titles. How much room those leave for
the calculator is likewise the host's to say: the panels' height comes from
`--etc-shell-height`, which a host overrides in one line
(`.castor-etc { --etc-shell-height: calc(100vh - 160px); }`) instead of
patching the layout rule. Where the host defines Kinder's
`--kw-*` theme variables the calculator picks them up automatically; where it
doesn't, the fallbacks in `etc.css` apply.

## Standalone

```bash
python src/castorGUI/server.py     # http://127.0.0.1:8600
```

`server.py` substitutes `etc_body.html` and `etc_simple_body.html` into
`index.html`'s `<!--CASTOR_ETC_BODY-->` and `<!--CASTOR_ETC_SIMPLE_BODY-->`
markers at request time, so editing a partial only needs a browser refresh.

## Desktop

```bash
python src/castorGUI/desktop.py
```

The same files again, in a native window: `desktop.py` starts `server.py` on a
loopback port and points the platform's own webview at it. There is no separate
desktop UI to keep in step, and no browser is bundled — see the packaging command
in that file's docstring.

## Mounting inside Kinder

Kinder already vendors this repository at `app/modules/CASTOR/` and already
exposes the three routes from
`app/routes/astronomy_tools/astronomy_tools_routes.py`. What changes is that its
`exposure_time_calculator.html` stops carrying its own copy of the form and
includes this one instead:

```python
# Make the shared partial visible to Jinja alongside Kinder's own templates
CASTOR_FRONTEND = os.path.join(os.path.dirname(__file__), '..', '..',
                               'modules', 'CASTOR', 'src', 'castorGUI', 'frontend')
app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(CASTOR_FRONTEND)])

@astronomy_tools_bp.route('/castor-static/<path:filename>')
def castor_static(filename):
    return send_from_directory(CASTOR_FRONTEND, filename)
```

```jinja
{% include '_navbar.html' %}
{% include 'etc_body.html' %}
<script>window.CASTOR_ETC_CONFIG = { ... };</script>
<link rel="stylesheet" href="{{ url_for('astronomy_tools.castor_static', filename='css/etc.css') }}">
<script src="{{ url_for('astronomy_tools.castor_static', filename='js/etc.js') }}" defer></script>
```

Kinder keeps its existing CDN `<script>` for Plotly; no vendored copy is served.

The icons in `img/` are not part of the partial, because a `<head>` is not: only
the standalone shell can link them. A host that wants the same tab icon links it
from its own template — `castor_static` already serves the file.

## Conventions

Two of these are easy to trip over when editing the form:

- **Percent vs fraction.** Efficiency fields show 0–100 to the reader, while
  `castor.schema` always receives the 0–1 fraction. The `data-percent` attribute
  on an input is what marks the difference, and `etc.js` converts in both
  directions around it.
- **SAVE files are requests.** What SAVE writes is `castor.schema`'s own shape,
  not a private format, so a saved file is readable by any other caller of the
  engine. It is deliberately a superset of a valid request — every branch of
  every discriminated union keeps its value — which is why it is read back
  through the form rather than posted straight to the API.
- **Image FWHM is required on LOAD.** A file without `environment.total_fwhm`
  cannot inherit the current form's value. One holding the former four
  components is rewritten in the dialog with their quadrature sum, the width the
  old engine used, and applied only on a second Import. The definition is in
  [ATBD §4.1.2](../../../docs/ATBD.md#412-spatial-resolution).
