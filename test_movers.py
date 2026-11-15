# test_movers.py
# Tests movers.py (Backend 36). Run it with:  python test_movers.py
# Parts 1-3 need nothing. Part 4 needs the mock files (python data_mock.py).

import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import movers

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


SIZE = 60


def blob(x, y, amp, sigma=1.2):
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    return amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma ** 2))


def make_sky(dots, seed=0, cosmic=None):
    """Noise + 3 fixed stars + moving dots (x, y, amp) [+ a one-pixel cosmic ray (x, y, amp)]."""
    rng = np.random.default_rng(seed)
    image = rng.normal(10.0, 1.0, (SIZE, SIZE))
    for sx, sy, amp in ((10, 12, 80), (45, 15, 60), (15, 48, 50)):
        image += blob(sx, sy, amp, 1.5)
    for x, y, amp in dots:
        image += blob(x, y, amp)
    if cosmic is not None:
        image[cosmic[1], cosmic[0]] += cosmic[2]
    return {"image": image, "obs_time": datetime(2026, 1, 1) + timedelta(days=seed), "wcs": None}


# Two movers at different speeds that never meet each other or a fixed star
A = [(5.0 + 6.0 * i, 30.0) for i in range(8)]
B = [(50.0 - 5.0 * i, 55.0 - 2.0 * i) for i in range(8)]


def near(cands, spot, tol=1.5):
    return any(math.hypot(c["x"] - spot[0], c["y"] - spot[1]) <= tol for c in cands)


print("--- Part 1: two movers on a fake sky ---")
frames = [make_sky([(*A[i], 150.0), (*B[i], 120.0)], seed=i) for i in range(8)]
res = movers.find_candidates(frames)
check("one entry per frame, numbered", len(res) == 8 and [r["index"] for r in res] == list(range(8)))
check("mover A is found in every frame", all(near(r["candidates"], A[i]) for i, r in enumerate(res)))
check("mover B is found in every frame", all(near(r["candidates"], B[i]) for i, r in enumerate(res)))
check("nothing else is reported (exactly 2 candidates per frame)", all(len(r["candidates"]) == 2 for r in res))
check("the fixed stars are not reported",
      not any(near(r["candidates"], s, 3) for r in res for s in ((10, 12), (45, 15), (15, 48))))
check("candidates are sorted brightest first",
      all(r["candidates"][0]["snr"] >= r["candidates"][1]["snr"] for r in res))
c = res[0]["candidates"][0]
check("a candidate has x, y, png_x, png_y, ra_deg, dec_deg, snr", set(c) == {"x", "y", "png_x", "png_y", "ra_deg", "dec_deg", "snr"})
check("no WCS gives no sky position", c["ra_deg"] is None and c["dec_deg"] is None)
check("obs_time is copied", res[3]["obs_time"] == frames[3]["obs_time"])
check("original frames are not changed", np.array_equal(frames[0]["image"], make_sky([(*A[0], 150.0), (*B[0], 120.0)], seed=0)["image"]))

print("\n--- Part 2: things that could fool it ---")
spoiled = [make_sky([(*A[i], 150.0)], seed=i, cosmic=(50, 5, 60.0) if i == 2 else None) for i in range(8)]
r2 = movers.find_candidates(spoiled)
check("a one-pixel cosmic ray (60) is rejected", not near(r2[2]["candidates"], (50, 5), 1.0))
check("with min_neighbours=0 the same cosmic ray IS reported",
      near(movers.find_candidates(spoiled, min_neighbours=0)[2]["candidates"], (50, 5), 1.0))
check("the real mover is still found in that frame", near(r2[2]["candidates"], A[2]))

quiet = movers.find_candidates([make_sky([], seed=i) for i in range(8)])
check("pure noise and fixed stars: nothing is reported", all(r["candidates"] == [] for r in quiet))

capped = movers.find_candidates(frames, max_per_frame=1)
check("max_per_frame=1 keeps only the brightest (A, amplitude 150)",
      all(len(r["candidates"]) == 1 and near(r["candidates"], A[i]) for i, r in enumerate(capped)))
check("a very high min_snr reports nothing", all(r["candidates"] == [] for r in movers.find_candidates(frames, min_snr=5000)))

holes = [make_sky([(*A[i], 150.0)], seed=i) for i in range(8)]
holes[4]["image"][:, :10] = np.nan
check("NaN pixels do not crash it and the mover is found", near(movers.find_candidates(holes)[4]["candidates"], A[4]))
allnan = [make_sky([(*A[i], 150.0)], seed=i) for i in range(8)]
allnan[5]["image"] = np.full((SIZE, SIZE), np.nan)
r5 = movers.find_candidates(allnan)
check("an all-NaN frame has no candidates", r5[5]["candidates"] == [])
check("the other frames still work", near(r5[0]["candidates"], A[0]))

print("\n--- Part 3: bad input ---")
check("fewer than 3 frames is refused", fails(movers.find_candidates, frames[:2]))
check("frames of different sizes are refused",
      fails(movers.find_candidates, frames[:2] + [{"image": np.zeros((30, 30))}]))
check("min_snr 0 is refused", fails(movers.find_candidates, frames, 0))
check("max_per_frame 0 is refused", fails(movers.find_candidates, frames, 6.0, 0))
check("max_per_frame text is refused", fails(movers.find_candidates, frames, 6.0, "3"))
check("min_neighbours 5 is refused", fails(movers.find_candidates, frames, 6.0, 10, 2.0, 5))

print("\n--- Part 4: on the mock data ---")
if not MOCK_FILE.exists():
    print("SKIPPED  no mock files. Run:  python data_mock.py")
else:
    from astropy.io import fits
    import data_mock
    import processing

    h = fits.getheader(MOCK_FILE)
    mock = data_mock.get_frames(h["CRVAL1"], h["CRVAL2"], 6.0)
    res = movers.find_candidates(mock)
    trail = processing.find_moving_dot(mock)
    check("12 mock frames", len(mock) == 12)
    check("the brightest candidate is in every frame",
          all(r["candidates"] for r in res))
    gaps = [math.hypot(r["candidates"][0]["x"] - t["x"], r["candidates"][0]["y"] - t["y"]) for r, t in zip(res, trail)]
    print("   gap between the top candidate and find_moving_dot (pixels):", [round(g, 1) for g in gaps])
    check("the top candidate is within 1.5 pixels of find_moving_dot's dot in every frame", max(gaps) < 1.5)
    check("sky positions are given", all(r["candidates"][0]["ra_deg"] is not None for r in res))

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")