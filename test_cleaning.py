# test_cleaning.py
# Tests cleaning.py (after-data #7). Run it with:  python test_cleaning.py
# No server, no data files and no internet are needed.

import numpy as np

import cleaning
import flags

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


REAL = flags.REAL_TABLE_DRAFT
MOCK = flags.MOCK_TABLE


def frame(flag_values=None, size=10):
    """A 10x10 frame of ones; flag_values = {(x, y): value} for image[y, x]."""
    fl = np.zeros((size, size), dtype=np.int32)
    for (x, y), v in (flag_values or {}).items():
        fl[y, x] = v
    return {"image": np.ones((size, size)), "variance": np.full((size, size), 0.5),
            "flags": fl, "detector": 3, "source_file": "f"}


print("--- Part 1: which bits are masked ---")
bad_real = cleaning.mask_value(REAL)
check("real: OUTLIER (bit 19) is masked", bad_real & (1 << 19) != 0)
check("real: NONFUNC (bit 6) is masked", bad_real & (1 << 6) != 0)
check("real: SOURCE (bit 21, info) is NOT masked", bad_real & (1 << 21) == 0)
check("real: HALO (bit 28, contaminated) is NOT masked by default", bad_real & (1 << 28) == 0)
check("real: the default equals flags.mask_for('bad')", bad_real == flags.mask_for("bad", REAL))
check("mock: bad mask is 3", cleaning.mask_value(MOCK) == 3)
both = cleaning.mask_value(REAL, categories=("bad", "contaminated"))
check("categories can be widened", both & (1 << 28) != 0 and both & (1 << 21) == 0)
keep = cleaning.mask_value(REAL, keep_names=("OUTLIER", "TRANSIENT"))
check("keep_names leaves those bits unmasked", keep & (1 << 19) == 0 and keep & (1 << 0) == 0 and keep & (1 << 6) != 0)
check("a mistyped keep name is refused", fails(cleaning.mask_value, REAL, ("bad",), ("OUTLIERS",)))
check("an unknown category is refused", fails(cleaning.mask_value, REAL, ("banana",)))

print("\n--- Part 2: clean_frame ---")
f = frame({(2, 3): 1 << 19, (5, 5): 1 << 21, (7, 1): 1 << 28, (4, 4): (1 << 6) | (1 << 21)})
c = cleaning.clean_frame(f, REAL)
check("an OUTLIER pixel becomes NaN (image[3, 2])", bool(np.isnan(c["image"][3, 2])))
check("a NONFUNC + SOURCE pixel becomes NaN", bool(np.isnan(c["image"][4, 4])))
check("a SOURCE-only pixel is kept", c["image"][5, 5] == 1.0)
check("a HALO-only pixel is kept (contaminated is not masked by default)", c["image"][1, 7] == 1.0)
check("exactly 2 pixels were masked", int(np.isnan(c["image"]).sum()) == 2)
check("the variance of a masked pixel is NaN too", bool(np.isnan(c["variance"][3, 2])) and c["variance"][5, 5] == 0.5)
check("the original is not changed", np.isfinite(f["image"]).all() and np.isfinite(f["variance"]).all())
check("other keys are kept (flags are the same object content)", np.array_equal(c["flags"], f["flags"]) and c["detector"] == 3)
check("the result has the same keys", set(c) == set(f))
check("image stays normal float64", c["image"].dtype == np.float64 and c["variance"].dtype == np.float64)
w = cleaning.clean_frame(f, REAL, categories=("bad", "contaminated"))
check("with 'contaminated' added the HALO pixel is masked too", bool(np.isnan(w["image"][1, 7])))
k = cleaning.clean_frame(f, REAL, keep_names=("OUTLIER",))
check("keep_names=('OUTLIER',) keeps the OUTLIER pixel", k["image"][3, 2] == 1.0 and bool(np.isnan(k["image"][4, 4])))

print("\n--- Part 3: NaN, inf and bad variance ---")
g = frame()
g["image"][0, 0] = np.inf
g["image"][1, 1] = -np.inf
g["image"][2, 2] = np.nan
g["variance"][3, 3] = -1.0
g["variance"][4, 4] = np.nan
cg = cleaning.clean_frame(g, REAL)
check("inf and -inf become NaN", bool(np.isnan(cg["image"][0, 0])) and bool(np.isnan(cg["image"][1, 1])))
check("a NaN pixel stays NaN and its variance is NaN", bool(np.isnan(cg["image"][2, 2])) and bool(np.isnan(cg["variance"][2, 2])))
check("a negative variance masks the image pixel", bool(np.isnan(cg["image"][3, 3])) and bool(np.isnan(cg["variance"][3, 3])))
check("a NaN variance masks the image pixel", bool(np.isnan(cg["image"][4, 4])))
check("everything else is untouched", int(np.isfinite(cg["image"]).sum()) == 95)

print("\n--- Part 4: frames without flags or variance ---")
n = frame()
n["flags"] = None
n["variance"] = None
cn = cleaning.clean_frame(n, REAL)
check("no flags and no variance: only non-finite pixels would change (none here)", np.array_equal(cn["image"], n["image"]))
check("variance stays None and flags stay None", cn["variance"] is None and cn["flags"] is None)
check("flagged_pixels gives None without flags", cleaning.flagged_pixels(n, REAL) is None)
check("no 'flags' key at all works too", cleaning.clean_frame({"image": np.ones((3, 3))}, REAL)["image"].shape == (3, 3))
big = frame({(0, 0): 1 << 28})
check("an int32 array with bit 28 works", cleaning.flagged_pixels(big, REAL, ("contaminated",))[0, 0])
swapped = frame({(0, 0): 1 << 19})
swapped["flags"] = swapped["flags"].astype(">i4")
check("a big-endian flags array (as read from a file) works too", bool(cleaning.flagged_pixels(swapped, REAL)[0, 0]))

print("\n--- Part 5: clean_frames and masked_share ---")
frames = [frame({(0, 0): 1 << 19}), frame(), frame({(0, 0): 1 << 6, (1, 0): 1 << 6})]
cleaned = cleaning.clean_frames(frames, REAL)
check("same number of frames, same order", len(cleaned) == 3 and [int(np.isnan(x["image"]).sum()) for x in cleaned] == [1, 0, 2])
check("masked_share: 2 of 100 pixels = 0.02", abs(cleaning.masked_share(frames[2], cleaned[2]) - 0.02) < 1e-12)
edge = frame({(0, 0): 1 << 19})
edge["image"][:5, :] = np.nan                               # half of the picture has no data
ce = cleaning.clean_frame(edge, REAL)
check("masked_share ignores pixels that had no data (the flagged pixel is in the NaN half)", cleaning.masked_share(edge, ce) == 0.0)
check("empty list gives empty list", cleaning.clean_frames([], REAL) == [])
allnan = {"image": np.full((4, 4), np.nan)}
check("an all-NaN frame gives share 0.0", cleaning.masked_share(allnan, cleaning.clean_frame(allnan, REAL)) == 0.0)

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")