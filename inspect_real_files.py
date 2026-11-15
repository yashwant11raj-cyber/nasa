# inspect_real_files.py
# After-data #1: look INSIDE real SPHEREx cutouts, one from EACH detector (D1-D6).
# Not part of the server. Needs the internet and astroquery (already installed).
#
# It answers four questions (it only PRINTS facts; it decides nothing):
#   1. Is the sky WCS rotated or mirrored (is north up and east left)?
#   2. What are the FLAGS dtype, which bits really occur, and does the FLAGS
#      header say anything about bit VALUES? (UNVERIFIED so far: "bit n = 2**n")
#   3. Is DETECTOR a number or text, and does it match the SIA bandpass name?
#   4. Do all 6 detectors have the same extensions, units and header keys?
#
# Method is the same as try_real_query.py (SIA search, then
# link = access_url + ?center=RA,DECd&size=DEGREES), which worked on 2026-11-15.
#
# Run it with:  python inspect_real_files.py
# It takes about 2-5 minutes the first time (each download took 13-27 s).
# The cutouts are saved in cache/real_cutouts/ (cache/ is in .gitignore), so a
# second run does not download again. Delete that folder to start fresh.
# Output: the console (short) and docs/real_files_report.txt (everything).

import http.client
import time
import urllib.error
import warnings
from pathlib import Path

import numpy as np
from astropy import log as astropy_log
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.utils.data import conf
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
from astroquery.ipac.irsa import Irsa

import config
import targets

conf.remote_timeout = 120          # the IRSA tutorial raises astropy's default timeout this way
astropy_log.setLevel("WARNING")    # hides astropy's long INFO note about "-SIP" in CTYPE

TARGET_ID = "wise0855"
FOV_ARCMIN = 6.0
BANDPASSES = [f"SPHEREx-D{n}" for n in range(1, 7)]   # D1..D6 (seen in the SIA results)
SAVE_DIR = config.CACHE_DIR / "real_cutouts"
REPORT = Path(__file__).parent / "docs" / "real_files_report.txt"

SEARCH_TRIES = 4            # IRSA answered 502 on 2026-11-15, so the search is retried
SEARCH_WAIT_S = 30

# Fallback if the SIA search keeps failing: the ONE link that worked in try_real_query.py
# (copied from docs/real_query_report.txt, "First link"). Only D3. It is for the same
# target position and size, so it only works while TARGET_ID and FOV_ARCMIN are unchanged.
KNOWN_LINKS = {
    "SPHEREx-D3": {
        "url": ("https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W19_1B/"
                "l2b-v27-2026-197/3/level2_2025W19_1B_0116_1D3_spx_l2b-v27-2026-197.fits"
                "?center=133.75976461144327,-7.242186d&size=0.1"),
        "t_min": 60800.700028,
    },
}

lines = []                  # everything printed is also kept for the report file
first_keys = {}             # header keys of the first cutout, to compare the others with it


def say(text="", console=True):
    """Remember a line for the report; print it too unless console=False."""
    lines.append(str(text))
    if console:
        print(text)


def wrap180(angle):
    """Angle in degrees -> the range -180 to +180."""
    return (float(angle) + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------
# 1. Find and download
# ---------------------------------------------------------------
def find_cutouts(coord, size_deg):
    """SIA search. Returns {bandpass: {url, t_min}} with the OLDEST image of each detector."""
    t0 = time.time()
    for attempt in range(SEARCH_TRIES):
        try:
            found = Irsa.query_sia(pos=(coord, 1 * u.arcsec),
                                   collection=list(config.SPHEREX_SIA_COLLECTIONS))
            break
        except Exception as err:
            first_line = str(err).strip().splitlines()[0] if str(err).strip() else ""
            say(f"SIA search failed, try {attempt + 1} of {SEARCH_TRIES}: "
                f"{type(err).__name__}: {first_line[:150]}")
            if attempt == SEARCH_TRIES - 1:
                raise
            time.sleep(SEARCH_WAIT_S)
    say(f"SIA answered in {time.time() - t0:.1f} s with {len(found)} images.")
    found.sort("t_min")
    ra, dec = coord.ra.deg, coord.dec.deg
    chosen = {}
    for row in found:
        band = str(row["energy_bandpassname"])
        if band in BANDPASSES and band not in chosen:
            chosen[band] = {
                "url": f"{row['access_url']}?center={ra},{dec}d&size={size_deg}",
                "t_min": float(row["t_min"]),
            }
    return chosen


def download(url, path, tries=3):
    """Download one cutout and save it on disk (skipped if it is already there)."""
    if path.exists():
        say(f"   already on disk: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    for attempt in range(tries):
        try:
            t0 = time.time()
            with fits.open(url, memmap=False, cache=False) as hdul:
                for hdu in hdul:
                    hdu.data                       # read every extension before the file closes
                hdul.writeto(temp, overwrite=True)
            temp.replace(path)
            say(f"   downloaded in {time.time() - t0:.1f} s")
            return
        except (TimeoutError, urllib.error.URLError, http.client.IncompleteRead,
                http.client.RemoteDisconnected) as err:
            say(f"   transient error ({type(err).__name__}), try {attempt + 1} of {tries}")
            if attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))


