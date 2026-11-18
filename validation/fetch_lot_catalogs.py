"""Fetch reference catalogues for the calibrated LOT frames (GRB261011A, EP261006a).

Three sources, all over HTTP:

* Gaia DR3 joined with its synthetic photometry (GSPC), whose `*_sdss_mag` are
  standardised to SDSS ugriz. It covers both fields and puts them on one system,
  and it is the primary reference because the Astrodon filters are SDSS-style.
  The full gaia_source cone is kept too, since isolation is judged against
  every Gaia source, not only the ones with XP spectra.
* SkyMapper DR4 PSF magnitudes, as an independent check (a southern survey
  that still reaches EP261006a at dec +12.9).
* Pan-STARRS DR2 mean PSF magnitudes, the catalogue LOT's g'r'i' throughputs
  were measured against (`lulin.py`), so a new band can be put on the same
  footing as those.

Run: python -I validation/fetch_lot_catalogs.py <catalog_dir>
"""
import os
import sys
import urllib.parse
import urllib.request

FIELDS = {"EP261006a": (21.7887, 12.8848), "GRB261011A": (21.894, -21.555)}
RADIUS_DEG = 0.14            # frame is 13.1' across, so 0.14 deg covers the corners

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
SM_TAP = "https://api.skymapper.nci.org.au/public/tap/sync"
PS1_URL = "https://catalogs.mast.stsci.edu/api/v0.1/panstarrs/dr2/mean.csv"

_SDSS = ", ".join(f"s.{b}_sdss_mag, s.{b}_sdss_flux, s.{b}_sdss_flux_error, s.{b}_sdss_flag"
                  for b in "ugriz")
GAIA_Q = f"""
SELECT g.source_id, g.ra, g.dec, g.pmra, g.pmdec, g.phot_g_mean_mag, g.bp_rp, g.ruwe, {_SDSS}
FROM gaiadr3.gaia_source AS g
LEFT OUTER JOIN gaiadr3.synthetic_photometry_gspc AS s ON g.source_id = s.source_id
WHERE 1 = CONTAINS(POINT('ICRS', g.ra, g.dec), CIRCLE('ICRS', {{ra}}, {{dec}}, {{r}}))
"""
SM_Q = """
SELECT object_id, raj2000, dej2000, flags, nimaflags, class_star,
       u_ngood, u_psf, e_u_psf, g_psf, z_ngood, z_psf, e_z_psf
FROM dr4.master
WHERE 1 = CONTAINS(POINT('ICRS', raj2000, dej2000), CIRCLE('ICRS', {ra}, {dec}, {r}))
"""
PS1_COLS = ["objID", "raMean", "decMean", "nDetections", "qualityFlag",
            "gMeanPSFMag", "rMeanPSFMag", "iMeanPSFMag", "iMeanKronMag",
            "zMeanPSFMag", "zMeanPSFMagErr", "zMeanKronMag", "nz"]


def fetch(url, data=None):
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=300) as r:
        text = r.read().decode()
    if text.lstrip().startswith("<"):
        raise RuntimeError(f"error from {url}: {text[:500]}")
    return text


def tap(url, query):
    return fetch(url, urllib.parse.urlencode(dict(REQUEST="doQuery", LANG="ADQL", FORMAT="csv",
                                                  QUERY=query)).encode())


def ps1(ra, dec, r):
    q = urllib.parse.urlencode({"ra": ra, "dec": dec, "radius": r, "nDetections.gte": 5,
                                "columns": "[" + ",".join(PS1_COLS) + "]", "pagesize": 50000})
    return fetch(f"{PS1_URL}?{q}")


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for name, (ra, dec) in FIELDS.items():
        for tag, get in (("gaia", lambda: tap(GAIA_TAP, GAIA_Q.format(ra=ra, dec=dec, r=RADIUS_DEG))),
                         ("skymapper", lambda: tap(SM_TAP, SM_Q.format(ra=ra, dec=dec, r=RADIUS_DEG))),
                         ("ps1", lambda: ps1(ra, dec, RADIUS_DEG))):
            text = get()
            path = os.path.join(out_dir, f"{tag}_{name}.csv")
            with open(path, "w") as fh:
                fh.write(text)
            print(f"{path}: {text.count(chr(10)) - 1} rows", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
