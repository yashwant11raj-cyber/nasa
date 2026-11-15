# data_mock.py
# Makes 12 fake SPHEREx-like FITS images with one moving dot.
# Each file has 3 parts: the image, a FLAGS map and a VARIANCE map.
# Run it with:  python data_mock.py
# Running it only WRITES files into data/mock/. It never makes PNGs or pictures.
#
# NEW (Backend 9): get_frames() at the bottom READS those files back and
# returns them as frames (see FRAME_FORMAT.md). The web server uses it.

import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from processing import cutout_frame      # NEW: used by get_frames()
from targets import TARGETS, position_at_epoch

# ---------- Settings you can change ----------
OUT_DIR = Path(__file__).parent / "data" / "mock"   # where files are saved
N_FRAMES = 12                    # how many fake images
IMAGE_SIZE = 100                 # image is 100 x 100 pixels
PIXEL_SCALE_ARCSEC = 6.2         # ASSUMPTION: arcseconds per pixel (verify later)
START_DATE = datetime(2026, 1, 1)
DAYS_BETWEEN = 30                # days between frames
SPEED_BOOST = 10                 # dot moves 10x faster than the real object
WAVE_MIN_UM, WAVE_MAX_UM = 0.75, 5.0   # ASSUMPTION: mock wavelength range (microns)
DOT_AMPLITUDE = 200.0            # dot is the brightest thing in the image
DOT_SIGMA_PIX = 1.2              # dot size
SEED = 42                        # makes the noise the same every run

# Flag settings. These bit meanings are INVENTED for the mock.
# Real SPHEREx bit meanings must be loaded from its documentation later.
FLAG_BAD = 1                     # bit value 1: dead pixel
FLAG_COSMIC = 2                  # bit value 2: cosmic ray hit
FLAG_CONTAM = 4                  # bit value 4: contaminated (near a fixed star)
N_BAD_PIXELS = 15                # dead pixels (same places in every frame)
N_COSMIC_RAYS = 5                # random spikes (new places in every frame)
COSMIC_AMPLITUDE = 60.0          # how much a cosmic ray adds to its pixel
CONTAM_RADIUS_PIX = 4            # pixels this close to a fixed star get flagged

# Fixed stars as (x, y, brightness) in pixel coordinates. They never move.
STATIC_STARS = [
    (20, 25, 80), (75, 30, 60), (30, 75, 50),
    (80, 80, 70), (60, 15, 40), (15, 60, 55),
]


def dot_sky_position(days_since_start):
    """Return (ra_deg, dec_deg) of the moving dot, a number of days after START_DATE.

    Starts at WISE 0855's 2026.0 position and moves with its real
    proper motion multiplied by SPEED_BOOST.
    """
    t = TARGETS["wise0855"]
    ra0, dec0 = position_at_epoch("wise0855", 2026.0)
    years = days_since_start / 365.25
    # mas/yr -> degrees: divide by 3,600,000
    d_dec = t["pmdec_mas_yr"] * SPEED_BOOST * years / 3_600_000
    # pmra already includes cos(Dec), so divide it out to get a change in RA
    d_ra = (t["pmra_mas_yr"] * SPEED_BOOST * years / 3_600_000
            / math.cos(math.radians(dec0)))
    return ra0 + d_ra, dec0 + d_dec