# ---------------------------------------------------------------
# 2. Look inside one cutout
# ---------------------------------------------------------------
def look_at_wcs(ih, hdul, coord, shape):
    """Sky WCS: rotation, mirroring, pixel scale, distortion. Returns a dict for the summary."""
    out = {"pa_y": None, "parity": "?", "scale": None, "wave": "?"}
    ny, nx = shape
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        w = WCS(ih)
    say(f"   sky WCS: CTYPE {list(w.wcs.ctype)}, CUNIT {[str(c) for c in w.wcs.cunit]}")
    say(f"            CRVAL {list(w.wcs.crval)}, CRPIX {list(w.wcs.crpix)}")
    say(f"            has CD matrix: {w.wcs.has_cd()}, has PC matrix: {w.wcs.has_pc()}, "
        f"SIP distortion: {w.sip is not None}")
    matrix = w.pixel_scale_matrix * 3600.0
    say(f"            pixel matrix (arcsec per pixel): {matrix.tolist()}, determinant sign "
        f"{'negative' if np.linalg.det(matrix) < 0 else 'positive'}")
    out["scale"] = float(np.mean(proj_plane_pixel_scales(w))) * 3600.0

    # Where do the +x and +y pixel directions point on the sky?
    # Position angle: 0 = north, 90 = east, 270 = west.
    # Normal map (north up, east LEFT): +y is 0 and +x is 270.
    cx, cy = (nx - 1) / 2.0, (ny - 1) / 2.0
    centre = w.pixel_to_world(cx, cy)
    pa_y = float(centre.position_angle(w.pixel_to_world(cx, cy + 10)).deg)
    pa_x = float(centre.position_angle(w.pixel_to_world(cx + 10, cy)).deg)
    turn = wrap180(pa_y)
    diff = (pa_x - pa_y) % 360.0
    if abs(diff - 270.0) < 5:
        parity = "normal (east left when north is up)"
    elif abs(diff - 90.0) < 5:
        parity = "MIRRORED (east right when north is up)"
    else:
        parity = f"unusual (angle between +y and +x is {diff:.1f}, expected 270 or 90)"
    say(f"   direction of +y pixel: {pa_y:.2f} deg from north; of +x pixel: {pa_x:.2f} deg")
    say(f"   -> image is turned by {turn:+.2f} deg from north-up "
        f"({'ROTATED' if abs(turn) > 1 else 'not rotated (within 1 deg)'}); orientation: {parity}")
    out["pa_y"], out["parity"] = turn, parity

    try:
        x, y = w.world_to_pixel(coord)
        say(f"   the target (2026.0 position) is at pixel ({float(x):.1f}, {float(y):.1f}); "
            f"the cutout centre is ({cx:.1f}, {cy:.1f})")
    except Exception as err:
        say(f"   could not place the target ({type(err).__name__}: {err})")

    # Wavelength from the second ("W") WCS. Recipe from IRSA's tutorial (see DATA_NOTES.md).
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sp = WCS(ih, fobj=hdul, key="W")
            sp.sip = None
            values = []
            for label, (px, py) in (("centre", (cx, cy)), ("corner (0,0)", (0, 0)),
                                    ("corner (nx-1,0)", (nx - 1, 0)),
                                    ("corner (0,ny-1)", (0, ny - 1)),
                                    ("corner (nx-1,ny-1)", (nx - 1, ny - 1))):
                wavelength, _bandwidth = sp.pixel_to_world(px, py)
                values.append((label, float(wavelength.to(u.um).value)))
        say("   wavelength (um): " + ", ".join(f"{lab} {val:.4f}" for lab, val in values))
        spread = max(v for _l, v in values) - min(v for _l, v in values)
        say(f"   spread across the cutout: {spread:.4f} um")
        out["wave"] = f"{values[0][1]:.3f} (spread {spread:.3f})"
    except Exception as err:
        say(f"   wavelength FAILED ({type(err).__name__}: {err})")
    return out


