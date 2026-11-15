# flags.py
# Backend 29: turns the numbers in a frame's FLAGS map into names and masks.
#
# A FLAGS pixel is one whole number. Each BIT of that number means one thing
# (bit 0 = value 1, bit 1 = value 2, bit 2 = value 4 ...). The meaning of each
# bit lives in a TABLE, so the table can be swapped without touching any code:
#
#     bit number -> (name, description, category)
#
# category says how much a flag matters to us:
#     "bad"           the pixel value cannot be trusted
#     "contaminated"  the pixel may be polluted by something else
#     "info"          just information, not a problem
#
# Two tables are here:
#   MOCK_TABLE        the invented bits of data_mock.py (1 = bad, 2 = cosmic ray,
#                     4 = contaminated). Those are certain, they are our own.
#   REAL_TABLE_DRAFT  the 22 real SPHEREx bits. The NAMES and DESCRIPTIONS are
#                     copied from docs/real_query_report.txt (the FLAGS header of
#                     a real cutout). 
#                     Verified (FLAGS header MSKM cards, 6 detectors): bit n = 1<<n.
#                     NOT verified: the CATEGORY of every bit (my own guess).
#                     Replace it using the table in IRSA's SPHEREx Explanatory
#                     Supplement (after-data #7 and #17).
#
# This file needs only numpy. It never reads files and never downloads anything.

import numpy as np

import config

BAD = "bad"
CONTAMINATED = "contaminated"
INFO = "info"
CATEGORIES = (BAD, CONTAMINATED, INFO)

MOCK_TABLE = {
    0: ("BAD", "Dead pixel (mock)", BAD),
    1: ("COSMIC", "Cosmic ray hit (mock)", BAD),
    2: ("CONTAM", "Near a fixed star (mock)", CONTAMINATED),
}

# Names and descriptions: from the real FLAGS header. Categories: GUESSES.
REAL_TABLE_DRAFT = {
    0: ("TRANSIENT", "Transient detected during SUR", BAD),
    1: ("OVERFLOW", "Overflow detected during SUR", BAD),
    2: ("SUR_ERROR", "Error in onboard processing", BAD),
    6: ("NONFUNC", "Permanently unusable", BAD),
    7: ("DICHROIC", "Low efficiency due to dichroic", INFO),
    9: ("MISSING_DATA", "Onboard data lost", BAD),
    10: ("HOT", "Hot pixel", BAD),
    11: ("COLD", "Anomalously low signal", BAD),
    12: ("FULLSAMPLE", "Pixel full sample history is available", INFO),
    14: ("PHANMISS", "Phantom correction was not applied", INFO),
    15: ("NONLINEAR", "Nonlinearity correction cannot be applied reliably", BAD),
    17: ("PERSIST", "Persistent charge above threshold", CONTAMINATED),
    19: ("OUTLIER", "Pixel flagged by Detect Outliers", BAD),
    20: ("CROSSTALK", "Pixel affected by crosstalk.", CONTAMINATED),
    21: ("SOURCE", "Pixel mapped to a known source", INFO),
    22: ("GHOST", "Affected by a bright source inside the exposure", CONTAMINATED),
    23: ("GHOST_FPA", "Affected by a bright source on another detector", CONTAMINATED),
    24: ("GHOST_EXT", "Pixel affected by a bright source outside FOV", CONTAMINATED),
    25: ("STREAK", "Pixel affected by a streak", CONTAMINATED),
    26: ("BLOOM", "Pixel part of a bloom artifact", CONTAMINATED),
    27: ("SNOWBALL", "Pixel part of a snowball artifact", CONTAMINATED),
    28: ("HALO", "Pixel part of a transient halo", CONTAMINATED),
}


