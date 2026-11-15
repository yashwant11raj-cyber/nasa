# test_data_irsa.py
# Tests data_irsa.py (after-data #2 to #5). Run it with:  python test_data_irsa.py
# No server, no data files and NO internet are needed: the IRSA search and the
# download are replaced by small fakes. (The real thing is tried by
# try_real_frames.py.)

import inspect
from datetime import date, datetime
from pathlib import Path

import numpy as np
from astropy.io import fits

import data_irsa
import data_mock

problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


def raises(error_type, func, *args, **kwargs):
    """True if the call raises error_type. Prints the message."""
    try:
        func(*args, **kwargs)
    except error_type as err:
        print(f"        message: {err}")
        return True
    print("        NO ERROR RAISED")
    return False


def not_written(func, *args):
    try:
        func(*args)
    except NotImplementedError as err:
        print(f"        message: {err}")
        return "not written yet" in str(err)
    print("        NO ERROR RAISED")
    return False


print("--- Part 1: get_frames is still a skeleton ---")
check("get_frames has the same parameter names as data_mock.get_frames",
      list(inspect.signature(data_irsa.get_frames).parameters)
      == list(inspect.signature(data_mock.get_frames).parameters))
check("fov 0 gives ValueError", raises(ValueError, data_irsa.get_frames, 10, 10, 0))
check("get_frames raises NotImplementedError", not_written(data_irsa.get_frames, 10, 10, 6.0))
check("every public function has a docstring",
      all(inspect.getdoc(f) for f in (data_irsa.get_frames, data_irsa.search_images,
                                      data_irsa.download_cutout, data_irsa.read_cutout,
                                      data_irsa.centre_wavelength, data_irsa.wavelength_map)))

print("\n--- Part 2: FRAME_KEYS matches FRAME_FORMAT.md ---")
text = (Path(__file__).parent / "FRAME_FORMAT.md").read_text(encoding="utf-8")
check("8 keys", len(data_irsa.FRAME_KEYS) == 8)
check("every key is listed in FRAME_FORMAT.md", all(f"- {k}:" in text for k in data_irsa.FRAME_KEYS))

print("\n--- Part 3: search_images (fake IRSA) ---")
B = "https://irsa.ipac.caltech.edu/ibe/data/"
ROWS = [
    {"access_url": B + "b.fits", "t_min": 60801.514177, "energy_bandpassname": "SPHEREx-D4"},
    {"access_url": B + "a.fits", "t_min": 60800.700028, "energy_bandpassname": "SPHEREx-D3"},
    {"access_url": B + "c.fits", "t_min": 60801.106596, "energy_bandpassname": "SPHEREx-D5"},
    {"access_url": B + "nan.fits", "t_min": float("nan"), "energy_bandpassname": "SPHEREx-D1"},
    {"access_url": None, "t_min": 60802.0, "energy_bandpassname": "SPHEREx-D2"},
]
fake_search = lambda ra, dec: ROWS
found = data_irsa.search_images(133.8, -7.2, 6.0, sia_function=fake_search)
check("rows without a time or link are left out (3 remain)", len(found) == 3)
check("oldest first", [f["url"].split("?")[0][-6:] for f in found] == ["a.fits", "c.fits", "b.fits"])
check("link = access_url + ?center=RA,DECd&size=DEGREES",
      found[0]["url"] == B + "a.fits?center=133.8,-7.2d&size=0.1")
check("each entry has url, t_min, obs_time, bandpass, detector",
      all(set(f) == {"url", "t_min", "obs_time", "bandpass", "detector"} for f in found))
check("detector comes from the bandpass name", [f["detector"] for f in found] == [3, 5, 4])
check("MJD 60800.700028 is 2025-05-05 16:48 UTC",
      found[0]["obs_time"].date() == date(2025, 5, 5) and found[0]["obs_time"].hour == 16
      and found[0]["obs_time"].minute == 48)
check("a bandpass filter keeps only that detector",
      [f["bandpass"] for f in data_irsa.search_images(1, 2, 6, "SPHEREx-D4", sia_function=fake_search)] == ["SPHEREx-D4"])
