# Future work

Ideas that are NOT built. They come from the project plan and from the "Known problems"
in PROGRESS.md.

## Ideas from the plan

- **Automatic mover detection, further.** `movers.py` only lists spots that differ from the
  fixed sky, frame by frame. Next: link the spots from frame to frame into tracks, ignore
  variable stars, use the real flags, and rank tracks. A very slow mover is lost in the
  median, so a user-placed starting point or the expected path may be needed.
- **A "report a find" button.** Let a visitor send the marked positions, dates and
  wavelengths (the CSV export is the first step) to a place where someone can check them.
- **A bigger sky-survey view.** Zoom out to a large field, or a map such as Aladin Lite
  (the challenge text suggests it), to pick a patch and see neighbours.

## Needed before real data works well (from Known problems)

- **Re-align frames onto one pixel grid.** Real cutouts differ by a pixel in size and by
  pointing. Difference, stack, trail, colour picture, movers and the GIF/CSV rely on one grid.
- **Download in parallel with retries, and pre-cache the 5 demo targets.** Real cutouts took
  13 to 27 seconds each in the first test, and one position has 258 images.
- **Default for many images.** `MAX_FRAMES` (50) is enforced only by the GIF so far.
  A default such as one detector at a time is still to be chosen.
- **Retest IRSA's TAP search** (asynchronous route) before dropping it; SIA is used for now
  and lags about a day.
- **Cache age.** Cached positions never expire after new weekly data.
- **Request limits** so one visitor cannot overload a public server.
- **Parallax.** Expected paths and overlay positions use straight-line proper motion only.
- **Flag meanings.** The real flag table categories are guesses; replace them with IRSA's
  Explanatory Supplement table.
- **"Is it real?" per detector.** Compare frames of the same detector, not only neighbours.
- **WISE proper motions.** Some AllWISE values look unreliable; check before moving
  overlay circles with them.
- **Retune every guessed number** on real data (stretch, thresholds, hit radius, field-of-view limits).
