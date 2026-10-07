# Presets

`src/castorGUI/data/presets.json` — the named sites and hardware that let a user
say "Lulin, LOT, Sophia, Sloan r'" instead of spelling out thirty fields.

> Read by both clients: [`castorCLI/presets.py`](../src/castorCLI/presets.py) for
> Python callers ([CLI](cli.md)) and `frontend/js/etc.js` for the browser
> ([GUI](gui_architecture.md)). Kinder serves the file verbatim from its presets
> route, **so its shape is a contract, not an internal detail.** Other files of
> the same shape can be read beside it — see [Several files](#several-files).

## Shape

Fragments are shaped like `castor.schema` itself — `telescope`, `camera`,
`optic_filter`, `environment.location` — rather than dotted-path strings, so a
preset is a literal subset of the request a user would save or send.

A profile owns three catalogues: **telescopes, cameras and filters**. All three
are properties of the observatory — it has the instruments it has, and the filter
wheel holds what it holds — which is why choosing a site is what narrows them,
and why the site selector sits above the other three. They stay separate lists
rather than fixed pairings because cameras do get moved between telescopes.

### Order is significant

The first entry in each catalogue is the default, applied on load so the
calculator opens on a real, named configuration instead of anonymous numbers.

Kinder's presets route serves raw bytes rather than `jsonify` for exactly this
reason — Flask would otherwise alphabetise the keys and scramble the intended
order.

## What a profile may and may not claim

**A profile with an `environment` block is a real observing site**, and applying
it fills in the site's coordinates and sky. A profile without one is a hardware
family only and touches nothing outside `instrument` — deliberately, because
inventing a location for a telescope model would silently produce wrong airmass
and moon geometry rather than an error. Its hardware is still usable under a real
site, named from there — see [Hardware from another
profile](#hardware-from-another-profile).

**`median_seeing_fwhm` is displayed and never applied.** Seeing is a condition of
the night being planned, not a property of the site, and it is the field an
observer is most likely to have set deliberately.

**`caveat` is free text shown beside the profile's name** by every host. A
profile whose numbers are not good enough to plan real observations with says so
here, in the one place a user picking it will actually look —
[`validation/provenance.py`](../validation/provenance.py) records where every
value came from, but that file is in the repository, not in front of someone
choosing from a dropdown. VLT carries one.

## Band-dependent overrides

A filter entry may also carry `environment` and `telescope` fragments, applied
only when that filter is the one selected, overriding the site and the rig.

This exists because **both sky brightness and optical efficiency depend on the
band, and the request has exactly one number for each.** At Lulin the sky runs
21.44 in g' to 20.04 in i' — a factor of 3.8 in background flux — so a single
site-wide figure is wrong for at least two bands whichever one it is.

It goes on the filter rather than into `filter_transmission` because that field
holds the manufacturer's published curve and can be checked against it.
Overwriting a number that has a document behind it with one that does not is
exactly how the FORS2 preset came to be wrong in every band but one.

```jsonc
"Sloan_r": {
  "optic_filter": { ... },              // the published curve
  "environment": {                      // what the sky is through this filter
    "mu_dark": 21.26,
    "zodiacal_share": 0.267,
    "extinction_coeff": 0.314
  },
  "telescope": {                        // keyed by telescope, see below
    "LOT": { "optical_throughput": 0.568 },
    "SLT": { "optical_throughput": 0.474 }
  }
}
```

**The `telescope` override is keyed by telescope id**, and that key is load
bearing. Band-dependent optical efficiency belongs to one specific telescope's
optics, not to the filter in the abstract; two telescopes at the same site can
both carry a measurement for the same filter. An earlier version was not keyed,
and selecting SLT with a filter LOT had measured silently returned LOT's number.
`castor check` now catches an override naming a telescope the profile does not
list — see [CLI](cli.md).

**Only a real site may have its sky overridden this way.** Giving an
`environment` to a filter in a hardware-family profile is refused when the file
is read, rather than being quietly ignored: an unapplied number in a data file is
indistinguishable from a wrong one until somebody measures the difference.

## `mu_dark` means two different things, and the file says which

For **Lulin's g'/r'/i'**, `mu_dark` is the *local* sky only — airglow and light
pollution. The zodiacal light and scattered starlight that were in the original
photometric measurement have been split back out, and `zodiacal_share` records
what fraction of that original total the split removed. The engine adds an
equivalent term back in, sized to wherever the target actually is on the sky,
rather than baking in the one sightline those three bands happened to be measured
down.

**Everywhere else** — the site-wide 21.5 fallback, u', VLT, `other` — there is no
such split, no `zodiacal_share`, and `mu_dark` is the whole moonless sky exactly
as before.

Derivation in `castor/moon.py`'s `ZODIACAL_LATITUDE_SHAPE`; the reasoning and its
limits in [`validation/QUESTIONS.md`](../validation/QUESTIONS.md) 9, 10 and 16.

## Where the numbers come from

Every value in this file has an entry in
[`validation/provenance.py`](../validation/provenance.py) giving its origin —
`MEASURED`, `DOCUMENT`, `DERIVED` or `GUESS` — and a test fails if the file holds
a number the table does not account for, or a different number than the one
recorded. Changing a preset means saying where the new value came from.

`GUESS` rows are not defects to be hidden. They are the honest state of the file,
and naming them is what stops anyone having to rediscover which ones they are.

## Several files

The shipped file need not be the only one. A host can generate profiles of its
own — OWL builds hardware families from its equipment catalogue — and have them
read beside these sites rather than instead of them.

| | reads |
|---|---|
| `presets.load(*paths)` | exactly the files given, merged in order; with none, the shipped file alone |
| `castor` with no `--presets-file`, and castorGUI's presets route (`server.py`) | `presets.search_path()`: the shipped file, then each file on `CASTOR_PRESETS_PATH` |
| `castor … --presets-file A --presets-file B` | A, then B, and nothing else |
| Kinder's presets route | the shipped file alone, as raw bytes; reading the variable too would mean serving `presets.document(*presets.search_path(…))`, still without `jsonify`'s key sorting |

`CASTOR_PRESETS_PATH` is a list like `PATH` (`:`-separated, `;` on Windows).
`load()` never reads it on its own: a library caller gets the files it named.

**Files merge by profile, and nothing is overridden.**

- Profiles keep their order, file by file, so the first file's first profile is
  still the default a host opens on.
- A profile id defined in two files is an error naming both. A quiet override
  would leave the losing profile sitting in its file looking used — the same
  unapplied number the rest of this page refuses. A profile is defined once,
  whole; a second file cannot patch one.
- Every file is held to every rule a single file is.
- Everything outside `profiles`, `_comment` included, is ignored, as it always
  was. A host that hands the document on as written (`presets.document()`, which
  castorGUI's route serves) keeps the first file's.

The [provenance](#where-the-numbers-come-from) table covers the shipped file
only. A file from elsewhere answers for its own numbers.

## Hardware from another profile

`--telescope`, `--camera` and `--filter` — and `resolve()`, `labels()` and
`caveats()` — also take an entry from another profile's catalogue, written
`PROFILE/KEY`:

```bash
castor calc --site lulin --telescope other/RedCat51 --ra 210.8 --dec 54.3 --mag 18 --exp 300 -n 10
```

The site still supplies the location and the sky; only the named entry is
borrowed. This is what makes a hardware family usable without inventing anything:
as a `--site` it has no location to give and the calculation stops for want of
one, but its hardware can be named under a real site.

**What a borrowed filter carries stays where it was measured.**

- Its `environment` override applies only when the filter is the site's own. A
  band's sky belongs to the site it was measured at.
- Its `telescope` override applies only to a telescope from the filter's own
  profile, because the keys name that profile's telescopes. A RedCat under
  Lulin's sky keeps its own throughput rather than the r' figure measured on
  LOT — the bug the [keying](#band-dependent-overrides) exists to stop.

So a hardware family still cannot gain a sky: borrowing a site's filter does not
bring the site along.

**A borrowed entry brings its profile's `caveat`.** `castor calc` prints it
beside the site's, prefixed with the profile id: a camera nobody should plan
with is no more trustworthy for being mounted under a measured sky. An entry
with no `name` is labelled by its qualified name, so the header still says where
it came from.

**No profile id or catalogue key may contain `/`**, and a file holding one is
refused when read: such a name could not be told from a qualified one. None
does today. Qualifying with the site's own profile (`lulin/SLT` under
`--site lulin`) is the plain name written in full.

### In the browser

The browser does not offer `PROFILE/KEY`: its selectors stay within the chosen
profile. Another file's profiles are listed in the same profile selector as the
sites, but a hardware family chosen there is not a site and gives the form no
sky. The form keeps the one it holds — the last site's location, `mu_dark` and
extinction — **less the previous filter's band correction**, which leaves with
that filter just as a borrowed filter's sky stays behind above. So a family
chosen after Lulin sends the preset values this resolves to:

```bash
castor calc --site lulin --telescope FAMILY/T --camera FAMILY/C --filter FAMILY/F …
```

Lulin's site-wide sky, that is, not its r' sky under a filter never measured
there. `tests/test_gui_form.py` holds the browser to that, and to `resolve()`
for every shipped configuration. A sky value typed over by hand, or read in by
LOAD, is the reader's own and stays.

Known limitation: nothing on the page but the location fields says whose sky a
family is running under — the selector shows the family's name — and the way to
choose that site is to pick it first, then the family.
