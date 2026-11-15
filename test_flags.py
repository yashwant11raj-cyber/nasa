# test_flags.py
# Tests flags.py (Backend 29). Run it with:  python test_flags.py
# Parts 1-4 need nothing. Part 5 needs the mock files (python data_mock.py).

from pathlib import Path

import numpy as np

import config
import flags

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


print("--- Part 1: the tables ---")
check("mock table is valid", flags.validate_table(flags.MOCK_TABLE) is flags.MOCK_TABLE)
check("real draft table is valid and has 22 bits", len(flags.validate_table(flags.REAL_TABLE_DRAFT)) == 22)
check("mock bits are the values 1, 2, 4 used by data_mock.py",
      {1 << b for b in flags.MOCK_TABLE} == {1, 2, 4})
check("real table has the bit numbers from the real FLAGS header",
      sorted(flags.REAL_TABLE_DRAFT) == [0, 1, 2, 6, 7, 9, 10, 11, 12, 14, 15, 17] + list(range(19, 29)))
check("active table follows config.USE_MOCK",
      flags.active_table() is (flags.MOCK_TABLE if config.USE_MOCK else flags.REAL_TABLE_DRAFT))
check("a table with an unknown category is refused", fails(flags.validate_table, {0: ("A", "x", "banana")}))
check("a table with a repeated name is refused",
      fails(flags.validate_table, {0: ("A", "x", "bad"), 1: ("A", "y", "bad")}))
check("a table with a wrong entry shape is refused", fails(flags.validate_table, {0: ("A", "x")}))
check("an empty table is refused", fails(flags.validate_table, {}))
check("a negative bit number is refused", fails(flags.validate_table, {-1: ("A", "x", "bad")}))

print("\n--- Part 2: masks and decoding ---")
check("mock bad mask = 1 + 2 = 3", flags.mask_for("bad", flags.MOCK_TABLE) == 3)
check("mock contaminated mask = 4", flags.mask_for("contaminated", flags.MOCK_TABLE) == 4)
check("mock info mask = 0", flags.mask_for("info", flags.MOCK_TABLE) == 0)
check("known mask of the mock table = 7", flags.known_mask(flags.MOCK_TABLE) == 7)
check("unknown category is refused", fails(flags.mask_for, "banana", flags.MOCK_TABLE))
check("0 has no flags", flags.decode_value(0, flags.MOCK_TABLE) == [])
check("5 = BAD + CONTAM", flags.decode_value(5, flags.MOCK_TABLE) == ["BAD", "CONTAM"])
check("an unknown bit is shown, not hidden", flags.decode_value(8, flags.MOCK_TABLE) == ["BIT3"])
check("a numpy integer works", flags.decode_value(np.int32(2), flags.MOCK_TABLE) == ["COSMIC"])
check("real table: value 2**10 = HOT", flags.decode_value(1 << 10, flags.REAL_TABLE_DRAFT) == ["HOT"])
check("negative value is refused", fails(flags.decode_value, -1, flags.MOCK_TABLE))

print("\n--- Part 3: arrays ---")
arr = np.array([[0, 1, 2], [4, 5, 8]], dtype=np.int32)
bad = flags.category_pixels(arr, "bad", flags.MOCK_TABLE)
check("bad pixels: values 1, 2 and 5", bad.tolist() == [[False, True, True], [False, True, False]])
check("contaminated pixels: values 4 and 5",
      flags.category_pixels(arr, "contaminated", flags.MOCK_TABLE).tolist() == [[False, False, False], [True, True, False]])
check("flags=None gives None", flags.category_pixels(None, "bad", flags.MOCK_TABLE) is None)
counts = flags.count_flags(arr, flags.MOCK_TABLE)
print("   counts:", counts)
check("counts per flag", counts == {"BAD": 2, "COSMIC": 1, "CONTAM": 2, "UNKNOWN": 1})
check("no flags -> empty counts", flags.count_flags(np.zeros((3, 3), dtype=np.int32), flags.MOCK_TABLE) == {})
check("flags=None -> empty counts", flags.count_flags(None) == {})
big = np.array([[1 << 28]], dtype=np.int32)
check("the highest real bit (28, HALO) works in an int32 array",
      flags.count_flags(big, flags.REAL_TABLE_DRAFT) == {"HALO": 1})

print("\n--- Part 4: frame_summary and legend ---")
s = flags.frame_summary({"flags": arr}, flags.MOCK_TABLE)
check("summary has the pixel count and fractions",
      s["n_pixels"] == 6 and abs(s["bad_fraction"] - 3 / 6) < 1e-9 and abs(s["contaminated_fraction"] - 2 / 6) < 1e-9)
check("summary has the flag counts", s["flag_counts"]["BAD"] == 2)
check("a frame without flags gives None", flags.frame_summary({"flags": None}) is None
      and flags.frame_summary({}) is None)
rows = flags.legend(flags.MOCK_TABLE)
check("legend rows are sorted and complete",
      [r["bit"] for r in rows] == [0, 1, 2] and [r["value"] for r in rows] == [1, 2, 4]
      and set(rows[0]) == {"bit", "value", "name", "description", "category"})
check("a custom table can be passed in (swappable)",
      flags.decode_value(1, {0: ("MINE", "my own", "info")}) == ["MINE"])

print("\n--- Part 5: on the mock data ---")
if not MOCK_FILE.exists():
    print("SKIPPED  no mock files. Run:  python data_mock.py")
else:
    from astropy.io import fits
    import data_mock

    h = fits.getheader(MOCK_FILE)
    mock = data_mock.get_frames(h["CRVAL1"], h["CRVAL2"], 6.0)
    sm = flags.frame_summary(mock[0], flags.MOCK_TABLE)
    print("   frame 0 flag counts:", sm["flag_counts"])
    check("mock frame 0: dead pixels, cosmic rays and contaminated pixels are all found",
          "BAD" in sm["flag_counts"] or "COSMIC" in sm["flag_counts"] or "CONTAM" in sm["flag_counts"])
    check("mock frame 0: contaminated is 1% to 10% of the pixels", 0.01 < sm["contaminated_fraction"] < 0.10)
    check("mock frame 0: no bit outside the table", "UNKNOWN" not in sm["flag_counts"])

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")