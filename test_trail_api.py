# test_trail_api.py
# Tests GET /api/trail (main.py).
#
# Part 1 needs nothing:                   python test_trail_api.py
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
check("/api/trail is registered", "/api/trail" in paths)
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
    url = BASE + "/api/trail"

    r = requests.get(url, params=q)
    check("status 200", r.status_code == 200)
    data = r.json()
    needed = {"index", "obs_time", "found", "x", "y", "png_x", "png_y", "ra_deg", "dec_deg", "snr"}
    check("12 entries and frame_count 12", data["frame_count"] == 12 and len(data["trail"]) == 12)
    check("every entry has exactly the expected fields", all(set(e) == needed for e in data["trail"]))
    check("mode is echoed", data["mode"] == "normal")
    check("the dot is found in every mock frame", all(e["found"] for e in data["trail"]))
    check("numbers are real numbers (JSON-safe)", all(isinstance(e["png_x"], float) for e in data["trail"]))
    check("the answer can be re-encoded as JSON", len(json.dumps(data)) > 0)

    frames_json = requests.get(f"{BASE}/api/frames", params=q).json()["frames"]
    check("index and obs_time match /api/frames for every frame",
          [(e["index"], e["obs_time"]) for e in data["trail"]]
          == [(f["index"], f["obs_time"]) for f in frames_json])
    xs = [e["x"] for e in data["trail"]]
    check("x runs steadily one way (the dot moves)", xs == sorted(xs) or xs == sorted(xs, reverse=True))

    st = requests.get(url, params={**q, "mode": "stack"}).json()
    check("mode=stack gives 6 entries, like /api/frames", st["frame_count"] == 6 and len(st["trail"]) == 6)
    check("mode=difference is accepted", requests.get(url, params={**q, "mode": "difference"}).status_code == 200)

    one = requests.get(url, params={**q, "mode": "stack", "group": "all"})
    check("a single stacked frame (fewer than 3) gives 400 and a message",
          one.status_code == 400 and isinstance(one.json().get("detail"), str))
    print("   message:", one.json().get("detail"))

    for label, extra in [("mode=banana", {"mode": "banana"}), ("ra=400", {"ra": 400}),
                         ("fov=100", {"fov": 100}), ("group=banana", {"mode": "stack", "group": "banana"})]:
        resp = requests.get(url, params={**q, **extra})
        check(f"{label} gives 400 and a message", resp.status_code == 400 and "detail" in resp.json())
    check("missing ra gives 422 with a sentence",
          requests.get(url, params={"dec": 0}).status_code == 422)
    far = requests.get(url, params={**q, "ra": (header["CRVAL1"] + 5) % 360})
    check("a position with no images gives 404", far.status_code == 404)

    print("\nTry it in your browser:")
    print(f"  {BASE}/api/trail?ra={q['ra']}&dec={q['dec']}&fov=6")

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")