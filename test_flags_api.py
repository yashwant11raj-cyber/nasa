# test_flags_api.py
# Tests GET /api/flags (main.py).
#
# Part 1 needs nothing:                   python test_flags_api.py
# Part 2 needs the mock files:            python data_mock.py   (once)
# Part 2 also needs the server running:   uvicorn main:app --reload   (other terminal)
# Part 2 is skipped if either is missing.

import json
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
MOCK_FILE = Path(__file__).parent / "data" / "mock" / "mock_00.fits"
problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


print("--- Part 1: the route exists (no server) ---")
import main
paths = {getattr(route, "path", None) for route in main.app.routes}
check("/api/flags is registered", "/api/flags" in paths)
check("the static mount is still the last route", getattr(main.app.routes[-1], "name", "") == "static")

print("\n--- Part 2: the live server ---")
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
    url = BASE + "/api/flags"

    r = requests.get(url, params=q)
    check("status 200", r.status_code == 200)
    data = r.json()
    needed = {"index", "status", "reasons", "detector_changed", "wavelength_changed",
              "flagged_names", "flag_counts", "bad_fraction", "contaminated_fraction"}
    check("12 entries and frame_count 12", data["frame_count"] == 12 and len(data["frames"]) == 12)
    check("every entry has exactly the expected fields", all(set(e) == needed for e in data["frames"]))
    check("mode is echoed", data["mode"] == "normal")
    check("the answer can be re-encoded as JSON", len(json.dumps(data)) > 0)
    check("status is one of green / yellow / red / grey",
          all(e["status"] in ("green", "yellow", "red", "grey") for e in data["frames"]))
    check("reasons are lists of {code, message}",
          all(isinstance(x, dict) and set(x) == {"code", "message"} for e in data["frames"] for x in e["reasons"]))
    check("frame 0 never says 'changed'", not data["frames"][0]["detector_changed"] and not data["frames"][0]["wavelength_changed"])
    check("the mock detector changes every frame, so frames 1-11 say detector_changed",
          all(e["detector_changed"] for e in data["frames"][1:]))
    check("fractions are numbers from 0 to 1",
          all(0 <= e["bad_fraction"] <= 1 and 0 <= e["contaminated_fraction"] <= 1 for e in data["frames"]))
    check("flag_counts is a dictionary of whole numbers",
          all(isinstance(e["flag_counts"], dict) and all(isinstance(v, int) for v in e["flag_counts"].values())
              for e in data["frames"]))

    legend = data["legend"]
    check("legend has the 3 mock bits (values 1, 2, 4)", [row["value"] for row in legend] == [1, 2, 4])
    check("legend rows have bit, value, name, description, category",
          all(set(row) == {"bit", "value", "name", "description", "category"} for row in legend))
    names = {row["name"] for row in legend}
    check("every counted flag name is in the legend",
          all(set(e["flag_counts"]) <= names for e in data["frames"]))

    frames_json = requests.get(f"{BASE}/api/frames", params=q).json()
    check("same number of frames as /api/frames", data["frame_count"] == frames_json["frame_count"])
    check("index numbering matches /api/frames", [e["index"] for e in data["frames"]] == [f["index"] for f in frames_json["frames"]])

    st = requests.get(url, params={**q, "mode": "stack"}).json()
    check("mode=stack gives 6 entries, like /api/frames", st["frame_count"] == 6 and len(st["frames"]) == 6)
    check("mode=difference is accepted", requests.get(url, params={**q, "mode": "difference"}).status_code == 200)

    one = requests.get(url, params={**q, "mode": "stack", "group": "all"})
    check("a single stacked frame (fewer than 3) still gives 200", one.status_code == 200)
    check("... with status grey (no dot position, nothing else suspicious)",
          one.json()["frames"][0]["status"] == "grey")
    check("... and its flag counts are still given", isinstance(one.json()["frames"][0]["flag_counts"], dict))

    for label, extra in [("mode=banana", {"mode": "banana"}), ("ra=400", {"ra": 400}),
                         ("fov=100", {"fov": 100}), ("group=banana", {"mode": "stack", "group": "banana"})]:
        resp = requests.get(url, params={**q, **extra})
        check(f"{label} gives 400 and a message", resp.status_code == 400 and "detail" in resp.json())
    check("missing ra gives 422 with a sentence",
          requests.get(url, params={"dec": 0}).status_code == 422)
    far = requests.get(url, params={**q, "ra": (header["CRVAL1"] + 5) % 360})
    check("a position with no images gives 404", far.status_code == 404)

    print("\nTry it in your browser:")
    print(f"  {BASE}/api/flags?ra={q['ra']}&dec={q['dec']}&fov=6")

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")