# test_export_csv.py
# Tests export_csv.py and GET /api/export.csv (Backend 35).
#
# Parts 1-2 need nothing:                 python test_export_csv.py
# Part 3 needs the mock files:            python data_mock.py   (once)
# Part 3 also needs the server running:   uvicorn main:app --reload   (other terminal)
# Part 3 is skipped if either is missing.

import csv
import io
from datetime import datetime
from pathlib import Path

import numpy as np
import requests

import export_csv

BASE = "http://127.0.0.1:8000"
MOCK_FILE = Path(__file__).parent / "data" / "mock" / "mock_00.fits"
problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


def fails(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except ValueError as err:
        print(f"        message: {err}")
        return True
    print("        NO ERROR RAISED")
    return False


def read(text):
    return list(csv.DictReader(io.StringIO(text)))


frames = [{"obs_time": datetime(2026, 1, 1, 12, 30), "detector": 1, "wavelength_um": 0.75},
          {"obs_time": datetime(2026, 2, 1), "detector": 2, "wavelength_um": 1.5, "n_stacked": 2},
          {"obs_time": datetime(2026, 3, 1), "detector": 3, "wavelength_um": 2.25}]
trail = [{"found": True, "x": 10.123456789, "y": 20.0, "ra_deg": 133.75, "dec_deg": -7.25, "snr": 42.5},
         {"found": False, "x": None, "y": None, "ra_deg": None, "dec_deg": None, "snr": 1.2},
         None]

print("--- Part 1: build_rows and to_csv_text (trail) ---")
rows = export_csv.build_rows("trail", frames, trail)
check("one row per frame", len(rows) == 3)
check("every row has exactly the keys in COLUMNS", all(set(r) == set(export_csv.COLUMNS) for r in rows))
text = export_csv.to_csv_text(rows)
check("the first line is the header", text.splitlines()[0] == ",".join(export_csv.COLUMNS))
parsed = read(text)
check("3 data lines", len(parsed) == 3)
check("time is ISO text", parsed[0]["obs_time"] == "2026-01-01T12:30:00")
check("floats are rounded to 6 decimals", parsed[0]["x"] == "10.123457")
check("whole floats lose the useless zeros", parsed[0]["y"] == "20")
check("integers stay integers", parsed[0]["frame"] == "0" and parsed[0]["detector"] == "1")
check("ok is true or false for a trail", parsed[0]["ok"] == "true" and parsed[1]["ok"] == "false")
check("unknown values are empty cells", parsed[1]["x"] == "" and parsed[1]["ra_deg"] == "")
check("a missing position (None) gives empty cells and no crash", parsed[2]["x"] == "" and parsed[2]["ok"] == "")
check("n_stacked defaults to 1", parsed[0]["n_stacked"] == "1" and parsed[1]["n_stacked"] == "2")
check("snr is filled for a trail", parsed[0]["snr"] == "42.5")
check("kind is written", all(r["kind"] == "trail" for r in parsed))

print("\n--- Part 2: expected path, odd values, bad input ---")
located = [{"inside": True, "x": 1.0, "y": 2.0, "ra_deg": 10.0, "dec_deg": 5.0},
           {"inside": False, "x": -3.5, "y": 2.0, "ra_deg": 10.1, "dec_deg": 5.0},
           {"inside": True, "x": np.float32(2.5), "y": np.float64(3.0), "ra_deg": float("nan"), "dec_deg": float("inf")}]
p = read(export_csv.to_csv_text(export_csv.build_rows("expected", frames, located)))
check("expected: ok follows 'inside'", [r["ok"] for r in p] == ["true", "false", "true"])
check("expected: snr is empty", all(r["snr"] == "" for r in p))
check("numpy numbers are written", p[2]["x"] == "2.5" and p[2]["y"] == "3")
check("NaN and infinity become empty cells", p[2]["ra_deg"] == "" and p[2]["dec_deg"] == "")
check("a numpy bool works", export_csv._cell(np.bool_(True)) == "true")
check("no frames gives just the header", export_csv.to_csv_text(export_csv.build_rows("trail", [], [])).count("\n") == 1)
check("unknown kind is refused", fails(export_csv.build_rows, "banana", frames, trail))
check("different list lengths are refused", fails(export_csv.build_rows, "trail", frames, trail[:2]))
check("a cell with a comma is quoted, so columns do not shift",
      read(export_csv.to_csv_text([{"kind": "a,b"}]))[0]["kind"] == "a,b")

print("\n--- Part 3: the live server ---")
try:
    requests.get(BASE + "/docs", timeout=5)
    server_up = True
except requests.exceptions.ConnectionError:
    server_up = False
if not server_up:
    print("SKIPPED  server is not running. Start it with:  uvicorn main:app --reload")
elif not MOCK_FILE.exists():
    print("SKIPPED  no mock files. Run:  python data_mock.py")
else:
    from astropy.io import fits
    header = fits.getheader(MOCK_FILE)
    q = {"ra": header["CRVAL1"], "dec": header["CRVAL2"], "fov": 6}
    url = BASE + "/api/export.csv"

    r = requests.get(url, params=q)
    check("trail: status 200", r.status_code == 200)
    check("content type is text/csv", r.headers.get("content-type", "").startswith("text/csv"))
    check("it is offered as a download", "attachment" in r.headers.get("content-disposition", ""))
    rows_ = read(r.text)
    check("12 rows for the 12 mock frames", len(rows_) == 12)
    check("the header has all columns", list(rows_[0]) == list(export_csv.COLUMNS))
    check("the dot was found in every frame", all(x["ok"] == "true" for x in rows_))
    frames_json = requests.get(f"{BASE}/api/frames", params=q).json()["frames"]
    check("obs_time matches the frame list", [x["obs_time"] for x in rows_] == [f["obs_time"] for f in frames_json])
    xs = [float(x["x"]) for x in rows_]
    check("x runs steadily one way (the dot moves)", xs == sorted(xs) or xs == sorted(xs, reverse=True))

    r = requests.get(url, params={**q, "kind": "expected", "target": "wise0855"})
    check("expected path: status 200 and 12 rows", r.status_code == 200 and len(read(r.text)) == 12)
    check("expected path: kind column says expected", all(x["kind"] == "expected" for x in read(r.text)))
    r = requests.get(url, params={**q, "mode": "stack"})
    check("mode=stack gives 6 rows", len(read(r.text)) == 6)

    for label, extra in [("kind=banana", {"kind": "banana"}), ("kind=expected without target", {"kind": "expected"}),
                         ("unknown target", {"kind": "expected", "target": "Vega"}), ("ra=400", {"ra": 400})]:
        resp = requests.get(url, params={**q, **extra})
        check(f"{label} gives 400 and a message", resp.status_code == 400 and "detail" in resp.json())
        print("   message:", resp.json().get("detail"))
    far = requests.get(url, params={**q, "ra": (header["CRVAL1"] + 5) % 360})
    check("a position with no images gives 404", far.status_code == 404)

    print("\nTry it in your browser (it downloads a file):")
    print(f"  {BASE}/api/export.csv?ra={q['ra']}&dec={q['dec']}&fov=6&kind=trail")

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")