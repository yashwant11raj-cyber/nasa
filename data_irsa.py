# data_irsa.py
# Backend 25: SKELETON of the real data source (IRSA / SPHEREx).
# Nothing here downloads anything yet. Every function says what it WILL do
# and raises NotImplementedError. Later only the insides change:
# get_frames() keeps the signature of data_mock.get_frames and returns
# frames in the FRAME_FORMAT.md format.
#
# Facts marked (tutorial) come from IRSA's SPHEREx tutorial notebooks
# ("Introduction to SPHEREx Spectral Images" and "Download a collection of
# SPHEREx Spectral Image cutouts ..."). Facts marked (UNVERIFIED) have not
# been checked yet: see docs/DATA_NOTES.md.
#
# Real code is written in the "after the data" part of TODO_LIST.md
# (#2 search, #3 download, #4 read). Nothing here is connected to main.py.
import math
import re

# Start of every cutout link (tutorial: the TAP query puts this in front of a.uri)
IRSA_BASE_URL = "https://irsa.ipac.caltech.edu/"

# Bandpass names look like 'SPHEREx-D2' in the tutorial. D1-D6 is my inference
# from the six detectors (UNVERIFIED). Only this exact pattern is allowed
# into the query text.
_BANDPASS = re.compile(r"^SPHEREx-D[1-6]$")


# The keys every frame must have (see FRAME_FORMAT.md). The contract test
# (after-data #6) will compare real frames against this list.
FRAME_KEYS = ("image", "wcs", "obs_time", "wavelength_um", "detector",
              "flags", "variance", "source_file")


def _not_written(name, step):
    raise NotImplementedError(
        f"data_irsa.{name}() is not written yet (TODO after-data #{step}). "
        f"Set USE_MOCK = True in config.py to use the mock data.")

def size_degrees(fov_arcmin):
    """Cutout size for the IRSA link. The tutorial gives size in degrees
    (its example uses 0.1 for 6 arcmin); not yet checked against the cutout
    service page (UNVERIFIED)."""
    fov = float(fov_arcmin)
    if not math.isfinite(fov) or fov <= 0:
        raise ValueError("Field of view must be a number greater than zero.")
    return round(fov / 60.0, 6)


def build_search_query(ra_deg, dec_deg, fov_arcmin, bandpass=None):
    """The TAP query text for 'which images cover this position' (no network).

    Same query as IRSA's cutout tutorial: one row per spectral image, with the
    cutout link, the observation time and the bandpass, oldest first.
    Live query, so no list of files is kept anywhere. Only numbers (checked)
    and a bandpass that matches 'SPHEREx-D1'..'SPHEREx-D6' go into the text.
    bandpass: None = all detectors.
    """
    ra, dec = float(ra_deg), float(dec_deg)
    if not (math.isfinite(ra) and 0 <= ra <= 360):
        raise ValueError("RA must be between 0 and 360 degrees.")
    if not (math.isfinite(dec) and -90 <= dec <= 90):
        raise ValueError("Dec must be between -90 and +90 degrees.")
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

def search_images(ra_deg, dec_deg, fov_arcmin):
    """Asks IRSA's SIA service (Irsa.query_sia, collections from config.SPHEREX_SIA_COLLECTIONS) which images cover this position. Sort by t_min (an MJD). Cutout link = access_url + ?center=RA,DECd&size=DEGREES (verified 2026-11-15)."""
    _not_written("search_images", 2)


def download_cutout(cutout_url):
    """WILL download one cutout and return it as an astropy HDUList held in memory.

    Tutorial: reading can exceed astropy's default timeout (they set
    astropy.utils.data.conf.remote_timeout = 120), and a few downloads fail
    with transient errors (TimeoutError, urllib.error.HTTPError,
    http.client.IncompleteRead, http.client.RemoteDisconnected), so this needs
    retries (TODO after-data #10). Raises TimeoutError if it keeps failing.
    """
    _not_written("download_cutout", 3)


def read_cutout(hdulist, source_url, obs_time):
    """WILL turn one downloaded cutout into a frame dictionary (FRAME_FORMAT.md).

    Planned mapping:
      image          <- extension IMAGE (surface brightness, MJy/sr)      (tutorial)
      wcs            <- WCS(IMAGE header), the sky WCS of the cutout       (tutorial)
      obs_time <- header DATE-OBS or MJD-OBS (verified 2026-11-15). NOT the DATE card: that is the processing date.
      wavelength_um  <- spectral WCS (key "W") at the cutout centre.       (tutorial)
                        Wavelength varies across a detector, so this is the
                        centre-pixel value.
      detector       <- IMAGE header card DETECTOR                         (tutorial)
      flags          <- extension FLAGS; bit meanings are in its header
                        (MSKNnnnn name, MSKDnnnn description)              (tutorial)
      variance       <- extension VARIANCE (MJy^2/sr^2)                    (tutorial)
      source_file    <- source_url
    Not used for now: ZODI, EPSF, WCS-WAVE.
    """
    _not_written("read_cutout", 4)


def get_frames(ra_deg, dec_deg, fov_arcmin):
    """The real data source. Same signature as data_mock.get_frames.

    WILL: search_images -> download_cutout -> read_cutout for each hit, drop
    downloads that failed, sort by obs_time and return the list (empty if no
    image covers the position). Capping the count (config.MAX_FRAMES) comes
    in after-data #8.
    """
    if fov_arcmin <= 0:
        raise ValueError("Field of view must be greater than zero.")
    _not_written("get_frames", "2-4")