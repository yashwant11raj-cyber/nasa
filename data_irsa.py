# data_irsa.py
# Real data source (IRSA / SPHEREx).
#
# Written now (after-data #2 to #5):
#   search_images()      which images cover a position (SIA search)        #2
#   download_cutout()    one cutout into memory, with retries              #3
#   read_cutout()        one downloaded cutout -> one frame dictionary     #4
#   centre_wavelength()  wavelength at the middle of a cutout              #4
#   wavelength_map()     wavelength of EVERY pixel of a cutout             #5
#
# NOT written yet: get_frames(). The pieces above exist, but without the frame
# limit (#8), robust downloading (#10) and re-aligning onto one north-up grid
# (#30), one request would download 258 cutouts one after another (over an hour)
# and give rotated pictures. main.py still answers 501 for real data.
#
# Facts marked "verified" were seen in docs/real_files_report.txt (run on
# 2026-11-15). Facts marked UNVERIFIED have not been checked by running code.
# Real cutouts: PRIMARY (no data), IMAGE, FLAGS, VARIANCE, ZODI, EPSF, WCS-WAVE.

import http.client
import math
import re
import time
import urllib.error
import warnings
from datetime import datetime, timedelta

import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.wcs import WCS

import config

# Start of every cutout link. Verified: the SIA access_url starts with this.
IRSA_BASE_URL = "https://irsa.ipac.caltech.edu/"

# Bandpass names. Verified: the SIA results had SPHEREx-D1 ... SPHEREx-D6.
_BANDPASS = re.compile(r"^SPHEREx-D[1-6]$")

# The keys every frame must have (see FRAME_FORMAT.md).
FRAME_KEYS = ("image", "wcs", "obs_time", "wavelength_um", "detector",
              "flags", "variance", "source_file")

# Retry settings. First guesses; retune in after-data #10.
SEARCH_TRIES = 3
SEARCH_WAIT_S = 10          # waits 10 s, then 20 s ...
DOWNLOAD_TRIES = 3
DOWNLOAD_WAIT_S = 10
DOWNLOAD_TIMEOUT_S = 120    # IRSA's tutorial raises astropy's default timeout to 120 s

# Errors that are worth trying again (the ones IRSA's tutorials mention).
_TRANSIENT = (TimeoutError, ConnectionError, urllib.error.URLError,
              http.client.IncompleteRead, http.client.RemoteDisconnected)

# MJD (days) of 1970-01-01. Verified: SIA t_min is an MJD.
_MJD_OF_1970 = 40587.0


def _not_written(name, step):
    raise NotImplementedError(
        f"data_irsa.{name}() is not written yet (TODO after-data #{step}). "
        f"Set USE_MOCK = True in config.py to use the mock data.")


def _check_position(ra_deg, dec_deg):
    """RA and Dec as floats, or ValueError."""
    ra, dec = float(ra_deg), float(dec_deg)
    if not (math.isfinite(ra) and 0 <= ra <= 360):
        raise ValueError("RA must be between 0 and 360 degrees.")
    if not (math.isfinite(dec) and -90 <= dec <= 90):
        raise ValueError("Dec must be between -90 and +90 degrees.")
    return ra, dec


def size_degrees(fov_arcmin):
    """Cutout size for the IRSA link, in DEGREES (verified: 0.1 gave about 6 arcmin)."""
    fov = float(fov_arcmin)
    if not math.isfinite(fov) or fov <= 0:
        raise ValueError("Field of view must be a number greater than zero.")
    return round(fov / 60.0, 6)


def mjd_to_datetime(mjd):
    """MJD (days) -> naive UTC datetime, like the mock frames use."""
    return datetime(1970, 1, 1) + timedelta(days=float(mjd) - _MJD_OF_1970)


def build_search_query(ra_deg, dec_deg, fov_arcmin, bandpass=None):
    """The TAP query text for 'which images cover this position' (no network).

    NOT used any more: IRSA's TAP service failed with 502 on 2026-11-15, so
    search_images() uses SIA. Kept because test_update_design.py checks it.
    """
    ra, dec = _check_position(ra_deg, dec_deg)
    size = size_degrees(fov_arcmin)
    extra = ""
    if bandpass is not None:
        if not _BANDPASS.match(str(bandpass)):
            raise ValueError("The bandpass must look like SPHEREx-D2 (D1 to D6).")
        extra = f"\n        AND p.energy_bandpassname = '{bandpass}'"
    return f"""
SELECT
    '{IRSA_BASE_URL}' || a.uri || '?center={ra},{dec}d&size={size}' AS uri,
    p.time_bounds_lower,
    p.energy_bandpassname
FROM spherex.artifact a
JOIN spherex.plane p ON a.planeid = p.planeid
WHERE 1 = CONTAINS(POINT('ICRS', {ra}, {dec}), p.poly){extra}
ORDER BY p.time_bounds_lower
"""


