# main.py
# The web server (FastAPI). Start it with:   uvicorn main:app --reload
# Then open  http://127.0.0.1:8000/docs  to try the endpoints in your browser.
#
# Jobs:
#   GET /api/resolve?name=..                                 a target name -> RA/Dec (JSON)
#   GET /api/trail?...                                       where the moving dot is in each frame (JSON)
#   GET /api/limits                                          field-of-view limits (JSON)
#   GET /api/targets?year=..                                 the 5 preset targets (JSON)
#   GET /api/frames?ra=..&dec=..&fov=..&mode=..&stretch=..&match=..   list of frames (JSON)
#   GET /api/frames/{index}/image?...                        one frame as a PNG picture
#   GET /api/animation.gif?...&speed_ms=..                   all frames as one animated GIF (download)
#   GET /api/export.csv?...&kind=trail|expected&target=..    positions per frame as a CSV file (download)
#   everything else                                          files from the static/ folder
#
# Backend 11: every setting in the address is checked by params.py first.
# A bad value gives a clear message (HTTP 400) instead of a crash.
# Backend 19: mode=stack adds frames together, so the list can be shorter
# than the number of raw images (for example one frame per detector).
#
# main.py only connects the other files. The real work is done elsewhere:
#   params.py -> checks the address,  data_mock.py -> frames,
#   cache.py -> saves them,  processing.py -> PNG.

from pathlib import Path
from urllib.parse import urlencode
import logging
import math

import numpy as np
from astropy.wcs.utils import proj_plane_pixel_scales
from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import cache
import config
import coords
import data_mock
import errors
import export_csv
import gif_export
import names
import params
import practice_check
import processing
import targets

app = FastAPI(title="SPHEREx Sky Viewer")

logger = logging.getLogger("uvicorn.error")   # prints into the terminal where uvicorn runs


# Backend 14: every error leaves the server as {"detail": "a friendly sentence"}.

@app.exception_handler(RequestValidationError)
async def handle_validation_error(request, exc):
    """A setting is missing or has the wrong type (for example a missing ra)."""
    return JSONResponse(status_code=422,
                        content={"detail": errors.validation_message(exc.errors())})


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request, exc):
    """Our own HTTPException messages pass through; stock wording is replaced."""
    detail = errors.friendly_http_detail(exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail},
                        headers=getattr(exc, "headers", None))


