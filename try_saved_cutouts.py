# try_saved_cutouts.py
# After-data #3, #4 and #5 WITHOUT IRSA's search service (it answered 502 on 2026-11-15).
# Reads the six cutouts that inspect_real_files.py saved in cache/real_cutouts/,
# turns them into frames, builds the wavelength maps, and checks pickle (cache).
# It also tries ONE real download of the known D3 link (only works if IRSA's
# cutout service is up; if not, that part is reported as "not tested").
# Run it with:  python try_saved_cutouts.py        (about 1-2 minutes)

import pickle
import time

import numpy as np
from astropy.io import fits

import config
import data_irsa

SAVE_DIR = config.CACHE_DIR / "real_cutouts"

# Numbers copied from docs/real_files_report.txt:
#   detector: (rows, columns, wavelength at the centre, wavelength at pixel x=0, y=0)
EXPECTED = {
    1: (59, 58, 0.9926, 0.9983),
    2: (59, 59, 1.5151, 1.5246),
    3: (59, 58, 2.3632, 2.3773),
    4: (58, 58, 3.3582, 3.3807),
    5: (59, 59, 4.2950, 4.3045),
    6: (59, 59, 4.9674, 4.9771),
}
TOLERANCE = 0.0006       # microns

# The one link that worked in Backend 26 (copied from inspect_real_files.py, D3 only)
KNOWN_D3_LINK = ("https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W19_1B/"
                 "l2b-v27-2026-197/3/level2_2025W19_1B_0116_1D3_spx_l2b-v27-2026-197.fits"
                 "?center=133.75976461144327,-7.242186d&size=0.1")

problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


def load_from_disk(path):
    """Open a saved cutout and read every extension into memory (same pattern as download)."""
    hdul = fits.open(path, memmap=False)
    try:
        for hdu in hdul:
            hdu.data
    finally:
        hdul.close()
    return hdul


print("--- Read the saved cutouts (after-data #4 and #5) ---")
saved = {}
for det in range(1, 7):
    files = sorted(SAVE_DIR.glob(f"wise0855_SPHEREx-D{det}_*_fov6.fits"))
    if not files:
        print(f"SKIPPED  D{det}: no saved file in {SAVE_DIR}. Run inspect_real_files.py when IRSA is back.")
        continue
    path = files[0]
    rows, cols, centre_expected, corner_expected = EXPECTED[det]
    print(f"\nD{det}: {path.name}")
    hdul = load_from_disk(path)
    saved[det] = hdul
    frame = data_irsa.read_cutout(hdul, path.name)

    check(f"D{det}: frame has exactly the FRAME_KEYS", set(frame) == set(data_irsa.FRAME_KEYS))
    check(f"D{det}: detector is {det}", frame["detector"] == det and type(frame["detector"]) is int)
    check(f"D{det}: shape is ({rows}, {cols}) as in the report", frame["image"].shape == (rows, cols))
    check(f"D{det}: image float64, flags native int32, variance float64",
          frame["image"].dtype == np.float64 and frame["flags"].dtype == np.int32
          and frame["flags"].dtype.isnative and frame["variance"].dtype == np.float64)
    check(f"D{det}: obs_time is a naive 2025 date ({frame['obs_time']})",
          frame["obs_time"].year == 2025 and frame["obs_time"].tzinfo is None)
    check(f"D{det}: centre wavelength {frame['wavelength_um']:.4f} um (report: {centre_expected})",
          abs(frame["wavelength_um"] - centre_expected) < TOLERANCE)

    t0 = time.time()
    wmap = data_irsa.wavelength_map(hdul)
    print(f"   wavelength_map took {time.time() - t0:.2f} s")
    check(f"D{det}: wavelength map has the image's shape", wmap.shape == frame["image"].shape)
    check(f"D{det}: every wavelength is a real number", bool(np.isfinite(wmap).all()))
    print(f"   map range {wmap.min():.4f} to {wmap.max():.4f} um; pixel (x=0, y=0) = {wmap[0, 0]:.4f} (report: {corner_expected})")
    check(f"D{det}: map pixel (x=0, y=0) agrees with the report", abs(wmap[0, 0] - corner_expected) < TOLERANCE)

    print(f"   WCS has SIP distortion: {frame['wcs'].sip is not None}")
    back = pickle.loads(pickle.dumps(frame))      # cache.py saves frames with pickle
    check(f"D{det}: the frame survives pickle (cache) with the same WCS",
          np.allclose(frame["wcs"].pixel_to_world_values(10, 10),
                      back["wcs"].pixel_to_world_values(10, 10), atol=1e-9)
          and np.array_equal(back["flags"], frame["flags"]))

print("\n--- One real download of the known D3 link (after-data #3) ---")
t0 = time.time()
try:
    hdul = data_irsa.download_cutout(KNOWN_D3_LINK)
except TimeoutError as err:
    print(f"NOT TESTED  IRSA's cutout service did not answer: {err}")
except Exception as err:
    check(f"download worked (it raised {type(err).__name__}: {err})", False)
else:
    print(f"   downloaded in {time.time() - t0:.1f} s")
    frame = data_irsa.read_cutout(hdul, KNOWN_D3_LINK)
    check("the downloaded cutout is a D3 frame with 22 flag-table cards or more", frame["detector"] == 3)
    check("its wavelength agrees with the report", abs(frame["wavelength_um"] - EXPECTED[3][2]) < TOLERANCE)
    if 3 in saved:
        same = np.array_equal(np.asarray(saved[3]["FLAGS"].data), np.asarray(hdul["FLAGS"].data))
        check("its FLAGS are identical to the saved D3 file", same)

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")
print("Paste the whole output back to me.")