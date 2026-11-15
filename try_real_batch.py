# try_real_batch.py
# After-data #6, #7, #8, #9, #10 on REAL data, in one run. Not part of the server.
# Needs the internet. Run it with:
#
#     python try_real_batch.py [images per detector] [workers]
#     python try_real_batch.py 4 4         (the defaults: 24 cutouts, 4 at a time)
#
# What it does (it only PRINTS facts and decides nothing):
#   1. Search (#2) and pick a few images per detector, evenly spread (#8 selection.py)
#   2. Download them in parallel (#10 downloads.py), then again to prove the disk copies
#   3. Compare one fresh download with its trimmed disk copy (ZODI and EPSF dropped)
#   4. Read every cutout into a frame and run the contract check (#6 contract.py)
#   5. Share of pixels masked by each flag, and the bad fraction of every frame with
#      three flag-table variants (#9 quality.py). The variants are MY OWN choices.
#   6. What cleaning (#7 cleaning.py) masks, and whether the flags at WISE 0855's
#      expected position would be masked (OUTLIER and TRANSIENT are the suspects)
#   7. How far wcs_world2pix (no SIP) is from all_world2pix (with SIP) at that position
#
# If IRSA's search is down (502), it falls back to the six cutouts saved in
# cache/real_cutouts/ and reports steps 1-3 as NOT TESTED.
# Output: the console and docs/real_batch_report.txt. Paste the console output back.

import sys
import time
from pathlib import Path

import numpy as np
from astropy.io import fits

import cleaning
import config
import contract
import data_irsa
import downloads
import flags
import quality
import selection
import targets

TARGET_ID = "wise0855"
FOV_ARCMIN = 6.0
SAVE_DIR = config.CACHE_DIR / "real_cutouts"
REPORT = Path(__file__).parent / "docs" / "real_batch_report.txt"
NEAR_RADIUS = 2          # pixels around the expected position that are inspected

lines = []
problems = 0


def say(text=""):
    print(text)
    lines.append(str(text))


