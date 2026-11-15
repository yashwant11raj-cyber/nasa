# SPHEREx Sky Viewer

A web tool for the NASA Space Apps SPHEREx challenge. You give it a spot in the sky
(RA and Dec) and it returns the SPHEREx images of that patch, one per observation
date, so a moving or changing object can be spotted like in a short video.

**Status (read this first)**

- The backend (FastAPI) works on **mock data** (fake FITS files made by `data_mock.py`).
- **Real SPHEREx data is not connected yet.** With `USE_MOCK = False` in `config.py` every frames request answers HTTP 501. `data_irsa.py` can search, download and read real cutouts, but `get_frames` is not written (it needs a frame limit, robust downloads and re-aligning).
- The web page (`frontend/`) is built (plain HTML, CSS and JavaScript). Open http://127.0.0.1:8000/ with the server running. Still missing: spectrum plot, flags display, overlays, colour picture, motion trail and the practice game page (the backend has the code but no endpoints for them yet).

## Setup (Windows, PowerShell)

```
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python data_mock.py
python cache.py clear
```

Python 3.13 is used because Python 3.15 could not install PyYAML on Windows.
After you run `data_mock.py` again, run `python cache.py clear` so old cached pictures go away.

## Run

```
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/docs to try every address in your browser.

On the mock data only the patch around WISE 0855 has images. Use the
`center` printed by `python check_mock.py`, or the WISE 0855 preset from
`/api/targets?year=2026`. Other positions answer 404 ("No images cover ...").

## Web addresses (API)

| Address                         | What it returns                                                                                                                                                                            |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /api/limits`               | Field-of-view minimum, maximum and default (arcminutes)                                                                                                                                    |
| `GET /api/targets?year=2026`    | The 5 preset targets (positions moved to that year with proper motion)                                                                                                                     |
| `GET /api/resolve?name=..`      | A target name to RA/Dec. The 5 built-in targets work offline (positions at 2026.0); other names use the online lookup (CDS), which may be down                                             |
| `GET /api/frames`               | The frame list: image links, dates, detector, wavelength, pixel scale, centre                                                                                                              |
| `GET /api/frames/{index}/image` | One frame as a PNG picture (north up)                                                                                                                                                      |
| `GET /api/flags`                | Per frame: flag counts, bad and contaminated fractions, and the "Is it real?" traffic light (green, yellow, red, grey) with reasons, plus the flag legend. Same numbering as `/api/frames` |
| `GET /api/animation.gif`        | All frames as one animated GIF (a download)                                                                                                                                                |
| `GET /api/export.csv`           | One row per frame with the dot's (or a target's expected) position, as CSV (a download)                                                                                                    |
| `GET /api/trail`                | Where the moving dot is found in each frame (JSON, same numbering as `/api/frames`)                                                                                                        |
| `GET /api/expected-path`        | Where a preset target should be in each frame (from its proper motion)                                                                                                                     |
| `GET /api/practice/check`       | Practice game: is a click on a hidden mover?                                                                                                                                               |

### URL settings

Every setting is in the web address, so a link can be shared or embedded.

| Setting     | Meaning                                                                                                                                 | Default    |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `ra`, `dec` | Position. Degrees (`133.8`) or sexagesimal (`08h55m10.8s`, `08:55:10.8`, `-07d14m42s`). A sexagesimal RA without a unit letter is hours | required   |
| `fov`       | Field of view in arcminutes, from `MIN_FOV_ARCMIN` to `MAX_FOV_ARCMIN` in `config.py` (1 to 30)                                         | 6          |
| `stretch`   | `linear`, `sqrt`, `log`, `asinh`                                                                                                        | `sqrt`     |
| `mode`      | `normal`, `difference`, `stack`                                                                                                         | `normal`   |
| `match`     | `on` / `off`: same background level and brightness scale in every frame                                                                 | `off`      |
| `ref`       | Only `mode=difference`: `first` or `previous` frame is subtracted                                                                       | `first`    |
| `combine`   | Only `mode=stack`: `mean` or `sum`                                                                                                      | `mean`     |
| `group`     | Only `mode=stack`: `detector` (one stack per detector) or `all`                                                                         | `detector` |
| `speed_ms`  | Only the GIF: milliseconds per frame, 20 to 5000                                                                                        | 200        |
| `kind`      | Only the CSV: `trail` (where the moving dot is found) or `expected`                                                                     | `trail`    |
| `target`    | Only `kind=expected` and `/api/expected-path`: one of the 5 preset targets                                                              | none       |

Example:

```
http://127.0.0.1:8000/api/frames?ra=133.76&dec=-7.24&fov=6&mode=difference&ref=previous
```

Mistakes come back as `{"detail": "a friendly sentence"}` with a status code:
400 bad value, 404 no images, 422 missing setting, 501 real data not connected,
503 mock files missing, 504 data source too slow.

Limits worth knowing:

- A GIF may hold at most `MAX_FRAMES` frames (50, set in `config.py`). The error message suggests `mode=stack`.
- The CSV trail needs at least 3 frames of the same size.

## Data release

`RELEASE_NAME` in `config.py` is a label used in the cache key. To start with a fresh
cache after a new data release, change that one line (old cache files are simply no longer used),
or run `python cache.py clear`. The cache never expires by itself.

## Tests

Every part has its own test file (`test_*.py`). Run them all with:

```
python run_all_tests.py
```

Start the server first (`uvicorn main:app --reload`, other terminal) so the server
parts run too; without it they print SKIPPED. Run a few files only with
`python run_all_tests.py cache fov`. Tests that need the mock files say
`SKIPPED` until you run `python data_mock.py`.

## Files

| File                                              | Job                                                                       |
| ------------------------------------------------- | ------------------------------------------------------------------------- |
| `main.py`                                         | The web server; only connects the other files                             |
| `params.py`, `coords.py`, `names.py`, `errors.py` | Check and explain what arrives in the web address                         |
| `data_mock.py`, `data_practice.py`                | Fake data and the practice sky                                            |
| data_irsa.py                                      | Real data source (search, download, read cutouts; get_frames not written) |
| `cache.py`, `config.py`                           | Saved cutouts and all settings                                            |
| `processing.py`                                   | Cutouts, stretch, difference, stack, trail, colour, PNG                   |
| `gif_export.py`, `export_csv.py`                  | GIF and CSV downloads                                                     |
| `flags.py`, `quality.py`, `realcheck.py`,         | Used by main.py (/api/flags)                                              |
| `spectra.py`, `overlays.py`, `movers.py`          | Extras (not connected to `main.py` yet)                                   |
| `targets.py`                                      | The 5 test targets                                                        |

Notes for helpers: `PROGRESS.md` (what is done and what is known to be wrong),
`FRAME_FORMAT.md` (the frame dictionary), `docs/DATA_NOTES.md` (real data findings),
`docs/FUTURE_WORK.md` (ideas not built).