def look_at_flags(hdul):
    """FLAGS dtype, which bits really occur, and what the header says. Returns a dict."""
    fl = hdul["FLAGS"]
    data = np.asarray(fl.data)
    say(f"   FLAGS: dtype {data.dtype}, shape {data.shape}, header BITPIX {fl.header.get('BITPIX')}, "
        f"{int((data < 0).sum())} negative values")

    # The header table (MSKNnnnn = name, MSKDnnnn = description). The number is
    # called "bit" in our flags.py: that is the UNVERIFIED part.
    table = {}
    for key in fl.header["MSKN*"]:
        table[int(key[4:])] = fl.header[key]
    values = data.astype(np.int64) & 0xFFFFFFFF          # look at all 32 bits, no sign trouble
    seen = {}
    for b in range(32):
        n = int(np.count_nonzero(values & (1 << b)))
        if n:
            seen[b] = n
    say(f"   header table has {len(table)} entries; bit numbers {sorted(table)}")
    say("   bits that are actually SET in this cutout (bit, name from header, pixels):")
    if not seen:
        say("      (none: every FLAGS pixel is 0)")
    for b, n in seen.items():
        say(f"      bit {b:2d}  {table.get(b, '*** NOT IN THE HEADER TABLE ***'):<14} {n} pixels")
    unknown = [b for b in seen if b not in table]
    say(f"   set bits missing from the header table: {unknown if unknown else 'none'}")

    distinct, counts = np.unique(values, return_counts=True)
    order = np.argsort(-counts)[:8]
    say("   most common FLAGS values (value, pixels, bits set):")
    for i in order:
        v = int(distinct[i])
        say(f"      {v:>12d}  {int(counts[i]):>6d}  {[b for b in range(32) if v & (1 << b)]}")

    # Header cards that are NOT part of the MSKN/MSKD table: they might hold bit values.
    other = [c for c in fl.header.cards if not str(c.keyword).startswith(("MSKN", "MSKD"))]
    say(f"   FLAGS header: {len(fl.header)} cards; {len(other)} are not MSKN/MSKD. Their names:")
    say("      " + " ".join(sorted({str(c.keyword) for c in other})))
    return {"dtype": str(data.dtype), "seen": sorted(seen), "unknown": unknown}


