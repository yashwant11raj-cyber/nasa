# test_overlays.py
# Tests overlays.py (Backend 33). Run it with:  python test_overlays.py
# Parts 1-3 need only numpy. Parts 4-5 need astropy (it is in requirements.txt).
# NO internet is used: the online catalogue is replaced by a small fake function.
# (To try the REAL catalogues by hand, run:  python overlays.py)

import math
from datetime import datetime

import numpy as np

import overlays
import targets
from overlays import OverlayError

problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


def fails(func, *args, **kwargs):
    """True if the call raises OverlayError. Prints the message."""
    try:
        func(*args, **kwargs)
    except OverlayError as err:
        print(f"        message: {err}")
        return True
    print("        NO ERROR RAISED")
    return False


def gaia_row(ident, ra, dec, pmra=0.0, pmdec=0.0, mag=15.0):
    """A fake row that uses the Gaia column names from overlays.CATALOGS."""
    return {"source_id": ident, "ra": ra, "dec": dec, "pmra": pmra, "pmdec": pmdec, "phot_g_mean_mag": mag}


print("--- Part 1: normalize_rows ---")
rows = overlays.normalize_rows([gaia_row(111, 150.0, 2.0, 5.0, -3.0, 12.5)], "gaia")
check("one row in, one row out", len(rows) == 1)
r = rows[0]
check("our own key names are used",
      r["id"] == "111" and r["ra_deg"] == 150.0 and r["dec_deg"] == 2.0
      and r["pmra_mas_yr"] == 5.0 and r["pmdec_mas_yr"] == -3.0 and r["mag"] == 12.5)
check("catalogue name and epoch are added", r["catalog"] == "gaia" and r["epoch"] == overlays.CATALOGS["gaia"]["epoch"])
check("a NaN proper motion becomes None", overlays.normalize_rows([gaia_row(1, 1, 1, float("nan"), 2.0)], "gaia")[0]["pmra_mas_yr"] is None)
check("a masked value becomes None",
      overlays.normalize_rows([gaia_row(1, 1, 1, np.ma.masked, 2.0)], "gaia")[0]["pmra_mas_yr"] is None)
check("a missing magnitude becomes None", overlays.normalize_rows([gaia_row(1, 1, 1, mag=None)], "gaia")[0]["mag"] is None)
check("a row without a usable RA is left out", overlays.normalize_rows([gaia_row(1, float("nan"), 1), gaia_row(2, 10, 1)], "gaia")[0]["id"] == "2")
check("RA 400 and Dec 95 are left out", overlays.normalize_rows([gaia_row(1, 400, 1), gaia_row(2, 10, 95)], "gaia") == [])
check("an empty answer gives an empty list", overlays.normalize_rows([], "gaia") == [])
check("a missing RA column is refused with the real column names in the message",
      fails(overlays.normalize_rows, [{"foo": 1, "bar": 2}], "gaia"))
wise = overlays.normalize_rows([{"designation": "J0855", "ra": 133.7, "dec": -7.2, "pmra": 1.0, "pmdec": 2.0, "w1mpro": 17.0}], "wise")
check("the WISE column names work too", wise[0]["id"] == "J0855" and wise[0]["mag"] == 17.0 and wise[0]["catalog"] == "wise")
check("an unknown catalogue is refused", fails(overlays.normalize_rows, [], "banana"))
check("OverlayError is a ValueError", issubclass(OverlayError, ValueError))

print("\n--- Part 2: fetch_sources (with a fake online service) ---")
asked = []


def fake_fetcher(ra, dec, radius):
    asked.append((ra, dec, radius))
    return [gaia_row(1, 150.0, 2.0, mag=10.0), gaia_row(2, 150.01, 2.01, mag=14.0)]


got = overlays.fetch_sources("gaia", 150.0, 2.0, 6.0, fetcher=fake_fetcher)
check("two sources come back, normalised", len(got) == 2 and got[0]["id"] == "1")
expected_radius = 3.0 * math.sqrt(2) + overlays.SEARCH_MARGIN_ARCMIN
check(f"the search radius covers the corners of the cutout plus the margin ({expected_radius:.2f} arcmin)",
      abs(asked[0][2] - expected_radius) < 1e-9 and asked[0][:2] == (150.0, 2.0))
