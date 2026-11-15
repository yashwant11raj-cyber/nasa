# Backend addresses for the frontend

All settings go in the URL: ra, dec, fov (arcmin), stretch, mode, match, ref, combine, group.
Every error is JSON: {"detail": "a sentence you can show"}.

- GET /api/targets?year=2026 the 5 preset buttons (use year=2026 positions)
- GET /api/limits min / max / default FOV
- GET /api/frames frame list (image_url, date, detector, wavelength, pixel scale, centre)
- GET /api/frames/{i}/image one frame as a PNG
- GET /api/animation.gif whole animation as a download
- GET /api/export.csv positions per frame as a CSV (kind=trail or expected)
- GET /api/expected-path where a preset target should be in each frame
- GET /api/practice/check practice game: is a click on a hidden mover?

Not connected yet: name search, spectra, flags, overlays, "Is it real?", colour picture.

Warning: real data will differ from the mock data.

- One position can return about 258 frames, not 12 (we will add a default limit).
- Each request will be slow (many seconds), so the page needs a loading state and a retry.
- Frame sizes and pointing may differ by a pixel.
- Frame numbers change when mode changes (stack gives fewer frames), so reload the list when mode changes.
