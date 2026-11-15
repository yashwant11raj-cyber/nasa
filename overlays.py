# overlays.py
# Backend 33: known stars from other telescopes (Gaia, WISE) as pixel positions,
# so the page can draw little circles on top of the SPHEREx pictures.
#
# Two separate jobs:
#   1. FETCH   fetch_sources()   asks an online catalogue for the sources around
#                                a position (needs the internet and astroquery).
#   2. PLACE   place_sources()   turns catalogue rows into a pixel position in
#                                EVERY frame. Pure maths, no internet. Stars move
#                                (proper motion), so each source is first moved
#                                to the date of each frame.
#   get_overlay() does both.
#
# Why the move matters: Gaia positions are for the year 2016 and WISE positions
# for about 2010, but SPHEREx observes in 2025 and 2026. Barnard's Star moves
# about 10 arcsec in a year, which is almost two SPHEREx pixels. Without the
# move the circle would sit in the wrong place.
#
# !!! WHAT IS AND IS NOT VERIFIED !!!
# I could not run any online query while writing this file. Everything in the
# CATALOGS table below (the table names, the column names, the epochs) comes
# from my memory of the Gaia and AllWISE documentation. It is NOT checked.
# Run   python overlays.py   once with the internet on: it prints the real
# column names it received, so you can compare them with the table. If a name is
# wrong, change that ONE entry in CATALOGS and nothing else.
#
# The fetch function can be replaced (parameter `fetcher`), so every other part
# of this file is tested offline with a fake catalogue (see test_overlays.py).
# This file is NOT connected to main.py and never changes the frames.
#
# Pixel convention: x, y counted from 0, y from the bottom row (as everywhere).
# png_x / png_y are the same spot in the PNG picture (processing.pixel_to_png_position).

import math
import sys

import numpy as np

import targets


class OverlayError(ValueError):
    """The overlay could not be made. The message is safe to show to a user."""


# ---------- The catalogues (UNVERIFIED, see the note at the top) ----------
#   label    name to show a person
#   epoch    the year the catalogue positions are valid for (UNVERIFIED)
#   columns  our name -> the catalogue's column name (UNVERIFIED)
#            id = source name or number, mag = one brightness value to show
CATALOGS = {
    "gaia": {
        "label": "Gaia DR3",
        "epoch": 2016.0,
        "columns": {"id": "source_id", "ra": "ra", "dec": "dec",
                    "pmra": "pmra", "pmdec": "pmdec", "mag": "phot_g_mean_mag"},
    },
    "wise": {
        "label": "AllWISE",
        "epoch": 2010.5,
        "columns": {"id": "designation", "ra": "ra", "dec": "dec",
                    "pmra": "pmra", "pmdec": "pmdec", "mag": "w1mpro"},
    },
}

# Most sources kept per request. A first guess: a crowded field would otherwise
# make the page draw thousands of circles. Retune on real data.
MAX_SOURCES = 300

# The search circle is the cutout's half-diagonal plus this margin (arcmin), so
# stars that move INTO the picture between the catalogue year and now are found.
# A guess: Barnard's Star moves about 2.5 arcmin in 15 years.
SEARCH_MARGIN_ARCMIN = 3.0


def _number(value):
    """A real, finite float, or None (for masked, empty, NaN or non-numeric values)."""
    try:
        if np.ma.is_masked(value):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _check_catalog(catalog):
    if catalog not in CATALOGS:
        raise OverlayError(f"Unknown catalogue '{catalog}'. Choose one of: {', '.join(CATALOGS)}.")
    return CATALOGS[catalog]


def search_radius_arcmin(fov_arcmin, margin_arcmin=SEARCH_MARGIN_ARCMIN):
    """Radius of the circle that covers the whole square cutout (plus a margin)."""
    fov = _number(fov_arcmin)
    margin = _number(margin_arcmin)
    if fov is None or fov <= 0:
        raise OverlayError("The field of view must be a number greater than zero.")
    if margin is None or margin < 0:
        raise OverlayError("The margin must be a number of zero or more.")
    return fov / 2.0 * math.sqrt(2.0) + margin


# ---------- 1. FETCH ----------

