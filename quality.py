# quality.py
# Backend 28: leave out frames that are mostly bad.
#
# A frame is "mostly bad" when more than MAX_BAD_FRACTION of its usable pixels
# carry a flag of category "bad" (see flags.py). Such a frame only adds noise
# to the animation, so it can be dropped before it is shown.
#
# Rules:
#   - Only pixels that have a value (finite image pixels) are counted. The NaN
#     edge of a cutout that hangs off the image is "no data", not "bad data".
#   - A frame with no usable pixel at all counts as completely bad (1.0).
#   - A frame without flags (flags = None) counts as fine (0.0): we cannot tell.
#   - Which bits are "bad" comes from the flag table in flags.py, so the same
#     code works for the mock bits now and for the real bits later.
#
# This file does not read files or download anything, and it is NOT connected
# to main.py yet. The original frames are never changed.

import numpy as np

import flags

# Frames with MORE bad pixels than this share are dropped. 0.5 is a first guess;
# retune on real flags (TODO after-data #9).
MAX_BAD_FRACTION = 0.5


def bad_fraction(frame, table=None):
    """Share (0 to 1) of the frame's usable pixels that are flagged "bad"."""
    finite = np.isfinite(frame["image"])
    n_usable = int(finite.sum())
    if n_usable == 0:
        return 1.0
    bad = flags.category_pixels(frame.get("flags"), flags.BAD, table)
    if bad is None:
        return 0.0
    return float((bad & finite).sum() / n_usable)


def drop_mostly_bad(frames, max_fraction=MAX_BAD_FRACTION, table=None):
    """Split frames into the ones to keep and the ones left out.

    Returns (kept, dropped):
      kept     list of the frames to show, same order, same objects
      dropped  list of dictionaries {index, source_file, bad_fraction} for the
               frames left out (index = place in the list that was passed in)
    A frame is dropped when its bad fraction is GREATER than max_fraction.
    Raises ValueError if max_fraction is not a number from 0 to 1.
    """
    if (isinstance(max_fraction, bool) or not isinstance(max_fraction, (int, float))
            or not 0 <= max_fraction <= 1):
        raise ValueError("max_fraction must be a number from 0 to 1.")
    kept, dropped = [], []
    for i, frame in enumerate(frames):
        fraction = bad_fraction(frame, table)
        if fraction > max_fraction:
            dropped.append({"index": i, "source_file": frame.get("source_file"),
                            "bad_fraction": fraction})
        else:
            kept.append(frame)
    return kept, dropped