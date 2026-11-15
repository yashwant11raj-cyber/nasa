# try_real_frames.py
# After-data #2 to #5 on REAL data: search, download, read, wavelength map.
# Needs the internet. It takes about 2-4 minutes (6 downloads of 10-30 s).
# Run it with:  python try_real_frames.py
# It compares the results with docs/real_files_report.txt (inspect_real_files.py).
# It writes nothing to disk.

import pickle
import time
from datetime import timedelta

import numpy as np

import data_irsa
import targets

TARGET_ID = "wise0855"
FOV_ARCMIN = 6.0

# Numbers copied from docs/real_files_report.txt (oldest image of each detector):
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

problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


ra, dec = targets.position_at_epoch(TARGET_ID, 2026.0)
ra %= 360.0
print(f"Target {TARGET_ID} at 2026.0: RA {ra:.6f}, Dec {dec:+.6f}\n")

print("--- Search (after-data #2) ---")
t0 = time.time()
images = data_irsa.search_images(ra, dec, FOV_ARCMIN)
print(f"   {len(images)} images in {time.time() - t0:.1f} s")
bands = {}
for item in images:
    bands[item["bandpass"]] = bands.get(item["bandpass"], 0) + 1
print("   per bandpass:", dict(sorted(bands.items())))
print("   first:", images[0]["obs_time"], " last:", images[-1]["obs_time"])
print("   first link:", images[0]["url"])
check("at least 258 images (the number seen on 2026-11-15)", len(images) >= 258)
check("sorted oldest first", [i["t_min"] for i in images] == sorted(i["t_min"] for i in images))
check("all six detectors are there", sorted(bands) == [f"SPHEREx-D{n}" for n in range(1, 7)])

print("\n--- Download, read, wavelengths (after-data #3, #4, #5): oldest image of each detector ---")
for det in range(1, 7):
    item = next(i for i in images if i["detector"] == det)
    rows, cols, centre_expected, corner_expected = EXPECTED[det]
    print(f"\nD{det}: {item['url']}")
    t0 = time.time()
    hdul = data_irsa.download_cutout(item["url"])
    print(f"   downloaded in {time.time() - t0:.1f} s")
    frame = data_irsa.read_cutout(hdul, item["url"], item["obs_time"])

    check(f"D{det}: frame has exactly the FRAME_KEYS", set(frame) == set(data_irsa.FRAME_KEYS))
    check(f"D{det}: detector is {det}", frame["detector"] == det)
    check(f"D{det}: shape is ({rows}, {cols}) as in the report", frame["image"].shape == (rows, cols))
    check(f"D{det}: image float64, flags native int32, variance float64",
          frame["image"].dtype == np.float64 and frame["flags"].dtype == np.int32
          and frame["flags"].dtype.isnative and frame["variance"].dtype == np.float64)
    gap = abs((frame["obs_time"] - item["obs_time"]).total_seconds())
    check(f"D{det}: DATE-OBS agrees with the search time within 1 s (gap {gap:.3f} s)", gap < 1.0)
    check(f"D{det}: centre wavelength {frame['wavelength_um']:.4f} um (report: {centre_expected})",
          abs(frame["wavelength_um"] - centre_expected) < TOLERANCE)

    t0 = time.time()
    wmap = data_irsa.wavelength_map(hdul)
    print(f"   wavelength_map took {time.time() - t0:.2f} s")
    check(f"D{det}: wavelength map has the image's shape", wmap.shape == frame["image"].shape)
    check(f"D{det}: every wavelength is a real number", bool(np.isfinite(wmap).all()))
    print(f"   map range {wmap.min():.4f} to {wmap.max():.4f} um; pixel (x=0, y=0) = {wmap[0, 0]:.4f} (report: {corner_expected})")
    check(f"D{det}: map pixel (x=0, y=0) agrees with the report", abs(wmap[0, 0] - corner_expected) < TOLERANCE)

    wcs = frame["wcs"]
    print(f"   WCS has SIP distortion: {wcs.sip is not None}; pixel scale from the frame list code is checked later")
    back = pickle.loads(pickle.dumps(frame))      # cache.py saves frames with pickle
    here = wcs.pixel_to_world_values(10, 10)
    there = back["wcs"].pixel_to_world_values(10, 10)
    check(f"D{det}: the frame survives pickle (cache) with the same WCS",
          np.allclose(here, there, atol=1e-9) and np.array_equal(back["flags"], frame["flags"]))

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")
print("Paste the whole output back to me.")