def validate_table(table):
    """Raise ValueError if a table is not in the right shape. Returns the table."""
    if not isinstance(table, dict) or not table:
        raise ValueError("A flag table must be a non-empty dictionary.")
    names = set()
    for bit, entry in table.items():
        if isinstance(bit, bool) or not isinstance(bit, int) or not 0 <= bit <= 62:
            raise ValueError(f"Flag bit numbers must be whole numbers from 0 to 62 (got {bit!r}).")
        if not (isinstance(entry, tuple) and len(entry) == 3):
            raise ValueError(f"Bit {bit}: the entry must be (name, description, category).")
        name, _description, category = entry
        if not isinstance(name, str) or not name:
            raise ValueError(f"Bit {bit}: the name must be a non-empty text.")
        if name in names:
            raise ValueError(f"The flag name '{name}' is used twice.")
        names.add(name)
        if category not in CATEGORIES:
            raise ValueError(f"Bit {bit}: unknown category '{category}'. Use one of {CATEGORIES}.")
    return table


def active_table():
    """The table for the data source in use now (mock or real)."""
    return MOCK_TABLE if config.USE_MOCK else REAL_TABLE_DRAFT


def _table(table):
    return active_table() if table is None else table


def mask_for(category, table=None):
    """One whole number with a 1 in every bit of this category."""
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category '{category}'. Use one of {CATEGORIES}.")
    mask = 0
    for bit, (_name, _description, cat) in _table(table).items():
        if cat == category:
            mask |= 1 << bit
    return mask


def known_mask(table=None):
    """One whole number with a 1 in every bit the table knows."""
    mask = 0
    for bit in _table(table):
        mask |= 1 << bit
    return mask


def decode_value(value, table=None):
    """Names of the flags set in ONE pixel value, lowest bit first.

    A set bit that the table does not know is shown as 'BIT<n>' (never hidden).
    """
    value = int(value)
    if value < 0:
        raise ValueError("A flag value cannot be negative.")
    t = _table(table)
    found = []
    bit = 0
    while value >> bit:
        if (value >> bit) & 1:
            found.append(t[bit][0] if bit in t else f"BIT{bit}")
        bit += 1
    return found


def category_pixels(flags, category, table=None):
    """True/False array: which pixels carry at least one flag of this category.

    flags = None (frame without flags) gives None.
    """
    if flags is None:
        return None
    values = np.asarray(flags).astype(np.int64)
    return (values & mask_for(category, table)) != 0


def count_flags(flags, table=None):
    """How many pixels carry each flag: a dictionary name -> pixel count.

    Only flags that occur are listed. Set bits not in the table are counted
    together under 'UNKNOWN'. flags = None gives an empty dictionary.
    """
    if flags is None:
        return {}
    values = np.asarray(flags).astype(np.int64)
    t = _table(table)
    counts = {}
    for bit, (name, _description, _category) in sorted(t.items()):
        n = int(np.count_nonzero(values & (1 << bit)))
        if n:
            counts[name] = n
    unknown = int(np.count_nonzero(values & ~known_mask(t)))
    if unknown:
        counts["UNKNOWN"] = unknown
    return counts


def frame_summary(frame, table=None):
    """Contamination info for one frame (a dictionary the API can send as JSON).

    Returns None if the frame has no flags. Fractions are of ALL pixels
    in the cutout (NaN edge pixels carry flag 0, see processing.cutout_frame).
    """
    flags = frame.get("flags")
    if flags is None:
        return None
    n = int(np.asarray(flags).size)
    bad = category_pixels(flags, BAD, table)
    contaminated = category_pixels(flags, CONTAMINATED, table)
    return {
        "n_pixels": n,
        "flag_counts": count_flags(flags, table),
        "bad_fraction": float(bad.sum() / n) if n else 0.0,
        "contaminated_fraction": float(contaminated.sum() / n) if n else 0.0,
    }


def legend(table=None):
    """The table as a list of dictionaries, for a legend on the web page."""
    return [{"bit": bit, "value": 1 << bit, "name": name,
             "description": description, "category": category}
            for bit, (name, description, category) in sorted(_table(table).items())]


validate_table(MOCK_TABLE)
validate_table(REAL_TABLE_DRAFT)


if __name__ == "__main__":
    # Quick look: run  python flags.py
    print("Active table:", "MOCK" if config.USE_MOCK else "REAL (draft)")
    for row in legend():
        print(f"  bit {row['bit']:2d}  value {row['value']:>10d}  {row['name']:<13} "
              f"{row['category']:<13} {row['description']}")