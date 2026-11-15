# test_contract.py
# Tests contract.py and checks that mock frames and real frames follow the same
# contract (after-data #6).
#
# Part 1 needs only numpy:                 python test_contract.py
# Parts 2-4 need astropy, and:
#   Part 2 the mock files:                 python data_mock.py   (once)
#   Part 4 the saved real cutouts:         cache/real_cutouts/ (made by inspect_real_files.py)
# Each part is skipped if its requirements are missing. NO internet is used.

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import config
import contract

problems = 0


def check(label, ok):
    global problems
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems += 1


class FakeWcs:
    def wcs_world2pix(self, *a):
        return a

    def pixel_to_world_values(self, *a):
        return a


def good(size=6, **changes):
    frame = {"image": np.zeros((size, size)), "wcs": FakeWcs(), "obs_time": datetime(2026, 1, 1),
             "wavelength_um": 2.5, "detector": 3, "flags": np.zeros((size, size), dtype=np.int32),
             "variance": np.ones((size, size)), "source_file": "f.fits"}
    frame.update(changes)
    return frame


def says(frame, word, **kw):
    found = contract.frame_problems(frame, **kw)
    return any(word in p for p in found)


print("--- Part 1: the rules, on fake frames ---")
check("a good frame has no problems", contract.frame_problems(good()) == [])
check("flags=None and variance=None are fine", contract.frame_problems(good(flags=None, variance=None)) == [])
f = good()
del f["flags"]
check("a missing key is reported", says(f, "Missing keys: flags"))
check("an unexpected key is reported", says(good(banana=1), "Unexpected keys: banana"))
check("n_stacked is allowed only for stacked frames",
      says(good(n_stacked=2), "n_stacked") and contract.frame_problems(good(n_stacked=2), allow_stacked=True) == [])
check("a list is not a frame", contract.frame_problems([1, 2]) != [])
check("image float32 is refused", says(good(image=np.zeros((6, 6), dtype=np.float32)), "image must be float64"))
check("image big-endian is refused", says(good(image=np.zeros((6, 6), dtype=">f8")), "native"))
check("image 1D is refused", says(good(image=np.zeros(6)), "2D"))
check("image as a list is refused", says(good(image=[[1.0]]), "numpy array"))
check("wcs None is refused", says(good(wcs=None), "wcs must be"))
check("wcs as text is refused", says(good(wcs="x"), "wcs must be"))
check("obs_time with a timezone is refused", says(good(obs_time=datetime(2026, 1, 1, tzinfo=timezone.utc)), "naive"))
check("obs_time as text is refused", says(good(obs_time="2026-01-01"), "datetime"))
check("wavelength as int is refused", says(good(wavelength_um=2), "float"))
check("wavelength NaN is refused", says(good(wavelength_um=float("nan")), "finite"))
check("wavelength 0 is refused", says(good(wavelength_um=0.0), "above zero"))
check("numpy float wavelength is fine", contract.frame_problems(good(wavelength_um=np.float64(2.5))) == [])
check("detector 0 is refused for raw frames, fine for stacks",
      says(good(detector=0), "from 1 to 6") and contract.frame_problems(good(detector=0, n_stacked=2), allow_stacked=True) == [])
check("detector 7 is refused", says(good(detector=7), "from 1 to 6"))
check("detector as numpy int is refused (must be a plain int)", says(good(detector=np.int64(3)), "plain int"))
check("detector True is refused", says(good(detector=True), "plain int"))
check("flags int64 is refused", says(good(flags=np.zeros((6, 6), dtype=np.int64)), "int32"))
check("flags big-endian int32 is refused", says(good(flags=np.zeros((6, 6), dtype=">i4")), "native"))
check("flags of a different shape are refused", says(good(flags=np.zeros((5, 6), dtype=np.int32)), "shape"))
check("variance float32 is refused", says(good(variance=np.ones((6, 6), dtype=np.float32)), "float64"))
check("source_file as a number is refused", says(good(source_file=3), "text"))

frames = [good(obs_time=datetime(2026, 1, 2)), good(obs_time=datetime(2026, 1, 1))]
found = contract.list_problems(frames)
check("an unsorted list is reported", any("not sorted" in p for p in found))
check("a sorted list of good frames is fine", contract.list_problems(frames[::-1]) == [])
check("problems of a list name the frame", any(p.startswith("frame 1:") for p in contract.list_problems([good(), good(detector=9)])))
check("an empty list is fine", contract.list_problems([]) == [])
sig = contract.type_signature(good())
check("type_signature has the 8 keys", list(sig) == list(contract.FRAME_KEYS))
check("signature of arrays has dtype and dimensions", sig["image"] == ("ndarray", "float64", 2) and sig["flags"] == ("ndarray", "int32", 2))
check("signatures do not depend on the size", contract.type_signature(good(size=9)) == sig)
check("signatures differ when a type differs", contract.type_signature(good(detector=np.int64(3))) != sig)