# ---------------------------------------------------------------
# After-data #2: search
# ---------------------------------------------------------------
def _sia_query(ra, dec):
    """The real SIA search (same call as inspect_real_files.py). Needs the internet.
    astroquery is imported here so this file loads without it."""
    from astropy.coordinates import SkyCoord
    from astroquery.ipac.irsa import Irsa
    coord = SkyCoord(ra * u.deg, dec * u.deg)
    return Irsa.query_sia(pos=(coord, 1 * u.arcsec),
                          collection=list(config.SPHEREX_SIA_COLLECTIONS))


def search_images(ra_deg, dec_deg, fov_arcmin, bandpass=None,
                  sia_function=None, sleep=time.sleep):
    """Which SPHEREx images cover this position? Oldest first. Needs the internet.

    Returns a list of dictionaries (one per image):
      url       cutout link = SIA access_url + ?center=RA,DECd&size=DEGREES
                (verified by download in Backend 26)
      t_min     observation time as an MJD (a number), from the SIA table
      obs_time  the same time as a naive UTC datetime
      bandpass  'SPHEREx-D1' ... 'SPHEREx-D6'
      detector  1 to 6 (from the bandpass name), or None
    bandpass: None = every detector, or e.g. 'SPHEREx-D3' for just one.
    Rows without a usable link or time are left out. An empty list means no image
    covers the position.

    Bad input raises ValueError. If IRSA does not answer after SEARCH_TRIES
    tries, raises TimeoutError (main.frames_for turns that into HTTP 504).
    sia_function / sleep: tests replace them. Normally leave them None.
    """
    ra, dec = _check_position(ra_deg, dec_deg)
    size = size_degrees(fov_arcmin)
    if bandpass is not None and not _BANDPASS.match(str(bandpass)):
        raise ValueError("The bandpass must look like SPHEREx-D2 (D1 to D6).")

    ask = sia_function or _sia_query
    table = None
    for attempt in range(SEARCH_TRIES):
        try:
            table = ask(ra, dec)
            break
        except Exception as err:
            if attempt == SEARCH_TRIES - 1:
                raise TimeoutError(
                    "IRSA's image search did not answer "
                    f"({type(err).__name__}). Please try again in a moment.") from err
            sleep(SEARCH_WAIT_S * (attempt + 1))

    images = []
    for row in (table if table is not None else []):
        try:
            t_min = float(row["t_min"])
        except (TypeError, ValueError):
            continue
        url = row["access_url"]
        if not math.isfinite(t_min) or url is None or str(url).strip() in ("", "--"):
            continue
        band = str(row["energy_bandpassname"])
        if bandpass is not None and band != bandpass:
            continue
        match = re.match(r"^SPHEREx-D([1-6])$", band)
        images.append({
            "url": f"{str(url).strip()}?center={ra},{dec}d&size={size}",
            "t_min": t_min,
            "obs_time": mjd_to_datetime(t_min),
            "bandpass": band,
            "detector": int(match.group(1)) if match else None,
        })
    images.sort(key=lambda item: item["t_min"])
    return images


# ---------------------------------------------------------------
# After-data #3: download
# ---------------------------------------------------------------
def _open_remote(url):
    """Download one cutout completely into memory and return the HDUList."""
    from astropy.utils.data import conf
    conf.remote_timeout = DOWNLOAD_TIMEOUT_S
    hdulist = fits.open(url, memmap=False, cache=False)
    try:
        for hdu in hdulist:
            hdu.data                 # read every extension before the file closes
    finally:
        hdulist.close()              # the data stays in memory (same pattern as try_real_query.py)
    return hdulist


def download_cutout(cutout_url, opener=None, sleep=time.sleep):
    """Download one cutout and return it as an astropy HDUList held in memory.

    Only links that start with IRSA_BASE_URL are accepted (so nobody can make
    the server fetch other sites). A few downloads fail at random (IRSA's tutorial
    saw 4 of 84), so transient errors are tried again up to DOWNLOAD_TRIES times.
    Raises TimeoutError if it keeps failing, ValueError for a link that is not
    an IRSA link. Other errors (for example a file that is not FITS) are passed on.
    opener / sleep: tests replace them. Normally leave them None.
    """
    if not isinstance(cutout_url, str) or not cutout_url.startswith(IRSA_BASE_URL):
        raise ValueError(f"Only links that start with {IRSA_BASE_URL} can be downloaded.")
    open_it = opener or _open_remote
    last_error = None
    for attempt in range(DOWNLOAD_TRIES):
        try:
            return open_it(cutout_url)
        except _TRANSIENT as err:
            last_error = err
            if attempt < DOWNLOAD_TRIES - 1:
                sleep(DOWNLOAD_WAIT_S * (attempt + 1))
    raise TimeoutError(
        f"A cutout could not be downloaded after {DOWNLOAD_TRIES} tries "
        f"({type(last_error).__name__}).") from last_error


