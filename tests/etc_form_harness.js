/* ============================================================================
   Runs frontend/js/etc.js under Node and reports what the form would send.

   Driven by tests/test_gui_form.py, which says why it exists. Reads one JSON
   object on stdin:

     { "presets": <the document the presets route serves>,
       "steps": [ { "select": "<selector id>", "value": "<option value>" },
                  { "edit": "<input name>", "value": "<text typed>" },
                  { "load": <a saved request, as LOAD takes it> } ] }

   and writes a JSON array to stdout: the request the form POSTs once it has
   opened, then the one it POSTs after each step.

   The page is a stand-in, deep enough for the form and no deeper. Its controls
   are read out of etc_body.html itself, so a field renamed or re-defaulted there
   is renamed or re-defaulted here; every other element is an inert object that
   accepts whatever etc.js sets on it. The calculation is never answered — what is
   under test is the request — and the debounce timers run on demand rather than
   on the clock.
============================================================================ */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const FRONTEND = path.join(__dirname, '..', 'src', 'castorGUI', 'frontend');
const API_URL = '/api/exposure_time_calculator';

// ==========================================
// Elements
// ==========================================

class Element {
    constructor(tag, attributes) {
        this.tagName = tag.toUpperCase();
        this._attributes = attributes || {};
        this._listeners = {};
        this.id = this._attributes.id || '';
        this.name = this._attributes.name || '';
        this.type = tag === 'select' ? 'select-one'
            : tag === 'input' ? (this._attributes.type || 'text') : tag;
        this.options = tag === 'select' ? [] : null;
        this.defaultValue = this._attributes.value || '';
        this._value = this.defaultValue;
        this.checked = 'checked' in this._attributes;
        this.hidden = 'hidden' in this._attributes;
        this.disabled = false;
        this.open = false;
        this.readOnly = false;
        this.textContent = '';
        this.dataset = {};
        this.style = {};
        this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
    }

    // A select holds only a value one of its options has, as a browser's does.
    get value() { return this._value; }
    set value(text) {
        text = String(text);
        if (this.options) {
            this._value = this.options.some((option) => option.value === text) ? text : '';
        } else {
            this._value = text;
        }
    }

    get innerHTML() { return ''; }
    set innerHTML(html) {
        if (this.options) {
            this.options = [];
            this._value = '';
        }
    }

    appendChild(child) {
        if (this.options && child.tagName === 'OPTION') {
            this.options.push(child);
            if (this.options.length === 1) { this._value = child.value; }
        }
        return child;
    }

    addEventListener(type, listener) {
        (this._listeners[type] = this._listeners[type] || []).push(listener);
    }

    dispatch(type) {
        const event = { type: type, target: this, preventDefault() {} };
        (this._listeners[type] || []).forEach((listener) => listener(event));
    }

    click() { this.dispatch('click'); }
    hasAttribute(name) { return name in this._attributes; }
    getAttribute(name) { return name in this._attributes ? this._attributes[name] : null; }
    setAttribute(name, value) { this._attributes[name] = String(value); }
    closest() { return null; }
    querySelector() { return new Element('div'); }
    querySelectorAll() { return []; }
    removeEventListener() {}
    focus() {}
    select() {}
    scrollIntoView() {}
    showModal() {}
    close() {}
}

// ==========================================
// The page, from etc_body.html
// ==========================================

