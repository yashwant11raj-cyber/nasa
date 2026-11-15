# spectra.py
# Backend 31 + 32: brightness versus wavelength (a "spectrum") from a list of frames.
#
# Idea: every frame is a picture taken at ONE wavelength. If we read the
# brightness of the SAME spot in every frame and sort the readings by
# wavelength, we get a rough spectrum of that spot.
#
# Backend 31 (one spot):
#   spectrum_at_pixel()   a spot given as a pixel (x, y), the same in every frame
#   spectrum_at_sky()     a spot given as RA/Dec; each frame's own WCS finds the pixel
#   spectrum_along_path() a spot that can be somewhere else in each frame
#                         (this is the general function; the two above use it)
# Backend 32 (two spots):
#   compare_spectra()     the spectrum of a MOVER (it changes place from frame to
#                         frame) and of a FIXED star, ready to plot on one graph
#
# Pixel convention (same as the rest of the project): x and y are counted from 0
# and y is counted from the BOTTOM row, exactly how numpy indexes: image[y, x].
#
# How one reading is made:
#   - Take a small square of pixels around the spot (half_size=0 means just one
#     pixel, 1 means 3x3, 2 means 5x5).
#   - Leave out pixels without a value (NaN) and pixels flagged "bad" (flags.py).
#   - flux  = average of the pixels that are left
#   - error = noise of that average, from the VARIANCE map (None if not available)
#
# Things this file does NOT do (yet):
#   - It does not subtract the sky background. A reading is the brightness of the
#     spot PLUS the background around it. Real background handling comes after
#     the data arrives (TODO after-data #19).
#   - It does not correct differences between detectors. Different detectors may
#     have a different brightness scale, so a jump between bands can come from the
#     instrument. realcheck.py already warns about this.
#   - It is not connected to main.py. The frames are never changed.
#
# processing.py (and so astropy) is only loaded when a sky position is used, so
# the pixel functions work with numpy alone.

import math

import numpy as np

import flags


def _is_number(value):
    """True for a real, finite number (not a bool, not NaN, not text)."""
    return (isinstance(value, (int, float, np.integer, np.floating))
            and not isinstance(value, bool) and math.isfinite(float(value)))


def _check_half_size(half_size):
    if isinstance(half_size, bool) or not isinstance(half_size, (int, np.integer)) or not 0 <= half_size <= 10:
        raise ValueError("half_size must be a whole number from 0 to 10 (0 = one pixel, 1 = 3x3 pixels).")


def _read_one(frame, position, half_size, table):
    """One reading (a dictionary) for one frame."""
    wavelength = frame.get("wavelength_um")
    point = {
        "wavelength_um": float(wavelength) if _is_number(wavelength) else None,
        "detector": frame.get("detector"),
        "obs_time": frame.get("obs_time"),
        "x": None, "y": None,
        "flux": None, "error": None,
        "n_pixels": 0,
        "usable": False,
        "reason": None,
    }
    pos = position or {}
    x, y = pos.get("x"), pos.get("y")
    if not (_is_number(x) and _is_number(y)):
        point["reason"] = "The position in this frame is not known."
        return point
    point["x"], point["y"] = float(x), float(y)

    image = np.asarray(frame["image"], dtype=float)
    height, width = image.shape
    xc, yc = int(round(float(x))), int(round(float(y)))
    if not (0 <= xc < width and 0 <= yc < height):
        point["reason"] = "The position is outside this frame."
        return point

    # The square of pixels around the spot, cut off at the image edge
    y0, y1 = max(0, yc - half_size), min(height, yc + half_size + 1)
    x0, x1 = max(0, xc - half_size), min(width, xc + half_size + 1)
    window = image[y0:y1, x0:x1]
    keep = np.isfinite(window)                       # pixels that have a value

    bad = flags.category_pixels(frame.get("flags"), flags.BAD, table)
    if bad is not None:
        keep &= ~np.asarray(bad)[y0:y1, x0:x1]       # leave out "bad" pixels

    n = int(keep.sum())
    point["n_pixels"] = n
    if n == 0:
        point["reason"] = "Every pixel around the position is empty or flagged bad."
        return point

    point["flux"] = float(window[keep].mean())
    point["usable"] = True

    variance = frame.get("variance")
    if variance is not None:
        values = np.asarray(variance, dtype=float)[y0:y1, x0:x1][keep]
        if np.isfinite(values).all() and (values >= 0).all():
            # Variances of added pixels add up; a mean divides by n squared
            point["error"] = float(math.sqrt(values.sum()) / n)
    return point


