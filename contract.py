# contract.py
# After-data #6: the frame contract in code. Mock frames and real frames must look
# IDENTICAL to everything after them (processing, stack, trail, flags, spectra ...).
# FRAME_FORMAT.md describes the contract in words; this file checks it.
#
#   frame_problems(frame)       list of plain sentences, empty = the frame is fine
#   list_problems(frames)       the same for a whole list, plus "sorted by obs_time"
#   type_signature(frame)       key -> (type, dtype, ndim): to compare two sources
#
# Rules (FRAME_FORMAT.md, "Extra rules found in the real files"):
#   keys           exactly the 8 FRAME_KEYS (a stacked frame may also have n_stacked)
#   image          2D numpy array, float64, native byte order
#   wcs            not None, and it must be able to convert pixels and sky positions
#                  (checked by the two methods the project uses, so it needs no astropy)
#   obs_time       datetime WITHOUT a timezone
#   wavelength_um  a finite float above zero
#   detector       a plain int, 1 to 6 (0 for a stack of several detectors)
#   flags          None, or a 2D int32 array (native) of the same shape as image
#   variance       None, or a 2D float64 array (native) of the same shape as image
#   source_file    text
# This file reads no files and downloads nothing.

from datetime import datetime

import numpy as np

FRAME_KEYS = ("image", "wcs", "obs_time", "wavelength_um", "detector",
              "flags", "variance", "source_file")
STACK_KEYS = ("n_stacked",)          # extra key made by processing.stack_frames


def _array_problem(name, value, kind, shape=None):
    """A sentence if `value` is not a 2D native array of this kind, else None."""
    if not isinstance(value, np.ndarray):
        return f"{name} must be a numpy array (it is {type(value).__name__})."
    if value.ndim != 2:
        return f"{name} must be 2D (it has {value.ndim} dimensions)."
    if not value.dtype.isnative:
        return f"{name} must be in native byte order (it is {value.dtype})."
    if kind == "float64" and value.dtype != np.dtype("float64"):
        return f"{name} must be float64 (it is {value.dtype})."
    if kind == "int32" and value.dtype != np.dtype("int32"):
        return f"{name} must be int32 (it is {value.dtype})."
    if shape is not None and value.shape != shape:
        return f"{name} has shape {value.shape} but image has shape {shape}."
    return None


def frame_problems(frame, allow_stacked=False):
    """List of sentences that say what is wrong with one frame (empty = fine)."""
    problems = []
    if not isinstance(frame, dict):
        return [f"A frame must be a dictionary (it is {type(frame).__name__})."]
    allowed = set(FRAME_KEYS) | (set(STACK_KEYS) if allow_stacked else set())
    missing = [k for k in FRAME_KEYS if k not in frame]
    extra = [k for k in frame if k not in allowed]
    if missing:
        problems.append(f"Missing keys: {', '.join(missing)}.")
    if extra:
        problems.append(f"Unexpected keys: {', '.join(sorted(extra))}.")

    image = frame.get("image")
    if "image" in frame:
        found = _array_problem("image", image, "float64")
        if found:
            problems.append(found)
    shape = image.shape if isinstance(image, np.ndarray) and image.ndim == 2 else None

    if "wcs" in frame:
        wcs = frame["wcs"]
        if wcs is None or not (hasattr(wcs, "wcs_world2pix") and hasattr(wcs, "pixel_to_world_values")):
            problems.append("wcs must be a WCS object (it is "
                            f"{type(wcs).__name__}).")

    if "obs_time" in frame:
        when = frame["obs_time"]
        if not isinstance(when, datetime):
            problems.append(f"obs_time must be a datetime (it is {type(when).__name__}).")
        elif when.tzinfo is not None:
            problems.append("obs_time must be naive UTC (no timezone).")

    if "wavelength_um" in frame:
        wave = frame["wavelength_um"]
        if isinstance(wave, bool) or not isinstance(wave, (float, np.floating)):
            problems.append(f"wavelength_um must be a float (it is {type(wave).__name__}).")
        elif not (np.isfinite(wave) and wave > 0):
            problems.append(f"wavelength_um must be a finite number above zero (it is {wave}).")

    if "detector" in frame:
        det = frame["detector"]
        low = 0 if allow_stacked else 1
        if type(det) is not int:
            problems.append(f"detector must be a plain int (it is {type(det).__name__}).")
        elif not low <= det <= 6:
            problems.append(f"detector must be from {low} to 6 (it is {det}).")

    for name, kind in (("flags", "int32"), ("variance", "float64")):
        if name in frame and frame[name] is not None:
            found = _array_problem(name, frame[name], kind, shape)
            if found:
                problems.append(found)

    if "source_file" in frame and not isinstance(frame["source_file"], str):
        problems.append(f"source_file must be text (it is {type(frame['source_file']).__name__}).")
    return problems


def list_problems(frames, allow_stacked=False):
    """Problems of every frame (prefixed 'frame N: ') plus the time order of the list."""
    problems = []
    for i, frame in enumerate(frames):
        problems.extend(f"frame {i}: {p}" for p in frame_problems(frame, allow_stacked))
    times = [f["obs_time"] for f in frames
             if isinstance(f, dict) and isinstance(f.get("obs_time"), datetime) and f["obs_time"].tzinfo is None]
    if times != sorted(times):
        problems.append("The frames are not sorted by obs_time.")
    return problems


def type_signature(frame):
    """Key -> (type name, dtype or None, number of dimensions or None).

    Two data sources follow the same contract when their signatures are equal.
    The shape is left out on purpose: real cutouts differ by a pixel.
    """
    signature = {}
    for key in FRAME_KEYS:
        value = frame.get(key)
        if isinstance(value, np.ndarray):
            signature[key] = ("ndarray", str(value.dtype), value.ndim)
        elif key == "wcs":
            signature[key] = ("wcs" if value is not None else "None", None, None)
        else:
            signature[key] = (type(value).__name__, None, None)
    return signature