const ATTRIBUTES = /([^\s=]+)(?:="([^"]*)")?/g;
const CONTROL = /<(input|select|textarea)\b((?:[^>"]|"[^"]*")*)>/g;
const OPTION = /<option\b((?:[^>"]|"[^"]*")*)>([\s\S]*?)<\/option>/g;

function attributes(source) {
    const found = {};
    for (const match of source.matchAll(ATTRIBUTES)) {
        found[match[1]] = match[2] === undefined ? '' : match[2];
    }
    return found;
}

function readPage() {
    const html = fs.readFileSync(path.join(FRONTEND, 'etc_body.html'), 'utf8')
        .replace(/<!--[\s\S]*?-->/g, '');
    const formStart = html.indexOf('<form id="castor-form"');
    const formEnd = html.indexOf('</form>', formStart);
    if (formStart < 0 || formEnd < 0) { throw new Error('etc_body.html has no castor-form'); }

    const byId = new Map();
    const form = new Element('form', { id: 'castor-form' });
    const elements = [];

    for (const match of html.matchAll(CONTROL)) {
        const tag = match[1];
        const control = new Element(tag, attributes(match[2]));
        if (tag === 'select') {
            const body = html.slice(match.index, html.indexOf('</select>', match.index));
            let chosen = null;
            for (const option of body.matchAll(OPTION)) {
                const optionAttributes = attributes(option[1]);
                const element = new Element('option', optionAttributes);
                element.value = 'value' in optionAttributes ? optionAttributes.value : option[2].trim();
                control.appendChild(element);
                if ('selected' in optionAttributes) { chosen = element.value; }
            }
            if (chosen !== null) { control.value = chosen; }
        }
        if (control.id) { byId.set(control.id, control); }
        if (match.index > formStart && match.index < formEnd) {
            elements.push(control);
            if (control.name) { elements[control.name] = control; }
        }
    }
    form.elements = elements;
    byId.set('castor-form', form);
    return { byId: byId, form: form };
}

// ==========================================
// Running it
// ==========================================

async function main() {
    const input = JSON.parse(fs.readFileSync(0, 'utf8'));
    const page = readPage();
    const created = [];
    const posted = [];
    const errors = [];

    const document = {
        getElementById(id) {
            if (!page.byId.has(id)) { page.byId.set(id, new Element('div', { id: id })); }
            return page.byId.get(id);
        },
        createElement(tag) {
            const element = new Element(tag);
            created.push(element);
            return element;
        }
    };

    // Debounce and busy-cue timers, run by settle() rather than by the clock.
    const timers = new Map();
    let nextTimer = 1;

    function fetch(url, options) {
        if (options && options.method === 'POST') {
            posted.push({ url: url, body: JSON.parse(options.body) });
            return new Promise(() => {});
        }
        const document = JSON.parse(JSON.stringify(input.presets));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(document) });
    }

    const sandbox = {
        document: document,
        fetch: fetch,
        setTimeout(callback) { const id = nextTimer++; timers.set(id, callback); return id; },
        clearTimeout(id) { timers.delete(id); },
        AbortController: AbortController,
        getComputedStyle() { return { getPropertyValue() { return ''; } }; },
        navigator: {},
        console: {
            log() {},
            warn() {},
            error(...args) { errors.push(args.map(String).join(' ')); }
        }
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);

    async function settle() {
        for (let round = 0; round < 50; round++) {
            await new Promise((resolve) => setImmediate(resolve));
            if (!timers.size) { return; }
            const due = Array.from(timers.values());
            timers.clear();
            due.forEach((callback) => callback());
        }
        throw new Error('the form never settled');
    }

    function lastRequest(since) {
        const sent = posted.slice(since).filter((entry) => entry.url === API_URL);
        if (!sent.length) { throw new Error('the form sent no request'); }
        return sent[sent.length - 1].body;
    }

    function act(step) {
        if ('select' in step) {
            const select = document.getElementById(step.select);
            select.value = step.value;
            if (select.value !== step.value) {
                throw new Error(step.select + ' offers no ' + JSON.stringify(step.value));
            }
            select.dispatch('change');
        } else if ('edit' in step) {
            page.form.elements[step.edit].value = step.value;
            page.form.dispatch('input');
        } else if ('load' in step) {
            document.getElementById('btn-load').click();
            document.getElementById('json-dialog-text').value = JSON.stringify(step.load);
            const importButton = created.filter((element) => element.textContent === 'Import').pop();
            importButton.click();
        } else {
            throw new Error('unknown step ' + JSON.stringify(step));
        }
    }

    const source = fs.readFileSync(path.join(FRONTEND, 'js', 'etc.js'), 'utf8');
    vm.runInContext(source, sandbox, { filename: 'etc.js' });

    const requests = [];
    let since = 0;
    await settle();
    requests.push(lastRequest(since));
    for (const step of input.steps || []) {
        since = posted.length;
        act(step);
        await settle();
        requests.push(lastRequest(since));
    }

    if (errors.length) { throw new Error('etc.js reported: ' + errors.join('\n')); }
    process.stdout.write(JSON.stringify(requests));
}

main().catch((error) => {
    process.stderr.write(String(error && error.stack || error) + '\n');
    process.exit(1);
});
