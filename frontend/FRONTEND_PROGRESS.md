# Frontend Progress Log

## Current task

Tasks 1-32 are written (not yet tested in the browser). Task 15 and Task 33 are blocked (see Requests for backend). Task 25 (GIF) is being wired to /api/animation.gif.

## Done

- Task 1-14: see earlier log (skeleton, image, form, name search, player, counter/loop, keys/swipe, presets, URL, copy link, FOV, info panel, colour strip, spinner/errors). Written, not yet tested by me.
- Task 16: "Brightness curve" dropdown (linear, sqrt, log, asinh) sends `stretch=`. "Match background" checkbox sends `match=on/off`. Both reload the frames.
- Task 17: Normal / Difference / Stack buttons send `mode=`. Difference shows a "Subtract first/previous frame" choice (`ref=`). Stack shows "per detector / all together" (`group=`). The frame list is reloaded on every change, because stack mode changes the frame numbers. `combine=` is not offered (mean and sum give the same picture, see PROGRESS.md).
- Task 18: Blink compare: choose frame A and B, press Blink to flip between them every 0.4 s. Play, slider, arrows or Pause stop it.
- Task 19: Colour picture switch is shown but disabled (no endpoint).
- Task 20: `?embed=1` hides the header and the side controls. Settings still come from the URL.
- Task 21: Click the picture to place a marker circle. It is stored as RA/Dec and drawn in every frame at that same sky position. "Clear marker" removes it.
- Task 22: "Expected path" toggle (preset targets only) calls /api/expected-path and draws a dashed line plus a ring on the current frame. The page address now also has `target=<preset id>` (page only, never sent to /api/frames). "Motion trail" is shown but disabled (no endpoint).
- Task 23: Hover readout shows RA/Dec under the mouse. Brightness is not available (see requests).
- Task 24: Magnifier checkbox: a 3x lens follows the mouse (hidden on phones).
  Task 25: GIF button calls /api/animation.gif with the current settings and speed. A 400 (for example more than 50 frames) is shown in the status line.
- Task 26: "Download marker CSV" is made in the browser: one row per frame (date, detector, wavelength, marker RA/Dec). It is a fixed sky position, not a tracked object. The backend also has /api/export.csv (kind=trail or expected); the page does not use it yet.
- Task 27: "Coming later" panel reserves space for spectrum, flags legend and a disabled overlay toggle.
- Task 28: "Is it real?" row in the info panel: green = first frame or same detector and colour as the frame before; yellow = detector changed, or wavelength changed by more than 5 % (my guess). Red (flagged pixels) is not possible yet (no flags in the API).
- Task 29: Dark theme already there. Added phone rules (44 px tap targets, taller colour strip, lens hidden). Controls stack under the picture below 760 px.
  Task 30: favicon (inline emoji), page description, skip link, tooltips on buttons, aria-labels on the blink selects, "Reset view" button (puts mode, stretch, match, ref, group, FOV, marker, expected path and magnifier back to their starting values, then reloads), and an "Advanced tools" box (<details>, closed by default) around Blink, Tools, Save and Coming later. The "Is it real?" badge now has a symbol (✓ ▲ ✖) as well as a colour.
- Task 31: "How to spot a moving object" collapsible panel (plain HTML, 7 steps).
- Task 32: "Guided mission": 8 steps. Next runs an action (load WISE 0855, open Advanced tools, switch to Difference, switch to Normal and turn on Expected path). Back and Exit never change the page. Uses only existing API calls.

## In progress

- (nothing)

## Next step

Run the browser checklist, then wire Task 25. Task 15 and 33 wait for the backend.

## Decisions made

- Plain HTML + CSS + JS. No framework, library or CDN.
- Page address uses the API names (?ra=&dec=&fov=&stretch=&mode=&match=&ref=&group=) plus the page-only `target=` and `embed=1`.
- Marker, hover and lens maths assume north up and east left (API_GUIDE). The overlay uses the PNG's own pixel size, so png_x / png_y from the API are used as they are.
- The "Is it real?" wavelength limit (5 %) and blink speed (0.4 s) are my own choices.
- Disabled controls are shown (not hidden) so the layout stays the same when the backend work arrives.

## Requests for backend

- Name search endpoint (names.py has no URL). Until then the name box only finds the 5 presets.
- (Optional) One-box coordinates: a `name=` or `coords=` parameter.
- Task 15 (brightness slider): no parameter for the black/white level exists. Please add one (for example `clip_low` / `clip_high` or `brightness`) to /api/frames and the image links, with min/max/default in /api/limits.
- Task 19 (colour picture): an endpoint or `mode=colour` that returns the 3-wavelength PNG (functions exist in processing.py, no URL).
- Task 22 (motion trail):(the CSV endpoint with kind=trail gives the same positions as a file only).
- Task 23 (hover brightness): a way to read the value of one pixel (for example `/api/frames/{index}/pixel?x=&y=` with units).

- Task 28 (red state): per-frame flag info (Backend 29/30).
- Task 33 (practice game page): the practice frames are not served. Please add a way to get the practice set in the same format as /api/frames, and its PNG images, for example a `source=practice` parameter or a separate endpoint, WITHOUT exposing answers.json. Please also tell me whether `frame` in /api/practice/check is counted from 0 or from 1, and whether it matches the "index" in the frame list. I will build the practice game page only after this exists.

## Known problems

- With mock data only WISE 0855 returns frames; the other 4 presets give 404 and the page shows the server's message (expected). The expected-path toggle can only be tested with WISE 0855.
- On mock data the dot moves 10x faster than the real star, so the expected path only matches the dot in frame 0 (see PROGRESS.md).
- The mock frames have different wavelengths per frame, so the "Is it real?" badge may often be yellow on mock data.
- The marker is a fixed sky position, so it does not follow a moving object.
- The copy-link button may be blocked outside https/localhost.
- Swipe, keyboard, magnifier and the phone layout are not tested on a real phone / screen reader.
- A tap on a phone places a marker; a swipe should not, but check this.
- Wavelength strip with 258 real frames will have very thin blocks.
- The marker tool is mouse/touch only. There is no keyboard way to place a marker yet.
- The mission's Back button does not undo what a step did.
- The mission only works for WISE 0855, and on mock data the dot moves 10x faster than the real star, so the expected-path step says the line only matches in frame 0.
- Screen-reader support is based on labels and live regions only; not tested with a real screen reader.

## How to run and test

- Backend: venv active, python data_mock.py (once), python cache.py clear, uvicorn main:app --reload
- Open http://127.0.0.1:8000/