check("search_radius_arcmin grows with the field of view",
      overlays.search_radius_arcmin(30) > overlays.search_radius_arcmin(6))


def broken_fetcher(ra, dec, radius):
    raise ConnectionError("pretend the service is down")


check("a failing service gives a friendly OverlayError", fails(overlays.fetch_sources, "gaia", 150, 2, 6, broken_fetcher))
check("a fetcher that returns None gives an empty list", overlays.fetch_sources("gaia", 150, 2, 6, lambda a, b, c: None) == [])
check("an unknown catalogue is refused", fails(overlays.fetch_sources, "banana", 150, 2, 6, fake_fetcher))
check("RA 400 is refused", fails(overlays.fetch_sources, "gaia", 400, 2, 6, fake_fetcher))
check("Dec text is refused", fails(overlays.fetch_sources, "gaia", 150, "x", 6, fake_fetcher))
check("FOV 0 is refused", fails(overlays.fetch_sources, "gaia", 150, 2, 0, fake_fetcher))
check("the catalogue table lists gaia and wise", set(overlays.CATALOGS) == {"gaia", "wise"})

print("\n--- Part 3: position_at_year (proper motion) ---")
base = {"ra_deg": 100.0, "dec_deg": 60.0, "pmra_mas_yr": 1000.0, "pmdec_mas_yr": 2000.0, "epoch": 2016.0}
ra, dec = overlays.position_at_year(base, 2016.0)
check("in the catalogue year the position does not change", ra == 100.0 and dec == 60.0)
ra, dec = overlays.position_at_year(base, 2026.0)
check("Dec moves by pmdec * years (2000 mas/yr * 10 yr = 20 arcsec)", abs((dec - 60.0) * 3600 - 20.0) < 1e-6)
check("RA moves by pmra / cos(Dec) (1000 mas/yr * 10 yr = 10 arcsec on the sky = 20 arcsec of RA at Dec 60)",
      abs((ra - 100.0) * 3600 - 20.0) < 1e-6)
ra, dec = overlays.position_at_year(base, 2006.0)
check("a year BEFORE the catalogue year moves backwards", ra < 100.0 and dec < 60.0)
none = dict(base, pmra_mas_yr=None, pmdec_mas_yr=None)
check("without proper motion nothing moves", overlays.position_at_year(none, 2030.0) == (100.0, 60.0))
barnard = dict(base, ra_deg=269.45, dec_deg=4.69, pmra_mas_yr=-801.551, pmdec_mas_yr=10362.394)
_, d = overlays.position_at_year(barnard, 2026.0)
check("Barnard's Star moves about 104 arcsec north in 10 years", abs((d - 4.69) * 3600 - 103.62394) < 1e-4)
wrap = dict(base, ra_deg=359.9999, dec_deg=0.0, pmra_mas_yr=5000.0, pmdec_mas_yr=0.0)
check("RA wraps past 360 back to 0", 0 <= overlays.position_at_year(wrap, 2026.0)[0] < 1.0)

print("\n--- Part 4: place_sources (needs astropy) ---")
try:
    from astropy.wcs import WCS
except ImportError:
    print("SKIPPED  astropy is not installed here")