def _fetch_gaia(ra_deg, dec_deg, radius_arcmin):
    """Ask Gaia (astroquery.gaia). UNVERIFIED: written from the astroquery docs
    from memory; not run. Returns an astropy Table."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astroquery.gaia import Gaia
    Gaia.ROW_LIMIT = MAX_SOURCES * 3        # the default limit is small (UNVERIFIED how it is applied)
    coord = SkyCoord(ra_deg * u.deg, dec_deg * u.deg, frame="icrs")
    job = Gaia.cone_search_async(coord, radius=radius_arcmin * u.arcmin)
    return job.get_results()


def _fetch_wise(ra_deg, dec_deg, radius_arcmin):
    """Ask IRSA for AllWISE (astroquery.ipac.irsa, which this project already uses
    for SPHEREx). UNVERIFIED: the catalogue name 'allwise_p3as_psd' and the call
    are from memory; not run. Returns an astropy Table."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astroquery.ipac.irsa import Irsa
    coord = SkyCoord(ra_deg * u.deg, dec_deg * u.deg, frame="icrs")
    return Irsa.query_region(coordinates=coord, catalog="allwise_p3as_psd",
                             spatial="Cone", radius=radius_arcmin * u.arcmin)


_FETCHERS = {"gaia": _fetch_gaia, "wise": _fetch_wise}


def normalize_rows(table, catalog):
    """Turn a catalogue answer into a list of simple dictionaries.

    table: an astropy Table, or a list of dictionaries, using the catalogue's own
           column names (CATALOGS[catalog]["columns"]).
    Each result has: id, ra_deg, dec_deg, pmra_mas_yr, pmdec_mas_yr (None when
    unknown), mag (None when unknown), catalog, epoch.
    Rows without a usable RA and Dec are left out.
    Raises OverlayError if a needed column is missing.
    """
    info = _check_catalog(catalog)
    cols = info["columns"]
    names = list(getattr(table, "colnames", None) or (table[0].keys() if len(table) else []))
    if len(table) and not all(cols[k] in names for k in ("ra", "dec")):
        raise OverlayError(
            f"The {info['label']} answer has no '{cols['ra']}' / '{cols['dec']}' columns. "
            f"It has: {', '.join(map(str, names))}. Fix the column names in overlays.CATALOGS.")

    def get(row, key):
        return row[cols[key]] if cols[key] in names else None

    rows = []
    for row in table:
        ra, dec = _number(get(row, "ra")), _number(get(row, "dec"))
        if ra is None or dec is None or not (0 <= ra <= 360 and -90 <= dec <= 90):
            continue
        ident = get(row, "id")
        rows.append({
            "id": None if ident is None or np.ma.is_masked(ident) else str(ident),
            "ra_deg": ra, "dec_deg": dec,
            "pmra_mas_yr": _number(get(row, "pmra")),
            "pmdec_mas_yr": _number(get(row, "pmdec")),
            "mag": _number(get(row, "mag")),
            "catalog": catalog,
            "epoch": info["epoch"],
        })
    return rows


def fetch_sources(catalog, ra_deg, dec_deg, fov_arcmin, fetcher=None):
    """Ask a catalogue for the sources around a position. Returns normalised rows.

    catalog:  "gaia" or "wise".
    fetcher:  a function (ra_deg, dec_deg, radius_arcmin) -> table. Tests use it to
              pretend to be the online service. Normally leave it None.
    Raises OverlayError (friendly message) if the service fails.
    """
    info = _check_catalog(catalog)
    ra, dec = _number(ra_deg), _number(dec_deg)
    if ra is None or dec is None or not (0 <= ra <= 360 and -90 <= dec <= 90):
        raise OverlayError("RA must be 0 to 360 degrees and Dec must be -90 to +90 degrees.")
    radius = search_radius_arcmin(fov_arcmin)
    try:
        table = (fetcher or _FETCHERS[catalog])(ra, dec, radius)
    except Exception as err:
        raise OverlayError(
            f"I couldn't get the {info['label']} sources. The online service may be down, or the "
            f"query needs fixing (error type: {type(err).__name__}). "
            f"The SPHEREx pictures still work without the overlay.") from err
    if table is None:
        return []
    return normalize_rows(table, catalog)


