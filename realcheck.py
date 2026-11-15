# realcheck.py
# Backend 30: the "Is it real?" check.
#
# A dot that jumps between two frames is only interesting if the jump is not
# caused by the instrument. For every frame this file gives a traffic light:
#
#   "red"     flagged pixels ("bad" or "contaminated", see flags.py) sit close
#             to the dot's position in this frame
#   "yellow"  the detector or the wavelength differs from the PREVIOUS frame
#             (a change in brightness or position may come from that)
#   "green"   nothing suspicious was found
#   "grey"    we could not check the flags (no flags, or no usable position)
#             and nothing else was suspicious
#
# Red wins over yellow, yellow wins over green and grey. Each frame also lists
# its reasons as plain sentences, so the page can show them in a tooltip.
#
# The dot positions come from outside: for example from
# processing.find_moving_dot() (where the dot IS) or processing.locate_in_frames()
# (where a known star SHOULD be). Both give "x" and "y" in the pixel convention
# of the frame image: counted from 0, y counted from the bottom row, which is
# exactly how numpy indexes the array: image[y, x].
#
# This file does not read files or download anything and is NOT connected to
# main.py yet. The frames are never changed.

import math

import numpy as np

import flags

# "Near the dot" means within this many pixels. A guess: SPHEREx's PSF is
# larger than the mock dot, so retune on real data (TODO after-data #18).
NEAR_RADIUS_PIX = 3.0

# A wavelength counts as changed when it differs from the previous frame's by
# more than this share. A guess based on one observation: two real D6 frames
# differed by 0.7% (4.9674 vs 5.0034 um), which should NOT count as a change.
# Retune after-data #18.
WAVELENGTH_CHANGE_FRACTION = 0.05


def _usable(value):
    return (isinstance(value, (int, float, np.floating, np.integer))
            and not isinstance(value, bool) and math.isfinite(float(value)))


def _reason(code, message):
    return {"code": code, "message": message}


def check_frames(frames, positions, radius=NEAR_RADIUS_PIX,
                 wave_fraction=WAVELENGTH_CHANGE_FRACTION, table=None):
    """Traffic-light check for every frame. Returns one dictionary per frame.

    frames:     list of frames (FRAME_FORMAT.md), in time order.
    positions:  list with one dictionary per frame holding "x" and "y"
                (pixel position of the dot, or None when unknown).
                Entries from find_moving_dot or locate_in_frames work as they are.
    radius:     "near the dot" distance in pixels.
    wave_fraction: share by which the wavelength must differ to count as changed.

    Each result has:
      index, status ("green" | "yellow" | "red" | "grey"),
      reasons                a list of {"code", "message"}
      detector_changed       True/False (always False for frame 0)
      wavelength_changed     True/False (always False for frame 0)
      near_bad_pixels        number of "bad" pixels within the radius (or None)
      near_contaminated_pixels  number of "contaminated" pixels within it (or None)
      flagged_names          names of the bad/contaminated flags found there
      flags_checked          True if the flags near the dot could be looked at
    Raises ValueError for lists of different length or a bad radius / fraction.
    """
    if len(frames) != len(positions):
        raise ValueError("There must be exactly one position for each frame.")
    if not (_usable(radius) and radius > 0):
        raise ValueError("The radius must be a number greater than zero.")
    if not (_usable(wave_fraction) and wave_fraction > 0):
        raise ValueError("wave_fraction must be a number greater than zero.")

    watched = flags.mask_for(flags.BAD, table) | flags.mask_for(flags.CONTAMINATED, table)
    results = []
    for i, frame in enumerate(frames):
        reasons = []
        det_changed = wave_changed = False

        # 1. Compare with the previous frame
        if i > 0:
            before = frames[i - 1]
            d0, d1 = before.get("detector"), frame.get("detector")
            if d0 != d1:
                det_changed = True
                reasons.append(_reason(
                    "detector_changed",
                    f"The detector changed from {d0} to {d1}, so a change may come from the instrument."))
            w0, w1 = before.get("wavelength_um"), frame.get("wavelength_um")
            if _usable(w0) and _usable(w1) and w0 > 0 and abs(w1 - w0) / w0 > wave_fraction:
                wave_changed = True
                reasons.append(_reason(
                    "wavelength_changed",
                    f"The wavelength changed from {w0:.2f} to {w1:.2f} um, "
                    f"so a brightness change may be a colour change."))

        # 2. Look at the flags around the dot
        near_bad = near_cont = None
        flagged_names = []
        flags_checked = False
        pos = positions[i] or {}
        x, y = pos.get("x"), pos.get("y")
        values = frame.get("flags")
        if values is None:
            reasons.append(_reason("no_flags", "This frame has no flags, so the pixels near the dot were not checked."))
        elif not (_usable(x) and _usable(y)):
            reasons.append(_reason("no_position", "The dot's position in this frame is not known, so the flags were not checked."))
        else:
            values = np.asarray(values).astype(np.int64)
            height, width = values.shape
            yy, xx = np.ogrid[0:height, 0:width]
            near = (xx - float(x)) ** 2 + (yy - float(y)) ** 2 <= float(radius) ** 2
            if not near.any():
                reasons.append(_reason("outside_frame", "The dot's position is outside this frame, so the flags were not checked."))
            else:
                flags_checked = True
                around = values[near]
                near_bad = int(np.count_nonzero(around & flags.mask_for(flags.BAD, table)))
                near_cont = int(np.count_nonzero(around & flags.mask_for(flags.CONTAMINATED, table)))
                if near_bad or near_cont:
                    seen = int(np.bitwise_or.reduce(around)) & watched
                    flagged_names = flags.decode_value(seen, table)
                    reasons.append(_reason(
                        "flagged_near_dot",
                        f"Flagged pixels sit close to the dot ({near_bad} bad, {near_cont} contaminated: "
                        f"{', '.join(flagged_names)})."))

        # 3. The traffic light
        if near_bad or near_cont:
            status = "red"
        elif det_changed or wave_changed:
            status = "yellow"
        elif flags_checked:
            status = "green"
        else:
            status = "grey"

        results.append({
            "index": i, "status": status, "reasons": reasons,
            "detector_changed": det_changed, "wavelength_changed": wave_changed,
            "near_bad_pixels": near_bad, "near_contaminated_pixels": near_cont,
            "flagged_names": flagged_names, "flags_checked": flags_checked,
        })
    return results