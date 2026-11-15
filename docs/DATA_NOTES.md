## Real data: first look (Backend 26)

### From IRSA's tutorials (read 2026-11-15, not yet checked by running code)

- Wide-survey collections: spherex_dr1, spherex_qr3. QR3 and DR1 supersede QR2.
- TAP tables: spherex.artifact (a) joined to spherex.plane (p) on a.planeid = p.planeid.
  Columns used by the tutorial: a.uri, p.time_bounds_lower, p.energy_bandpassname, p.poly.
  Cutout link = 'https://irsa.ipac.caltech.edu/' || a.uri || '?center=RA,DECd&size=SIZE'.
- TAP sees new data right after ingestion (weekly); SIA lags about a day.
- Extensions: PRIMARY (no data), IMAGE (MJy/sr), FLAGS, VARIANCE, ZODI, EPSF, WCS-WAVE.
- IMAGE header cards used by the tutorial: DETECTOR, BUNIT, OBSID, DATE, PSF_FWHM.
- Wavelength: WCS(header, fobj=hdulist, key="W"), then .sip = None, then pixel_to_world(x, y)
  gives (wavelength, bandwidth).
- Bands: D1 0.75-1.09, D2 1.10-1.62, D3 1.63-2.41, D4 2.42-3.82, D5 3.83-4.41, D6 4.42-5.00 um.
- In the tutorial runs a few cutout downloads failed (4 of 84 in serial, 15 in parallel).

### What I saw when I ran try_real_query.py (2026-11-15)

- TAP (sync, astroquery): FAILED twice after about 400 s with "502 Proxy Error" (/TAP/sync). Async not tried.
- SIA (collections spherex_dr1, spherex_qr3): 258 images for WISE 0855 in 4.3 s.
  Per bandpass: D1 36, D2 48, D3 45, D4 36, D5 48, D6 45.
- SIA t_min is an MJD: first 60800.700028 (2025-05-05), last 61174.287218 (2026-05-14).
- Header: DATE-OBS / MJD-OBS (also DATE-BEG, DATE-AVG, DATE-END, TIMESYS=UTC) hold the
  observation time. DATE is the processing date (2026-07-17), not the observation.
  PRIMARY has VERSION = 7.0.5. OBSID = 2025W19_1B_0116_1.
- Cutout link = SIA access_url + ?center=RA,DECd&size=0.1 (size in degrees). Worked.
- Cutout size for 6 arcmin: 59x58, 59x59, 58x58 pixels; pixel scale 6.15-6.16 arcsec.
- DETECTOR printed as 3, 6, 6. Wavelength at the target: 2.3634 um (D3), 4.9674 and 5.0034 um (D6).
- FLAGS header holds 22 flag bits (MSKN/MSKD); same list as in IRSA's tutorial.
- IMAGE (first cutout): 0.0% NaN, min -2.043, median 0.149, max 33.11 MJy/sr.
- Downloads: 18.5 s, 26.8 s (after one HTTPError retry), 13.5 s per cutout.
- Picture of the first cutout: the centre is empty. Possible centring or proper-motion problem. Check in after-data #12.
- Surprises: cutouts differ in size by a pixel; one position has 258 images.

## After-data #3, #4, #5: checked on real data (try_saved_cutouts.py, 2026-11-15)

- IRSA's SIA search answered "502 Proxy Error" on https://irsa.ipac.caltech.edu/SIA/capabilities, so
  search_images could not be tried (it retried 3 times and raised its planned TimeoutError). The cutout
  service worked.
- Download: the known D3 link (center=133.75976461144327,-7.242186d&size=0.1) downloaded in 17.8 s on the
  first try. Its FLAGS equal the saved D3 file from inspect_real_files.py. The HDUList can be used after
  closing the file, as long as every extension was read first.
- read_cutout on the six saved cutouts (one per detector): detector int 1 to 6, shapes (59,58), (59,59),
  (59,58), (58,58), (59,59), (59,59), obs_time from DATE-OBS (for example D1 2025-05-06T12:20:24.888),
  centre wavelength equal to the inspect report to 4 decimals (0.9926, 1.5151, 2.3632, 3.3582, 4.2950, 4.9674 um).
- wavelength_map ranges (um): D1 0.9867-0.9985, D2 1.5058-1.5246, D3 2.3491-2.3773, D4 3.3357-3.3808,
  D5 4.2855-4.3045, D6 4.9577-4.9771. All inside the nominal band edges. The pixel (x=0, y=0) is the
  longest wavelength and the (x=0, y=ny-1) corner the shortest, so the wavelength changes mostly along y.
  The call takes 0.01-0.02 s per cutout.
- A frame holding a real SIP WCS survives pickle (the cache works with real frames).
- astropy prints an INFO message ("SIP coefficients were detected, but CTYPE is missing a -SIP suffix")
  when the spectral "W" WCS is built. It is harmless: sip is set to None for that WCS and the wavelengths match
  the report. It is not silenced yet.