@app.exception_handler(Exception)
async def handle_unexpected_error(request, exc):
    """Anything we did not expect. Details go to the terminal, not to the visitor."""
    logger.error("Unexpected error on %s", request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": errors.SERVER_ERROR_MESSAGE})


STATIC_DIR = Path(__file__).parent / "frontend"

# Text shown in the /docs page for the settings
RA_HELP = "Right ascension. Degrees (133.8) or hours (08h55m10.8s, 08:55:10.8)."
DEC_HELP = "Declination. Degrees (-7.2) or -07d14m42s, -07:14:42."
FOV_HELP = f"Field of view in arcminutes, {config.MIN_FOV_ARCMIN:g} to {config.MAX_FOV_ARCMIN:g}. Default {config.DEFAULT_FOV_ARCMIN:g}."
STRETCH_HELP = "Brightness stretch: " + ", ".join(processing.STRETCH_MODES) + f". Default {params.DEFAULT_STRETCH}."
MODE_HELP = "How frames are combined: " + ", ".join(params.READY_MODES) + f". Default {params.DEFAULT_MODE}."
YEAR_HELP = "Optional year, for example 2026.0. Positions are moved to that year using proper motion. Empty = J2000."
MATCH_HELP = "Background matching: on or off. Default off. On = every frame gets the same background level and brightness scale."
REF_HELP = "Only for mode=difference: which frame is subtracted: " + ", ".join(processing.DIFFERENCE_REFERENCES) + f". Default {params.DEFAULT_REF}."
COMBINE_HELP = "Only for mode=stack: how frames are combined: " + ", ".join(processing.STACK_COMBINE) + f". Default {params.DEFAULT_COMBINE}."
GROUP_HELP = "Only for mode=stack: which frames are stacked together: " + ", ".join(processing.STACK_GROUPS) + f". Default {params.DEFAULT_GROUP}."


def check_request(ra, dec, fov, stretch, mode, match=None, ref=None, combine=None, group=None):
    """Check the settings from the address. Bad input becomes a clear HTTP 400."""
    try:
        return params.validate_request(ra, dec, fov, stretch, mode, match, ref, combine, group)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


def frames_for(p):
    """Get the frames for one request: from the cache, or from the data source."""
    if not config.USE_MOCK:
                # data_irsa.py is only a skeleton so far (Backend 25); real code comes after-data #2-#4
        raise HTTPException(
            status_code=501,
            detail="Real SPHEREx data is not connected yet. Set USE_MOCK = True in config.py.")
    try:
        frames = cache.get_or_load(p.ra, p.dec, p.fov, data_mock.get_frames)
    except FileNotFoundError as err:        # mock files were never created
        raise HTTPException(status_code=503, detail=str(err))
    except TimeoutError:                    # a slow data source (used by real data later)
        raise HTTPException(status_code=504, detail=errors.TIMEOUT_MESSAGE)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not frames:
        raise HTTPException(status_code=404,
                            detail=errors.no_images_message(p.ra, p.dec, config.USE_MOCK))
    return frames


def stack_for(frames, p):
    """Backend 19: add or average the frames (mode=stack). Bad input becomes HTTP 400."""
    try:
        return processing.stack_frames(frames, p.combine, p.group)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


def describe_frame(index, frame, p):
    """Turn one frame into a small dictionary that can be sent as JSON."""
    height, width = frame["image"].shape
    wcs = frame["wcs"]

    # Pixel scale: how many arcseconds one pixel covers (mean of the two axes)
    pixel_scale_arcsec = float(np.mean(proj_plane_pixel_scales(wcs))) * 3600.0
    # Sky position of the middle of this cutout (pixel numbers start at 0)
    centre_ra, centre_dec = wcs.pixel_to_world_values((width - 1) / 2, (height - 1) / 2)

    # The link repeats every setting, in plain numbers, so it works on its own
    query = urlencode({"ra": p.ra, "dec": p.dec, "fov": p.fov, "mode": p.mode,
                       "stretch": p.stretch, "match": "on" if p.match else "off",
                       "ref": p.ref, "combine": p.combine, "group": p.group})
    return {
        "index": index,
        "image_url": f"/api/frames/{index}/image?{query}",
        "obs_time": frame["obs_time"].isoformat(),
        "detector": int(frame["detector"]),       # 0 = several detectors stacked together
        "wavelength_um": float(frame["wavelength_um"]),
        "n_stacked": int(frame.get("n_stacked", 1)),
        "width_px": int(width),
        "height_px": int(height),
        "pixel_scale_arcsec": pixel_scale_arcsec,
        "center_ra_deg": float(centre_ra),
        "center_dec_deg": float(centre_dec),
    }


@app.get("/api/frames")
def list_frames(
    ra: str = Query(..., description=RA_HELP),
    dec: str = Query(..., description=DEC_HELP),
    fov: str | None = Query(None, description=FOV_HELP),
    stretch: str | None = Query(None, description=STRETCH_HELP),
    mode: str | None = Query(None, description=MODE_HELP),
    match: str | None = Query(None, description=MATCH_HELP),
    ref: str | None = Query(None, description=REF_HELP),
    combine: str | None = Query(None, description=COMBINE_HELP),
    group: str | None = Query(None, description=GROUP_HELP),
):
    """The frame list: one entry per image, sorted by date."""
    p = check_request(ra, dec, fov, stretch, mode, match, ref, combine, group)
    frames = frames_for(p)
    if p.mode == "stack":
        frames = stack_for(frames, p)           # fewer, less noisy frames
    return {
        "source": cache.current_release(),
        "ra_deg": p.ra,
        "dec_deg": p.dec,
        "fov_arcmin": p.fov,
        "stretch": p.stretch,
        "mode": p.mode,
        "match": p.match,
        "ref": p.ref,
        "combine": p.combine,
        "group": p.group,
        "frame_count": len(frames),
        "frames": [describe_frame(i, f, p) for i, f in enumerate(frames)],
    }


@app.get("/api/frames/{index}/image")
def frame_image(
    index: int,
    ra: str = Query(..., description=RA_HELP),
    dec: str = Query(..., description=DEC_HELP),
    fov: str | None = Query(None, description=FOV_HELP),
    stretch: str | None = Query(None, description=STRETCH_HELP),
    mode: str | None = Query(None, description=MODE_HELP),
    match: str | None = Query(None, description=MATCH_HELP),
    ref: str | None = Query(None, description=REF_HELP),
    combine: str | None = Query(None, description=COMBINE_HELP),
    group: str | None = Query(None, description=GROUP_HELP),
):
    """One frame as a PNG picture. `index` is the number from the frame list."""
    p = check_request(ra, dec, fov, stretch, mode, match, ref, combine, group)
    frames = frames_for(p)                      # instant when it is already cached
    if p.match:
        frames = processing.match_backgrounds(frames)
    if p.mode == "stack":
        frames = stack_for(frames, p)           # backgrounds are matched first, then stacked
    if index < 0 or index >= len(frames):
        raise HTTPException(status_code=404,
                            detail=f"There is no frame {index}. This request has {len(frames)} frames.")

    if p.mode == "difference":
        # Subtract the reference frame, then draw with one shared scale:
        # grey = no change, white = brighter, black = dimmer.
        try:
            frames = processing.difference_frames(frames, p.ref)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err))
        limit = processing.shared_difference_limit(frames)
        grey = processing.stretch_difference(frames[index]["image"], mode=p.stretch, limit=limit)
    else:
        # normal and stack
        limits = processing.shared_limits(frames) if p.match else None
        grey = processing.stretch_image(frames[index]["image"], mode=p.stretch, limits=limits)
    return Response(content=processing.image_to_png_bytes(grey), media_type="image/png")

