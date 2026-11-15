# test_selection.py
# Tests selection.py (after-data #8). Run it with:  python test_selection.py
# No server, no data files and no internet are needed.

import config
import selection

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


# The same numbers as the real search on 2026-11-15: 36, 48, 45, 36, 48, 45 = 258 images
COUNTS = {1: 36, 2: 48, 3: 45, 4: 36, 5: 48, 6: 45}
images = []
for det, n in COUNTS.items():
    for k in range(n):
        images.append({"url": f"u{det}_{k}", "t_min": 60800.0 + k * 8.0 + det * 0.01,
                       "obs_time": None, "bandpass": f"SPHEREx-D{det}", "detector": det})
# Shuffle in a fixed way so "any order" is really tested
images = images[::2] + images[1::2]
check("premise: 258 images", len(images) == 258)

print("--- Part 1: sort, group, count ---")
before = list(images)
ordered = selection.sort_images(images)
check("oldest first", [i["t_min"] for i in ordered] == sorted(i["t_min"] for i in images))
check("the input list is not changed (same order as before)", images == before)
groups = selection.group_by_detector(images)
check("six groups", sorted(groups) == [1, 2, 3, 4, 5, 6])
check("each group has the right size and is sorted",
      all(len(groups[d]) == COUNTS[d] and [i["t_min"] for i in groups[d]] == sorted(i["t_min"] for i in groups[d])
          for d in groups))
check("count_by_detector matches the real numbers", selection.count_by_detector(images) == COUNTS)
odd = images + [{"url": "x", "t_min": 1.0, "detector": None}, {"url": "y", "t_min": 2.0, "detector": 9}]
check("images without a usable detector are left out of the groups", selection.count_by_detector(odd) == COUNTS)
check("empty list gives empty results", selection.group_by_detector([]) == {} and selection.count_by_detector([]) == {})

print("\n--- Part 2: spread_pick ---")
items = list(range(100))
p = selection.spread_pick(items, 5)
print("   5 of 0..99:", p)
check("first and last are included", p[0] == 0 and p[-1] == 99)
check("evenly spread (gaps 24 or 25)", all(24 <= b - a <= 25 for a, b in zip(p, p[1:])))
check("fewer items than n: all of them", selection.spread_pick([1, 2, 3], 10) == [1, 2, 3])
check("exactly n items: all of them", selection.spread_pick(list(range(5)), 5) == [0, 1, 2, 3, 4])
check("n = 1 gives the middle one", selection.spread_pick(list(range(9)), 1) == [4])
check("n = 2 gives first and last", selection.spread_pick(list(range(9)), 2) == [0, 8])
for total in (11, 48, 99, 258):
    for n in (2, 3, 7, 10, 50):
        out = selection.spread_pick(list(range(total)), n)
        if len(out) != min(n, total) or len(set(out)) != len(out) or out != sorted(out):
            check(f"spread_pick({total}, {n}) is wrong: {out}", False)
            break
else:
    check("no repeated place and the right count for many combinations", True)
check("n = 0 is refused", fails(selection.spread_pick, items, 0))
check("n = 'a' is refused", fails(selection.spread_pick, items, "a"))
check("empty list gives empty list", selection.spread_pick([], 3) == [])

print("\n--- Part 3: choose_images ---")
chosen, available = selection.choose_images(images, detector=3)
check("detector 3: all 45 (below MAX_FRAMES)", len(chosen) == 45 and available == 45)
check("only detector 3", {i["detector"] for i in chosen} == {3})
check("oldest first", [i["t_min"] for i in chosen] == sorted(i["t_min"] for i in chosen))
chosen, available = selection.choose_images(images, detector=2)
check("detector 2 has 48 images and MAX_FRAMES is 50, so none are dropped",
      config.MAX_FRAMES >= 48 and len(chosen) == 48 and available == 48)
chosen, available = selection.choose_images(images, max_frames=10, detector=2)
check("max_frames=10 keeps 10 of 48, evenly spread over the year",
      len(chosen) == 10 and available == 48
      and chosen[0]["t_min"] == min(i["t_min"] for i in groups[2])
      and chosen[-1]["t_min"] == max(i["t_min"] for i in groups[2]))
chosen, available = selection.choose_images(images)
check("all detectors: 258 available, the default limit (config.MAX_FRAMES) applies",
      available == 258 and len(chosen) == config.MAX_FRAMES)
check("the chosen images are real entries of the input", all(c in images for c in chosen))
check("no image at all gives ([], 0)", selection.choose_images([]) == ([], 0))
check("a detector with no images gives ([], 0)",
      selection.choose_images([i for i in images if i["detector"] != 5], detector=5) == ([], 0))
check("detector 7 is refused", fails(selection.choose_images, images, None, 7))
check("detector '3' (text) is refused", fails(selection.choose_images, images, None, "3"))
check("detector True is refused", fails(selection.choose_images, images, None, True))
check("max_frames 0 is refused", fails(selection.choose_images, images, 0))

print("\n--- Part 4: limit_per_detector ---")
many = selection.limit_per_detector(images, 6)
print("   per detector:", selection.count_by_detector(many))
check("36 images: 6 of each detector", len(many) == 36 and set(selection.count_by_detector(many).values()) == {6})
check("oldest first over all detectors", [i["t_min"] for i in many] == sorted(i["t_min"] for i in many))
check("a detector with fewer images keeps what it has",
      selection.count_by_detector(selection.limit_per_detector(images[:10], 6)) != {})
check("per_detector 0 is refused", fails(selection.limit_per_detector, images, 0))
check("empty list gives empty list", selection.limit_per_detector([], 3) == [])

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")