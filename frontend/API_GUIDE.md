# API guide for the frontend (written from main.py, params.py, errors.py)

Base: same origin as the page (http://127.0.0.1:8000). Full interactive docs: /docs.

## Rules that apply everywhere

- Every error is JSON {"detail": "a friendly sentence"}. Show `detail` directly.
- Status codes: 400 bad value, 404 no images / no such frame, 405 wrong method,
  422 missing setting, 500 crash, 501 real data not connected, 503 mock files
  missing, 504 data source too slow.
- RA/Dec accept plain degrees or sexagesimal text (08h55m10.8s, -07d14m42s).
  A "+" in a URL means a space, so encode it as %2B (use URLSearchParams).
- FOV is in ARCMINUTES. Get min/max/default from /api/limits, never hardcode.

## Endpoints

1. GET /api/limits
   -> {"fov_arcmin": {"min", "max", "default"}} (use for the FOV control)

2. GET /api/targets?year=2026
   -> {"epoch", "count", "targets": [{id, label, simbad_name, ra_deg, dec_deg,
   ra_j2000_deg, dec_j2000_deg, pmra_mas_yr, pmdec_mas_yr, note}]}
   Use year=2026 so the preset positions match when SPHEREx observed.

3. GET /api/frames?ra=&dec=&fov=&stretch=&mode=&match=&ref=&combine=&group=
   Only ra and dec are required.
   - stretch: linear | sqrt | log | asinh (default sqrt)
   - mode: normal | difference | stack (default normal)
   - match: on | off (default off)
   - ref: first | previous (only for mode=difference)
   - combine: mean | sum, group: detector | all (only for mode=stack)
     -> {source, ra_deg, dec_deg, fov_arcmin, stretch, mode, match, ref, combine,
     group, frame_count, frames: [{index, image_url, obs_time, detector,
     wavelength_um, n_stacked, width_px, height_px, pixel_scale_arcsec,
     center_ra_deg, center_dec_deg}]}
   - `image_url` is a ready-to-use link. Put it in <img src>. Do not build it yourself.
   - In mode=stack the list is the STACKED list (6 frames on mock data), so
     frame numbers change: reload the list whenever mode/group/combine changes.
   - detector 0 means "several detectors stacked".

4. GET /api/frames/{index}/image?...same settings... -> PNG (north up, ~400 px)

5. GET /api/expected-path?target=&ra=&dec=&fov=&mode=&combine=&group=
   target must be one of the 5 presets (id or name, e.g. wise0855).
   -> {target, mode, frame_count, path: [{index, obs_time, ra_deg, dec_deg,
   x, y, png_x, png_y, inside}]}
   png_x/png_y are in PNG pixels from the top-left: draw the marker there.
   Use the same ra/dec/fov/mode/combine/group as /api/frames.

6. GET /api/practice/check?ra=&dec=&frame=
   -> {hit, mover_id, label, frame, radius_arcsec, movers_total}

7. GET /api/animation.gif?ra=&dec=&fov=&stretch=&mode=&match=&ref=&combine=&group=&speed_ms=
   -> an animated GIF file (download). speed_ms is 20 to 5000 (default 200).
   More than 50 frames gives 400 with a message suggesting mode=stack.

8. GET /api/export.csv?ra=&dec=&fov=&mode=&combine=&group=&kind=&target=
   -> a CSV file (download). kind=trail (default) finds the moving dot
   automatically (needs at least 3 frames on the same grid).
   kind=expected needs target=<preset id> (e.g. wise0855).
   Columns: kind, frame, obs_time, detector, wavelength_um, n_stacked, x, y,
   ra_deg, dec_deg, ok, snr. Empty cell = unknown.

9. GET /api/trail?ra=&dec=&fov=&mode=&combine=&group=
   Same ra/dec/fov/mode/combine/group as /api/frames, so entry N belongs to frame N.
   -> {mode, frame_count, trail: [{index, obs_time, found, x, y, png_x, png_y,
   ra_deg, dec_deg, snr}]}
   found=false means no dot was found in that frame: x, y, png_x, png_y, ra_deg
   and dec_deg are then null (skip it when drawing). png_x/png_y are in PNG pixels
   from the top-left, like /api/expected-path. Needs at least 3 frames, otherwise 400.
   In mode=difference the trail is worked out on the raw frames.

10. GET /api/resolve?name=
    -> {ra_deg, dec_deg, label, source, target_id}
    source is "local" (one of the 5 presets, works offline, position at 2026.0 like
    /api/targets?year=2026, target_id is the preset id) or "online" (CDS lookup,
    may be down or slow, target_id is null, label is the text that was typed).
    Use ra_deg/dec_deg as ra/dec for /api/frames. The expected path only works when
    target_id is not null (pass it as target=). Show label with textContent.
    Errors: 400 empty or longer than 100 characters, 404 name not found or the online
    service is down (show detail), 422 name missing.

11. GET /api/flags?ra=&dec=&fov=&mode=&combine=&group=
    Same ra/dec/fov/mode/combine/group as /api/frames, so entry N belongs to frame N.
    -> {mode, frame_count, frames: [{index, status, reasons, detector_changed,
    wavelength_changed, flagged_names, flag_counts, bad_fraction,
    contaminated_fraction}], legend: [{bit, value, name, description, category}]}
    status is "green", "yellow", "red" or "grey" (grey = could not check).
    reasons is a list of {code, message}: show message as a tooltip (textContent).
    flag_counts is {flag name: pixel count}; bad_fraction and
    contaminated_fraction are 0 to 1. They are null when a frame has no flags.
    legend explains every flag name (category: bad, contaminated or info).
    Needs no minimum frame count: with fewer than 3 frames the status comes
    only from detector/wavelength changes (yellow) or is grey.

## NOT available yet (do not build against these)

- Colour picture: function exists, no endpoint.
- Spectrum, overlays: no endpoints. (flags and “is it real?” now exist).
- Practice game frames: practice files are not served (only /api/practice/check works).
- Brightness clip levels (black/white point): no parameter.

## Current data situation (Backend 25-27)

- config.USE_MOCK = True: only the WISE 0855 preset (year-2026 position) returns
  frames. The other 4 presets give 404. This is expected; show the detail message.
- USE_MOCK = False currently gives 501 "Real data is not connected yet".
- `source` in /api/frames is the cache label ("mock" now, later the release name).
  Show it in the info panel.
- Real data will differ (Backend 26 findings): ~258 images per position
  (not 12), cutouts differ by a pixel in size, each download takes 13-27 s,
  and wavelength varies per frame. So the page will later need progress text,
  a frame limit and retry (Frontend Section 4, tasks 6-7).
- Hover/marker maths assume north up and east left. Recheck on real data.