check("no result gives an empty list", data_irsa.search_images(1, 2, 6, sia_function=lambda r, d: []) == [])
check("None from the service gives an empty list", data_irsa.search_images(1, 2, 6, sia_function=lambda r, d: None) == [])

calls, naps = [], []


def flaky(ra, dec):
    calls.append(1)
    if len(calls) < 3:
        raise ConnectionError("502 Proxy Error")
    return ROWS


got = data_irsa.search_images(133.8, -7.2, 6.0, sia_function=flaky, sleep=naps.append)
check("a search that fails twice and then works is retried", len(calls) == 3 and len(got) == 3 and len(naps) == 2)

calls.clear()
naps.clear()


def dead(ra, dec):
    calls.append(1)
    raise ConnectionError("down")


check("a search that never works gives TimeoutError",
      raises(TimeoutError, data_irsa.search_images, 1, 2, 6, sia_function=dead, sleep=naps.append))
check("it tried SEARCH_TRIES times", len(calls) == data_irsa.SEARCH_TRIES and len(naps) == data_irsa.SEARCH_TRIES - 1)

calls.clear()
check("bad RA is refused before asking IRSA",
      raises(ValueError, data_irsa.search_images, 400, 0, 6, sia_function=lambda r, d: calls.append(1)) and not calls)
check("bad Dec is refused", raises(ValueError, data_irsa.search_images, 10, 95, 6, sia_function=fake_search))
check("FOV 0 is refused", raises(ValueError, data_irsa.search_images, 10, 5, 0, sia_function=fake_search))
check("bad bandpass is refused", raises(ValueError, data_irsa.search_images, 10, 5, 6, "x' OR 1=1", sia_function=fake_search))

print("\n--- Part 4: download_cutout (fake opener) ---")
sentinel = object()
check("a good link returns what the opener gives", data_irsa.download_cutout(B + "a.fits", opener=lambda url: sentinel) is sentinel)
opened = []
check("a link to another site is refused and never opened",
      raises(ValueError, data_irsa.download_cutout, "https://example.com/x.fits", opener=opened.append) and not opened)
check("a non-text link is refused", raises(ValueError, data_irsa.download_cutout, None))

import urllib.error
attempts, naps = [], []


def flaky_open(url):
    attempts.append(1)
    if len(attempts) < 3:
        raise urllib.error.URLError("transient")
    return sentinel


check("two transient errors and then success works",
      data_irsa.download_cutout(B + "a.fits", opener=flaky_open, sleep=naps.append) is sentinel and len(attempts) == 3 and len(naps) == 2)

attempts.clear()
naps.clear()


def always_fails(url):
    attempts.append(1)
    raise TimeoutError("slow")


check("it keeps failing -> TimeoutError", raises(TimeoutError, data_irsa.download_cutout, B + "a.fits", always_fails, naps.append))
check("it tried DOWNLOAD_TRIES times", len(attempts) == data_irsa.DOWNLOAD_TRIES)

attempts.clear()


def not_fits(url):
    attempts.append(1)
    raise OSError("not a FITS file")


check("an error that is not transient is passed on at once (no retry)",
      raises(OSError, data_irsa.download_cutout, B + "a.fits", not_fits) and len(attempts) == 1)

print("\n--- Part 5: read_cutout on a fake cutout ---")


def fake_cutout(ny=59, nx=58, detector=3, date_obs="2025-05-05T16:48:02.459"):
    """A small stand-in for a real cutout: rotated WCS (numbers from the real D1 file),
    big-endian arrays like the real files."""
    rng = np.random.default_rng(0)
    h = fits.Header()
    h["DETECTOR"] = detector
    if date_obs:
        h["DATE-OBS"] = date_obs
    h["CTYPE1"], h["CTYPE2"] = "RA---TAN", "DEC--TAN"
    h["CUNIT1"], h["CUNIT2"] = "deg", "deg"
    h["CRVAL1"], h["CRVAL2"] = 133.4, -9.0
    h["CRPIX1"], h["CRPIX2"] = 29.0, 30.0
    h["CDELT1"], h["CDELT2"] = 1.0, 1.0
    h["PC1_1"], h["PC1_2"] = 0.0016235783793, -0.0006013768757
    h["PC2_1"], h["PC2_2"] = -0.00054089308468, -0.00159935379439
    image = fits.ImageHDU(rng.normal(0.2, 0.1, (ny, nx)).astype(">f4"), header=h, name="IMAGE")
    flags = fits.ImageHDU(np.full((ny, nx), 1 << 21, dtype=">i4"), name="FLAGS")
    variance = fits.ImageHDU(np.full((ny, nx), 0.0003, dtype=">f4"), name="VARIANCE")
    return fits.HDUList([fits.PrimaryHDU(), image, flags, variance])


