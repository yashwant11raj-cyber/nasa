# test_quality.py
# Tests quality.py (Backend 28). Run it with:  python test_quality.py
# Parts 1-3 need nothing. Part 4 needs the mock files (python data_mock.py).

from pathlib import Path

import numpy as np

import quality

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


# Mock bits: 1 = bad pixel, 2 = cosmic ray (both "bad"), 4 = contaminated (not "bad")
def fake(bad_share=0.0, flag=1, name="f", size=10):
    """A 10x10 frame whose first `bad_share` of the pixels carry the given flag."""
    flags = np.zeros((size, size), dtype=np.int32)
    flags.reshape(-1)[:int(round(bad_share * size * size))] = flag
    return {"image": np.ones((size, size)), "flags": flags, "source_file": name}


print("--- Part 1: bad_fraction ---")
check("no flags set = 0", quality.bad_fraction(fake(0.0)) == 0.0)
check("30% bad pixels = 0.3", abs(quality.bad_fraction(fake(0.3)) - 0.3) < 1e-9)
check("cosmic rays count as bad", abs(quality.bad_fraction(fake(0.2, flag=2)) - 0.2) < 1e-9)
check("contaminated pixels do NOT count as bad", quality.bad_fraction(fake(0.9, flag=4)) == 0.0)
check("a pixel with several flags counts once", abs(quality.bad_fraction(fake(0.4, flag=3)) - 0.4) < 1e-9)
nan_frame = fake(0.5)
nan_frame["image"][5:, :] = np.nan          # the bottom half has no data
check("NaN pixels (no data) are not counted: 50 bad of 50 usable pixels = 1.0",
      abs(quality.bad_fraction(nan_frame) - 1.0) < 1e-9)
edge = fake(0.0)
edge["image"][:, :5] = np.nan
check("a NaN edge alone is not 'bad'", quality.bad_fraction(edge) == 0.0)
all_nan = fake(0.0)
all_nan["image"][:] = np.nan
check("an all-NaN frame counts as completely bad", quality.bad_fraction(all_nan) == 1.0)
no_flags = {"image": np.ones((5, 5)), "flags": None}
check("a frame without flags counts as fine", quality.bad_fraction(no_flags) == 0.0)
check("a frame with no 'flags' key counts as fine", quality.bad_fraction({"image": np.ones((5, 5))}) == 0.0)
check("a custom table can be passed in",
      quality.bad_fraction(fake(0.5, flag=4), {2: ("X", "mine", "bad")}) == 0.5)

print("\n--- Part 2: drop_mostly_bad ---")
frames = [fake(0.0, name="a"), fake(0.8, name="b"), fake(0.5, name="c"), fake(0.6, name="d"), fake(0.1, name="e")]
kept, dropped = quality.drop_mostly_bad(frames)
print("   kept:", [f["source_file"] for f in kept], " dropped:", dropped)
check("0.6 and 0.8 are dropped, 0.5 is kept (limit is 'more than 0.5')",
      [f["source_file"] for f in kept] == ["a", "c", "e"] and [d["source_file"] for d in dropped] == ["b", "d"])
check("dropped entries give the place in the input list", [d["index"] for d in dropped] == [1, 3])
check("dropped entries give the bad fraction", abs(dropped[0]["bad_fraction"] - 0.8) < 1e-9)
check("the kept frames are the same objects, same order", kept[0] is frames[0] and kept[2] is frames[4])
check("the input list is not changed", len(frames) == 5)
k2, d2 = quality.drop_mostly_bad(frames, max_fraction=0.05)
check("a stricter limit drops more", [f["source_file"] for f in k2] == ["a"] and len(d2) == 4)
k3, d3 = quality.drop_mostly_bad(frames, max_fraction=1.0)
check("limit 1.0 keeps every frame that has some data", len(k3) == 5 and d3 == [])
check("empty list gives two empty lists", quality.drop_mostly_bad([]) == ([], []))
check("everything bad: nothing kept, all reported", quality.drop_mostly_bad([fake(1.0), fake(1.0)])[0] == [])

print("\n--- Part 3: bad limits are refused ---")
for value in (-0.1, 1.5, "half", None, float("nan"), True):
    check(f"max_fraction={value!r} is refused", fails(quality.drop_mostly_bad, frames, value))

print("\n--- Part 4: on the mock data ---")
if not MOCK_FILE.exists():
    print("SKIPPED  no mock files. Run:  python data_mock.py")
else:
    from astropy.io import fits
    import data_mock

    h = fits.getheader(MOCK_FILE)
    mock = data_mock.get_frames(h["CRVAL1"], h["CRVAL2"], 6.0)
    fractions = [quality.bad_fraction(f) for f in mock]
    print("   bad fractions of the 12 mock frames:", [round(x, 4) for x in fractions])
    check("12 mock frames", len(mock) == 12)
    check("every mock frame is less than 5% bad", max(fractions) < 0.05)
    kept, dropped = quality.drop_mostly_bad(mock)
    check("by default no mock frame is dropped", len(kept) == 12 and dropped == [])
    ruined = dict(mock[3])
    ruined["flags"] = np.full(mock[3]["flags"].shape, 1, dtype=np.int32)   # every pixel "dead"
    kept, dropped = quality.drop_mostly_bad(mock[:3] + [ruined] + mock[4:])
    check("a ruined mock frame (every pixel flagged) is dropped and the rest are kept",
          len(kept) == 11 and [d["index"] for d in dropped] == [3])
    check("the real mock frame is untouched", mock[3]["flags"].max() > 0 and quality.bad_fraction(mock[3]) < 0.05)

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")