# ---------- 2. PLACE ----------

def position_at_year(row, year):
    """(ra_deg, dec_deg) of a catalogue row moved to `year` with its proper motion.

    A row without proper motion is not moved. Straight-line motion, no parallax
    (the same simple method as targets.position_at_epoch).
    """
    years = year - row["epoch"]
    pmra, pmdec = row.get("pmra_mas_yr"), row.get("pmdec_mas_yr")
    d_dec = (pmdec or 0.0) * years / 3_600_000                    # mas -> degrees
    # pmra already includes cos(Dec), so divide it out to get a change in RA
    cos_dec = max(math.cos(math.radians(row["dec_deg"])), 1e-6)
    d_ra = (pmra or 0.0) * years / 3_600_000 / cos_dec
    return (row["ra_deg"] + d_ra) % 360.0, row["dec_deg"] + d_dec


def place_sources(frames, rows, max_sources=MAX_SOURCES):
    """Where every source is in every frame. Returns a list, one entry per source.

    Each entry: the row's keys plus
      pm_known   True if the row had a proper motion (False = not moved)
      path       one dictionary per frame: index, x, y, png_x, png_y, inside
                 (x, y are None for a frame without a WCS)
    A source that is outside EVERY frame is left out. When there are more than
    max_sources sources, the brightest ones are kept (smaller mag = brighter;
    sources without a magnitude come last). Frames are not changed.
    """
    if isinstance(max_sources, bool) or not isinstance(max_sources, int) or max_sources < 1:
        raise OverlayError("max_sources must be a whole number of 1 or more.")
    if not frames or not rows:
        return []
    import processing                      # loaded here so the pure maths above needs no astropy

    times = [targets.decimal_year(f["obs_time"]) for f in frames]
    ordered = sorted(rows, key=lambda r: (r["mag"] is None, r["mag"] if r["mag"] is not None else 0.0))

    placed = []
    for row in ordered:
        positions = [position_at_year(row, year) for year in times]
        located = processing.locate_in_frames(frames, positions)
        if not any(p["inside"] for p in located):
            continue
        entry = dict(row)
        entry["pm_known"] = row["pmra_mas_yr"] is not None and row["pmdec_mas_yr"] is not None
        entry["path"] = [{k: p[k] for k in ("index", "x", "y", "png_x", "png_y", "inside")} for p in located]
        placed.append(entry)
        if len(placed) >= max_sources:
            break
    return placed


def get_overlay(frames, catalog, ra_deg, dec_deg, fov_arcmin, fetcher=None, max_sources=MAX_SOURCES):
    """Fetch a catalogue and place its sources in the frames. Returns a dictionary:
      catalog, label, epoch, source_count, sources (see place_sources)
    Raises OverlayError.
    """
    info = _check_catalog(catalog)
    rows = fetch_sources(catalog, ra_deg, dec_deg, fov_arcmin, fetcher)
    sources = place_sources(frames, rows, max_sources)
    return {"catalog": catalog, "label": info["label"], "epoch": info["epoch"],
            "source_count": len(sources), "sources": sources}


if __name__ == "__main__":
    # Needs the internet. Run:  python overlays.py            (WISE 0855, Gaia)
    #                           python overlays.py wise
    # It prints the REAL column names, so you can check the CATALOGS table.
    catalog = sys.argv[1] if len(sys.argv) > 1 else "gaia"
    ra, dec = targets.position_at_epoch("wise0855", 2026.0)
    print(f"Asking {catalog} around RA {ra % 360:.5f}, Dec {dec:+.5f} (6 arcmin field)...")
    try:
        table = _FETCHERS[catalog](ra % 360.0, dec, search_radius_arcmin(6.0))
    except Exception as err:
        print(f"FAILED: {type(err).__name__}: {err}")
        raise SystemExit
    print(f"{len(table)} rows. Real column names: {table.colnames}")
    print("Names expected by overlays.CATALOGS:", CATALOGS[catalog]["columns"])
    try:
        rows = normalize_rows(table, catalog)
        print(f"normalize_rows kept {len(rows)} rows. First one: {rows[0] if rows else None}")
    except OverlayError as err:
        print("Problem:", err)