def spectrum_along_path(frames, positions, half_size=0, table=None):
    """Read the brightness at one position per frame. Returns a list of readings.

    frames:    list of frames (FRAME_FORMAT.md).
    positions: one dictionary per frame with "x" and "y" (pixel position, or None
               when unknown). The lists from processing.find_moving_dot() and
               processing.locate_in_frames() work as they are.
    half_size: 0 = one pixel, 1 = 3x3 pixels, ... (up to 10).
    table:     flag table (None = the one for the data source in use).

    Each reading has:
      index          place of the frame in `frames`
      wavelength_um, detector, obs_time   copied from the frame
      x, y           the pixel that was read (None if the position was unknown)
      flux           average brightness (None if not usable)
      error          noise of that average (None if there is no variance map)
      n_pixels       how many pixels went into the average
      usable         True if flux is a real number
      reason         plain sentence saying why a reading is not usable (else None)
    The list is sorted by wavelength (readings without a wavelength go last).
    Raises ValueError for lists of different length or a bad half_size.
    """
    if len(frames) != len(positions):
        raise ValueError("There must be exactly one position for each frame.")
    _check_half_size(half_size)

    points = []
    for i, (frame, position) in enumerate(zip(frames, positions)):
        point = _read_one(frame, position, half_size, table)
        point["index"] = i
        points.append(point)
    points.sort(key=lambda p: (p["wavelength_um"] is None, p["wavelength_um"] or 0.0, p["index"]))
    return points


def spectrum_at_pixel(frames, x, y, half_size=0, table=None):
    """Spectrum of the SAME pixel (x, y) in every frame.

    Only right when every frame has the same pixel grid (true for the mock data).
    For real frames, which point in slightly different directions, use
    spectrum_at_sky() instead.
    """
    if not (_is_number(x) and _is_number(y)):
        raise ValueError("x and y must be numbers.")
    return spectrum_along_path(frames, [{"x": x, "y": y}] * len(frames), half_size, table)


def spectrum_at_sky(frames, ra_deg, dec_deg, half_size=0, table=None):
    """Spectrum of a fixed sky position (RA/Dec in degrees).

    Each frame's own WCS turns the sky position into that frame's pixel, so this
    works even when the frames do not share a pixel grid.
    """
    if not (_is_number(ra_deg) and _is_number(dec_deg)):
        raise ValueError("RA and Dec must be numbers (degrees).")
    if not 0 <= ra_deg <= 360 or not -90 <= dec_deg <= 90:
        raise ValueError("RA must be 0 to 360 degrees and Dec must be -90 to +90 degrees.")
    import processing                      # loaded here so the pixel functions need no astropy
    located = processing.locate_in_frames(frames, [(ra_deg, dec_deg)] * len(frames))
    return spectrum_along_path(frames, located, half_size, table)


# ---------- Backend 32: two spectra for one graph ----------

def _scale_to_median(points):
    """Divide every reading by the median flux of the usable readings.

    Returns the number that was divided by. Raises ValueError if it cannot be done.
    """
    fluxes = [p["flux"] for p in points if p["usable"]]
    if not fluxes:
        raise ValueError("There is no usable reading, so the spectrum cannot be normalised.")
    scale = float(np.median(fluxes))
    if not scale > 0:
        raise ValueError("The median brightness is not above zero, so the spectrum cannot be normalised.")
    for p in points:
        if p["usable"]:
            p["flux"] /= scale
            if p["error"] is not None:
                p["error"] /= scale
    return scale


def compare_spectra(frames, mover_positions, star_ra_deg, star_dec_deg,
                    half_size=0, normalize=False, table=None):
    """The spectrum of a mover and of a fixed star, for one graph.

    mover_positions: one {"x", "y"} per frame, where the mover is in that frame
                     (for example the result of processing.find_moving_dot()).
    star_ra_deg, star_dec_deg: the fixed star's sky position.
    normalize: False = real brightness numbers.
               True  = each spectrum is divided by its own median, so the SHAPES
                       can be compared even if one object is much brighter.

    Returns a dictionary:
      mover       list of readings (see spectrum_along_path)
      star        list of readings
      normalized  True or False
      scales      {"mover": number or None, "star": number or None}
                  (the numbers the spectra were divided by; None if not normalised)
    Raises ValueError for bad input, or when normalising is not possible.
    """
    mover = spectrum_along_path(frames, mover_positions, half_size, table)
    star = spectrum_at_sky(frames, star_ra_deg, star_dec_deg, half_size, table)
    scales = {"mover": None, "star": None}
    if normalize:
        scales["mover"] = _scale_to_median(mover)
        scales["star"] = _scale_to_median(star)
    return {"mover": mover, "star": star, "normalized": bool(normalize), "scales": scales}