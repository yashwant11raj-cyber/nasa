# test_resolve_api.py
# Tests GET /api/resolve (main.py). NO internet is used: the online lookup is
# replaced by fakes, and the server part only asks about the 5 built-in targets
# and about bad input.
#
# Part 1 needs nothing:                   python test_resolve_api.py
# Part 2 needs the server running first:  uvicorn main:app --reload   (other terminal)
# Part 2 is skipped if the server is not running.

import requests
from fastapi import HTTPException

import main
import names
import targets

BASE = "http://127.0.0.1:8000"
problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


def status_of(func, *args):
    """(status_code, detail) of the HTTPException a call raises, or (None, None)."""
    try:
        func(*args)
    except HTTPException as err:
        print(f"        {err.status_code}: {err.detail}")
        return err.status_code, err.detail
    print("        NO ERROR RAISED")
    return None, None


# Safety: until a test swaps in a fake, any online lookup is a failure.
real_lookup = names._online_lookup


def forbidden(name):
    raise AssertionError("the online lookup was used in a test")


names._online_lookup = forbidden

print("--- Part 1: resolve_name_address (no server, no internet) ---")
check("/api/resolve is registered", "/api/resolve" in {getattr(r, "path", None) for r in main.app.routes})
check("the static mount is still the last route", getattr(main.app.routes[-1], "name", "") == "static")

preset = {t["id"]: t for t in targets.target_list(2026.0)}
spellings = {"wise0855": "WISE 0855", "barnard": "Barnard's Star", "epsindib": "eps Ind B",
             "rwaur": "rw aur", "rdra": "R Draconis"}
for tid, text in spellings.items():
    r = main.resolve_name_address(text)
    check(f"'{text}' -> {tid}, local, same position as /api/targets?year=2026",
          r["target_id"] == tid and r["source"] == "local"
          and abs(r["ra_deg"] - preset[tid]["ra_deg"]) < 1e-9
          and abs(r["dec_deg"] - preset[tid]["dec_deg"]) < 1e-9)
r = main.resolve_name_address("WISE 0855")
check("the answer has exactly the 5 fields",
      set(r) == {"ra_deg", "dec_deg", "label", "source", "target_id"} and r["label"] == "WISE 0855")
check("the position is the 2026 one, not J2000",
      abs(r["ra_deg"] - targets.TARGETS["wise0855"]["ra_deg"]) > 0.01)
check("RA is in 0..360", all(0 <= main.resolve_name_address(t)["ra_deg"] < 360 for t in spellings.values()))

names._online_lookup = lambda n: (279.2347, 38.7837)          # fake online service
r = main.resolve_name_address("  Some Other Star  ")
check("an unknown name uses the (fake) online lookup",
      r["source"] == "online" and r["target_id"] is None and abs(r["ra_deg"] - 279.2347) < 1e-9)
check("the online label is the typed name without spaces", r["label"] == "Some Other Star")


def broken(n):
    raise ConnectionError("pretend CDS is down")


names._online_lookup = broken
code, detail = status_of(main.resolve_name_address, "Some Other Star")
check("online service down -> 404 with a friendly sentence", code == 404 and isinstance(detail, str) and len(detail) > 20)
names._online_lookup = lambda n: (400.0, 0.0)
check("online lookup gives RA 400 -> 404", status_of(main.resolve_name_address, "x")[0] == 404)
names._online_lookup = forbidden

check("empty name -> 400", status_of(main.resolve_name_address, "")[0] == 400)
check("spaces only -> 400", status_of(main.resolve_name_address, "    ")[0] == 400)
check("100 characters is allowed (local miss -> fake online)",
      (lambda: (setattr(names, "_online_lookup", lambda n: (1.0, 2.0)),
                main.resolve_name_address("a" * 100))[1]["source"] == "online")())
names._online_lookup = forbidden
check("101 characters -> 400 (the online lookup is never called)",
      status_of(main.resolve_name_address, "a" * 101)[0] == 400)

names._online_lookup = real_lookup

print("\n--- Part 2: the live server (built-in targets only, no internet) ---")
try:
    requests.get(BASE + "/docs", timeout=5)
except requests.exceptions.ConnectionError:
    print("SKIPPED  server is not running. Start it with:  uvicorn main:app --reload")
else:
    url = BASE + "/api/resolve"
    server_targets = {t["id"]: t for t in requests.get(f"{BASE}/api/targets", params={"year": 2026}).json()["targets"]}
    for tid, text in spellings.items():
        r = requests.get(url, params={"name": text})
        d = r.json()
        check(f"'{text}': 200, local, matches /api/targets?year=2026",
              r.status_code == 200 and d["target_id"] == tid and d["source"] == "local"
              and abs(d["ra_deg"] - server_targets[tid]["ra_deg"]) < 1e-9
              and abs(d["dec_deg"] - server_targets[tid]["dec_deg"]) < 1e-9)
    r = requests.get(url, params={"name": "Barnard\u2019s Star"})
    check("a curly apostrophe works", r.status_code == 200 and r.json()["target_id"] == "barnard")

    for label, value in [("empty name", ""), ("spaces only", "   "), ("101 characters", "a" * 101)]:
        resp = requests.get(url, params={"name": value})
        check(f"{label} gives 400 and a message", resp.status_code == 400 and isinstance(resp.json().get("detail"), str))
        print("   message:", resp.json().get("detail"))
    resp = requests.get(url)
    check("missing name gives 422 with a sentence", resp.status_code == 422 and isinstance(resp.json().get("detail"), str))
    print("   message:", resp.json().get("detail"))

    print("\nTry it in your browser:")
    print(f"  {BASE}/api/resolve?name=Barnard's Star")

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")