def look_at_cutout(band, info, path, coord):
    """Print everything we want to know about one saved cutout. Returns a summary dict."""
    global first_keys
    say("\n" + "=" * 70)
    say(f"{band}   ({path.name})")
    summary = {"band": band}
    with fits.open(path, memmap=False) as hdul:
        ih = hdul["IMAGE"].header

        say("Extensions:")
        shapes = {}
        for hdu in hdul:
            if isinstance(hdu, fits.BinTableHDU):
                say(f"   {hdu.name:<9} table {len(hdu.data)} rows, columns {hdu.columns.names}, "
                    f"formats {hdu.columns.formats}")
            elif hdu.data is None:
                say(f"   {hdu.name:<9} no data, {len(hdu.header)} header cards")
            else:
                shapes[hdu.name] = hdu.data.shape
                say(f"   {hdu.name:<9} shape {hdu.data.shape}, dtype {hdu.data.dtype}, "
                    f"BUNIT {hdu.header.get('BUNIT')!r}")
        same = len({shapes.get(n) for n in ("IMAGE", "FLAGS", "VARIANCE", "ZODI")}) == 1
        say(f"   IMAGE, FLAGS, VARIANCE and ZODI have the same shape: {same}")
        summary["shape"] = shapes.get("IMAGE")

        # DETECTOR: number or text? Does it match the SIA bandpass name?
        say("DETECTOR:")
        for name, header in (("PRIMARY", hdul[0].header), ("IMAGE", ih)):
            if "DETECTOR" in header:
                value = header["DETECTOR"]
                say(f"   in {name}: {value!r}  (Python type {type(value).__name__})")
                if name == "IMAGE":
                    summary["det"] = f"{value!r} {type(value).__name__}"
            else:
                say(f"   no DETECTOR card in {name}")
        say(f"   IMAGE header cards with DET in the name: {[k for k in ih if 'DET' in k.upper()]}")
        say(f"   SIA bandpass name for this file: {band}")

        # Observation time cross-check (DATA_NOTES says t_min equals MJD-OBS)
        say(f"Time: SIA t_min {info['t_min']:.6f} | header MJD-OBS {ih.get('MJD-OBS')} | "
            f"DATE-OBS {ih.get('DATE-OBS')} | DATE-AVG {ih.get('DATE-AVG')} | DATE {ih.get('DATE')} (processing)")

        # IMAGE and VARIANCE values
        img = np.asarray(hdul["IMAGE"].data, dtype=float)
        var = np.asarray(hdul["VARIANCE"].data, dtype=float)
        say(f"IMAGE: {100 * (1 - np.isfinite(img).mean()):.1f}% NaN, min {np.nanmin(img):.4g}, "
            f"median {np.nanmedian(img):.4g}, max {np.nanmax(img):.4g}")
        say(f"VARIANCE: {100 * (1 - np.isfinite(var).mean()):.1f}% NaN, min {np.nanmin(var):.4g}, "
            f"median {np.nanmedian(var):.4g}, negative values: {int((var < 0).sum())}")

        say("Sky WCS and wavelength:")
        summary.update(look_at_wcs(ih, hdul, coord, img.shape))
        say("FLAGS:")
        flag_info = look_at_flags(hdul)
        summary["flags"] = flag_info

        # Header keys: full dump for the FIRST cutout (report file only), differences for the others
        keys = set(ih.keys())
        if not first_keys:
            first_keys = keys
            say("   (full IMAGE and FLAGS headers of this first cutout are in the report file)")
            say("\n--- FULL IMAGE HEADER ---", console=False)
            say(ih.tostring(sep="\n"), console=False)
            say("\n--- FULL FLAGS HEADER ---", console=False)
            say(hdul["FLAGS"].header.tostring(sep="\n"), console=False)
        else:
            say(f"IMAGE header keys that this cutout LACKS compared with the first one: "
                f"{sorted(first_keys - keys) or 'none'}")
            say(f"IMAGE header keys that this cutout HAS extra: {sorted(keys - first_keys) or 'none'}")
    return summary


def main():
    ra, dec = targets.position_at_epoch(TARGET_ID, 2026.0)
    ra %= 360.0
    coord = SkyCoord(ra * u.deg, dec * u.deg)
    size_deg = FOV_ARCMIN / 60
    say(f"Target {TARGET_ID} at 2026.0: RA {ra:.6f}, Dec {dec:+.6f}, cutout {FOV_ARCMIN} arcmin = {size_deg} deg")

    try:
        chosen = find_cutouts(coord, size_deg)
    except Exception as err:
        say(f"SIA search FAILED for good: {type(err).__name__}")
        say("FALLBACK: using the one known link (D3 only). D1, D2, D4, D5 and D6 are NOT "
            "inspected; run the script again when IRSA's SIA service is back.")
        chosen = dict(KNOWN_LINKS)
    missing = [b for b in BANDPASSES if b not in chosen]
    say(f"Chosen (oldest image of each detector): {sorted(chosen)}; missing: {missing or 'none'}")

    summaries = []
    for band in BANDPASSES:
        if band not in chosen:
            continue
        info = chosen[band]
        say(f"\nDownloading {band} ...")
        path = SAVE_DIR / f"{TARGET_ID}_{band}_{info['t_min']:.5f}_fov{FOV_ARCMIN:g}.fits"
        try:
            download(info["url"], path)
            summaries.append(look_at_cutout(band, info, path, coord))
        except Exception as err:
            say(f"   {band} FAILED: {type(err).__name__}: {err}")

    # One compact table to paste back
    say("\n" + "=" * 70)
    say("SUMMARY (one line per detector)")
    for s in summaries:
        flags = s.get("flags", {})
        say(f"{s['band']}: shape {s.get('shape')} | DETECTOR {s.get('det')} | "
            f"scale {s.get('scale') or 0:.3f} arcsec | turned {s.get('pa_y')} deg | {s.get('parity')} | "
            f"FLAGS {flags.get('dtype')}, bits set {flags.get('seen')}, not in table {flags.get('unknown')} | "
            f"wavelength {s.get('wave')}")


main()
REPORT.parent.mkdir(exist_ok=True)
REPORT.write_text("\n".join(lines), encoding="utf-8")
print(f"\nFull report saved to {REPORT}. Paste the console output back to me.")