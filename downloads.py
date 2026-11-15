# downloads.py
# After-data #10: download MANY real cutouts without losing the whole request when a
# few of them fail, and keep what was downloaded on disk.
#
# data_irsa.download_cutout() already downloads ONE cutout and retries transient errors
# (3 tries, waits of 10 s and 20 s, timeout 120 s). This file adds:
#   - several downloads at the same time (a small number of workers: IRSA's tutorial
#     saw 15 of 84 cutouts fail in parallel against 4 of 84 in serial, so the default
#     is 4 and the number is a guess to retune with try_real_batch.py)
#   - one failed cutout does NOT stop the others: every result says "ok" or gives the
#     error text
#   - a disk copy of every cutout (cache/cutout_files/), so a repeat request, or a
#     second look at the same frames, needs no download at all. Only the extensions
#     we use are kept (the EPSF table is about 4 MB per cutout and is not used).
#   - require_some(): "nothing at all could be downloaded" becomes a TimeoutError, which
#     main.frames_for already turns into HTTP 504 with a friendly message.
#
# "No images cover this position" is NOT handled here: search_images() gives an empty
# list, selection.choose_images() gives ([], 0), and the caller returns [] (HTTP 404).
#
# The download function is passed in (fetch=...), so everything except the real network
# call is tested offline. astropy is only imported when a file is read or written.
# Not connected to main.py yet (data_irsa.get_frames is still not written).
#
# Cache files here are FITS files that this program wrote itself. They never expire
# (like cache.py); delete the folder, or run  python downloads.py clear.

import hashlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import config

FILE_DIR = config.CACHE_DIR / "cutout_files"

# Extensions kept on disk. read_cutout needs IMAGE, FLAGS, VARIANCE; the wavelength
# needs WCS-WAVE. ZODI and EPSF are not used.
KEEP_EXTENSIONS = ("PRIMARY", "IMAGE", "FLAGS", "VARIANCE", "WCS-WAVE")

DEFAULT_WORKERS = 4          # a guess; retune in try_real_batch.py
MAX_WORKERS = 16


def file_path(url, cache_dir=None):
    """Where the copy of this cutout link lives. The link contains the position and
    size, so different requests never share a file."""
    folder = Path(cache_dir) if cache_dir is not None else FILE_DIR
    return folder / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:40] + ".fits")


def load_saved(url, cache_dir=None):
    """The saved cutout as an HDUList held in memory, or None if there is no usable copy.

    A damaged file is deleted and treated as missing.
    """
    path = file_path(url, cache_dir)
    if not path.exists():
        return None
    from astropy.io import fits
    try:
        hdulist = fits.open(path, memmap=False)
        try:
            for hdu in hdulist:
                hdu.data                      # read every extension before the file closes
        finally:
            hdulist.close()
        return hdulist
    except Exception:
        path.unlink(missing_ok=True)
        return None


def save_trimmed(hdulist, url, cache_dir=None):
    """Write the cutout (only KEEP_EXTENSIONS) to disk. Returns the path.

    Written to a temporary file first and then renamed, so a stop half-way never
    leaves a broken file (same idea as cache.py).
    """
    from astropy.io import fits
    path = file_path(url, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = fits.HDUList([hdu for hdu in hdulist if hdu.name in KEEP_EXTENSIONS])
    temp = path.with_suffix(".part")
    kept.writeto(temp, overwrite=True)
    temp.replace(path)
    return path


def download_many(urls, fetch, max_workers=DEFAULT_WORKERS, use_disk=True,
                  cache_dir=None, progress=None, load=None, save=None):
    """Get many cutouts. Returns one dictionary per link, in the same order:
      url        the link
      hdulist    the cutout (HDUList in memory), or None if it failed
      error      None, or a short text such as 'TimeoutError: ...'
      from_disk  True if it came from the disk copy
    A failure of one link never stops the others and never raises.

    urls:      list of cutout links.
    fetch:     function link -> HDUList (normally data_irsa.download_cutout).
    max_workers: how many downloads run at the same time (1 to 16).
    use_disk:  False = ignore and do not write disk copies.
    progress:  optional function (done, total), called after each link (any thread,
               one at a time).
    load/save: replace the disk functions (tests only).
    """
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= MAX_WORKERS:
        raise ValueError(f"max_workers must be a whole number from 1 to {MAX_WORKERS}.")
    urls = list(urls)
    load = load or (lambda url: load_saved(url, cache_dir))
    save = save or (lambda hdulist, url: save_trimmed(hdulist, url, cache_dir))
    lock = threading.Lock()
    done = [0]

    def one(url):
        result = {"url": url, "hdulist": None, "error": None, "from_disk": False}
        try:
            if use_disk:
                saved = load(url)
                if saved is not None:
                    result["hdulist"], result["from_disk"] = saved, True
            if result["hdulist"] is None:
                result["hdulist"] = fetch(url)
                if use_disk:
                    try:
                        save(result["hdulist"], url)
                    except Exception:
                        pass              # no room or no permission: the download itself still counts
        except Exception as err:
            result["hdulist"] = None
            result["error"] = f"{type(err).__name__}: {err}"
        with lock:
            done[0] += 1
            if progress is not None:
                progress(done[0], len(urls))
        return result

    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(urls))) as pool:
        return list(pool.map(one, urls))        # map keeps the order of urls


def summarize(results):
    """(number ok, number from disk, list of error texts) for a download_many answer."""
    ok = [r for r in results if r["hdulist"] is not None]
    return len(ok), sum(1 for r in ok if r["from_disk"]), [r["error"] for r in results if r["error"]]


def require_some(results):
    """Raise TimeoutError if links were asked for but NONE could be downloaded.

    main.frames_for turns TimeoutError into HTTP 504 ('the data source took too long').
    Some failures are fine: the caller works with the frames that did arrive.
    """
    if results and not any(r["hdulist"] is not None for r in results):
        first = next((r["error"] for r in results if r["error"]), "unknown error")
        raise TimeoutError(f"None of the {len(results)} cutouts could be downloaded (first error: {first}).")
    return results


def clear_files(cache_dir=None):
    """Delete every saved cutout file. Returns how many were deleted."""
    folder = Path(cache_dir) if cache_dir is not None else FILE_DIR
    count = 0
    if folder.exists():
        for p in list(folder.glob("*.fits")) + list(folder.glob("*.part")):
            p.unlink()
            count += 1
    return count


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("Deleted", clear_files(), "saved cutout file(s) from", FILE_DIR)
    else:
        files = list(FILE_DIR.glob("*.fits")) if FILE_DIR.exists() else []
        print("Folder:", FILE_DIR)
        print(f"{len(files)} file(s), {sum(p.stat().st_size for p in files) / 1e6:.1f} MB")
        