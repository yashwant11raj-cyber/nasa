# test_realcheck.py
# Tests realcheck.py (Backend 30). Run it with:  python test_realcheck.py
# Parts 1-4 need nothing. Part 5 needs the mock files (python data_mock.py).

from pathlib import Path

import numpy as np

import realcheck

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


# Mock bits: 1 = bad pixel, 2 = cosmic ray (bad), 4 = contaminated
def fake(detector=1, wave=2.0, size=40, flagged=None):
    """A 40x40 frame. flagged = {(x, y): value} puts flag values at pixel (x, y)."""
    flags = np.zeros((size, size), dtype=np.int32)
    for (x, y), value in (flagged or {}).items():
        flags[y, x] = value                       # image[y, x]: y is the row
    return {"image": np.ones((size, size)), "flags": flags, "detector": detector, "wavelength_um": wave}


POS = {"x": 20.0, "y": 20.0}

print("--- Part 1: green and the traffic-light order ---")
same = [fake(), fake(), fake()]
res = realcheck.check_frames(same, [POS] * 3)
check("same detector, same wavelength, clean flags: all green", [r["status"] for r in res] == ["green"] * 3)
check("one result per frame, numbered", [r["index"] for r in res] == [0, 1, 2])
check("green frames have no reasons", all(r["reasons"] == [] for r in res))
check("flags were checked", all(r["flags_checked"] for r in res))
check("zero flagged pixels near the dot", res[0]["near_bad_pixels"] == 0 and res[0]["near_contaminated_pixels"] == 0)

print("\n--- Part 2: yellow (detector or wavelength changed) ---")
res = realcheck.check_frames([fake(detector=1), fake(detector=2)], [POS] * 2)
check("frame 0 is green, frame 1 is yellow", [r["status"] for r in res] == ["green", "yellow"])
check("the reason is detector_changed", [x["code"] for x in res[1]["reasons"]] == ["detector_changed"])
check("the message names both detectors", "1" in res[1]["reasons"][0]["message"] and "2" in res[1]["reasons"][0]["message"])
check("detector_changed True, wavelength_changed False", res[1]["detector_changed"] and not res[1]["wavelength_changed"])
check("frame 0 is never 'changed'", not res[0]["detector_changed"] and not res[0]["wavelength_changed"])
res = realcheck.check_frames([fake(wave=2.0), fake(wave=2.5)], [POS] * 2)
check("a 25% wavelength change is yellow", res[1]["status"] == "yellow" and res[1]["wavelength_changed"])
check("the reason is wavelength_changed", [x["code"] for x in res[1]["reasons"]] == ["wavelength_changed"])
res = realcheck.check_frames([fake(wave=4.9674), fake(wave=5.0034)], [POS] * 2)
check("the real 0.7% shift (4.9674 -> 5.0034 um) is NOT a change", res[1]["status"] == "green")
res = realcheck.check_frames([fake(wave=2.0), fake(wave=2.5)], [POS] * 2, wave_fraction=0.5)
check("wave_fraction can be raised", res[1]["status"] == "green")
res = realcheck.check_frames([fake(detector=1, wave=2.0), fake(detector=2, wave=3.0)], [POS] * 2)
check("both changes give two reasons, still yellow",
      res[1]["status"] == "yellow" and len(res[1]["reasons"]) == 2)
res = realcheck.check_frames([fake(wave=None), fake(wave=2.0)], [POS] * 2)
check("a missing wavelength does not crash and is not a change", res[1]["status"] == "green")