else:
    import processing

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [150.0, 2.0]
    w.wcs.crpix = [25.5, 25.5]                    # 1-based, so pixel 24.5 counting from 0
    w.wcs.cdelt = [-6.2 / 3600, 6.2 / 3600]
    w.wcs.cunit = ["deg", "deg"]

    def frame(when):
        return {"image": np.zeros((50, 50)), "wcs": w, "obs_time": when}

    frames = [frame(datetime(2026, 1, 1)), frame(datetime(2027, 1, 1))]

    def row(ident, ra, dec, pmra=None, pmdec=None, mag=15.0, epoch=2025.0):
        return {"id": ident, "ra_deg": ra, "dec_deg": dec, "pmra_mas_yr": pmra, "pmdec_mas_yr": pmdec,
                "mag": mag, "catalog": "gaia", "epoch": epoch}

    fixed = row("fixed", 150.0, 2.0, 0.0, 0.0)
    mover = row("mover", 150.0, 2.0, 0.0, 6200.0)        # 6.2 arcsec per year = 1 pixel per year, north
    far = row("far", 151.0, 2.0)
    placed = overlays.place_sources(frames, [fixed, mover, far])
    print("   placed:", [p["id"] for p in placed])
    check("a source far outside every frame is left out", [p["id"] for p in placed] == ["fixed", "mover"] or
          sorted(p["id"] for p in placed) == ["fixed", "mover"])
    p = next(p for p in placed if p["id"] == "fixed")
    check("each source has a path with one entry per frame", len(p["path"]) == 2)
    check("a path entry has index, x, y, png_x, png_y, inside",
          set(p["path"][0]) == {"index", "x", "y", "png_x", "png_y", "inside"})
    check("the fixed source sits at pixel (24.5, 24.5) in both frames",
          all(abs(e["x"] - 24.5) < 0.02 and abs(e["y"] - 24.5) < 0.02 and e["inside"] for e in p["path"]))
    check("png position matches processing.pixel_to_png_position",
          (p["path"][0]["png_x"], p["path"][0]["png_y"])
          == processing.pixel_to_png_position(p["path"][0]["x"], p["path"][0]["y"], 50, 50))
    m = next(p for p in placed if p["id"] == "mover")
    print(f"   mover y: {m['path'][0]['y']:.2f} then {m['path'][1]['y']:.2f}")
    check("the mover is moved to the date of each frame: 1 pixel north in 2026, 2 pixels north in 2027",
          abs(m["path"][0]["y"] - 25.5) < 0.03 and abs(m["path"][1]["y"] - 26.5) < 0.03)
    check("pm_known is True for the mover and the fixed source (0 is a known value)", m["pm_known"] and p["pm_known"])
    check("a source without proper motion has pm_known False",
          overlays.place_sources(frames, [row("nopm", 150.0, 2.0)])[0]["pm_known"] is False)
    check("the input rows are not changed", "path" not in mover and mover["dec_deg"] == 2.0)
    check("original frames are not changed", "x" not in frames[0])

    many = [row(f"s{i}", 150.0 + 0.0005 * i, 2.0, mag=10.0 + i) for i in range(6)]
    top = overlays.place_sources(frames, list(reversed(many)), max_sources=3)
    check("max_sources keeps the brightest (smallest magnitudes: s0, s1, s2)", [s["id"] for s in top] == ["s0", "s1", "s2"])
    nomag = overlays.place_sources(frames, [row("dim", 150.0, 2.0, mag=None), row("bright", 150.001, 2.0, mag=9.0)], max_sources=1)
    check("a source without a magnitude comes last", nomag[0]["id"] == "bright")
    check("no rows gives an empty list", overlays.place_sources(frames, []) == [])
    check("no frames gives an empty list", overlays.place_sources([], [fixed]) == [])
    check("max_sources 0 is refused", fails(overlays.place_sources, frames, [fixed], 0))
    nowcs = [{"image": np.zeros((5, 5)), "obs_time": datetime(2026, 1, 1)}]
    check("a frame without a WCS gives no sources and no crash", overlays.place_sources(nowcs, [fixed]) == [])

    print("\n--- Part 5: get_overlay ---")
    def gaia_fetcher(ra, dec, radius):
        return [gaia_row(1, 150.0, 2.0, mag=11.0), gaia_row(2, 150.002, 2.001, mag=13.0), gaia_row(3, 160.0, 2.0)]

    out = overlays.get_overlay(frames, "gaia", 150.0, 2.0, 6.0, fetcher=gaia_fetcher)
    check("get_overlay returns catalog, label, epoch, source_count, sources",
          set(out) == {"catalog", "label", "epoch", "source_count", "sources"})
    check("label and epoch come from CATALOGS", out["label"] == "Gaia DR3" and out["epoch"] == overlays.CATALOGS["gaia"]["epoch"])
    check("the source far away (RA 160) is left out, 2 remain", out["source_count"] == 2 and len(out["sources"]) == 2)
    check("sources are brightest first", [s["id"] for s in out["sources"]] == ["1", "2"])
    check("a failing service gives an OverlayError", fails(overlays.get_overlay, frames, "gaia", 150.0, 2.0, 6.0, broken_fetcher))
    check("an unknown catalogue gives an OverlayError", fails(overlays.get_overlay, frames, "banana", 150.0, 2.0, 6.0, gaia_fetcher))

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")