def make_wcs(ra_center, dec_center):
    """Build the WCS: the rule that links pixel positions to RA/Dec."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]            # standard sky projection
    w.wcs.crval = [ra_center, dec_center]             # sky position of the reference pixel
    w.wcs.crpix = [(IMAGE_SIZE + 1) / 2, (IMAGE_SIZE + 1) / 2]  # reference pixel (image centre)
    scale_deg = PIXEL_SCALE_ARCSEC / 3600.0
    w.wcs.cdelt = [-scale_deg, scale_deg]             # RA grows to the left, as on a sky map
    w.wcs.cunit = ["deg", "deg"]
    return w


def add_blob(image, x, y, amplitude, sigma):
    """Add a round fuzzy spot (a 'Gaussian') to the image at pixel (x, y)."""
    yy, xx = np.mgrid[0:IMAGE_SIZE, 0:IMAGE_SIZE]
    image += amplitude * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma ** 2))


def random_pixels_off_dot_track(n, rng):
    """Pick n random pixel positions (x, y) that stay away from the dot's path.

    The dot travels along rows y = 49-50, so we only use rows 0-39 and 60-99.
    That way a defect can never hide the dot in our tests.
    """
    x = rng.integers(0, IMAGE_SIZE, n)
    y = rng.integers(0, 40, n)
    y = np.where(rng.random(n) < 0.5, y, y + 60)      # half of them move to rows 60-99
    return x, y


def make_flags_and_variance(image, bad_xy, rng):
    """Create the FLAGS and VARIANCE maps, and put defects into the image.

    Changes `image` in place (cosmic rays add a spike, dead pixels become 0).
    Returns (flags, variance).
    """
    # Variance first, from the clean signal: brighter pixel = noisier pixel.
    # This recipe is made up for the mock, it is not real physics.
    variance = 1.0 + 0.05 * np.clip(image, 0, None)

    flags = np.zeros((IMAGE_SIZE, IMAGE_SIZE), dtype=np.int32)

    # Contaminated: every pixel within CONTAM_RADIUS_PIX of a fixed star
    yy, xx = np.mgrid[0:IMAGE_SIZE, 0:IMAGE_SIZE]
    for (sx, sy, _amp) in STATIC_STARS:
        near = (xx - sx) ** 2 + (yy - sy) ** 2 <= CONTAM_RADIUS_PIX ** 2
        flags[near] |= FLAG_CONTAM        # |= adds the bit without removing others

    # Cosmic rays: random places, different in every frame
    cx, cy = random_pixels_off_dot_track(N_COSMIC_RAYS, rng)
    image[cy, cx] += COSMIC_AMPLITUDE
    flags[cy, cx] |= FLAG_COSMIC

    # Dead pixels: same places in every frame, they read zero
    bx, by = bad_xy
    image[by, bx] = 0.0
    flags[by, bx] |= FLAG_BAD

    return flags, variance


def generate_mock_frames():
    """Write N_FRAMES FITS files into OUT_DIR."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Centre the image on where the dot is halfway through, so it stays in view.
    mid_days = DAYS_BETWEEN * (N_FRAMES - 1) / 2
    ra_c, dec_c = dot_sky_position(mid_days)
    wcs = make_wcs(ra_c, dec_c)

    # Dead pixels are chosen once, so they are in the same place every frame
    bad_xy = random_pixels_off_dot_track(N_BAD_PIXELS, np.random.default_rng(SEED + 1000))

    for i in range(N_FRAMES):
        days = DAYS_BETWEEN * i
        obs_time = START_DATE + timedelta(days=days)
        detector = i % 6 + 1                                   # 1,2,...,6,1,2,...
        wavelength = WAVE_MIN_UM + i * (WAVE_MAX_UM - WAVE_MIN_UM) / (N_FRAMES - 1)

        # Background noise (different each frame, but repeatable)
        rng = np.random.default_rng(SEED + i)
        image = rng.normal(loc=10.0, scale=1.0, size=(IMAGE_SIZE, IMAGE_SIZE))

        # Fixed stars
        for (sx, sy, amp) in STATIC_STARS:
            add_blob(image, sx, sy, amp, 1.5)

        # Moving dot: sky position -> pixel position using the WCS
        ra, dec = dot_sky_position(days)
        dot_x, dot_y = wcs.wcs_world2pix(ra, dec, 0)           # 0 = pixels counted from 0
        add_blob(image, float(dot_x), float(dot_y), DOT_AMPLITUDE, DOT_SIGMA_PIX)

        # Flags and variance (this also adds cosmic rays and dead pixels)
        flags, variance = make_flags_and_variance(image, bad_xy, rng)

        # Build the FITS file: image + header
        hdu = fits.PrimaryHDU(data=image.astype(np.float32), header=wcs.to_header())
        hdu.header["DATE-OBS"] = (obs_time.isoformat(), "Observation date/time (UTC)")
        hdu.header["DETECTOR"] = (detector, "Detector number 1-6 (mock)")
        hdu.header["WAVE_UM"] = (round(wavelength, 4), "Band centre, microns (mock)")
        hdu.header["MOCK"] = (True, "Fake data for testing")
        hdu.header["DOTX"] = (float(dot_x), "TRUE dot x pixel (for testing)")
        hdu.header["DOTY"] = (float(dot_y), "TRUE dot y pixel (for testing)")

        # Two extra parts of the file, named so we can find them later
        flags_hdu = fits.ImageHDU(data=flags, name="FLAGS")
        flags_hdu.header["FLAG_1"] = "bad pixel (mock)"
        flags_hdu.header["FLAG_2"] = "cosmic ray (mock)"
        flags_hdu.header["FLAG_4"] = "contaminated (mock)"
        var_hdu = fits.ImageHDU(data=variance.astype(np.float32), name="VARIANCE")

        path = OUT_DIR / f"mock_{i:02d}.fits"
        fits.HDUList([hdu, flags_hdu, var_hdu]).writeto(path, overwrite=True)
        print("wrote", path.name)


# ---------- NEW (Backend 9): reading the mock files back ----------

def load_mock_frame(path):
    """Read one mock FITS file and return a frame dictionary (FRAME_FORMAT.md)."""
    with fits.open(path) as hdul:
        hdr = hdul[0].header
        return {
            "image": np.array(hdul[0].data, dtype=float),
            "wcs": WCS(hdr),
            "obs_time": datetime.fromisoformat(hdr["DATE-OBS"]),
            "wavelength_um": float(hdr["WAVE_UM"]),
            "detector": int(hdr["DETECTOR"]),
            "flags": np.asarray(hdul["FLAGS"].data).astype(np.int32),   # FITS gives big-endian; make it native int32
            "variance": np.array(hdul["VARIANCE"].data, dtype=float),
            "source_file": path.name,
        }


def get_frames(ra_deg, dec_deg, fov_arcmin):
    """The mock data source (signature from FRAME_FORMAT.md).

    Returns a list of frames sorted by obs_time. Each frame is already a
    small square cutout, fov_arcmin wide, centred on (ra_deg, dec_deg).
    Mock images that do not cover that position are left out, so the
    list can be empty. The real source (data_irsa.py) will behave the same way.
    """
    if fov_arcmin <= 0:
        raise ValueError("Field of view must be greater than zero.")

    files = sorted(OUT_DIR.glob("mock_*.fits"))
    if not files:
        raise FileNotFoundError("No mock files found. Run: python data_mock.py")

    frames = []
    for path in files:
        frame = load_mock_frame(path)
        try:
            frames.append(cutout_frame(frame, ra_deg, dec_deg, fov_arcmin))
        except ValueError:
            continue          # this image does not cover the requested position
    frames.sort(key=lambda f: f["obs_time"])
    return frames


if __name__ == "__main__":
    generate_mock_frames()