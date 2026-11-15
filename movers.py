# movers.py
# Backend 36 (optional): automatically highlight spots that are NOT in the same
# place in every frame. No new library is needed: numpy only.
#
# Idea (same as processing.find_moving_dot, but for MANY spots):
#   1. The fixed sky is the MEDIAN of all frames. Fixed stars stay in it.
#   2. Each frame minus the fixed sky leaves (mostly) the movers.
#   3. A candidate is a pixel that
#        - is the highest of its 8 neighbours (a local maximum),
#        - stands out by at least min_snr times the noise, and
#        - has at least min_neighbours of its 4 direct neighbours above
#          neighbour_snr times the noise. A real source is spread over several
#          pixels; a cosmic ray usually hits a single pixel and is rejected.
#   4. Per frame the brightest max_per_frame candidates are kept.
#
# Limits (so nobody trusts it too much):
#   - A very slow mover (staying near the same pixels in half the frames or
#     more) is absorbed into the median and NOT found.
#   - A variable star (RW Aur, R Dra) changes brightness and can show up as a
#     candidate although it does not move.
#   - It does not link candidates from frame to frame into tracks.
#   - Frames must have the same pixel size and grid (same assumption as
#     difference, stack and trail; real pointings need re-aligning first).
#   - Flags are not used (real bits are not verified).
#   - All numbers below are first guesses; retune on real data (after-data #24).
#
# Positions use the project convention: x, y counted from 0, y from the bottom
# row. png_x / png_y are the same spot in the PNG (processing.pixel_to_png_position).
# This file reads no files, downloads nothing and does not change the frames.

import warnings

import numpy as np

import processing

MOVER_MIN_SNR = 6.0
MOVER_MAX_PER_FRAME = 10
MOVER_NEIGHBOUR_SNR = 2.0
MOVER_MIN_NEIGHBOURS = 1
MOVER_SNR_CAP = 9999.0


def _shifted(padded, dy, dx, height, width):
    """The array moved by (dy, dx); `padded` has one extra border pixel."""
    return padded[1 + dy:1 + dy + height, 1 + dx:1 + dx + width]


def find_candidates(frames, min_snr=MOVER_MIN_SNR, max_per_frame=MOVER_MAX_PER_FRAME,
                    neighbour_snr=MOVER_NEIGHBOUR_SNR, min_neighbours=MOVER_MIN_NEIGHBOURS):
    """Spots that differ from the fixed sky, for every frame.

    Returns one dictionary per frame, in the order of `frames`:
      index, obs_time, candidates
    where candidates is a list (brightest first) of dictionaries:
      x, y, png_x, png_y, ra_deg, dec_deg (None without a WCS), snr
    Raises ValueError for fewer than 3 frames, frames of different sizes or
    bad settings.
    """
    if not min_snr > 0 or not neighbour_snr > 0:
        raise ValueError("min_snr and neighbour_snr must be greater than zero.")
    if isinstance(max_per_frame, bool) or not isinstance(max_per_frame, int) or max_per_frame < 1:
        raise ValueError("max_per_frame must be a whole number of 1 or more.")
    if isinstance(min_neighbours, bool) or not isinstance(min_neighbours, int) or not 0 <= min_neighbours <= 4:
        raise ValueError("min_neighbours must be a whole number from 0 to 4.")
    if len(frames) < 3:
        raise ValueError("At least 3 frames are needed to find moving spots.")
    shape = frames[0]["image"].shape
    if any(f["image"].shape != shape for f in frames):
        raise ValueError("The frames have different sizes, so moving spots cannot be worked out.")
    height, width = shape

    cube = np.stack([f["image"] for f in frames]).astype(float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)   # all-NaN pixels
        fixed_sky = np.nanmedian(cube, axis=0)

    results = []
    for i, frame in enumerate(frames):
        entry = {"index": i, "obs_time": frame.get("obs_time"), "candidates": []}
        results.append(entry)

        diff = frame["image"] - fixed_sky
        finite = np.isfinite(diff)
        if not finite.any():
            continue
        diff = diff - np.median(diff[finite])
        sigma = 1.4826 * float(np.median(np.abs(diff[finite])))
        if sigma > 0:
            snr_map = diff / sigma
        else:                                           # noiseless: any positive value is "huge"
            snr_map = np.where(diff > 0, MOVER_SNR_CAP, 0.0)
        snr_map = np.where(finite, np.minimum(snr_map, MOVER_SNR_CAP), -np.inf)

        padded = np.pad(snr_map, 1, constant_values=-np.inf)
        is_max = np.ones(shape, dtype=bool)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    is_max &= snr_map > _shifted(padded, dy, dx, height, width)
        direct = sum((_shifted(padded, dy, dx, height, width) > neighbour_snr).astype(int)
                     for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)))
        keep = is_max & (snr_map >= min_snr) & (direct >= min_neighbours)

        ys, xs = np.nonzero(keep)
        order = np.argsort(-snr_map[ys, xs])[:max_per_frame]
        wcs = frame.get("wcs")
        for k in order:
            x, y = int(xs[k]), int(ys[k])
            png_x, png_y = processing.pixel_to_png_position(x, y, height, width)
            ra = dec = None
            if wcs is not None:
                ra_value, dec_value = wcs.pixel_to_world_values(x, y)
                ra, dec = float(ra_value) % 360.0, float(dec_value)
            entry["candidates"].append({"x": float(x), "y": float(y), "png_x": png_x, "png_y": png_y,
                                        "ra_deg": ra, "dec_deg": dec, "snr": float(snr_map[y, x])})
    return results