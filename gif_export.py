# gif_export.py
# Backend 34: turns a list of grey pictures into ONE animated GIF (bytes).
#
# The pictures are the same uint8 grey arrays that the image endpoint turns into
# PNGs (0 = black, 255 = white). Each one goes through
# processing.image_to_png_bytes, so every GIF frame is flipped (north up) and
# enlarged exactly like the PNG on the page.
#
# This file makes no pictures itself and downloads nothing. main.py decides
# WHICH pictures to send (GET /api/animation.gif).
#
# Notes:
#   - A GIF has only 256 grey levels, which is exactly what our pictures have.
#   - The number of frames is capped by config.MAX_FRAMES, so one visitor
#     cannot ask for a huge file.
#   - Pillow may merge two identical frames that follow each other into one
#     (it adds their times together), so the GIF can have fewer frames than
#     pictures. The animation still plays for the same total time.

import io

from PIL import Image

import config
import processing

MIN_DURATION_MS = 20       # smaller values are not reliably shown by browsers (a guess)
MAX_DURATION_MS = 5000     # 5 seconds per frame is already very slow
DEFAULT_DURATION_MS = 200  # 5 frames per second


def check_duration(duration_ms):
    """Return the time per frame (milliseconds) or raise a friendly ValueError."""
    if (isinstance(duration_ms, bool) or not isinstance(duration_ms, int)
            or not MIN_DURATION_MS <= duration_ms <= MAX_DURATION_MS):
        raise ValueError(f"The time per frame must be a whole number of milliseconds "
                         f"from {MIN_DURATION_MS} to {MAX_DURATION_MS}.")
    return duration_ms


def greys_to_gif_bytes(greys, duration_ms=DEFAULT_DURATION_MS,
                       max_frames=None, target_size=400):
    """Make an animated GIF (as bytes) that loops forever.

    greys:        list of 2D uint8 arrays (see processing.stretch_image).
    duration_ms:  time each frame is shown.
    max_frames:   None = config.MAX_FRAMES.
    Raises ValueError for an empty list, too many frames or a bad duration.
    """
    check_duration(duration_ms)
    limit = config.MAX_FRAMES if max_frames is None else max_frames
    if not greys:
        raise ValueError("There are no frames to put in a GIF.")
    if len(greys) > limit:
        raise ValueError(f"This request has {len(greys)} frames, but a GIF may have at most {limit}. "
                         f"Try mode=stack, or a smaller field of view.")

    pictures = []
    for grey in greys:
        png = processing.image_to_png_bytes(grey, target_size)
        pictures.append(Image.open(io.BytesIO(png)).convert("L"))

    buffer = io.BytesIO()
    pictures[0].save(buffer, format="GIF", save_all=True, append_images=pictures[1:],
                     duration=duration_ms, loop=0)
    return buffer.getvalue()