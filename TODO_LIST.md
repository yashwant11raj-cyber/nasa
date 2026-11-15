# SPHEREx Sky Viewer: Project To-Do List

Backend and Frontend, before and after the data arrives.
This file replaces Todo_List.pdf. Nothing is ticked.

**How to read it**

- Work top to bottom inside each list. The order is the priority order.
- Numbers in brackets such as (#13) match Priority_list.txt.
- Items marked **(new)** were added after the original list. Everything else is from the original list.
- Part letters: A Data, B Processing, C API, D Frontend, E Config/targets, F Extras, G Project support.

---

## 1. BACKEND: Do now (before the data)

1. [✔] Create workflow files (Part G)
   PROGRESS.md, FRAME_FORMAT.md, docs/DATA_NOTES.md, rules file and .gitignore. Then commit to Git.
2. [✔] Verify the 5 targets (Part E)
   Use a SIMBAD script for exact RA/Dec and proper motion. Then write targets.py.
3. [✔] Mock data generator (#1) (Part A)
   Make about 12 fake FITS frames with a moving dot, a WCS, dates, and detector and wavelength in the header.
4. [✔] Mock FLAGS and VARIANCE (Part A)
   Add them to the mock frames so flags and noise features can be built and tested early.
5. [✔] Cutout, stretch, PNG (#2, #12) (Part B)
   Cut by sky position using WCS, apply percentile/log/sqrt stretch, save as PNG.
6. [✔] Config switch (Part E)
   Create config.py with USE_MOCK, default FOV, max frames and the release name.
7. [✔] Config limits and units (new) (Part E)
   Add MIN_FOV_ARCMIN and MAX_FOV_ARCMIN. Add DEFAULT_FOV_ARCMIN so everything uses arcminutes (config.py currently has degrees, FRAME_FORMAT.md uses arcminutes).
8. [✔] Cache (Part A)
   Save cutouts in cache/ keyed by RA, Dec, FOV and release so repeat requests are instant.
9. [✔] Frames endpoint (#3, M3) (Part C)
   Return the frame list with image links, dates, detectors and wavelengths. Also serve static/. Include the pixel scale and centre so the page can show sky positions on hover (new).
10. [✔] Flexible coordinate input (new) (Part E)
    A helper that accepts plain degrees and sexagesimal text such as 08h55m10.8s -07d14m42s. Rejects nonsense with a friendly message.
11. [✔] URL parameters and validation (#7, #9) (Part C)
    Accept ra, dec, fov, mode, stretch. Reject bad ranges (RA 0-360, Dec -90 to 90).
12. [✔] Search by name (new) (Part E)
    Type "Barnard's Star" instead of numbers. Check our 5 local targets first, then astropy's name lookup. The CDS name service may be down (see PROGRESS.md), so show a friendly message if it fails.
13. [✔] Targets endpoint (#6, #8) (Part C)
    Send the 5 presets to the page so the buttons come from one source.
14. [✔] Friendly errors (#11) (Part C)
    Return clear JSON messages for no images, bad input, slow data and server errors.
15. [✔] FOV handling (#9) (Part B)
    Make cutout size a parameter and set sensible minimum and maximum limits.
16. [✔] asinh stretch (new) (Part B)
    Add "asinh" to the stretch modes. Good for faint things next to bright ones.
17. [✔] Background-level matching (new) (Part B)
    Make the background level the same in every frame, so flicker is not mistaken for movement. Switchable on and off.
18. [✔] Difference imaging (#13) (Part B)
    Support "subtract first frame" and "subtract previous frame" on mock data.
19. [✔] Stacking and adding (#14, added) (Part B)
    Sum or average frames per detector to cut noise. Also offer a plain "add" option.
20. [✔] Motion trail data (new) (Part B)
    Work out the dot's pixel position in each frame so the page can draw a line through them.
21. [✔] Colour picture from 3 wavelengths (new) (Part B)
    Use three bands as red, green and blue to make one colour image. Test on mock data first.
22. [✔] Expected-path function (new) (Part E)
    Use position_at_epoch() to return where a known star should be on each frame's date. Add a small endpoint for it (Part C).
23. [✔] Practice mock files (new) (Part A)
    A second mock set with several dots moving at different speeds, for the practice game. Keep the answers in a separate file.
24. [✔] Practice game answer check (new) (Part C)
    A small endpoint that says whether a clicked position is close enough to a hidden mover.
25. [✔] Real data skeleton (#5) (Part A)
    Create data_irsa.py with empty documented functions and the same output format as the mock.
26. [✔] Try one real query by hand (Part A)
    Follow the IRSA intro tutorial for WISE 0855. Record what you see in DATA_NOTES.md.
27. [✔] Easy-update design (added) (Part A)
    Keep the release/collection name in config and query live instead of listing files.
28. [✔] Skip mostly-bad frames (new) (Part A)
    If a frame is mostly flagged bad, leave it out. Test the idea on mock flags first.
29. [✔] Flags and metadata (#16) (Part F)
    Write flags.py that decodes bits using a table you can swap in once real bit meanings are loaded.
30. [✔] "Is it real?" check (new) (Part F)
    Compare neighbouring frames. Warn when the detector or wavelength changed, or when flagged pixels sit near the dot.
31. [✔] Spectrum function (#15) (Part F)
    Write spectra.py that builds brightness vs wavelength from mock frames at one pixel.
32. [✔] Spectrum comparison (new) (Part F)
    Let spectra.py return two spectra (the mover and a fixed star) so they can be plotted together.
33. [✔] Overlay catalog function (#17) (Part F)
    Write overlays.py that fetches Gaia/WISE sources with astroquery and returns pixel positions.
34. [✔] GIF export (#19) (Part C)
    Add an endpoint or helper that bundles the frames into an animated GIF with Pillow.
35. [✔] Export a find as CSV (new) (Part C)
    An endpoint that returns the marked positions, dates and wavelengths as a CSV file.
36. [✔] Auto-find movers, optional (new) (Part B)
    Highlight dots that sit in different places across frames. May need a new library, so ask first. Skip if time is short.
37. [✔] Tests (added) (Part G)
    Add small tests per part (ask before installing pytest). Run them before each commit.
38. [✔] README and requirements (M9) (Part G)
    Document setup, running, URL parameters and the data release used.
39. [✔] Future-work notes (new) (Part G)
    A short docs page: automatic mover detection, a "report a find" button, a bigger sky-survey view.

---

## 2. FRONTEND: Do now (before the data)

1. [✔] Page skeleton (M4) (Part D)
   Create index.html, app.js and style.css with the layout from the design sketch.
2. [✔] Show one image (#2) (Part D)
   Fetch one PNG from the API and display it on the page.
3. [✔] RA/Dec form (#3) (Part D)
   Add inputs and a Go button so typing new coordinates changes the image.
4. [✔] Flexible coordinates and name search box (new) (Part D)
   One box that accepts degrees, sexagesimal text or a name like "Barnard's Star".
5. [✔] Animation player (#4) (Part D)
   Add play/pause, a frame slider and a speed control that step through the frames.
6. [✔] Frame counter and loop toggle (new) (Part D)
   Show "5 / 12" next to the slider. Add a loop on/off switch.
7. [✔] Keyboard shortcuts and swipe (new) (Part D)
   Space = play/pause, arrow keys = step, swipe left/right on phones.
8. [✔] Preset buttons (#8, #6) (Part D)
   Create one button per test target, loaded from the targets endpoint.
9. [✔] URL parameters (#7) (Part D)
   Read settings from the URL on load. Update the URL whenever settings change. 10.[✔] Copy-link button (new) (Part D)
   One click copies the shareable URL.
10. [✔] FOV control (#9) (Part D)
    Add a dropdown or slider that reloads the frames at the new size.
11. [✔] Frame info panel (#10) (Part D)
    Show date, detector, wavelength and flags status for the frame on screen.
12. [✔] Wavelength colour strip (new) (Part D)
    A rainbow bar under the slider showing each frame's wavelength. Click a block to jump to that frame.
13. [✔] Spinner and errors (#11) (Part D)
    Show a loading indicator and display the API's friendly error messages.
14. [✔] Stretch control (#12) (Part D)
    Add a brightness slider that requests a new stretch from the API.
15. [✔] Stretch type dropdown (new) (Part D)
    Choose linear, sqrt, log or asinh. Add a "match background" checkbox.
16. [✔] Mode switch (#13, #14) (Part D)
    Add Normal / Difference / Stack buttons that change the request mode.
17. [✔] Blink compare (new) (Part D)
    Pick two frames and flip quickly between them, like the Pluto discoverers did.
18. [✔] Colour picture toggle (new) (Part D)
    A switch that shows the 3-wavelength colour image instead of grey.
19. [✔] Embed mode (added) (Part D)
    Add ?embed=1 to hide the header and extra controls for use inside other pages.
20. [✔] Marker tool (#18) (Part D)
    Let users click to place a circle that follows the same sky position through the frames.
21. [✔] Trail and expected-path toggles (new) (Part D)
    Draw a line through the dot's positions. Draw a second marker where proper motion says the star should be.
22. [✔] Hover readout (new) (Part D)
    Move the mouse over the image to see the pixel's brightness and its RA/Dec.
23. [✔] Magnifier (new) (Part D)
    A small zoom lens that enlarges the area under the mouse without reloading.
24. [✔] GIF download button (#19) (Part D)
    Add a button that calls the GIF endpoint and saves the file.
25. [✔] Export CSV button (new) (Part D)
    Download the marked positions and dates.
26. [✔] Placeholders for extras (#15-#17) (Part D)
    Reserve space for the spectrum plot, flags legend and overlay toggle (Aladin Lite or markers).
27. [✔] "Is it real?" hint (new) (Part D)
    A small badge on each frame: green = fine, yellow = detector or wavelength changed, red = flagged pixels near the target.
28. [✔] Design and mobile layout (#20) (Part D)
    Use a dark theme. Stack controls under the image on phones. Test at narrow widths.
29. [✔] Polish and accessibility (new) (Part D)
    Page title and favicon, tooltips on buttons, a "reset view" button, a hidden-until-needed advanced panel, colour-blind-friendly colours, labels for screen readers.
30. [✔] Beginner tutorial (#20) (Part D)
    Write a short "how to spot a moving object" panel with simple steps.
31. [✔] Guided mission (new) (Part D)
    An interactive step-by-step "find the moving dot" lesson using WISE 0855.
32. [✔] Practice game page (new) (Part D)
    Find hidden fake movers in the practice mock data. Shows a score using the answer-check endpoint.

---

## 3. BACKEND: After the data comes in

1. [✔] Inspect real files (Part A)
   Open one real cutout, list extensions and header keywords, update FRAME_FORMAT.md if needed.
2. [ ] Real image search (#5) (Part A)
       Implement search_images in data_irsa.py with the SIA query (collections from config.SPHEREX_SIA_COLLECTIONS), sorted by t_min.
3. [✔] Real cutout download (Part A)
   Implement download_cutout. The link is the SIA access_url plus ?center=RA,DECd&size=DEGREES, verified by download in Backend 26.
4. [✔] Read real cutouts (Part A)
   Pull IMAGE, FLAGS, VARIANCE, WCS, DETECTOR and DATE into the frame format.
5. [✔] Wavelength map (Part A)
   Read the WCS-WAVE extension to get the wavelength at each pixel.
6. [✔] Contract test (Part G)
   Check that real frames and mock frames have identical keys and types.
7. [✔] Cleaning (Part A)
   Handle NaN pixels and mask bad flags using the bit table in the Explanatory Supplement.
8. [✔] Sort, group, limit (Part A)
   Order frames by date, group by detector, and cap the number of frames per request.
9. [ ] Skip mostly-bad frames on real flags (new) (Part A)
       Re-tune the "too many bad pixels" limit using the real flag bits. 10.[✔] Robust downloading (Part A)
       Add longer timeouts, retries, caching of real cutouts and "no images" handling.
10. [ ] Edge cases (Part A, B)
        Handle targets near image edges, partial cutouts and different pointings.
11. [ ] WISE 0855 first (Part E)
        Test it end to end, then check the motion direction against its proper motion.
12. [ ] All 5 targets (#6) (Part E)
        Verify each one returns frames. Fix coordinates in targets.py if needed.
13. [ ] Name search check (new) (Part E)
        Confirm all 5 names resolve (locally and through the online lookup) and note whether the CDS service is back.
14. [ ] Retune processing (Part B)
        Adjust stretch defaults for real units (MJy/sr). Tune difference and stack on real noise.
15. [ ] Retune background matching and asinh (new) (Part B)
        Check both on real frames and adjust the defaults.
16. [ ] Real flags (#16) (Part F)
        Decode FLAGS with the correct bit meanings and return per-frame contamination info.
17. [ ] Real "Is it real?" check (new) (Part F)
        Use real detector, wavelength and flag information, and tune the warning thresholds.
18. [ ] Real spectra (#15) (Part F)
        Build the spectrum from the real wavelength map and fluxes (ask before installing SPXQuery).
19. [ ] Real spectrum comparison (new) (Part F)
        Compare WISE 0855 with a nearby fixed star on real data.
20. [ ] Real overlays (#17) (Part F)
        Fetch Gaia/WISE sources and account for proper motion between epochs.
21. [ ] Expected-path check (new) (Part E)
        Compare the predicted path with the real dot for WISE 0855 and Barnard's Star. Fix any offset.
22. [ ] Real colour picture (new) (Part B)
        Choose which 3 bands to use as red, green and blue. Keep detector differences in mind.
23. [ ] Auto-find test, optional (new) (Part B)
        Try the mover finder on real frames. Keep it only if it works.
24. [ ] Export CSV check (new) (Part C)
        Confirm exported positions and dates match the real frames.
25. [ ] Update path (added) (Part A)
        Make switching to a newer release a one-line config change, and test it.
26. [ ] Performance (Part A, C)
        Measure load time per FOV, limit large requests, and pre-cache the 5 targets for demos.
27. [ ] Public hosting plan (Part G)
        Pick a host, set limits to protect the server, and test from another device.
28. [ ] Update docs and commit (Part G)
        Record what works in PROGRESS.md and DATA_NOTES.md. Update the README.
29. [ ] Re-align frames and default frame limit (new): resample all cutouts onto one pixel grid, then apply a default limit (for example one detector). Needed before difference, stack, trail, colour, movers and GIF work on real data.

---

## 4. FRONTEND: After the data comes in

1. [ ] Switch to real data (Part D)
       Turn mock off and check that every control still works with real frames.
2. [ ] Real frame info (#10) (Part D)
       Show true date, detector, wavelength and quality info in the panel.
3. [ ] Wavelength warning (Part D)
       Add a note or detector filter so colour changes are not mistaken for real changes.
4. [ ] "Is it real?" badge on real data (new) (Part D)
       Check the green/yellow/red badge makes sense on real frames.
5. [ ] Stretch ranges (#12) (Part D)
       Retune the brightness slider limits for real data.
6. [ ] Slow-load handling (#11) (Part D)
       Show progress text for slow downloads and add a cancel or retry button.
7. [ ] No-data message (#11) (Part D)
       Show a clear message when a spot has no SPHEREx images or is at the edge.
8. [ ] Preset check (#8) (Part D)
       Confirm each target button shows the expected result, such as WISE 0855 moving.
9. [ ] Name search test (new) (Part D)
       Try all 5 target names and a few misspellings. Check the error message is friendly.
10. [ ] Speed and frame order (#4) (Part D)
        Set a default animation speed that makes small shifts visible.
11. [ ] Difference and stack views (#13, #14) (Part D)
        Tune labels and defaults so moving objects pop out on real frames.
12. [ ] Blink compare test (new) (Part D)
        Pick two frames of WISE 0855 and check the jump is easy to see.
13. [ ] Marker tool test (#18) (Part D)
        Confirm the marker tracks WISE 0855 and Barnard's Star correctly.
14. [ ] Trail and expected-path test (new) (Part D)
        Check the trail and the predicted marker line up with the real dot.
15. [ ] Flags display (#16) (Part D)
        Show a real legend and highlight flagged pixels or frames.
16. [ ] Spectrum plot (#15) (Part D)
        Plot clicked-pixel spectra with real axes (wavelength in microns, flux units).
17. [ ] Spectrum comparison plot (new) (Part D)
        Show the mover and a fixed star on one graph with a legend.
18. [ ] Overlays (#17) (Part D)
        Add the Gaia/WISE toggle and check that markers line up with real stars.
19. [ ] Colour strip and colour picture check (new) (Part D)
        Check the wavelength strip shows the real bands and the colour picture looks sensible.
20. [ ] GIF download (#19) (Part D)
        Test GIF size and speed with real frames.
21. [ ] Hover readout and magnifier test (new) (Part D)
        Check real brightness values, units and RA/Dec under the mouse.
22. [ ] Embed and URL test (#7, added) (Part D)
        Paste a URL and an embed=1 link into a separate page to check they work.
23. [ ] Accessibility and keyboard check (new) (Part D)
        Use the page with the keyboard only. Check colours for colour-blind users.
24. [ ] Mobile and design polish (#20) (Part D)
        Test on a real phone (including swipe) and tidy spacing, colours and labels.
25. [ ] Tutorial update (#20) (Part D)
        Add real screenshots and a worked example (WISE 0855) to the help panel.
26. [ ] Guided mission with real data (new) (Part D)
        Update the mission steps with real WISE 0855 frames and screenshots.
27. [ ] Demo materials (M9) (Part G)
        Record a demo video, take screenshots and write a short script for judges.
28. [ ] Many frames (new): load only some frames at first and preload lazily (one position has 258).
