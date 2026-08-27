# Presets

`src/castorGUI/data/presets.json` — the named sites and hardware that let a user
say "Lulin, LOT, Sophia, Sloan r'" instead of spelling out thirty fields.

> Read by both clients: [`castorCLI/presets.py`](../src/castorCLI/presets.py) for
> Python callers ([CLI](cli.md)) and `frontend/js/etc.js` for the browser
> ([GUI](gui_architecture.md)). Kinder serves the file verbatim from its presets
> route, **so its shape is a contract, not an internal detail.**

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
and moon geometry rather than an error.

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
