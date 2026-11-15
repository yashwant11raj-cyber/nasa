# test_spectra.py
# Tests spectra.py (Backend 31 and 32). Run it with:  python test_spectra.py
# Parts 1-4 need only numpy. Part 5 needs astropy (it is in requirements.txt).
# Part 6 needs the mock files (python data_mock.py).

import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import spectra

MOCK_FILE = Path(__file__).parent / "data" / "mock" / "mock_00.fits"
problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


def fails(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except ValueError as err:
        print(f"        message: {err}")
        return True
    print("        NO ERROR RAISED")
    return False


# Mock flag bits: 1 = bad pixel, 2 = cosmic ray (both "bad"), 4 = contaminated (not "bad")
def fake(wave, value, detector=1, day=0, size=30, variance=1.0):
    """A frame that is `value` everywhere."""
    return {"image": np.full((size, size), float(value)),
            "variance": np.full((size, size), float(variance)),
            "flags": np.zeros((size, size), dtype=np.int32),
            "wavelength_um": wave, "detector": detector,
            "obs_time": datetime(2026, 1, 1) + timedelta(days=day), "source_file": f"f{day}"}


# Wavelengths are NOT in order, to prove the sorting works
frames = [fake(3.0, 30, day=0), fake(1.0, 10, day=1), fake(2.0, 20, day=2), fake(4.0, 40, day=3)]

print("--- Part 1: spectrum_at_pixel ---")
sp = spectra.spectrum_at_pixel(frames, 10, 10)
check("one reading per frame", len(sp) == 4)
check("sorted by wavelength", [p["wavelength_um"] for p in sp] == [1.0, 2.0, 3.0, 4.0])
check("flux follows the wavelength order (10, 20, 30, 40)", [p["flux"] for p in sp] == [10.0, 20.0, 30.0, 40.0])
check("index points back to the frame in the input list", [p["index"] for p in sp] == [1, 2, 0, 3])
check("detector and obs_time are copied", sp[0]["detector"] == 1 and sp[0]["obs_time"] == frames[1]["obs_time"])
check("every reading is usable with 1 pixel", all(p["usable"] and p["n_pixels"] == 1 for p in sp))
check("error from variance 1 and one pixel is 1", all(abs(p["error"] - 1.0) < 1e-9 for p in sp))
check("x and y are reported", sp[0]["x"] == 10.0 and sp[0]["y"] == 10.0)
check("original frames are not changed", frames[0]["image"][10, 10] == 30.0 and "flux" not in frames[0])
check("empty list gives an empty list", spectra.spectrum_at_pixel([], 1, 1) == [])

print("\n--- Part 2: the small square of pixels ---")
# One frame with a bright pixel at (x=10, y=12) in a flat sky of 5
img = np.full((30, 30), 5.0)
img[12, 10] = 50.0                                         # image[y, x]
one = {"image": img, "variance": np.full((30, 30), 4.0), "flags": np.zeros((30, 30), dtype=np.int32),
       "wavelength_um": 2.0, "detector": 1, "obs_time": None}
check("half_size 0 reads exactly one pixel (x=10, y=12 is image[12, 10])",
      spectra.spectrum_at_pixel([one], 10, 12)[0]["flux"] == 50.0)
nine = spectra.spectrum_at_pixel([one], 10, 12, half_size=1)[0]
check("half_size 1 averages 3x3 pixels: (50 + 8*5) / 9", nine["n_pixels"] == 9 and abs(nine["flux"] - 90 / 9) < 1e-9)
check("error of a mean of 9 pixels with variance 4: sqrt(36)/9 = 2/3", abs(nine["error"] - 2 / 3) < 1e-9)
check("x and y are not swapped (x=12, y=10 is a different pixel)",
      spectra.spectrum_at_pixel([one], 12, 10)[0]["flux"] == 5.0)
corner = spectra.spectrum_at_pixel([one], 0, 0, half_size=1)[0]
check("a square at the corner is cut off by the edge (4 pixels)", corner["n_pixels"] == 4 and corner["usable"])
check("fractional positions are rounded (10.4, 12.4 -> pixel 10, 12)",
      spectra.spectrum_at_pixel([one], 10.4, 12.4)[0]["flux"] == 50.0)

print("\n--- Part 3: bad pixels, NaN, outside, no variance ---")
flagged = {"image": img.copy(), "flags": np.zeros((30, 30), dtype=np.int32), "variance": None,
           "wavelength_um": 2.0, "detector": 1, "obs_time": None}
flagged["flags"][12, 10] = 1                               # the bright pixel is a dead pixel (bad)
r = spectra.spectrum_at_pixel([flagged], 10, 12, half_size=1)[0]
check("a pixel flagged bad is left out (8 pixels, all 5.0)", r["n_pixels"] == 8 and r["flux"] == 5.0)
check("no variance map: error is None", r["error"] is None)
flagged["flags"][12, 10] = 4                               # contaminated is NOT bad
r = spectra.spectrum_at_pixel([flagged], 10, 12, half_size=1)[0]
check("a contaminated pixel is still used (9 pixels)", r["n_pixels"] == 9)
only_bad = {"image": np.full((30, 30), 5.0), "flags": np.ones((30, 30), dtype=np.int32), "variance": None,
            "wavelength_um": 2.0, "detector": 1, "obs_time": None}
r = spectra.spectrum_at_pixel([only_bad], 5, 5)[0]
check("only bad pixels: not usable, flux None, with a reason",
      not r["usable"] and r["flux"] is None and "flagged bad" in r["reason"])
nan_frame = fake(2.0, 7)
nan_frame["image"][5, 5] = np.nan
check("a NaN pixel is not usable", not spectra.spectrum_at_pixel([nan_frame], 5, 5)[0]["usable"])
r = spectra.spectrum_at_pixel([nan_frame], 5, 5, half_size=1)[0]
check("a NaN pixel inside the square is skipped (8 pixels, flux 7)", r["n_pixels"] == 8 and r["flux"] == 7.0)
r = spectra.spectrum_at_pixel([fake(2.0, 7)], 100, 5)[0]
check("a position outside the frame: not usable, reason says so", not r["usable"] and "outside" in r["reason"])
r = spectra.spectrum_at_pixel([fake(2.0, 7)], -1, 5)[0]
check("negative pixel number is outside too", not r["usable"])
nv = fake(2.0, 7)
nv["variance"][5, 5] = np.nan
check("a NaN variance gives error None but still a flux",
      spectra.spectrum_at_pixel([nv], 5, 5)[0]["error"] is None and spectra.spectrum_at_pixel([nv], 5, 5)[0]["usable"])
nofl = fake(2.0, 7)
nofl["flags"] = None
check("a frame without flags still works", spectra.spectrum_at_pixel([nofl], 5, 5)[0]["flux"] == 7.0)
nowave = fake(None, 7)
mixed = spectra.spectrum_at_pixel([nowave, fake(1.0, 1)], 5, 5)
check("a frame without a wavelength goes last", mixed[0]["wavelength_um"] == 1.0 and mixed[1]["wavelength_um"] is None)
check("nan wavelength counts as no wavelength", spectra.spectrum_at_pixel([fake(float("nan"), 1)], 5, 5)[0]["wavelength_um"] is None)

print("\n--- Part 4: spectrum_along_path and bad input ---")
# A "mover": in frame i it sits at pixel (5 + 3*i, 10) and is bright there
mover_frames, path = [], []
for i in range(5):
    f = fake(1.0 + i, 10, day=i)
    f["image"][10, 5 + 3 * i] = 100.0
    mover_frames.append(f)
    path.append({"x": 5.0 + 3 * i, "y": 10.0})
along = spectra.spectrum_along_path(mover_frames, path)
check("following the mover gives its brightness in every frame", [p["flux"] for p in along] == [100.0] * 5)
fixed = spectra.spectrum_at_pixel(mover_frames, 5, 10)
check("a fixed pixel only catches the mover once", [p["flux"] for p in fixed].count(100.0) == 1)
unknown = spectra.spectrum_along_path(mover_frames[:2], [{"x": None, "y": None}, None])
check("unknown positions: not usable, reason says so",
      all(not p["usable"] and "not known" in p["reason"] for p in unknown))
check("different list lengths are refused", fails(spectra.spectrum_along_path, mover_frames, path[:2]))
for bad in (-1, 11, 1.5, "1", True, None):
    check(f"half_size={bad!r} is refused", fails(spectra.spectrum_along_path, mover_frames[:1], path[:1], bad))
check("text x is refused", fails(spectra.spectrum_at_pixel, frames, "a", 1))
check("NaN y is refused", fails(spectra.spectrum_at_pixel, frames, 1, float("nan")))

print("\n--- Part 5: sky positions and comparing two spectra (needs astropy) ---")
try:
    from astropy.wcs import WCS
except ImportError:
    print("SKIPPED  astropy is not installed here")
else:
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [150.0, 2.0]
    w.wcs.crpix = [25.5, 25.5]                    # 1-based, so pixel 24.5 counting from 0
    w.wcs.cdelt = [-6.2 / 3600, 6.2 / 3600]
    w.wcs.cunit = ["deg", "deg"]

    # A fixed star at pixel (30, 20) in every frame, brightness 100 + 10 per micron;
    # a mover that is at pixel (10 + 3*i, 40) in frame i, brightness 300 (flat).
    sky_frames, mover_path = [], []
    for i in range(6):
        wave = 1.0 + i
        img = np.full((50, 50), 5.0)
        img[20, 30] = 100.0 + 10.0 * wave
        img[40, 10 + 3 * i] = 300.0
        sky_frames.append({"image": img, "wcs": w, "wavelength_um": wave, "detector": 1,
                           "obs_time": datetime(2026, 1, 1 + i), "flags": None, "variance": None})
        mover_path.append({"x": 10.0 + 3 * i, "y": 40.0})
    star_ra, star_dec = w.wcs_pix2world(30, 20, 0)
    star_ra, star_dec = float(star_ra), float(star_dec)

    sp = spectra.spectrum_at_sky(sky_frames, star_ra, star_dec)
    print("   star fluxes:", [round(p["flux"], 1) for p in sp])
    check("spectrum_at_sky finds the star in every frame", all(p["usable"] for p in sp))
    check("the star's spectrum is 110, 120, ... 160", all(abs(p["flux"] - (100 + 10 * p["wavelength_um"])) < 1e-6 for p in sp))
    check("the pixel it read is (30, 20)", abs(sp[0]["x"] - 30) < 1e-6 and abs(sp[0]["y"] - 20) < 1e-6)
    far = spectra.spectrum_at_sky(sky_frames, star_ra + 1.0, star_dec)
    check("a sky position outside the frames: nothing usable", not any(p["usable"] for p in far))
    check("RA above 360 is refused", fails(spectra.spectrum_at_sky, sky_frames, 400, 0))
    check("Dec above 90 is refused", fails(spectra.spectrum_at_sky, sky_frames, 10, 95))
    check("text RA is refused", fails(spectra.spectrum_at_sky, sky_frames, "x", 0))
    nowcs = [dict(sky_frames[0])]
    nowcs[0].pop("wcs")
    check("a frame without a WCS: not usable, no crash",
          not spectra.spectrum_at_sky(nowcs, star_ra, star_dec)[0]["usable"])

    cmp_ = spectra.compare_spectra(sky_frames, mover_path, star_ra, star_dec)
    check("compare_spectra returns mover, star, normalized, scales",
          set(cmp_) == {"mover", "star", "normalized", "scales"} and cmp_["normalized"] is False)
    check("the mover is 300 in every frame", [p["flux"] for p in cmp_["mover"]] == [300.0] * 6)
    check("the star rises from 110 to 160", [round(p["flux"]) for p in cmp_["star"]] == [110, 120, 130, 140, 150, 160])
    check("both spectra use the same wavelengths", [p["wavelength_um"] for p in cmp_["mover"]] == [p["wavelength_um"] for p in cmp_["star"]])

    norm = spectra.compare_spectra(sky_frames, mover_path, star_ra, star_dec, normalize=True)
    check("normalised: the mover is 1.0 everywhere", all(abs(p["flux"] - 1.0) < 1e-9 for p in norm["mover"]))
    check("normalised: the star's median is 1.0", abs(float(np.median([p["flux"] for p in norm["star"]])) - 1.0) < 1e-9)
    check("the scales are reported (300 and the star's median 135)",
          abs(norm["scales"]["mover"] - 300.0) < 1e-9 and abs(norm["scales"]["star"] - 135.0) < 1e-9)
    check("the star's shape is kept (last / first = 160 / 110)",
          abs(norm["star"][-1]["flux"] / norm["star"][0]["flux"] - 160 / 110) < 1e-9)
    check("the input frames are not changed", sky_frames[0]["image"][20, 30] == 110.0)
    dark = [dict(f, image=np.zeros((50, 50))) for f in sky_frames]
    check("normalising an all-zero spectrum is refused",
          fails(spectra.compare_spectra, dark, mover_path, star_ra, star_dec, 0, True))

print("\n--- Part 6: on the mock data ---")
if not MOCK_FILE.exists():
    print("SKIPPED  no mock files. Run:  python data_mock.py")
else:
    from astropy.io import fits
    from astropy.wcs import WCS
    import data_mock
    import processing

    header = fits.getheader(MOCK_FILE)
    mock = data_mock.get_frames(header["CRVAL1"], header["CRVAL2"], 6.0)
    check("12 mock frames", len(mock) == 12)
    # The fixed mock star at pixel (75, 30) of the full image (brightness 60 on a background of 10)
    star_ra, star_dec = WCS(header).wcs_pix2world(75, 30, 0)
    star = spectra.spectrum_at_sky(mock, float(star_ra), float(star_dec), half_size=1)
    fluxes = [p["flux"] for p in star]
    print("   fixed star fluxes:", [round(f, 1) for f in fluxes])
    check("the fixed star is read in all 12 frames", all(p["usable"] for p in star))
    check("the mock star is bright (more than 40) in every frame", min(fluxes) > 40)
    check("the mock star is flat: the mock has the same brightness at every wavelength",
          (max(fluxes) - min(fluxes)) / np.mean(fluxes) < 0.15)
    check("wavelengths run from 0.75 to 5.0 um",
          abs(star[0]["wavelength_um"] - 0.75) < 0.01 and abs(star[-1]["wavelength_um"] - 5.0) < 0.01)

    trail = processing.find_moving_dot(mock)
    result = spectra.compare_spectra(mock, trail, float(star_ra), float(star_dec), half_size=1)
    mover_flux = [p["flux"] for p in result["mover"]]
    print("   mover fluxes:", [round(f, 1) for f in mover_flux])
    check("the mover is read in all 12 frames", all(p["usable"] for p in result["mover"]))
    check("the mover (dot, amplitude 200) is brighter than the star on average",
          np.mean(mover_flux) > np.mean(fluxes))
    # The mock dot moves only about 1 pixel per frame (10 x WISE 0855's real speed), so a fixed
    # pixel (no square) on its FIRST position is bright at the start and back to background at the end.
    fixed_on_track = spectra.spectrum_at_pixel(mock, trail[0]["x"], trail[0]["y"], half_size=0)
    by_frame = {p["index"]: p["flux"] for p in fixed_on_track}          # frame number -> flux
    print(f"   fixed pixel on the dot's first position: frame 0 = {by_frame[0]:.1f}, frame 11 = {by_frame[11]:.1f}")
    check("a fixed pixel on the dot's first position is bright in frame 0 (more than 100)", by_frame[0] > 100)
    check("... and back to background in frame 11 (less than 30), because the dot has moved away", by_frame[11] < 30)
    check("normalised comparison works on the mock data",
          spectra.compare_spectra(mock, trail, float(star_ra), float(star_dec), 1, True)["normalized"] is True)

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")