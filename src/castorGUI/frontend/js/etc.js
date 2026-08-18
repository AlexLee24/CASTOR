/* ============================================================================
   CASTOR ETC — controller for etc_body.html.

   Host-agnostic: every route it talks to comes from window.CASTOR_ETC_CONFIG,
   which the host page sets before loading this file (see frontend/README.md).
   Kinder points it at its own Flask blueprint; the standalone server.py points
   it at the identical paths it serves itself.

   Interaction model matches the Flet GUI it was ported from: four freely
   switchable tabs, no submit button, every edit recalculates. The one thing
   that has no Flet counterpart is the network — recalculating in-process is
   free, but over HTTP a slow earlier response can land after a fast later one
   and overwrite it, so each request family keeps a single AbortController and
   cancels its own predecessor.
============================================================================ */
(function () {
    'use strict';

    var CONFIG = Object.assign({
        apiUrl: '/api/exposure_time_calculator',
        batchUrl: '/api/exposure_time_calculator/batch',
        presetsUrl: '/api/exposure_time_calculator/presets'
    }, window.CASTOR_ETC_CONFIG || {});

    // Single-point is cheap; batch runs astropy ephemeris over the whole window,
    // so it waits longer before firing (same split as app.py's BATCH_DEBOUNCE).
    var SINGLE_DEBOUNCE_MS = 250;
    var BATCH_DEBOUNCE_MS = 500;

    var root = document.getElementById('castor-etc');
    var form = document.getElementById('castor-form');
    if (!root || !form) { return; }

    var el = function (id) { return document.getElementById(id); };

    // ========================================================================
    // Formatting helpers
    // ========================================================================

    function fmt(value, digits) {
        if (value === null || value === undefined || isNaN(value)) { return '—'; }
        return Number(value).toLocaleString(undefined, {
            maximumFractionDigits: digits === undefined ? 3 : digits
        });
    }

    /* Percentage inputs hold 0-100 while castor.schema wants the 0-1 fraction.
       Rounding before display matters: 0.804 * 100 is 80.39999999999999 in IEEE
       754, and showing that in a field the user is about to edit is worse than
       useless. Mirrors LeftPanel._format_percent. */
    function fractionToPercentText(fraction) {
        return String(Math.round(fraction * 100 * 1e6) / 1e6);
    }

    function toLocalInputValue(date) {
        var pad = function (n) { return String(n).padStart(2, '0'); };
        return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) +
            'T' + pad(date.getHours()) + ':' + pad(date.getMinutes());
    }

    function isoToLocalInputValue(iso) {
        var d = new Date(iso);
        return isNaN(d.getTime()) ? '' : toLocalInputValue(d);
    }

    // ========================================================================
    // Payload building
    // ========================================================================

    var PayloadBuilder = {
        /* prune=true drops inputs inside a hidden .dynamic-group, because
           castor.schema is strict: sending zero_point_flux while the brightness
           discriminator says ab_mag is a validation error, not a harmless extra.
           prune=false is for SAVE, which keeps every branch's value the way
           AppState.get_api_payload() does. */
        build: function (prune) {
            var payload = {};
            var elements = form.elements;

            for (var i = 0; i < elements.length; i++) {
                var input = elements[i];
                if (!input.name) { continue; }
                if (prune !== false && input.closest('.dynamic-group[hidden]')) { continue; }

                var value = this._read(input);
                if (value === null || value === '') { continue; }
                this._set(payload, input.name.split('.'), value);
            }
            return payload;
        },

        _read: function (input) {
            if (input.type === 'checkbox') { return input.checked; }
            if (input.type === 'datetime-local') {
                if (!input.value) { return null; }
                var d = new Date(input.value);   // parsed as local wall-clock time
                return isNaN(d.getTime()) ? null : d.toISOString();
            }
            if (input.type === 'number') {
                if (input.value === '') { return null; }
                var n = parseFloat(input.value);
                if (isNaN(n)) { return null; }
                return input.hasAttribute('data-percent') ? n / 100 : n;
            }
            return input.value;
        },

        _set: function (obj, path, value) {
            var node = obj;
            for (var i = 0; i < path.length - 1; i++) {
                if (!node[path[i]]) { node[path[i]] = {}; }
                node = node[path[i]];
            }
            node[path[path.length - 1]] = value;
        }
    };

    function buildSingleRequest() {
        var base = PayloadBuilder.build(true);
        delete base.batch;      // batch.* are UI-only fields, not part of ObservationRequest
        return base;
    }

    /* TimeSeriesEnvironment shares location / mu_dark / extinction / FWHM with the
       single-point environment and swaps the instant for a start/end/step range.
       It has no auto_calc_background: the batch path always layers the dynamic
       moon contribution. Mirrors AppState.build_batch_observation_request. */
    function buildBatchRequest() {
        var base = PayloadBuilder.build(true);
        var env = base.environment || {};
        var batch = base.batch || {};

        return {
            instrument: base.instrument,
            target: base.target,
            environment: {
                location: env.location,
                start_time_utc: batch.start_time_utc,
                end_time_utc: batch.end_time_utc,
                time_step_minutes: batch.time_step_minutes,
                mu_dark: env.mu_dark,
                extinction_coeff: env.extinction_coeff,
                seeing_fwhm: env.seeing_fwhm,
                diffraction_fwhm: env.diffraction_fwhm,
                optical_fwhm: env.optical_fwhm,
                tracking_fwhm: env.tracking_fwhm
            },
            options: base.options
        };
    }

    // ========================================================================
    // API
    // ========================================================================

    function postJSON(url, body, signal) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: signal
        }).then(function (response) {
            return response.json().then(function (data) {
                if (!response.ok) { throw new Error(data.error || ('HTTP ' + response.status)); }
                return data;
            });
        });
    }

    // ========================================================================
    // Results rendering
    // ========================================================================

    /* Single-point and batch warnings share one box but arrive from two
       independent requests that finish at different times — tracked separately
       so whichever lands second doesn't wipe out the other's lines. Same split
       as RightPanel._single_warn_lines / _batch_warn_lines. */
    var singleWarnings = [];
    var batchWarnings = [];

    function refreshWarnings() {
        var lines = singleWarnings.concat(batchWarnings);
        el('warning-text').textContent = lines.join('\n');
        el('warning-box').hidden = lines.length === 0;
    }

    var METRIC_IDS = [
        'res-source-rate', 'res-sky-rate', 'res-peak-rate', 'res-single-snr',
        'res-total-fwhm', 'res-pixel-scale', 'res-eff-area', 'res-throughput',
        'res-enclosed-flux', 'res-num-pixels', 'res-sat-time', 'res-optimal-time'
    ];

    function renderSingle(data, error) {
        if (error) {
            el('error-text').textContent = error;
            el('error-box').hidden = false;
            singleWarnings = [];
            refreshWarnings();
            el('hero-label').textContent = 'Primary Result';
            el('hero-value').textContent = '—';
            el('hero-desc').textContent = 'Invalid input, please check the fields on the left';
            // Blank the cards rather than leaving the last good run's numbers sitting
            // next to an error message, where they read as current results.
            METRIC_IDS.forEach(function (id) { el(id).textContent = '—'; });
            return;
        }

        el('error-box').hidden = true;

        var core = data.core, budget = data.budget, diag = data.diagnostics, flags = data.flags;

        if (core.required_exposures === null || core.required_exposures === undefined) {
            el('hero-label').textContent = 'Signal-to-Noise Ratio (SNR)';
            el('hero-value').textContent = fmt(core.total_snr, 2);
            el('hero-desc').textContent = 'Calculated based on the given exposure time.';
        } else {
            el('hero-label').textContent = 'Required Exposures';
            el('hero-value').textContent = core.required_exposures + ' frames';
            el('hero-desc').textContent = 'Target SNR achieved: ' + fmt(core.total_snr, 2);
        }

        singleWarnings = (flags.warnings || []).slice();
        if (flags.is_saturated) {
            singleWarnings.unshift('⚠️ Single exposure time exceeds the saturation limit (Full Well Capacity reached).');
        }
        refreshWarnings();

        el('res-source-rate').textContent = fmt(budget.source_count_rate, 2);
        el('res-sky-rate').textContent = fmt(budget.sky_count_rate, 2);
        el('res-peak-rate').textContent = fmt(budget.peak_pixel_rate, 2);
        el('res-single-snr').textContent = fmt(core.single_snr, 2);

        el('res-total-fwhm').textContent = fmt(diag.total_fwhm, 2);
        el('res-pixel-scale').textContent = fmt(diag.pixel_scale, 3);
        el('res-eff-area').textContent = fmt(diag.effective_area, 3);
        el('res-throughput').textContent = fmt(diag.total_throughput * 100, 1);
        el('res-enclosed-flux').textContent = fmt(diag.enclosed_flux_fraction * 100, 1);
        el('res-num-pixels').textContent = fmt(diag.num_pixels_aperture, 1);

        el('res-sat-time').textContent = fmt(core.saturation_time_limit, 2);
        el('res-optimal-time').textContent = fmt(core.optimal_exposure_time, 2);
    }

    // ========================================================================
    // Observing Window chart (Plotly)
    // ========================================================================

    /* Returns [[startIdx, endIdx], ...] for each contiguous run where test() holds,
       end inclusive — a night can contain more than one below-horizon or
       saturation-risk window. Port of chart.py's _contiguous_runs. */
    function contiguousRuns(values, test) {
        var runs = [], start = null;
        for (var i = 0; i < values.length; i++) {
            if (test(values[i], i)) {
                if (start === null) { start = i; }
            } else if (start !== null) {
                runs.push([start, i - 1]);
                start = null;
            }
        }
        if (start !== null) { runs.push([start, values.length - 1]); }
        return runs;
    }

    function themeColor(name, fallback) {
        var value = getComputedStyle(root).getPropertyValue(name).trim();
        return value || fallback;
    }

    function setChartStatus(message) {
        var status = el('chart-status');
        status.textContent = message || '';
        status.hidden = !message;
    }

    /* Three stacked panels on one shared time axis, in reading order:
         1. Target & Moon elevation — is this window even above the horizon?
         2. Single-exposure SNR — how good is one frame right now?
         3. Saturation limit vs. the chosen exposure — will one frame saturate?
       Deliberately not total_snr (that tracks the chosen exposure count, not the
       sky) and deliberately not one dual-axis panel (SNR and seconds don't share
       a scale). Same reasoning as chart.py, which this replaces. */
    function renderChart(data, singleExpTime) {
        if (typeof window.Plotly === 'undefined') {
            setChartStatus('Plotly is not loaded on this page, so the chart cannot be drawn.');
            return;
        }

        var accent = themeColor('--etc-accent', '#C5A059');
        var moon = themeColor('--etc-moon', '#6FA8DC');
        var warning = themeColor('--etc-warning', '#fbbf24');
        var muted = themeColor('--etc-text-muted', '#9ca3af');
        var textMain = themeColor('--etc-text-main', '#e5e7eb');
        var gridColor = 'rgba(255, 255, 255, 0.08)';

        var times = data.core.timestamps_iso;
        var targetEl = data.ephemeris.target_elevation_deg;
        var moonEl = data.ephemeris.moon_elevation_deg;
        var singleSnr = data.core.single_snr;
        var tSat = data.core.saturation_time_limit;

        var traces = [
            { x: times, y: targetEl, name: 'Target', type: 'scatter', mode: 'lines',
              line: { color: accent, width: 2 }, xaxis: 'x', yaxis: 'y' },
            { x: times, y: moonEl, name: 'Moon', type: 'scatter', mode: 'lines',
              line: { color: moon, width: 2 }, xaxis: 'x', yaxis: 'y' },
            { x: times, y: singleSnr, name: 'Single-Exposure SNR', type: 'scatter', mode: 'lines',
              line: { color: accent, width: 2 }, showlegend: false, xaxis: 'x2', yaxis: 'y2' },
            { x: times, y: tSat, name: 'Saturation Limit', type: 'scatter', mode: 'lines',
              line: { color: accent, width: 2 }, showlegend: false, xaxis: 'x3', yaxis: 'y3' }
        ];

        var shapes = [];
        var annotations = [];

        // Panel 1: shade the stretches where the target is below the horizon.
        contiguousRuns(targetEl, function (v) { return v < 0; }).forEach(function (run) {
            shapes.push({
                type: 'rect', xref: 'x', yref: 'y domain',
                x0: times[run[0]], x1: times[run[1]], y0: 0, y1: 1,
                fillcolor: warning, opacity: 0.06, line: { width: 0 }, layer: 'below'
            });
        });
        shapes.push({
            type: 'line', xref: 'x', yref: 'y',
            x0: times[0], x1: times[times.length - 1], y0: 0, y1: 0,
            line: { color: muted, width: 1, dash: 'solid' }, opacity: 0.4, layer: 'below'
        });

        // Panel 2: direct-label the peak only — never every point.
        var peak = singleSnr.indexOf(Math.max.apply(null, singleSnr));
        annotations.push({
            x: times[peak], y: singleSnr[peak], xref: 'x2', yref: 'y2',
            text: fmt(singleSnr[peak], 0), showarrow: false, yshift: 14,
            font: { color: textMain, size: 11, family: 'inherit' }
        });

        // Panel 3: saturation-risk windows + the chosen exposure as a threshold.
        var riskRuns = contiguousRuns(tSat, function (v) { return v < singleExpTime; });
        riskRuns.forEach(function (run) {
            shapes.push({
                type: 'rect', xref: 'x3', yref: 'y3 domain',
                x0: times[run[0]], x1: times[run[1]], y0: 0, y1: 1,
                fillcolor: warning, opacity: 0.08, line: { width: 0 }, layer: 'below'
            });
        });
        shapes.push({
            type: 'line', xref: 'x3', yref: 'y3',
            x0: times[0], x1: times[times.length - 1], y0: singleExpTime, y1: singleExpTime,
            line: { color: muted, width: 1.5, dash: 'dash' }
        });
        annotations.push({
            x: times[times.length - 1], y: singleExpTime, xref: 'x3', yref: 'y3',
            text: 'your exposure: ' + fmt(singleExpTime, 0) + 's', showarrow: false,
            xanchor: 'right', yanchor: 'bottom', yshift: 4,
            font: { color: muted, size: 10, family: 'inherit' }
        });
        if (riskRuns.length) {
            annotations.push({
                x: times[riskRuns[0][0]], y: 1, xref: 'x3', yref: 'y3 domain',
                text: '⚠ saturation risk window', showarrow: false,
                xanchor: 'left', yanchor: 'top',
                font: { color: warning, size: 10, family: 'inherit' }
            });
        }
        var trough = tSat.indexOf(Math.min.apply(null, tSat));
        annotations.push({
            x: times[trough], y: tSat[trough], xref: 'x3', yref: 'y3',
            text: fmt(tSat[trough], 0) + 's', showarrow: false, yshift: -14,
            font: { color: textMain, size: 11, family: 'inherit' }
        });

        var axisBase = {
            gridcolor: gridColor, zeroline: false, linecolor: gridColor,
            tickfont: { color: muted, size: 10 }, automargin: true
        };
        var titleFont = { color: muted, size: 11 };

        // matches:'x3' keeps all three panels on one time axis (pan/zoom stays in
        // sync) while only the bottom one carries tick labels.
        var layout = {
            // No title and no warning banner drawn in here: the section heading and
            // the shared warning box above already say all of that.
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { family: 'inherit', color: muted },
            margin: { l: 62, r: 16, t: 8, b: 44 },
            height: 460,
            showlegend: true,
            legend: { orientation: 'h', x: 1, xanchor: 'right', y: 1.04, yanchor: 'bottom',
                      font: { color: textMain, size: 11 }, bgcolor: 'rgba(0,0,0,0)' },
            hovermode: 'x unified',
            shapes: shapes,
            annotations: annotations,
            xaxis:  Object.assign({}, axisBase, { domain: [0, 1], anchor: 'y',  matches: 'x3', showticklabels: false }),
            xaxis2: Object.assign({}, axisBase, { domain: [0, 1], anchor: 'y2', matches: 'x3', showticklabels: false }),
            xaxis3: Object.assign({}, axisBase, { domain: [0, 1], anchor: 'y3', title: { text: 'Time (UTC)', font: titleFont } }),
            yaxis:  Object.assign({}, axisBase, { domain: [0.72, 1],    anchor: 'x',  title: { text: 'Elevation (°)', font: titleFont } }),
            yaxis2: Object.assign({}, axisBase, { domain: [0.38, 0.64], anchor: 'x2', title: { text: 'Single-Exposure SNR', font: titleFont } }),
            yaxis3: Object.assign({}, axisBase, { domain: [0, 0.26],    anchor: 'x3', title: { text: 'Saturation Limit (s)', font: titleFont },
                                                  rangemode: 'tozero' })
        };

        window.Plotly.react(el('etc-chart'), traces, layout, {
            responsive: true, displaylogo: false,
            modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d']
        });
        setChartStatus('');
    }

    function renderBatch(data, error) {
        if (error) {
            batchWarnings = [];
            refreshWarnings();
            setChartStatus(error);
            return;
        }
        batchWarnings = (data.flags.warnings || []).slice();
        if (data.flags.is_saturated) {
            batchWarnings.unshift('⚠️ At least one point in the time series exceeds the saturation limit — see the shaded window(s) below.');
        }
        refreshWarnings();

        var expInput = form.elements['options.single_exp_time'];
        renderChart(data, parseFloat(expInput && expInput.value) || 0);
    }

    // ========================================================================
    // Scheduling — debounce + cancel-the-predecessor
    // ========================================================================

    function makeRunner(delay, buildBody, url, onResult) {
        var timer = null;
        var controller = null;

        return function schedule() {
            clearTimeout(timer);
            timer = setTimeout(function () {
                if (controller) { controller.abort(); }
                controller = new AbortController();
                var mine = controller;

                var body;
                try {
                    body = buildBody();
                } catch (err) {
                    onResult(null, err.message);
                    return;
                }

                postJSON(url, body, mine.signal).then(function (data) {
                    if (mine.signal.aborted) { return; }
                    onResult(data, null);
                }).catch(function (err) {
                    if (err.name === 'AbortError') { return; }
                    onResult(null, err.message);
                });
            }, delay);
        };
    }

    var scheduleSingle = makeRunner(SINGLE_DEBOUNCE_MS, buildSingleRequest, CONFIG.apiUrl, renderSingle);
    var scheduleBatch = makeRunner(BATCH_DEBOUNCE_MS, buildBatchRequest, CONFIG.batchUrl, renderBatch);

    function recalculate() {
        // The single-point result is always computed — the sweep is an addition on
        // top of it, not an alternate mode.
        scheduleSingle();

        if (!el('toggle-batch').checked) {
            el('observing-window').hidden = true;
            batchWarnings = [];
            refreshWarnings();
            return;
        }
        // Reveal the section immediately so flipping the switch has a visible
        // effect, rather than nothing happening until the request comes back.
        el('observing-window').hidden = false;
        setChartStatus('Calculating…');
        scheduleBatch();
    }

    // ========================================================================
    // Tabs & conditional field groups
    // ========================================================================

    function initTabs() {
        var tabs = root.querySelectorAll('.etc-tab');
        Array.prototype.forEach.call(tabs, function (tab) {
            tab.addEventListener('click', function () {
                Array.prototype.forEach.call(tabs, function (other) {
                    var active = other === tab;
                    other.classList.toggle('is-active', active);
                    other.setAttribute('aria-selected', String(active));
                });
                Array.prototype.forEach.call(root.querySelectorAll('.etc-tabpanel'), function (panel) {
                    panel.hidden = panel.dataset.panel !== tab.dataset.tab;
                });
            });
        });
    }

    function syncGroups(attribute, selected) {
        Array.prototype.forEach.call(root.querySelectorAll('[data-' + attribute + ']'), function (group) {
            group.hidden = group.dataset[attribute].split(' ').indexOf(selected) === -1;
        });
    }

    function syncConditionalFields() {
        var brightness = form.elements['target.brightness.type'].value;
        syncGroups('brightness', brightness);
        el('label-target-mag').textContent =
            brightness === 'ab_mag' ? 'Apparent Magnitude (AB)' : 'Apparent Magnitude';
        el('unit-flux-value').innerHTML =
            brightness === 'jansky_flux' ? 'Jy' : 'erg/s/cm&sup2;/&Aring;';

        syncGroups('sed', form.elements['target.sed.type'].value);
        syncGroups('options', form.elements['options.type'].value);
        syncGroups('when', el('toggle-batch').checked ? 'batch' : 'single');
    }

    // ========================================================================
    // Presets — an observing profile (site + its rigs) cascading into a rig, plus
    // an independent filter. Mirrors AppState.apply_profile/apply_rig/apply_filter;
    // the two implementations read the same data/presets.json.
    // ========================================================================

    var presets = {};

    function profiles() { return presets.profiles || {}; }

    /* Telescope and camera lists are scoped to the selected site — that scoping is
       why the site selector sits above them. */
    function catalogue(kind) {
        return (profiles()[el('select-profile').value] || {})[kind] || {};
    }

    /* Presets are stored shaped like castor.schema itself, so applying one means
       walking the fragment down to its leaves and writing each into the matching
       input. */
    function flattenFragment(prefix, fragment, out) {
        Object.keys(fragment).forEach(function (key) {
            var path = prefix + '.' + key;
            var value = fragment[key];
            if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
                flattenFragment(path, value, out);
            } else {
                out[path] = value;
            }
        });
        return out;
    }

    function applyFragment(section, fragment) {
        var flat = flattenFragment(section, fragment || {}, {});
        Object.keys(flat).forEach(function (path) {
            var input = form.elements[path];
            if (!input) { return; }
            input.value = input.hasAttribute('data-percent')
                ? fractionToPercentText(flat[path])
                : String(flat[path]);
        });
    }

    function fillSelect(select, entries, placeholder) {
        select.innerHTML = '';
        var blank = document.createElement('option');
        blank.value = '';
        blank.textContent = placeholder;
        select.appendChild(blank);
        entries.forEach(function (entry) {
            var option = document.createElement('option');
            option.value = entry[0];
            option.textContent = entry[1];
            select.appendChild(option);
        });
    }

    function named(source) {
        return Object.keys(source).map(function (key) {
            return [key, source[key].name || key];
        });
    }

    /* Live-derived from the form rather than from the preset, so it keeps telling the
       truth after a field is edited by hand. */
    function renderSpecs() {
        var value = function (name) { return parseFloat(form.elements[name].value); };
        var aperture = value('instrument.telescope.primary_mirror_diameter');
        var focal = value('instrument.telescope.focal_length');
        var num = function (v) { return String(Math.round(v * 1e6) / 1e6); };

        var lines = [
            num(aperture) + ' m aperture · ' + num(focal) + ' m focal length · ' +
                (aperture ? 'f/' + (focal / aperture).toFixed(1) : 'f/—'),
            num(value('instrument.camera.pixel_pitch')) + ' µm pixels · QE ' +
                value('instrument.camera.quantum_efficiency').toFixed(0) + '% · read noise ' +
                num(value('instrument.camera.readout_noise')) + ' e-'
        ];

        // Shown, never applied: seeing describes the night being planned, not the site,
        // and it is the field an observer is most likely to have set on purpose.
        var seeing = (profiles()[el('select-profile').value] || {}).median_seeing_fwhm;
        if (seeing !== undefined) {
            lines.push('Site median seeing ' + seeing + '" — reference only, not applied');
        }
        el('specs-card').textContent = lines.join('\n');
    }

    function applyProfile(profileId) {
        var profile = profiles()[profileId];
        var telescopeSelect = el('select-telescope');
        var cameraSelect = el('select-camera');

        if (!profile) {
            fillSelect(telescopeSelect, [], 'Custom');
            fillSelect(cameraSelect, [], 'Custom');
            renderSpecs();
            return;
        }
        // A profile with an environment block is a real site; one without is a hardware
        // family and must not invent a location. See data/presets.json.
        if (profile.environment) { applyFragment('environment', profile.environment); }

        fillSelect(telescopeSelect, named(profile.telescopes || {}), 'Custom');
        fillSelect(cameraSelect, named(profile.cameras || {}), 'Custom');

        var firstTelescope = Object.keys(profile.telescopes || {})[0];
        if (firstTelescope) {
            telescopeSelect.value = firstTelescope;
            applyFragment('instrument.telescope', profile.telescopes[firstTelescope].telescope);
        }
        var firstCamera = Object.keys(profile.cameras || {})[0];
        if (firstCamera) {
            cameraSelect.value = firstCamera;
            applyFragment('instrument.camera', profile.cameras[firstCamera].camera);
        }
        renderSpecs();
    }

    function initPresets() {
        var profileSelect = el('select-profile');
        var telescopeSelect = el('select-telescope');
        var cameraSelect = el('select-camera');
        var filterSelect = el('select-filter');

        /* Each of the three hardware selectors writes only its own slice. Picking a
           different camera at the same site is no reason to re-apply that site's sky
           over an mu_dark the observer tuned, nor to reset the telescope. */
        function bindSlice(select, kind, section, key) {
            select.addEventListener('change', function () {
                var preset = kind === 'filters'
                    ? (presets.filters || {})[select.value]
                    : catalogue(kind)[select.value];
                if (preset) { applyFragment(section, preset[key]); }
                renderSpecs();
                recalculate();
            });
        }

        fetch(CONFIG.presetsUrl).then(function (response) {
            if (!response.ok) { throw new Error('HTTP ' + response.status); }
            return response.json();
        }).then(function (data) {
            presets = data || {};
            fillSelect(profileSelect, named(profiles()), 'Custom');
            fillSelect(telescopeSelect, [], 'Custom');
            fillSelect(cameraSelect, [], 'Custom');
            fillSelect(filterSelect, named(presets.filters || {}), 'Custom');
            renderSpecs();

            profileSelect.addEventListener('change', function () {
                applyProfile(profileSelect.value);
                recalculate();
            });
            bindSlice(telescopeSelect, 'telescopes', 'instrument.telescope', 'telescope');
            bindSlice(cameraSelect, 'cameras', 'instrument.camera', 'camera');
            bindSlice(filterSelect, 'filters', 'instrument.optic_filter', 'optic_filter');
        }).catch(function (err) {
            // Presets are a convenience, not a requirement — every field already
            // carries a usable default, so say so plainly and leave them editable
            // instead of stranding the dropdown on "Loading…".
            console.error('Preset load failed:', err);
            [profileSelect, telescopeSelect, cameraSelect, filterSelect].forEach(function (select) {
                select.innerHTML = '<option>Presets unavailable — using defaults below</option>';
                select.disabled = true;
                select.classList.add('is-error');
            });
        });
    }

    // ========================================================================
    // SAVE / LOAD — same JSON shape as AppState.get_api_payload(), so a file
    // saved here opens in the Flet GUI and vice versa.
    // ========================================================================

    function initSaveLoad() {
        el('btn-save').addEventListener('click', function () {
            var all = PayloadBuilder.build(false);
            var batch = all.batch || {};
            delete all.batch;
            all.batch_time = {
                start_time_utc: batch.start_time_utc,
                end_time_utc: batch.end_time_utc,
                time_step_minutes: batch.time_step_minutes
            };
            all.batch_enabled = el('toggle-batch').checked;

            var blob = new Blob([JSON.stringify(all, null, 2)], { type: 'application/json' });
            var url = URL.createObjectURL(blob);
            var link = document.createElement('a');
            link.href = url;
            link.download = 'castor_request.json';
            link.click();
            URL.revokeObjectURL(url);
        });

        el('btn-load').addEventListener('click', function () { el('load-file-input').click(); });

        el('load-file-input').addEventListener('change', function (event) {
            var file = event.target.files && event.target.files[0];
            if (!file) { return; }
            file.text().then(function (text) {
                applyLoaded(JSON.parse(text));
            }).catch(function (err) {
                el('error-text').textContent = 'Could not read that file: ' + err.message;
                el('error-box').hidden = false;
            });
            event.target.value = '';   // so re-picking the same file fires change again
        });
    }

    function lookup(source, path) {
        var node = source;
        var parts = path.split('.');
        for (var i = 0; i < parts.length; i++) {
            if (node === null || typeof node !== 'object' || !(parts[i] in node)) { return undefined; }
            node = node[parts[i]];
        }
        return node;
    }

    function applyLoaded(data) {
        // Field-by-field rather than wholesale: a save file predating a newer field
        // leaves that field at its current value instead of blanking it. Same
        // deep-merge intent as AppState.load_from_dict.
        var elements = form.elements;
        for (var i = 0; i < elements.length; i++) {
            var input = elements[i];
            if (!input.name) { continue; }

            var path = input.name.indexOf('batch.') === 0
                ? input.name.replace('batch.', 'batch_time.')
                : input.name;
            var value = lookup(data, path);
            if (value === undefined || value === null) { continue; }

            if (input.type === 'checkbox') {
                input.checked = Boolean(value);
            } else if (input.type === 'datetime-local') {
                input.value = isoToLocalInputValue(value);
            } else if (input.hasAttribute('data-percent')) {
                input.value = fractionToPercentText(value);
            } else {
                input.value = String(value);
            }
        }

        if (typeof data.batch_enabled === 'boolean') {
            el('toggle-batch').checked = data.batch_enabled;
        }
        // Same reasoning as AppState.load_from_dict: leaving the selectors on their
        // previous choice would claim a provenance these numbers no longer have.
        ['select-profile', 'select-telescope', 'select-camera', 'select-filter'].forEach(
            function (id) { el(id).value = ''; }
        );
        renderSpecs();
        syncConditionalFields();
        recalculate();
    }

    // ========================================================================
    // Init
    // ========================================================================

    function initDefaultTimes() {
        var now = new Date();
        var later = new Date(now.getTime() + 6 * 3600 * 1000);
        form.elements['environment.observing_time_utc'].value = toLocalInputValue(now);
        form.elements['batch.start_time_utc'].value = toLocalInputValue(now);
        form.elements['batch.end_time_utc'].value = toLocalInputValue(later);
    }

    initTabs();
    initDefaultTimes();
    initPresets();
    initSaveLoad();
    syncConditionalFields();

    form.addEventListener('input', function () {
        syncConditionalFields();
        renderSpecs();
        recalculate();
    });
    form.addEventListener('change', function () {
        syncConditionalFields();
        recalculate();
    });

    // One calculation up front so the results panel isn't empty on first paint.
    recalculate();
})();