print("\n--- Part 2: the mock frames (needs astropy and the mock files) ---")
mock_frames = None
mock_file = config.MOCK_DIR / "mock_00.fits"
try:
    from astropy.io import fits
    import data_mock
    import data_irsa
except ImportError:
    print("SKIPPED  astropy (or a project module) cannot be imported here")
    fits = None
else:
    if not mock_file.exists():
        print("SKIPPED  no mock files. Run:  python data_mock.py")
    else:
        h = fits.getheader(mock_file)
        mock_frames = data_mock.get_frames(h["CRVAL1"], h["CRVAL2"], 6.0)
        check("12 mock frames", len(mock_frames) == 12)
        found = contract.list_problems(mock_frames)
        for p in found[:10]:
            print("        problem:", p)
        check("every mock frame follows the contract", found == [])
        check("the keys are exactly data_irsa.FRAME_KEYS", all(set(f) == set(data_irsa.FRAME_KEYS) for f in mock_frames))
        check("contract.FRAME_KEYS equals data_irsa.FRAME_KEYS", contract.FRAME_KEYS == data_irsa.FRAME_KEYS)

print("\n--- Part 3: a fake real cutout read by data_irsa.read_cutout ---")
real_like = None
if fits is None:
    print("SKIPPED  needs astropy")
else:
    def fake_cutout():
        """Like test_data_irsa.fake_cutout: rotated WCS, big-endian arrays as in the real files."""
        rng = np.random.default_rng(0)
        h = fits.Header()
        h["DETECTOR"] = 3
        h["DATE-OBS"] = "2025-05-05T16:48:02.459"
        h["CTYPE1"], h["CTYPE2"] = "RA---TAN", "DEC--TAN"
        h["CUNIT1"], h["CUNIT2"] = "deg", "deg"
        h["CRVAL1"], h["CRVAL2"] = 133.4, -9.0
        h["CRPIX1"], h["CRPIX2"] = 29.0, 30.0
        h["CDELT1"], h["CDELT2"] = 1.0, 1.0
        h["PC1_1"], h["PC1_2"] = 0.0016235783793, -0.0006013768757
        h["PC2_1"], h["PC2_2"] = -0.00054089308468, -0.00159935379439
        return fits.HDUList([fits.PrimaryHDU(),
                             fits.ImageHDU(rng.normal(0.2, 0.1, (59, 58)).astype(">f4"), header=h, name="IMAGE"),
                             fits.ImageHDU(np.full((59, 58), 1 << 21, dtype=">i4"), name="FLAGS"),
                             fits.ImageHDU(np.full((59, 58), 0.0003, dtype=">f4"), name="VARIANCE")])

    real_centre = data_irsa.centre_wavelength
    data_irsa.centre_wavelength = lambda hdulist: 2.5
    try:
        real_like = data_irsa.read_cutout(fake_cutout(), "https://irsa.ipac.caltech.edu/x.fits")
    finally:
        data_irsa.centre_wavelength = real_centre
    found = contract.frame_problems(real_like)
    for p in found:
        print("        problem:", p)
    check("a frame from read_cutout follows the contract (big-endian input made native)", found == [])

print("\n--- Part 4: saved real cutouts (needs astropy and cache/real_cutouts/) ---")
folder = config.CACHE_DIR / "real_cutouts"
saved = sorted(folder.glob("*.fits")) if folder.exists() else []
if fits is None or not saved:
    print("SKIPPED  no saved real cutouts. They come from inspect_real_files.py.")
else:
    real_frames = []
    for path in saved:
        hdul = fits.open(path, memmap=False)
        try:
            for hdu in hdul:
                hdu.data
        finally:
            hdul.close()
        real_frames.append(data_irsa.read_cutout(hdul, path.name))
    print(f"   {len(real_frames)} saved cutouts read")
    real_frames.sort(key=lambda f: f["obs_time"])
    found = contract.list_problems(real_frames)
    for p in found[:10]:
        print("        problem:", p)
    check("every real frame follows the contract", found == [])
    if mock_frames:
        same = all(contract.type_signature(f) == contract.type_signature(mock_frames[0]) for f in real_frames)
        if not same:
            for k, v in contract.type_signature(mock_frames[0]).items():
                w = contract.type_signature(real_frames[0])[k]
                if v != w:
                    print(f"        {k}: mock {v} / real {w}")
        check("real and mock frames have identical keys and types", same)

print("\nAll checks passed." if problems == 0 else f"\n{problems} check(s) FAILED.")