# config.py
# Central settings for the SPHEREx Sky Viewer.
# Other files do:  import config   and then use  config.USE_MOCK  etc.
# This file only holds settings. It never downloads or reads data.

from pathlib import Path

# ---------- Data source switch ----------
# True  = use the fake FITS files in data/mock/ (data_mock.py)
# False = use real SPHEREx data from IRSA (data_irsa.py, written later)
USE_MOCK = True

# ---------- Real data release ----------
# RELEASE_NAME is a LABEL used in the cache key (cache.current_release()).
# The real search (data_irsa.build_search_query) asks IRSA live and is NOT
# filtered by this name, so new weekly data shows up without any code change.
# To start with a fresh cache (for example after a new data release), change
# this ONE line. Old cache files are simply no longer used.
# IRSA's tutorials say DR1 and QR3 supersede QR2.
RELEASE_NAME = "spherex_dr1_qr3"

# IRSA collection names for the SIA search (names from IRSA's tutorial).
# Used by the SIA search (after-data #2). TAP failed with 502 on 2026-11-15, so SIA is the plan.
# switch to SIA (which lags about a day) is a one-place change.
# The deep-survey collections are spherex_dr1_deep and spherex_qr3_deep.
SPHEREX_SIA_COLLECTIONS = ("spherex_dr1", "spherex_qr3")

# ---------- Field of view ----------
# All field-of-view values in this project use ARCMINUTES (see FRAME_FORMAT.md).
# The limits below are enforced by params.py (Backend 11) and sent to the
# page by GET /api/limits (Backend 15).
MIN_FOV_ARCMIN = 1.0       # smallest patch allowed (guess; retune on real data)
DEFAULT_FOV_ARCMIN = 6.0   # matches the FOV used in test_processing.py
# Must be big enough to show Eps Ind B and its star (about 6.7 arcmin apart).
# Bigger patches mean slower downloads on real data.
MAX_FOV_ARCMIN = 30.0      # largest patch allowed (guess; retune on real data)

# ---------- Limits ----------
# Most frames returned for one request. 50 is a starting guess; retune on real data.
MAX_FRAMES = 50

# ---------- Folders ----------
BASE_DIR = Path(__file__).parent
MOCK_DIR = BASE_DIR / "data" / "mock"   # where data_mock.py writes the fake files
PRACTICE_DIR = BASE_DIR / "data" / "practice"   # where data_practice.py writes the practice files
CACHE_DIR = BASE_DIR / "cache"          # used by the cache step later (Backend 8)


if __name__ == "__main__":
    # Quick self-test: run  python config.py
    print("USE_MOCK           :", USE_MOCK)
    print("RELEASE_NAME       :", RELEASE_NAME, "(cache label)")
    print("MIN_FOV_ARCMIN     :", MIN_FOV_ARCMIN)
    print("DEFAULT_FOV_ARCMIN :", DEFAULT_FOV_ARCMIN)
    print("MAX_FOV_ARCMIN     :", MAX_FOV_ARCMIN)
    print("FOV order OK (min <= default <= max):",
          MIN_FOV_ARCMIN <= DEFAULT_FOV_ARCMIN <= MAX_FOV_ARCMIN)
    print("MAX_FRAMES         :", MAX_FRAMES)
    print("MOCK_DIR           :", MOCK_DIR, "| exists:", MOCK_DIR.exists())
    print("CACHE_DIR          :", CACHE_DIR)