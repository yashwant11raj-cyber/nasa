# selection.py
# After-data #8: sort, group and limit the real images BEFORE anything is downloaded.
#
# One real position has about 258 images (6 detectors, 36 to 48 each, over 12 months),
# and every cutout takes 10 to 30 seconds. So the list that search_images() gives
# must be cut down first. This file works on that list (dictionaries with the keys
# url, t_min, obs_time, bandpass, detector) and never touches the network, so it is
# easy to test.
#
# Two ways to cut the list down (both keep the images EVENLY SPREAD over time, so
# the animation still covers the whole year instead of just the first weeks):
#   choose_images()       one detector (or all) and at most max_frames images
#   limit_per_detector()  all detectors, but at most N images of each
#
# Why one detector at a time is the natural default: each detector has its own
# wavelength range and brightness scale, so frames of ONE detector are the ones that
# can be compared with each other (see realcheck.py). On 2026-11-15 the biggest
# detector had 48 images, which is below config.MAX_FRAMES (50).
#
# Not connected to main.py or the cache key yet (a detector setting needs a go-ahead).

import config

DETECTORS = (1, 2, 3, 4, 5, 6)


def _check_count(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a whole number of 1 or more.")
    return value


def _check_detector(detector):
    if detector is None:
        return None
    if isinstance(detector, bool) or not isinstance(detector, int) or detector not in DETECTORS:
        raise ValueError("The detector must be a whole number from 1 to 6 (or None for all).")
    return detector


def sort_images(images):
    """A NEW list, oldest first (by t_min). The input list is not changed."""
    return sorted(images, key=lambda item: item["t_min"])


def group_by_detector(images):
    """Dictionary detector number -> list of images (each list oldest first).

    Images without a detector number (None) are left out.
    """
    groups = {}
    for item in sort_images(images):
        if item.get("detector") in DETECTORS:
            groups.setdefault(item["detector"], []).append(item)
    return groups


def count_by_detector(images):
    """Dictionary detector number -> how many images. Handy for a message."""
    return {det: len(items) for det, items in sorted(group_by_detector(images).items())}


def spread_pick(items, n):
    """At most n items, evenly spread over the list (first and last always included).

    The list must already be in the order that matters (oldest first). Fewer than
    n items: all of them. n = 1 gives the middle one.
    """
    _check_count(n, "n")
    total = len(items)
    if total <= n:
        return list(items)
    if n == 1:
        return [items[total // 2]]
    step = (total - 1) / (n - 1)          # more than 1 here, so the rounded places differ
    return [items[round(i * step)] for i in range(n)]


def choose_images(images, max_frames=None, detector=None):
    """Pick the images to download. Returns (chosen, available).

    images:     the list from data_irsa.search_images (any order).
    max_frames: None = config.MAX_FRAMES.
    detector:   None = every detector, or 1 to 6 for just one.
    chosen:     oldest first, at most max_frames, evenly spread over time.
    available:  how many images matched BEFORE the limit (so the page can say
                "showing 48 of 258" or "showing 45 of 45").
    An empty list is fine (no image covers the position): ([], 0).
    Raises ValueError for a bad max_frames or detector.
    """
    limit = _check_count(config.MAX_FRAMES if max_frames is None else max_frames, "max_frames")
    detector = _check_detector(detector)
    ordered = sort_images(images)
    if detector is not None:
        ordered = [item for item in ordered if item.get("detector") == detector]
    return spread_pick(ordered, limit), len(ordered)


def limit_per_detector(images, per_detector):
    """Every detector, but at most `per_detector` images of each, evenly spread.

    Returns one list, oldest first. Useful for stack mode and for a sample over
    all wavelengths. Detectors with no images are simply missing.
    """
    _check_count(per_detector, "per_detector")
    picked = []
    for items in group_by_detector(images).values():
        picked.extend(spread_pick(items, per_detector))
    return sort_images(picked)