print("\n--- Part 3: red (flagged pixels near the dot) ---")
frames = [fake(), fake(flagged={(21, 20): 1}), fake(flagged={(20, 22): 4}), fake(flagged={(20, 30): 1})]
res = realcheck.check_frames(frames, [POS] * 4)
print("   statuses:", [r["status"] for r in res])
check("a bad pixel 1 pixel away is red", res[1]["status"] == "red" and res[1]["near_bad_pixels"] == 1)
check("a contaminated pixel 2 pixels away is red", res[2]["status"] == "red" and res[2]["near_contaminated_pixels"] == 1)
check("a bad pixel 10 pixels away is NOT near", res[3]["status"] == "green")
check("the flag name is in the message", "BAD" in res[1]["reasons"][0]["message"] and res[1]["flagged_names"] == ["BAD"])
check("contaminated flag is named too", res[2]["flagged_names"] == ["CONTAM"])
res = realcheck.check_frames([fake(), fake(detector=2, flagged={(21, 20): 1})], [POS] * 2)
check("red wins over yellow", res[1]["status"] == "red" and len(res[1]["reasons"]) == 2)
res = realcheck.check_frames([fake(flagged={(23, 20): 1})], [POS], radius=2.0)
check("a smaller radius leaves a pixel 3 away out", res[0]["status"] == "green")
res = realcheck.check_frames([fake(flagged={(23, 20): 1})], [POS], radius=3.0)
check("exactly on the radius counts as near", res[0]["status"] == "red")
res = realcheck.check_frames([fake(flagged={(20, 20): 16})], [POS])
check("a flag bit that is not in the table (16) is ignored", res[0]["status"] == "green")
res = realcheck.check_frames([fake(flagged={(0, 0): 1})], [{"x": 0.2, "y": 0.1}])
check("a dot at the corner works", res[0]["status"] == "red")

print("\n--- Part 4: grey, and bad input ---")
res = realcheck.check_frames([fake(), fake()], [{"x": None, "y": None}, None])
check("unknown position: grey, reason no_position",
      [r["status"] for r in res] == ["grey", "grey"] and res[0]["reasons"][0]["code"] == "no_position")
check("not checked means flags_checked False and counts None",
      not res[0]["flags_checked"] and res[0]["near_bad_pixels"] is None)
res = realcheck.check_frames([fake(), fake(detector=2)], [{"x": None, "y": None}] * 2)
check("unknown position but detector changed: yellow", res[1]["status"] == "yellow")
nf = fake()
nf["flags"] = None
res = realcheck.check_frames([nf], [POS])
check("a frame without flags: grey, reason no_flags", res[0]["status"] == "grey" and res[0]["reasons"][0]["code"] == "no_flags")
res = realcheck.check_frames([fake()], [{"x": 500.0, "y": 500.0}])
check("a position far outside the frame: grey, reason outside_frame",
      res[0]["status"] == "grey" and res[0]["reasons"][0]["code"] == "outside_frame")
res = realcheck.check_frames([fake()], [{"x": float("nan"), "y": 5}])
check("a NaN position counts as unknown", res[0]["status"] == "grey")
check("empty lists give an empty list", realcheck.check_frames([], []) == [])
check("different list lengths are refused", fails(realcheck.check_frames, [fake()], []))
check("radius 0 is refused", fails(realcheck.check_frames, [fake()], [POS], radius=0))
check("radius text is refused", fails(realcheck.check_frames, [fake()], [POS], radius="big"))
check("wave_fraction 0 is refused", fails(realcheck.check_frames, [fake()], [POS], wave_fraction=0))
orig = fake(flagged={(21, 20): 1})
before = orig["flags"].copy()
realcheck.check_frames([orig], [POS])
check("the frames are not changed", np.array_equal(orig["flags"], before))

print("\n--- Part 5: on the mock data ---")
if not MOCK_FILE.exists():
    print("SKIPPED  no mock files. Run:  python data_mock.py")
else:
    from astropy.io import fits
    import data_mock
    import processing

    h = fits.getheader(MOCK_FILE)
    mock = data_mock.get_frames(h["CRVAL1"], h["CRVAL2"], 6.0)
    trail = processing.find_moving_dot(mock)
    res = realcheck.check_frames(mock, trail)
    print("   statuses:", [r["status"] for r in res])
    check("12 results", len(res) == 12)
    check("frame 0 is green (nothing to compare, no flags near the dot)", res[0]["status"] == "green")
    check("the mock detector changes every frame, so frames 1-11 are yellow or red",
          all(r["status"] in ("yellow", "red") for r in res[1:]))
    check("every frame after the first reports detector_changed", all(r["detector_changed"] for r in res[1:]))
    check("the mock defects avoid the dot's rows, so no frame is red", not any(r["status"] == "red" for r in res))
    stacked = processing.stack_frames(mock, "mean", "detector")
    res2 = realcheck.check_frames(stacked, [{"x": None, "y": None}] * len(stacked))
    check("stacked frames work too (6 results)", len(res2) == 6)

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")