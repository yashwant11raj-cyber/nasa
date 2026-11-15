# test_gif_export.py
# Tests gif_export.py and GET /api/animation.gif (Backend 34).
#
# Parts 1-2 need nothing:                 python test_gif_export.py
# Part 3 needs the mock files:            python data_mock.py   (once)
# Part 3 also needs the server running:   uvicorn main:app --reload   (other terminal)
# Part 3 is skipped if either is missing.

import io
from pathlib import Path

import numpy as np
import requests
from PIL import Image

import gif_export

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


def grey(value, size=50):
    """A flat grey picture."""
    return np.full((size, size), value, dtype=np.uint8)


# Four pictures that all differ, so Pillow has nothing to merge
greys = [grey(40), grey(90), grey(140), grey(200)]

print("--- Part 1: greys_to_gif_bytes ---")
data = gif_export.greys_to_gif_bytes(greys)
check("the bytes start with the GIF signature", data[:3] == b"GIF" and data[:6] in (b"GIF87a", b"GIF89a"))
gif = Image.open(io.BytesIO(data))
check("4 pictures give 4 frames", getattr(gif, "n_frames", 1) == 4)
check("a 50 x 50 picture is enlarged 8 times (400 // 50) to 400 x 400", gif.size == (400, 400))
check("the default time per frame is used", gif.info.get("duration") == gif_export.DEFAULT_DURATION_MS)
check("it loops forever (loop = 0)", gif.info.get("loop") == 0)
fast = Image.open(io.BytesIO(gif_export.greys_to_gif_bytes(greys, 100)))
check("duration_ms=100 is stored", fast.info.get("duration") == 100)
gif.seek(3)
check("the last frame has the last grey (200)", int(np.array(gif.convert("L"))[0, 0]) == 200)

# FITS row 0 is the BOTTOM row; image_to_png_bytes flips the picture so north is up,
# so a bright pixel in array row 0 must land in the bottom row of the GIF.
spot = np.zeros((50, 50), dtype=np.uint8)
spot[0, 10] = 255
one = Image.open(io.BytesIO(gif_export.greys_to_gif_bytes([spot, grey(10), grey(20)])))
pixels = np.array(one.convert("L"))
check("array row 0 (south) ends up at the bottom of the picture", pixels[-1, 84] == 255 and pixels[0, 84] == 0)

print("\n--- Part 2: bad input ---")
check("no frames is refused", fails(gif_export.greys_to_gif_bytes, []))
check("more frames than the limit is refused", fails(gif_export.greys_to_gif_bytes, greys, 200, 3))
check("exactly the limit is fine", len(gif_export.greys_to_gif_bytes(greys, 200, 4)) > 0)
check("by default the limit is config.MAX_FRAMES", fails(gif_export.greys_to_gif_bytes, [grey(i) for i in range(51)]))
for bad in (0, 19, 5001, 1.5, "200", None, True):
    check(f"duration {bad!r} is refused", fails(gif_export.check_duration, bad))
check("the limits themselves are allowed",
      gif_export.check_duration(20) == 20 and gif_export.check_duration(5000) == 5000)

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
    url = BASE + "/api/animation.gif"

    r = requests.get(url, params=q)
    check("status 200", r.status_code == 200)
    check("content type is image/gif", r.headers.get("content-type") == "image/gif")
    check("it is offered as a download",
          "attachment" in r.headers.get("content-disposition", "") and ".gif" in r.headers.get("content-disposition", ""))
    g = Image.open(io.BytesIO(r.content))
    check("12 mock frames give 12 GIF frames", getattr(g, "n_frames", 1) == 12)
    print("   size:", g.size, " bytes:", len(r.content))

    r = requests.get(url, params={**q, "mode": "stack"})
    check("mode=stack gives 6 frames", r.status_code == 200 and Image.open(io.BytesIO(r.content)).n_frames == 6)
    r = requests.get(url, params={**q, "mode": "difference"})
    check("mode=difference works", r.status_code == 200 and r.content[:3] == b"GIF")
    r = requests.get(url, params={**q, "match": "on", "stretch": "asinh"})
    check("match=on and stretch=asinh work", r.status_code == 200)
    r = requests.get(url, params={**q, "speed_ms": 500})
    check("speed_ms=500 is stored", Image.open(io.BytesIO(r.content)).info.get("duration") == 500)

    for label, extra in [("speed_ms=5", {"speed_ms": 5}), ("speed_ms=99999", {"speed_ms": 99999}),
                         ("mode=banana", {"mode": "banana"}), ("ra=400", {"ra": 400})]:
        resp = requests.get(url, params={**q, **extra})
        check(f"{label} gives 400 and a message", resp.status_code == 400 and "detail" in resp.json())
        print("   message:", resp.json().get("detail"))
    resp = requests.get(url, params={**q, "speed_ms": "fast"})
    check("speed_ms=fast gives 422 with a sentence", resp.status_code == 422 and isinstance(resp.json().get("detail"), str))
    resp = requests.get(url, params={"dec": 0})
    check("missing ra gives 422 with a sentence", resp.status_code == 422)
    far = requests.get(url, params={**q, "ra": (header["CRVAL1"] + 5) % 360})
    check("a position with no images gives 404", far.status_code == 404)

    print("\nTry it in your browser (it downloads a file):")
    print(f"  {BASE}/api/animation.gif?ra={q['ra']}&dec={q['dec']}&fov=6&speed_ms=200")

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")