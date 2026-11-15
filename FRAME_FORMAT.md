# Frame format

Each frame is a dictionary with:

- image: 2D numpy array (pixel values)
- wcs: astropy WCS object (pixel <-> sky conversion)
- obs_time: observation date/time (UTC)
- wavelength_um: band center in microns
- detector: detector number 1-6
- flags: 2D array of bad-pixel/contamination flags (or None)
- variance: 2D array of noise estimates (or None)
- source_file: where it came from

A data source function has this signature:
get_frames(ra_deg, dec_deg, fov_arcmin) -> list of frames sorted by obs_time

## Extra rules found in the real files (2026-11-15, all six detectors)

- Arrays must be NORMAL (native byte order): the files store big-endian
  numbers (FLAGS is >i4), so data_irsa.read_cutout converts: image and
  variance to float64, flags to int32.
- obs_time is a naive datetime in UTC (no timezone), like the mock frames.
- detector is a plain int 1-6.
- wavelength_um is the value at the CENTRE of the cutout. A real cutout changes
  by 0.01 to 0.05 um from corner to corner. Per-pixel values come from
  data_irsa.wavelength_map(), which is not a frame key.
- The wcs of a REAL frame is not north-up: the picture is rotated by about 160
  degrees and has SIP distortion. The mock WCS is north-up. Code that assumes
  north up (PNG flip, hover, marker) needs the frames re-aligned onto one
  north-up grid first (TODO after-data #30).
- Real cutouts of one request differ by a pixel in size (58 or 59 pixels).
- The frame list may be longer than the mock's 12 frames (258 for one position).
- contract.py checks these rules in code (python test_contract.py).
- Mock frames follow the same contract: data_mock.load_mock_frame converts flags to native
  int32 (FITS files give big-endian). Mock and real frames have identical keys and types
  (checked by test_contract.py).