TARGET_HELP = "Which preset target to follow: its id or name, for example wise0855."


@app.get("/api/expected-path")
def expected_path(
    target: str = Query(..., description=TARGET_HELP),
    ra: str = Query(..., description=RA_HELP),
    dec: str = Query(..., description=DEC_HELP),
    fov: str | None = Query(None, description=FOV_HELP),
    mode: str | None = Query(None, description=MODE_HELP),
    combine: str | None = Query(None, description=COMBINE_HELP),
    group: str | None = Query(None, description=GROUP_HELP),
):
    """Where the target should be in each frame, from its proper motion.

    Use the same ra, dec, fov, mode, combine and group as /api/frames, so
    entry number N here belongs to frame number N there.
    """
    p = check_request(ra, dec, fov, None, mode, None, None, combine, group)
    found = names.resolve_local(target)          # tolerant spelling, works offline
    if found is None:
        labels = ", ".join(t["label"] for t in targets.TARGETS.values())
        raise HTTPException(status_code=400,
                            detail=f"'{target}' is not one of the built-in targets ({labels}).")
    frames = frames_for(p)
    if p.mode == "stack":
        frames = stack_for(frames, p)            # same frame numbers as /api/frames
    positions = targets.expected_positions(found.target_id, [f["obs_time"] for f in frames])
    path = processing.locate_in_frames(frames, positions)
    for entry in path:
        entry["obs_time"] = entry["obs_time"].isoformat()
    return {
        "target": {"id": found.target_id, "label": found.label},
        "mode": p.mode,
        "frame_count": len(frames),
        "path": path,
    }

@app.get("/api/trail")
def trail(
    ra: str = Query(..., description=RA_HELP),
    dec: str = Query(..., description=DEC_HELP),
    fov: str | None = Query(None, description=FOV_HELP),
    mode: str | None = Query(None, description=MODE_HELP),
    combine: str | None = Query(None, description=COMBINE_HELP),
    group: str | None = Query(None, description=GROUP_HELP),
):
    """Where the moving dot is in each frame (processing.find_moving_dot).

    Use the same ra, dec, fov, mode, combine and group as /api/frames, so
    entry number N here belongs to frame number N there.
    """
    p = check_request(ra, dec, fov, None, mode, None, None, combine, group)
    frames = frames_for(p)
    if p.mode == "stack":
        frames = stack_for(frames, p)            # same frame numbers as /api/frames
    try:
        found = processing.find_moving_dot(frames)
    except ValueError as err:                    # fewer than 3 frames, or frames of different sizes
        raise HTTPException(status_code=400, detail=str(err))
    keys = ("index", "found", "x", "y", "png_x", "png_y", "ra_deg", "dec_deg", "snr")
    entries = []
    for item in found:
        entry = {k: item[k] for k in keys}
        entry["obs_time"] = item["obs_time"].isoformat()
        entries.append(entry)
    return {"mode": p.mode, "frame_count": len(frames), "trail": entries}

