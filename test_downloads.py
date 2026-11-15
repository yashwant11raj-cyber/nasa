# test_downloads.py
# Tests downloads.py (after-data #10). Run it with:  python test_downloads.py
# NO internet is used: the download is replaced by small fakes.
# Parts 1-3 need only the standard library. Part 4 needs astropy (disk files).

import shutil
import threading
import time

import config
import downloads

problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


def fails(error_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except error_type as err:
        print(f"        message: {err}")
        return True
    print("        NO ERROR RAISED")
    return False


URLS = [f"https://irsa.ipac.caltech.edu/x/{i}.fits" for i in range(10)]

print("--- Part 1: order, failures, progress (fake download, no disk) ---")
calls = []


def fetch(url):
    calls.append(url)
    n = int(url.rsplit("/", 1)[1].split(".")[0])
    time.sleep(0.02 * (10 - n))               # early links are slowest: order must still be kept
    if n in (3, 7):
        raise TimeoutError("IRSA is slow")
    return {"fake": n}


ticks = []
res = downloads.download_many(URLS, fetch, max_workers=4, use_disk=False, progress=lambda d, t: ticks.append((d, t)))
check("one result per link, in the same order", [r["url"] for r in res] == URLS)
check("the good ones have their data", all(r["hdulist"] == {"fake": i} for i, r in enumerate(res) if i not in (3, 7)))
check("the failed ones have no data and an error text",
      all(res[i]["hdulist"] is None and "TimeoutError" in res[i]["error"] for i in (3, 7)))
check("a failure never stops the others (all 10 were tried)", len(calls) == 10)
check("good results have error None and from_disk False", res[0]["error"] is None and res[0]["from_disk"] is False)
ok, cached, errors = downloads.summarize(res)
check("summarize: 8 ok, 0 from disk, 2 errors", (ok, cached, len(errors)) == (8, 0, 2))
check("progress was reported 10 times, ending at 10 / 10", len(ticks) == 10 and ticks[-1] == (10, 10)
      and [d for d, _ in ticks] == list(range(1, 11)))
check("require_some accepts a partial success", downloads.require_some(res) is res)
check("an empty list gives an empty list", downloads.download_many([], fetch) == [])

print("\n--- Part 2: several at the same time ---")
active, peak, lock = [0], [0], threading.Lock()


def counting_fetch(url):
    with lock:
        active[0] += 1
        peak[0] = max(peak[0], active[0])
    time.sleep(0.05)
    with lock:
        active[0] -= 1
    return url


t0 = time.time()
downloads.download_many(URLS, counting_fetch, max_workers=4, use_disk=False)
print(f"   peak at the same time: {peak[0]}, time {time.time() - t0:.2f} s (serial would be 0.50 s)")
check("never more than max_workers at once, and really in parallel", 2 <= peak[0] <= 4)
peak[0] = 0
downloads.download_many(URLS, counting_fetch, max_workers=1, use_disk=False)
check("max_workers=1 is one at a time", peak[0] == 1)
for bad in (0, 17, 2.5, "4", True, None):
    check(f"max_workers={bad!r} is refused", fails(ValueError, downloads.download_many, URLS, fetch, bad))

print("\n--- Part 3: disk copies (fake load and save) ---")
store = {}
loads, saves = [], []


def fake_load(url):
    loads.append(url)
    return store.get(url)


def fake_save(hdulist, url):
    saves.append(url)
    store[url] = hdulist


calls.clear()
res = downloads.download_many(URLS, fetch, use_disk=True, load=fake_load, save=fake_save)
check("first request: everything that downloaded is saved (8 saves), failures are not", len(saves) == 8 and len(store) == 8)
calls.clear()
res = downloads.download_many(URLS, fetch, use_disk=True, load=fake_load, save=fake_save)
print(f"   second request downloaded again: {len(calls)} link(s)")
check("second request: only the 2 failed links are downloaded again", sorted(calls) == [URLS[3], URLS[7]])
check("the 8 saved ones are marked from_disk", sum(1 for r in res if r["from_disk"]) == 8)
check("summarize counts them", downloads.summarize(res)[:2] == (8, 8))

calls.clear()
downloads.download_many(URLS[:2], fetch, use_disk=False, load=fake_load, save=fake_save)
check("use_disk=False ignores the saved copies", len(calls) == 2)


def broken_save(hdulist, url):
    raise OSError("disk full")


res = downloads.download_many(URLS[:2], fetch, use_disk=True, load=lambda u: None, save=broken_save)
check("a disk that cannot be written does not lose the download", all(r["hdulist"] is not None and r["error"] is None for r in res))


def broken_load(url):
    raise OSError("unreadable")


res = downloads.download_many(URLS[:2], fetch, use_disk=True, load=broken_load, save=fake_save)
check("an unreadable disk copy is reported as an error for that link only (no crash)",
      all(r["hdulist"] is None and "OSError" in r["error"] for r in res))

print("\n--- Part 3b: nothing could be downloaded ---")


def dead(url):
    raise ConnectionError("502 Proxy Error")


res = downloads.download_many(URLS[:3], dead, use_disk=False)
check("every link failed: all errors reported", all(r["hdulist"] is None and "ConnectionError" in r["error"] for r in res))
check("require_some raises TimeoutError (main.py turns it into HTTP 504)", fails(TimeoutError, downloads.require_some, res))
check("no links at all is not an error here (that is the 'no images' case)", downloads.require_some([]) == [])

print("\n--- Part 4: real files on disk (needs astropy) ---")
try:
    import numpy as np
    from astropy.io import fits
except ImportError:
    print("SKIPPED  astropy is not installed here")
else:
    folder = config.CACHE_DIR / "test_downloads"
    shutil.rmtree(folder, ignore_errors=True)
    link = "https://irsa.ipac.caltech.edu/ibe/data/spherex/test.fits?center=1,2d&size=0.1"

    def make():
        image = fits.ImageHDU(np.arange(12, dtype=">f4").reshape(3, 4), name="IMAGE")
        image.header["DETECTOR"] = 3
        return fits.HDUList([fits.PrimaryHDU(), image,
                             fits.ImageHDU(np.ones((3, 4), dtype=">i4"), name="FLAGS"),
                             fits.ImageHDU(np.ones((3, 4), dtype=">f4"), name="VARIANCE"),
                             fits.ImageHDU(np.ones((3, 4), dtype=">f4"), name="ZODI"),
                             fits.BinTableHDU.from_columns([fits.Column(name="A", format="J", array=np.arange(5))], name="EPSF")])

    check("no copy yet gives None", downloads.load_saved(link, folder) is None)
    path = downloads.save_trimmed(make(), link, folder)
    check("a file was written", path.exists() and path.suffix == ".fits")
    check("the file name depends on the link", path != downloads.file_path(link + "x", folder))
    back = downloads.load_saved(link, folder)
    names = [h.name for h in back]
    print("   extensions on disk:", names)
    check("only the wanted extensions are kept (ZODI and EPSF are dropped)", names == ["PRIMARY", "IMAGE", "FLAGS", "VARIANCE"])
    check("the data is identical after the round trip", np.array_equal(back["IMAGE"].data, make()["IMAGE"].data)
          and back["IMAGE"].header["DETECTOR"] == 3)
    check("the HDUList can be used after the file was closed", float(back["IMAGE"].data[2, 3]) == 11.0)
    path.write_bytes(b"not a fits file")
    check("a damaged copy gives None and is deleted", downloads.load_saved(link, folder) is None and not path.exists())
    got = downloads.download_many([link], lambda u: make(), cache_dir=folder)
    again = downloads.download_many([link], dead, cache_dir=folder)
    check("download_many writes the copy, and the next call needs no download",
          got[0]["from_disk"] is False and again[0]["from_disk"] is True and again[0]["error"] is None)
    check("clear_files deletes the copies", downloads.clear_files(folder) == 1 and not list(folder.glob("*.fits")))
    shutil.rmtree(folder, ignore_errors=True)

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")