def check(label, ok):
    global problems
    say(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


def arg_int(position, default, low, high):
    if len(sys.argv) > position:
        try:
            value = int(sys.argv[position])
        except ValueError:
            raise SystemExit(f"Argument {position} must be a whole number.")
        if not low <= value <= high:
            raise SystemExit(f"Argument {position} must be from {low} to {high}.")
        return value
    return default


# ---------------------------------------------------------------
# The three flag-table variants (my own choices, UNVERIFIED)
# ---------------------------------------------------------------
HARDWARE_BITS = (1, 2, 6, 9, 10, 11)    # OVERFLOW, SUR_ERROR, NONFUNC, MISSING_DATA, HOT, COLD


def variant_tables():
    draft = dict(flags.REAL_TABLE_DRAFT)

    no_mover_bits = dict(draft)          # OUTLIER (19) and TRANSIENT (0) are not "bad"
    for bit in (0, 19):
        name, description, _category = draft[bit]
        no_mover_bits[bit] = (name, description, flags.INFO)

    hardware_only = {}                   # only instrument faults are "bad"
    for bit, (name, description, category) in draft.items():
        if category == flags.BAD and bit not in HARDWARE_BITS:
            category = flags.INFO
        hardware_only[bit] = (name, description, category)

    return {"A draft": draft, "B no OUTLIER/TRANSIENT": no_mover_bits, "C hardware only": hardware_only}


# ---------------------------------------------------------------
# Getting the cutouts
# ---------------------------------------------------------------
def load_saved_files():
    """Fallback: the six cutouts saved by inspect_real_files.py."""
    pairs = []
    for path in sorted(SAVE_DIR.glob(f"{TARGET_ID}_SPHEREx-D*_*_fov6.fits")):
        hdul = fits.open(path, memmap=False)
        try:
            for hdu in hdul:
                hdu.data
        finally:
            hdul.close()
        pairs.append((path.name, hdul))
    return pairs


def get_cutouts(ra, dec, per_detector, workers):
    """Returns a list of (name, hdulist). Steps 1-3 happen here."""
    say("--- 1. Search and selection (#2, #8) ---")
    try:
        t0 = time.time()
        images = data_irsa.search_images(ra, dec, FOV_ARCMIN)
    except Exception as err:
        say(f"SEARCH FAILED ({type(err).__name__}: {err})")
        pairs = load_saved_files()
        say(f"FALLBACK: {len(pairs)} saved cutouts from {SAVE_DIR}. "
            "Steps 1-3 (search, selection, download, disk copy) are NOT TESTED.")
        return pairs
    say(f"   {len(images)} images in {time.time() - t0:.1f} s; per detector: {selection.count_by_detector(images)}")
    check("search_images found images (the number was 258 on 2026-11-15)", len(images) > 0)
    if not images:
        return []

    chosen = selection.limit_per_detector(images, per_detector)
    say(f"   chosen {len(chosen)} images: {selection.count_by_detector(chosen)}")
    check("chosen images are sorted oldest first", [i["t_min"] for i in chosen] == sorted(i["t_min"] for i in chosen))
    urls = [item["url"] for item in chosen]

    say(f"\n--- 2. Parallel download, {workers} at a time (#10) ---")
    t0 = time.time()
    results = downloads.download_many(urls, data_irsa.download_cutout, max_workers=workers,
                                      progress=lambda done, total: say(f"   {done} of {total} finished"))
    seconds = time.time() - t0
    ok, cached, errors = downloads.summarize(results)
    say(f"   {ok} of {len(urls)} ok ({cached} from disk) in {seconds:.1f} s; {len(errors)} errors")
    for text in errors:
        say("   error: " + text[:200])
    try:
        downloads.require_some(results)
    except TimeoutError as err:
        check(f"at least one cutout arrived ({err})", False)
        return []
    check("every cutout arrived (failures are reported above, not hidden)", ok == len(urls))

    say("\n   Second request for the same links, with the network 'switched off':")

    def no_network(url):
        raise ConnectionError("this should have come from the disk copy")

    t0 = time.time()
    again = downloads.download_many(urls, no_network, max_workers=workers)
    ok2, cached2, _errors2 = downloads.summarize(again)
    say(f"   {ok2} ok, {cached2} from disk, in {time.time() - t0:.1f} s")
    check("every cutout that arrived the first time is now served from the disk copy", cached2 == ok)

    say("\n--- 3. Fresh download versus its trimmed disk copy ---")
    fresh = next((r for r in results if r["hdulist"] is not None and not r["from_disk"]), None)
    if fresh is None:
        say("NOT TESTED: every cutout already came from disk. Run  python downloads.py clear  and run again.")
    else:
        saved = downloads.load_saved(fresh["url"])
        check("the disk copy can be read back", saved is not None)
        if saved is not None:
            a, b = fresh["hdulist"], saved
            say("   extensions fresh: " + ", ".join(h.name for h in a))
            say("   extensions disk : " + ", ".join(h.name for h in b))
            check("IMAGE is identical", np.array_equal(np.asarray(a["IMAGE"].data, float),
                                                       np.asarray(b["IMAGE"].data, float), equal_nan=True))
            check("FLAGS are identical", np.array_equal(np.asarray(a["FLAGS"].data), np.asarray(b["FLAGS"].data)))
            check("VARIANCE is identical", np.array_equal(np.asarray(a["VARIANCE"].data, float),
                                                          np.asarray(b["VARIANCE"].data, float), equal_nan=True))
            wa, wb = data_irsa.centre_wavelength(a), data_irsa.centre_wavelength(b)
            say(f"   centre wavelength fresh {wa:.6f} um, disk {wb:.6f} um")
            check("the centre wavelength is identical (WCS-WAVE survived the trimming)", abs(wa - wb) < 1e-9)

    return [(item["url"], r["hdulist"]) for item, r in zip(chosen, results) if r["hdulist"] is not None]


# ---------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------
def make_frames(pairs):
    frames = []
    for name, hdul in pairs:
        try:
            frames.append(data_irsa.read_cutout(hdul, name))
        except ValueError as err:
            say(f"   could not read {name[-60:]}: {err}")
    frames.sort(key=lambda f: f["obs_time"])
    return frames


def contract_part(frames):
    say("\n--- 4. Contract (#6) ---")
    found = contract.list_problems(frames)
    for text in found[:10]:
        say("   problem: " + text)
    check(f"all {len(frames)} real frames follow the contract", found == [])
    shapes = {}
    for f in frames:
        shapes[f["image"].shape] = shapes.get(f["image"].shape, 0) + 1
    say(f"   shapes seen: {shapes}  (more than one shape = the re-align step #30 is needed)")


def flags_part(frames):
    say("\n--- 5. Flags and bad fractions (#9) ---")
    total_pixels = sum(f["flags"].size for f in frames)
    sums = {}
    for f in frames:
        for name, n in flags.count_flags(f["flags"], flags.REAL_TABLE_DRAFT).items():
            sums[name] = sums.get(name, 0) + n
    say(f"   share of ALL pixels carrying each flag (over {len(frames)} frames, {total_pixels} pixels):")
    category = {name: cat for (name, _d, cat) in flags.REAL_TABLE_DRAFT.values()}
    for name, n in sorted(sums.items(), key=lambda kv: -kv[1]):
        say(f"      {name:<13} {100 * n / total_pixels:6.2f} %   (draft category: {category.get(name, '?')})")

    tables = variant_tables()
    say("\n   bad fraction per frame (share of usable pixels), three variants:")
    say("      det  obs_time              shape    " + "  ".join(f"{name:<22}" for name in tables))
    worst = {name: 0.0 for name in tables}
    per_detector = {}
    for f in frames:
        values = {name: quality.bad_fraction(f, table) for name, table in tables.items()}
        for name, v in values.items():
            worst[name] = max(worst[name], v)
            slot = per_detector.setdefault(f["detector"], {n: 0.0 for n in tables})
            slot[name] = max(slot[name], v)
        say(f"      D{f['detector']}   {f['obs_time'].isoformat(timespec='minutes')}  {str(f['image'].shape):<8} "
            + "  ".join(f"{100 * values[name]:>21.2f}%" for name in tables))
    say("\n   WORST frame per detector (percent):")
    for det in sorted(per_detector):
        say(f"      D{det}: " + ", ".join(f"{name} {100 * v:.2f}" for name, v in per_detector[det].items()))
    say("   WORST frame overall: " + ", ".join(f"{name} {100 * v:.2f} %" for name, v in worst.items()))
    say(f"   current MAX_BAD_FRACTION is {quality.MAX_BAD_FRACTION}. Dropped by it with variant A: "
        f"{sum(1 for f in frames if quality.bad_fraction(f, tables['A draft']) > quality.MAX_BAD_FRACTION)} frames.")


def cleaning_part(frames):
    say("\n--- 6. Cleaning (#7) and the expected position of WISE 0855 ---")
    draft = flags.REAL_TABLE_DRAFT
    shares_default, shares_keep = [], []
    for f in frames:
        shares_default.append(cleaning.masked_share(f, cleaning.clean_frame(f, draft)))
        shares_keep.append(cleaning.masked_share(f, cleaning.clean_frame(f, draft, keep_names=("OUTLIER", "TRANSIENT"))))
    say(f"   share of pixels turned into NaN, mean over frames: default {100 * np.mean(shares_default):.2f} %, "
        f"keeping OUTLIER and TRANSIENT {100 * np.mean(shares_keep):.2f} %")

    positions = targets.expected_positions(TARGET_ID, [f["obs_time"] for f in frames])
    masked_centre = suspects = 0
    sip_gaps = []
    say(f"\n   {TARGET_ID} expected pixel in each frame (x, y from 0, y from the bottom row of the file):")
    say("      det  obs_time          x       y      inside  SIP gap  flags within "
        f"{NEAR_RADIUS} px")
    for f, (ra, dec) in zip(frames, positions):
        wcs = f["wcs"]
        try:
            x, y = (float(v) for v in wcs.all_world2pix(ra, dec, 0))          # with SIP
            x0, y0 = (float(v) for v in wcs.wcs_world2pix(ra, dec, 0))        # what locate_in_frames uses
            gap = float(np.hypot(x - x0, y - y0))
        except Exception as err:
            say(f"      D{f['detector']}   could not place it ({type(err).__name__})")
            continue
        sip_gaps.append(gap)
        height, width = f["flags"].shape
        xr, yr = int(round(x)), int(round(y))
        inside = 0 <= xr < width and 0 <= yr < height
        names = []
        if inside:
            window = f["flags"][max(0, yr - NEAR_RADIUS):yr + NEAR_RADIUS + 1,
                                max(0, xr - NEAR_RADIUS):xr + NEAR_RADIUS + 1]
            union = int(np.bitwise_or.reduce(window.ravel().astype(np.int64)))
            names = flags.decode_value(union, draft)
            if cleaning.flagged_pixels(f, draft)[yr, xr]:
                masked_centre += 1
            if "OUTLIER" in names or "TRANSIENT" in names:
                suspects += 1
        say(f"      D{f['detector']}   {f['obs_time'].isoformat(timespec='minutes')}  {x:6.1f}  {y:6.1f}  "
            f"{str(inside):<6}  {gap:6.2f}  {', '.join(names) or '-'}")
    say(f"\n   default cleaning would mask the exact expected pixel in {masked_centre} of {len(frames)} frames")
    say(f"   OUTLIER or TRANSIENT is set within {NEAR_RADIUS} px of it in {suspects} of {len(frames)} frames")
    if sip_gaps:
        say(f"   SIP gap (all_world2pix minus wcs_world2pix): mean {np.mean(sip_gaps):.2f} px, max {np.max(sip_gaps):.2f} px")
    say("   NOTE: WISE 0855 is very faint, so a flag here does not prove a real mover would be flagged.")


def main():
    per_detector = arg_int(1, 4, 1, 50)
    workers = arg_int(2, downloads.DEFAULT_WORKERS, 1, downloads.MAX_WORKERS)
    ra, dec = targets.position_at_epoch(TARGET_ID, 2026.0)
    ra %= 360.0
    say(f"Target {TARGET_ID} at 2026.0: RA {ra:.6f}, Dec {dec:+.6f}; {per_detector} images per detector, {workers} workers")

    pairs = get_cutouts(ra, dec, per_detector, workers)
    if not pairs:
        say("No cutouts to analyse.")
        return
    frames = make_frames(pairs)
    say(f"\n{len(frames)} frames read.")
    if not frames:
        return
    contract_part(frames)
    flags_part(frames)
    cleaning_part(frames)

    say("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")


main()
REPORT.parent.mkdir(exist_ok=True)
REPORT.write_text("\n".join(lines), encoding="utf-8")
print(f"\nFull report saved to {REPORT}. Paste the console output back to me.")