def grey_pictures(p):
    """ALL frames of one request as grey arrays (same steps as the image endpoint,
    so a GIF frame looks exactly like the PNG of that frame)."""
    frames = frames_for(p)
    if p.match:
        frames = processing.match_backgrounds(frames)
    if p.mode == "stack":
        frames = stack_for(frames, p)
    if p.mode == "difference":
        try:
            frames = processing.difference_frames(frames, p.ref)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err))
        limit = processing.shared_difference_limit(frames)
        return [processing.stretch_difference(f["image"], mode=p.stretch, limit=limit) for f in frames]
    limits = processing.shared_limits(frames) if p.match else None
    return [processing.stretch_image(f["image"], mode=p.stretch, limits=limits) for f in frames]


SPEED_HELP = (f"Time each frame is shown, in milliseconds, {gif_export.MIN_DURATION_MS} to "
              f"{gif_export.MAX_DURATION_MS}. Default {gif_export.DEFAULT_DURATION_MS}.")
KIND_HELP = ("Which positions to export: " + ", ".join(export_csv.KINDS) +
             ". trail = where the moving dot is found; expected = where a preset target should be (needs target).")


@app.get("/api/animation.gif")
def animation_gif(
    ra: str = Query(..., description=RA_HELP),
    dec: str = Query(..., description=DEC_HELP),
    fov: str | None = Query(None, description=FOV_HELP),
    stretch: str | None = Query(None, description=STRETCH_HELP),
    mode: str | None = Query(None, description=MODE_HELP),
    match: str | None = Query(None, description=MATCH_HELP),
    ref: str | None = Query(None, description=REF_HELP),
    combine: str | None = Query(None, description=COMBINE_HELP),
    group: str | None = Query(None, description=GROUP_HELP),
    speed_ms: int = Query(gif_export.DEFAULT_DURATION_MS, description=SPEED_HELP),
):
    """Every frame of the request as one animated GIF that loops forever."""
    p = check_request(ra, dec, fov, stretch, mode, match, ref, combine, group)
    try:
        gif_export.check_duration(speed_ms)
        data = gif_export.greys_to_gif_bytes(grey_pictures(p), speed_ms)
    except ValueError as err:                    # bad speed, or more frames than MAX_FRAMES
        raise HTTPException(status_code=400, detail=str(err))
    name = f"spherex_{p.ra:.4f}_{p.dec:+.4f}.gif"
    return Response(content=data, media_type="image/gif",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/export.csv")
def export_csv_file(
    ra: str = Query(..., description=RA_HELP),
    dec: str = Query(..., description=DEC_HELP),
    fov: str | None = Query(None, description=FOV_HELP),
    mode: str | None = Query(None, description=MODE_HELP),
    combine: str | None = Query(None, description=COMBINE_HELP),
    group: str | None = Query(None, description=GROUP_HELP),
    kind: str = Query("trail", description=KIND_HELP),
    target: str | None = Query(None, description=TARGET_HELP + " Only for kind=expected."),
):
    """One row per frame (same numbering as /api/frames) as a CSV file."""
    p = check_request(ra, dec, fov, None, mode, None, None, combine, group)
    kind = kind.strip().lower()
    if kind not in export_csv.KINDS:
        raise HTTPException(status_code=400,
                            detail=f"Unknown kind '{kind}'. Choose one of: {', '.join(export_csv.KINDS)}.")
    found = None
    if kind == "expected":
        if target is None or not target.strip():
            raise HTTPException(status_code=400, detail="kind=expected needs a target, for example target=wise0855.")
        found = names.resolve_local(target)
        if found is None:
            labels = ", ".join(t["label"] for t in targets.TARGETS.values())
            raise HTTPException(status_code=400,
                                detail=f"'{target}' is not one of the built-in targets ({labels}).")
    frames = frames_for(p)
    if p.mode == "stack":
        frames = stack_for(frames, p)            # same frame numbers as /api/frames
    try:
        if kind == "trail":
            positions = processing.find_moving_dot(frames)
        else:
            expected = targets.expected_positions(found.target_id, [f["obs_time"] for f in frames])
            positions = processing.locate_in_frames(frames, expected)
        text = export_csv.to_csv_text(export_csv.build_rows(kind, frames, positions))
    except ValueError as err:                    # for example fewer than 3 frames for a trail
        raise HTTPException(status_code=400, detail=str(err))
    name = f"spherex_{kind}_{p.ra:.4f}_{p.dec:+.4f}.csv"
    return Response(content=text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})

