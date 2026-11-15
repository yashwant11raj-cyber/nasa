# export_csv.py
# Backend 35: turns positions (one per frame) into CSV text a person can open
# in Excel or send to someone.
#
# The positions come from outside:
#   kind="trail"     processing.find_moving_dot(frames)   where the dot IS
#   kind="expected"  processing.locate_in_frames(...)     where a known star SHOULD be
# Both give one dictionary per frame with x, y, ra_deg, dec_deg.
#
# One row per frame. Columns (COLUMNS below):
#   kind, frame (number in the frame list), obs_time (ISO text), detector,
#   wavelength_um, n_stacked, x, y (pixels, from 0, y from the bottom row),
#   ra_deg, dec_deg, ok, snr
#   ok = "true"/"false": for a trail, whether a dot was found; for an expected
#   path, whether the spot lies inside the frame. snr is only filled for a trail.
# Empty cell = not known.
#
# Only numbers and ISO dates are written, never text typed by a visitor, so a
# spreadsheet cannot mistake a cell for a formula.
# This file reads no files and downloads nothing.

import csv
import io
import math
import numbers

import numpy as np

KINDS = ("trail", "expected")

COLUMNS = ("kind", "frame", "obs_time", "detector", "wavelength_um", "n_stacked",
           "x", "y", "ra_deg", "dec_deg", "ok", "snr")


def _cell(value):
    """One value as CSV text: None / NaN / inf -> empty, floats rounded to 6 decimals."""
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if value else "false"
    if isinstance(value, numbers.Real):
        number = float(value)
        if not math.isfinite(number):
            return ""
        if isinstance(value, numbers.Integral):
            return str(int(value))
        return f"{number:.6f}".rstrip("0").rstrip(".") or "0"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_rows(kind, frames, positions):
    """One dictionary per frame, with the keys in COLUMNS.

    positions: one dictionary per frame (None allowed = position unknown).
    Raises ValueError for an unknown kind or lists of different length.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown kind '{kind}'. Choose one of: {', '.join(KINDS)}.")
    if len(frames) != len(positions):
        raise ValueError("There must be exactly one position for each frame.")
    rows = []
    for i, (frame, pos) in enumerate(zip(frames, positions)):
        pos = pos or {}
        rows.append({
            "kind": kind,
            "frame": i,
            "obs_time": frame.get("obs_time"),
            "detector": frame.get("detector"),
            "wavelength_um": frame.get("wavelength_um"),
            "n_stacked": frame.get("n_stacked", 1),
            "x": pos.get("x"), "y": pos.get("y"),
            "ra_deg": pos.get("ra_deg"), "dec_deg": pos.get("dec_deg"),
            "ok": pos.get("found") if kind == "trail" else pos.get("inside"),
            "snr": pos.get("snr") if kind == "trail" else None,
        })
    return rows


def to_csv_text(rows):
    """CSV text: a header line, then one line per row."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([_cell(row.get(name)) for name in COLUMNS])
    return buffer.getvalue()