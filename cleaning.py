# cleaning.py
# After-data #7: make a frame safe to use, by turning unusable pixels into NaN.
#
# Every later step (stretch, difference, stack, trail, movers, spectra) already
# treats NaN as "no data" and skips it, so cleaning only has to put NaN in the
# right places:
#   1. pixels that are not finite (inf) become NaN
#   2. pixels whose FLAGS carry a flag of a masked category become NaN, in the
#      image AND in the variance (a pixel with no value has no noise estimate)
#   3. a variance that is negative or not finite becomes NaN, and then the image
#      pixel is NaN too
# The flag table decides what "masked" means (flags.py), so the same code works for
# the mock bits and the real bits.
#
# By default only category "bad" is masked. "contaminated" is kept (as in spectra.py)
# and "info" is never masked. Real bit 21 (SOURCE) is "info": it flags 38 to 55 % of
# the pixels of a cutout, because every star is "a known source".
#
# !!! UNVERIFIED !!! The categories of the real bits are my guesses (flags.py). Two
# bits that the draft calls "bad" might also hit a REAL MOVER: OUTLIER ("Pixel flagged
# by Detect Outliers") and TRANSIENT ("Transient detected during SUR"). If WISE 0855
# turns out to be masked, put their names into KEEP_NAMES (or pass keep_names=...).
# Check it with try_real_batch.py (it prints how many pixels each flag masks).
#
# The original frame is never changed. This file reads no files, downloads nothing
# and is NOT connected to main.py yet (it will be used by data_irsa.get_frames).

import numpy as np

import flags

# Names of flags that are NOT masked even though their category is masked.
# Empty for now; see the note above.
KEEP_NAMES = ()


def mask_value(table=None, categories=(flags.BAD,), keep_names=KEEP_NAMES):
    """One whole number with a 1 in every bit that cleaning masks.

    table:      flag table (None = the one for the data source in use).
    categories: which categories are masked.
    keep_names: flag names that stay unmasked. A name that is not in the table is
                refused, so a typo cannot silently change the result.
    """
    for category in categories:
        if category not in flags.CATEGORIES:
            raise ValueError(f"Unknown category '{category}'. Use one of {flags.CATEGORIES}.")
    t = flags.active_table() if table is None else table
    known = {entry[0] for entry in t.values()}
    for name in keep_names:
        if name not in known:
            raise ValueError(f"'{name}' is not a flag name in the table. Known names: {', '.join(sorted(known))}.")
    mask = 0
    for bit, (name, _description, category) in t.items():
        if category in categories and name not in keep_names:
            mask |= 1 << bit
    return mask


def flagged_pixels(frame, table=None, categories=(flags.BAD,), keep_names=KEEP_NAMES):
    """True/False array: which pixels cleaning would mask because of their flags.

    A frame without flags gives None.
    """
    values = frame.get("flags")
    if values is None:
        return None
    return (np.asarray(values).astype(np.int64) & mask_value(table, categories, keep_names)) != 0


def clean_frame(frame, table=None, categories=(flags.BAD,), keep_names=KEEP_NAMES):
    """Return a NEW frame with unusable pixels set to NaN (see the top of the file).

    Only "image" and "variance" are replaced; every other key (flags, wcs, ...) is
    kept as it is, so the cleaned frame still follows FRAME_FORMAT.md.
    """
    image = np.array(frame["image"], dtype=float)           # a copy, in normal float64
    masked = ~np.isfinite(image)

    flagged = flagged_pixels(frame, table, categories, keep_names)
    if flagged is not None:
        masked |= flagged

    variance = frame.get("variance")
    new_variance = None
    if variance is not None:
        new_variance = np.array(variance, dtype=float)
        broken = ~np.isfinite(new_variance) | (new_variance < 0)
        masked |= broken
        new_variance[masked] = np.nan

    image[masked] = np.nan
    new_frame = dict(frame)                                  # copy, so the original is untouched
    new_frame["image"] = image
    if new_variance is not None:
        new_frame["variance"] = new_variance
    return new_frame


def clean_frames(frames, table=None, categories=(flags.BAD,), keep_names=KEEP_NAMES):
    """clean_frame for a list of frames. Same order, new frames."""
    return [clean_frame(f, table, categories, keep_names) for f in frames]


def masked_share(original, cleaned):
    """Share (0 to 1) of the original's usable pixels that cleaning removed.

    Only pixels that had a finite value before are counted, so a NaN edge does not
    count as "removed". A frame with no usable pixels gives 0.0.
    """
    before = np.isfinite(np.asarray(original["image"], dtype=float))
    after = np.isfinite(np.asarray(cleaned["image"], dtype=float))
    n = int(before.sum())
    return float((before & ~after).sum() / n) if n else 0.0