real_centre = data_irsa.centre_wavelength
data_irsa.centre_wavelength = lambda hdulist: 2.5        # the real one needs a WCS-WAVE table
try:
    hdul = fake_cutout()
    check("premise: the fake flags are big-endian, like the real files", hdul["FLAGS"].data.dtype.byteorder == ">")
    frame = data_irsa.read_cutout(hdul, "http://x/a.fits")
    check("the frame has exactly the FRAME_KEYS", set(frame) == set(data_irsa.FRAME_KEYS))
    check("image is normal float64, shape (59, 58)", frame["image"].dtype == np.float64 and frame["image"].shape == (59, 58))
    check("flags are native int32 (not big-endian)", frame["flags"].dtype == np.int32 and frame["flags"].dtype.isnative)
    check("flag values are kept", int(frame["flags"][0, 0]) == 1 << 21)
    check("variance is float64", frame["variance"].dtype == np.float64)
    check("detector is an int", frame["detector"] == 3 and type(frame["detector"]) is int)
    check("obs_time comes from DATE-OBS", frame["obs_time"] == datetime(2025, 5, 5, 16, 48, 2, 459000))
    check("obs_time is a naive datetime (no timezone)", frame["obs_time"].tzinfo is None)
    check("wavelength comes from centre_wavelength", frame["wavelength_um"] == 2.5)
    check("source_file is the link", frame["source_file"] == "http://x/a.fits")
    ra, dec = frame["wcs"].pixel_to_world_values(28, 29)       # the reference pixel (1-based 29, 30)
    check("the WCS is the one from the header", abs(float(ra) - 133.4) < 1e-6 and abs(float(dec) + 9.0) < 1e-6)
    check("the downloaded file is not changed", hdul["FLAGS"].data.dtype.byteorder == ">")

    no_date = fake_cutout(date_obs=None)
    check("no DATE-OBS: the obs_time argument is used",
          data_irsa.read_cutout(no_date, "u", obs_time=datetime(2026, 1, 1))["obs_time"] == datetime(2026, 1, 1))
    check("no DATE-OBS and no argument: ValueError", raises(ValueError, data_irsa.read_cutout, no_date, "u"))
    check("a missing extension: ValueError", raises(ValueError, data_irsa.read_cutout, fits.HDUList([fits.PrimaryHDU(), hdul["IMAGE"]]), "u"))
    bad = fake_cutout()
    bad["FLAGS"].data = np.zeros((5, 5), dtype=">i4")
    check("different shapes: ValueError", raises(ValueError, data_irsa.read_cutout, bad, "u"))
    bad2 = fake_cutout()
    del bad2["IMAGE"].header["DETECTOR"]
    check("no DETECTOR card: ValueError", raises(ValueError, data_irsa.read_cutout, bad2, "u"))

    def broken_centre(hdulist):
        raise ValueError("no wavelength")

    data_irsa.centre_wavelength = broken_centre
    check("a wavelength that cannot be read: ValueError is passed on", raises(ValueError, data_irsa.read_cutout, fake_cutout(), "u"))
finally:
    data_irsa.centre_wavelength = real_centre

print("\n--- Part 6: wavelengths ---")
check("centre_wavelength on a file without WCS-WAVE gives a friendly ValueError",
      raises(ValueError, data_irsa.centre_wavelength, fake_cutout()))
print("   (the real centre_wavelength and wavelength_map are tried on real files by try_real_frames.py)")

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")