# ---------------------------------------------------------------
# After-data #4 and #5: read a cutout, wavelengths
# ---------------------------------------------------------------
def _spectral_wcs(hdulist):
    """The second ("W") WCS that holds the wavelength lookup table.
    Recipe from IRSA's tutorial; it worked in inspect_real_files.py."""
    header = hdulist["IMAGE"].header
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spectral = WCS(header, fobj=hdulist, key="W")
    spectral.sip = None
    return spectral


def centre_wavelength(hdulist):
    """Wavelength (microns) at the middle of the cutout.

    A real cutout does not have ONE wavelength: it changes by 0.01 to 0.05 um
    across the picture (verified), so this is the centre value only.
    Raises ValueError if the wavelength cannot be worked out.
    """
    try:
        ny, nx = hdulist["IMAGE"].data.shape
        spectral = _spectral_wcs(hdulist)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wavelength, _bandwidth = spectral.pixel_to_world((nx - 1) / 2.0, (ny - 1) / 2.0)
        value = float(wavelength.to(u.um).value)
    except Exception as err:
        raise ValueError(f"Could not read the wavelength of this cutout ({type(err).__name__}).") from err
    if not (math.isfinite(value) and value > 0):
        raise ValueError("The wavelength of this cutout is not a usable number.")
    return value


def wavelength_map(hdulist):
    """Wavelength (microns) of EVERY pixel: a 2D array, same shape as IMAGE.

    map[y, x] belongs to image[y, x] (y counted from 0 in the file's own order).
    The WCS-WAVE table only has a few control points; the WCS interpolates.
    UNVERIFIED: the call with whole arrays. If it fails or gives the wrong
    shape, it falls back to one pixel at a time (slower but the same call
    as centre_wavelength, which is verified).
    """
    ny, nx = hdulist["IMAGE"].data.shape
    spectral = _spectral_wcs(hdulist)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            yy, xx = np.mgrid[0:ny, 0:nx]
            wavelength, _bandwidth = spectral.pixel_to_world(xx, yy)
            values = np.asarray(wavelength.to(u.um).value, dtype=float)
            if values.shape == (ny, nx):
                return values
        except Exception:
            pass
        values = np.empty((ny, nx), dtype=float)
        for y in range(ny):
            for x in range(nx):
                wavelength, _bandwidth = spectral.pixel_to_world(x, y)
                values[y, x] = float(wavelength.to(u.um).value)
    return values


def _observation_time(header, fallback):
    """Naive UTC datetime. Verified: DATE-OBS (IMAGE header) equals the SIA t_min.
    The DATE card is the PROCESSING date and is never used."""
    text = header.get("DATE-OBS")
    if text:
        try:
            return datetime.fromisoformat(str(text).strip())
        except ValueError:
            pass
    if fallback is not None:
        return fallback
    raise ValueError("This cutout has no usable DATE-OBS and no observation time was given.")


def read_cutout(hdulist, source_url, obs_time=None):
    """Turn one downloaded cutout into a frame dictionary (FRAME_FORMAT.md).

      image          IMAGE (MJy/sr), as normal float64
      wcs            WCS of the IMAGE header. NOT north-up: real cutouts are rotated
                     by about 160 degrees and have SIP distortion (verified).
      obs_time       header DATE-OBS (naive UTC); obs_time argument if that is missing
      wavelength_um  centre_wavelength()
      detector       int(DETECTOR card of the IMAGE header)
      flags          FLAGS as native int32 (the file has big-endian int32)
      variance       VARIANCE (MJy2/sr2), as normal float64
      source_file    source_url
    Not used for now: ZODI, EPSF. wavelength_map() is separate (no extra frame key).
    Raises ValueError if the file does not look like a SPHEREx cutout.
    """
    try:
        header = hdulist["IMAGE"].header
        image = np.array(hdulist["IMAGE"].data, dtype=float)
        flags = np.asarray(hdulist["FLAGS"].data).astype(np.int32)
        variance = np.array(hdulist["VARIANCE"].data, dtype=float)
    except KeyError as err:
        raise ValueError(f"This file is missing the extension {err}, so it is not a SPHEREx cutout.") from err
    if not (image.shape == flags.shape == variance.shape and image.ndim == 2):
        raise ValueError("IMAGE, FLAGS and VARIANCE do not have the same 2D shape.")
    if "DETECTOR" not in header:
        raise ValueError("This cutout has no DETECTOR card.")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # astropy warns about the SIP / alternate WCS cards
        wcs = WCS(header)

    return {
        "image": image,
        "wcs": wcs,
        "obs_time": _observation_time(header, obs_time),
        "wavelength_um": centre_wavelength(hdulist),
        "detector": int(header["DETECTOR"]),
        "flags": flags,
        "variance": variance,
        "source_file": source_url,
    }


def get_frames(ra_deg, dec_deg, fov_arcmin):
    """The real data source. Same signature as data_mock.get_frames.

    NOT written yet: it needs the frame limit (#8), robust and parallel
    downloads (#10) and re-aligning onto one north-up grid (#30).
    """
    if fov_arcmin <= 0:
        raise ValueError("Field of view must be greater than zero.")
    _not_written("get_frames", "8, 10 and 30")