NAME_HELP = ("A target name, for example Barnard's Star or WISE 0855. The 5 built-in targets work "
             "offline. Other names use the online lookup (CDS), which may be down.")
NAME_MAX_CHARS = 100
RESOLVE_YEAR = 2026.0     # same year the page uses for /api/targets?year=2026


def resolve_name_address(name):
    """Turn a typed name into a position. Plain function, so tests can call it without a server."""
    if name is None or not name.strip():
        raise HTTPException(status_code=400, detail="Please type a name, for example: Barnard's Star")
    if len(name) > NAME_MAX_CHARS:
        raise HTTPException(status_code=400,
                            detail=f"The name is too long (at most {NAME_MAX_CHARS} characters).")
    try:
        result = names.resolve_name(name, year=RESOLVE_YEAR)
    except names.NameSearchError as err:
        raise HTTPException(status_code=404, detail=str(err))
    return {
        "ra_deg": result.ra,
        "dec_deg": result.dec,
        "label": result.label,
        "source": result.source,          # "local" (5 built-in targets) or "online"
        "target_id": result.target_id,    # preset id for local results, else None
    }


@app.get("/api/resolve")
def resolve(name: str = Query(..., description=NAME_HELP)):
    """Name -> RA/Dec in degrees. Local targets are moved to 2026.0 with proper motion,
    so they match /api/targets?year=2026. Online results are what the service gives."""
    return resolve_name_address(name)

@app.get("/api/targets")
def list_targets(year: str | None = Query(None, description=YEAR_HELP)):
    """The 5 preset targets, for the page's preset buttons."""
    epoch = None
    if year is not None and year.strip():
        try:
            epoch = float(year.strip())
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"The year '{year}' is not a number. Use for example year=2026.")
        if not (math.isfinite(epoch) and 1900 <= epoch <= 2100):
            raise HTTPException(status_code=400,
                                detail="The year must be between 1900 and 2100.")
    items = targets.target_list(epoch)
    return {
        "epoch": "J2000" if epoch is None else epoch,
        "count": len(items),
        "targets": items,
    }

@app.get("/api/practice/check")
def practice_check_click(
    ra: str = Query(..., description="RA of the click. " + RA_HELP),
    dec: str = Query(..., description="Dec of the click. " + DEC_HELP),
    frame: int = Query(..., description="Frame number the click was made on (0 = first)."),
):
    """Practice game: is the clicked position on a hidden mover in that frame?

    Answers only hit or miss (and which mover on a hit), never the answers themselves.
    """
    try:
        ra_deg = coords.parse_ra(ra)
        dec_deg = coords.parse_dec(dec)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    try:
        return practice_check.check_click(ra_deg, dec_deg, frame)
    except FileNotFoundError as err:               # data_practice.py was never run
        raise HTTPException(status_code=503, detail=str(err))
    except ValueError as err:                      # no such frame number
        raise HTTPException(status_code=404, detail=str(err))

@app.get("/api/limits")
def get_limits():
    """The field-of-view limits, so the page can build its FOV control."""
    return {
        "fov_arcmin": {
            "min": config.MIN_FOV_ARCMIN,
            "max": config.MAX_FOV_ARCMIN,
            "default": config.DEFAULT_FOV_ARCMIN,
        },
    }


# Serve the web page files. This MUST stay last, because it matches every other address.
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")