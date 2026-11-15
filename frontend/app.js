// SPHEREx Sky Blink: Tasks 1-14 and 16-29 (Task 15 is blocked, see FRONTEND_PROGRESS.md).
// Only uses what API_GUIDE.md describes:
//   GET /api/targets?year=2026    -> the 5 preset targets
//   GET /api/limits               -> FOV min / max / default (arcminutes)
//   GET /api/frames?ra=&dec=&fov=&stretch=&mode=&match=&ref=&group=  -> frame list
//   GET /api/expected-path?target=&ra=&dec=&fov=&mode=&group=        -> expected positions

// ---------------------------------------------------------------
// 1. Page elements
// ---------------------------------------------------------------
const skyImage = document.getElementById("sky-image");
const stage = document.getElementById("stage");
const stageMessage = document.getElementById("stage-message");
const statusLine = document.getElementById("status");
const spinner = document.getElementById("spinner");
const overlay = document.getElementById("overlay"); // Tasks 21-22
const lens = document.getElementById("lens"); // Task 24
const readout = document.getElementById("readout"); // Task 23

const coordForm = document.getElementById("coord-form");
const raInput = document.getElementById("ra-input");
const decInput = document.getElementById("dec-input");
const fovSelect = document.getElementById("fov-select");

const nameForm = document.getElementById("name-form");
const nameInput = document.getElementById("name-input");

const playButton = document.getElementById("play-button");
const slider = document.getElementById("frame-slider");
const speedSelect = document.getElementById("speed-select");
const counter = document.getElementById("frame-counter");
const loopToggle = document.getElementById("loop-toggle");

const waveStrip = document.getElementById("wave-strip");
const stripMin = document.getElementById("strip-min");
const stripMax = document.getElementById("strip-max");

const presetList = document.getElementById("preset-list");
const copyButton = document.getElementById("copy-link");

// Tasks 16-17: view settings
const modeButtons = Array.from(document.querySelectorAll(".mode-btn"));
const stretchSelect = document.getElementById("stretch-select");
const matchToggle = document.getElementById("match-toggle");
const refRow = document.getElementById("ref-row");
const refSelect = document.getElementById("ref-select");
const groupRow = document.getElementById("group-row");
const groupSelect = document.getElementById("group-select");

// Task 18: blink
const blinkA = document.getElementById("blink-a");
const blinkB = document.getElementById("blink-b");
const blinkButton = document.getElementById("blink-button");

// Tools and saving
const expectedToggle = document.getElementById("expected-toggle");
const magnifierToggle = document.getElementById("magnifier-toggle");
const clearMarkerButton = document.getElementById("clear-marker");
const csvButton = document.getElementById("csv-button");
const gifButton = document.getElementById("gif-button");

const info = {
  date: document.getElementById("info-date"),
  detector: document.getElementById("info-detector"),
  wave: document.getElementById("info-wave"),
  stacked: document.getElementById("info-stacked"),
  source: document.getElementById("info-source"),
  real: document.getElementById("info-real"), // Task 28
};

// ---------------------------------------------------------------
// 2. Things the page remembers
// ---------------------------------------------------------------
let frames = [];
let currentIndex = 0;
let timer = null;
let blinkTimer = null;
let targets = [];
let latestRequest = 0;
let source = ""; // the "source" label from /api/frames

let mode = "normal"; // normal | difference | stack
let lastRa = ""; // the position of the last load (used by reload())
let lastDec = "";
let currentTargetId = null; // set when a preset was used; needed by expected path
let marker = null; // {ra, dec} placed by clicking the picture
let showExpected = false;
let expectedPath = []; // from /api/expected-path, same numbering as frames

// Task 20: ?embed=1 hides the header and the controls
const isEmbed =
  new URLSearchParams(window.location.search).get("embed") === "1";
if (isEmbed) document.body.classList.add("embed");

// ---------------------------------------------------------------
// 3. Small helpers
// ---------------------------------------------------------------
function setStatus(text, isError = false) {
  statusLine.textContent = text;
  statusLine.classList.toggle("error", isError);
}

// Ask the server for JSON; on an error, throw the friendly "detail" sentence.
async function fetchJson(url) {
  let response;
  try {
    response = await fetch(url);
  } catch (networkError) {
    throw new Error(
      "Could not reach the server. Check that it is running (uvicorn main:app --reload).",
    );
  }
  let data = null;
  try {
    data = await response.json();
  } catch (parseError) {
    // body was not JSON
  }
  if (!response.ok) {
    throw new Error(
      data && data.detail
        ? data.detail
        : "Something went wrong (code " + response.status + ").",
    );
  }
  return data;
}

// "Barnard's Star" and "barnards star" both become "barnardsstar".
function simplifyName(text) {
  return String(text)
    .toLowerCase()
    .replace(/[\s'’`\-_]/g, "");
}

// ---------------------------------------------------------------
// 4. Sky <-> picture maths (Tasks 21, 23)
// ---------------------------------------------------------------
// Uses each frame's centre, pixel scale and size from /api/frames.
// ASSUMPTION (API_GUIDE.md): north is up and east is left. Recheck on real data.
// "fraction" = position inside the picture: fx 0 = left edge, 1 = right edge;
// fy 0 = top edge, 1 = bottom edge.

function fractionToSky(frame, fx, fy) {
  const scale = frame.pixel_scale_arcsec / 3600; // degrees per pixel
  const cosDec = Math.cos((frame.center_dec_deg * Math.PI) / 180);
  const dxPix = (fx - 0.5) * frame.width_px;
  const dyPix = (fy - 0.5) * frame.height_px;
  let ra = frame.center_ra_deg - (dxPix * scale) / cosDec; // east is left
  const dec = frame.center_dec_deg - dyPix * scale; // north is up
  ra = ((ra % 360) + 360) % 360;
  return { ra: ra, dec: dec };
}

function skyToFraction(frame, ra, dec) {
  const scale = frame.pixel_scale_arcsec / 3600;
  const cosDec = Math.cos((frame.center_dec_deg * Math.PI) / 180);
  let dra = ra - frame.center_ra_deg;
  if (dra > 180) dra -= 360; // handle the 0/360 wrap
  if (dra < -180) dra += 360;
  const dxPix = -(dra * cosDec) / scale;
  const dyPix = -(dec - frame.center_dec_deg) / scale;
  return {
    fx: 0.5 + dxPix / frame.width_px,
    fy: 0.5 + dyPix / frame.height_px,
  };
}

// Where is the mouse inside the picture? Returns null if outside it.
function pointInPicture(event) {
  if (skyImage.hidden || frames.length === 0) return null;
  const rect = skyImage.getBoundingClientRect();
  const fx = (event.clientX - rect.left) / rect.width;
  const fy = (event.clientY - rect.top) / rect.height;
  if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return null;
  return { fx: fx, fy: fy, rect: rect };
}

// ---------------------------------------------------------------
// 5. Overlay: marker circle (Task 21) and expected path (Task 22)
// ---------------------------------------------------------------
const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl(name, attrs) {
  const el = document.createElementNS(SVG_NS, name);
  Object.keys(attrs).forEach((key) => el.setAttribute(key, attrs[key]));
  return el;
}

// The SVG uses the PNG's own pixel size as its coordinates, so the
// png_x / png_y numbers from the API can be used as they are.
function drawOverlay() {
  overlay.replaceChildren();
  if (frames.length === 0 || skyImage.hidden || !skyImage.naturalWidth) return;
  const w = skyImage.naturalWidth;
  const h = skyImage.naturalHeight;
  overlay.setAttribute("viewBox", "0 0 " + w + " " + h);
  const line = Math.max(1.5, w / 200); // line thickness
  const radius = w * 0.05;

  // Task 22: expected path = dashed line through all dates, ring on the current one
  if (showExpected && expectedPath.length === frames.length) {
    const points = expectedPath.map((p) => p.png_x + "," + p.png_y).join(" ");
    overlay.appendChild(
      svgEl("polyline", {
        points: points,
        fill: "none",
        stroke: "#4dd0e1",
        "stroke-width": line,
        "stroke-dasharray": line * 3 + " " + line * 3,
      }),
    );
    const here = expectedPath[currentIndex];
    if (here && here.inside) {
      overlay.appendChild(
        svgEl("circle", {
          cx: here.png_x,
          cy: here.png_y,
          r: radius * 0.6,
          fill: "none",
          stroke: "#4dd0e1",
          "stroke-width": line * 1.5,
        }),
      );
    }
  }

  // Task 21: marker at a fixed sky position
  if (marker) {
    const f = skyToFraction(frames[currentIndex], marker.ra, marker.dec);
    if (f.fx >= 0 && f.fx <= 1 && f.fy >= 0 && f.fy <= 1) {
      overlay.appendChild(
        svgEl("circle", {
          cx: f.fx * w,
          cy: f.fy * h,
          r: radius,
          fill: "none",
          stroke: "#ffb454",
          "stroke-width": line * 1.5,
        }),
      );
    }
  }
}
skyImage.addEventListener("load", drawOverlay);

async function loadExpected() {
  expectedPath = [];
  if (!showExpected) {
    drawOverlay();
    return;
  }
  if (!currentTargetId) {
    showExpected = false;
    expectedToggle.checked = false;
    setStatus(
      "The expected path only works for the preset targets. Click a preset first.",
      true,
    );
    drawOverlay();
    return;
  }
  const thisRequest = latestRequest;
  // Same ra/dec/fov/mode/group as /api/frames, so entry N belongs to frame N.
  const base = currentParams(lastRa, lastDec);
  const query = new URLSearchParams({
    target: currentTargetId,
    ra: lastRa,
    dec: lastDec,
  });
  ["fov", "mode", "group"].forEach((key) => {
    if (base.has(key)) query.set(key, base.get(key));
  });
  try {
    const data = await fetchJson("/api/expected-path?" + query.toString());
    if (thisRequest !== latestRequest) return;
    expectedPath = data.path;
  } catch (error) {
    if (thisRequest !== latestRequest) return;
    setStatus(error.message, true);
  }
  drawOverlay();
}

expectedToggle.addEventListener("change", () => {
  showExpected = expectedToggle.checked;
  loadExpected();
});

// Click the picture to place the marker (Task 21).
stage.addEventListener("click", (event) => {
  const p = pointInPicture(event);
  if (!p) return;
  marker = fractionToSky(frames[currentIndex], p.fx, p.fy);
  drawOverlay();
  setStatus(
    "Marker at RA " +
      marker.ra.toFixed(4) +
      "°, Dec " +
      marker.dec.toFixed(4) +
      "°.",
  );
});

clearMarkerButton.addEventListener("click", () => {
  marker = null;
  drawOverlay();
});

// ---------------------------------------------------------------
// 6. Hover readout (Task 23) and magnifier (Task 24)
// ---------------------------------------------------------------
const LENS_SIZE = 120; // pixels (same as .lens in style.css)
const LENS_ZOOM = 3;

stage.addEventListener("mousemove", (event) => {
  const p = pointInPicture(event);
  if (!p) {
    lens.hidden = true;
    return;
  }
  const frame = frames[currentIndex];
  const sky = fractionToSky(frame, p.fx, p.fy);
  // Brightness is not in the API yet (see Requests for backend), so only RA/Dec.
  readout.textContent =
    "RA " +
    sky.ra.toFixed(4) +
    "°   Dec " +
    sky.dec.toFixed(4) +
    "°   (brightness: not available yet)";

  if (magnifierToggle.checked) {
    const stageBox = stage.getBoundingClientRect();
    lens.hidden = false;
    lens.style.left = event.clientX - stageBox.left - LENS_SIZE / 2 + "px";
    lens.style.top = event.clientY - stageBox.top - LENS_SIZE / 2 + "px";
    lens.style.backgroundImage = 'url("' + frame.image_url + '")';
    lens.style.backgroundSize =
      p.rect.width * LENS_ZOOM + "px " + p.rect.height * LENS_ZOOM + "px";
    lens.style.backgroundPosition =
      -(p.fx * p.rect.width * LENS_ZOOM - LENS_SIZE / 2) +
      "px " +
      -(p.fy * p.rect.height * LENS_ZOOM - LENS_SIZE / 2) +
      "px";
  } else {
    lens.hidden = true;
  }
});

stage.addEventListener("mouseleave", () => {
  lens.hidden = true;
  readout.textContent = "Move the mouse over the picture to see RA/Dec.";
});

magnifierToggle.addEventListener("change", () => {
  if (!magnifierToggle.checked) lens.hidden = true;
});

// ---------------------------------------------------------------
// 7. "Is it real?" badge (Task 28)
// ---------------------------------------------------------------
// Works only from what the frame list gives us. Compares a frame with the
// one before it. RED (flagged pixels near the target) needs flags, which
// the API does not have yet, so it is never shown for now.
const WAVE_CHANGE_LIMIT = 0.05; // 5 % change in wavelength: my own guess, retune on real data

function realCheck(index) {
  if (index === 0) return { level: "ok", text: "First frame" };
  const now = frames[index];
  const before = frames[index - 1];
  if (now.detector !== before.detector) {
    return {
      level: "warn",
      text: "Detector changed: a jump may not be real motion",
    };
  }
  const change =
    Math.abs(now.wavelength_um - before.wavelength_um) / before.wavelength_um;
  if (change > WAVE_CHANGE_LIMIT) {
    return { level: "warn", text: "Wavelength changed: brightness may differ" };
  }
  return { level: "ok", text: "Same detector and colour as the frame before" };
}

// ---------------------------------------------------------------
// 8. Show one frame (Tasks 2, 6, 12, 13, 28)
// ---------------------------------------------------------------
function showFrame(index) {
  currentIndex = index;
  const frame = frames[index];
  skyImage.src = frame.image_url; // ready to use: never build it ourselves
  skyImage.alt = "Sky image taken " + frame.obs_time;
  skyImage.hidden = false;
  stageMessage.hidden = true;
  stage.classList.add("can-click");
  slider.value = String(index);

  // Task 6: counter "5 / 12"
  counter.textContent = index + 1 + " / " + frames.length;

  // Task 12: info panel
  info.date.textContent = frame.obs_time;
  // API_GUIDE: detector 0 means "several detectors stacked"
  info.detector.textContent =
    frame.detector === 0 ? "several (stacked)" : frame.detector;
  info.wave.textContent = Number(frame.wavelength_um).toFixed(3) + " µm";
  info.stacked.textContent = frame.n_stacked;
  info.source.textContent = source;

  // Task 28: badge (text and colour)
  const check = realCheck(index);
  info.real.textContent = check.text;
  info.real.className = "badge " + check.level;

  // Task 13: highlight this frame in the colour strip
  Array.from(waveStrip.children).forEach((block, i) => {
    block.classList.toggle("current", i === index);
  });

  drawOverlay(); // markers move with the frame (the image "load" event redraws too)
}

function clearInfo() {
  counter.textContent = "0 / 0";
  Object.values(info).forEach((el) => {
    el.textContent = "-";
    el.className = "";
  });
  waveStrip.replaceChildren();
  stripMin.textContent = "";
  stripMax.textContent = "";
  blinkA.replaceChildren();
  blinkB.replaceChildren();
  blinkButton.disabled = true;
  overlay.replaceChildren();
  stage.classList.remove("can-click");
}

// ---------------------------------------------------------------
// 9. Task 13: wavelength colour strip
// ---------------------------------------------------------------
// One coloured block per frame. Short wavelength = violet, long = red.
function buildStrip() {
  waveStrip.replaceChildren();
  const waves = frames.map((f) => Number(f.wavelength_um));
  const low = Math.min(...waves);
  const high = Math.max(...waves);
  frames.forEach((frame, i) => {
    const t = high > low ? (frame.wavelength_um - low) / (high - low) : 0;
    const block = document.createElement("button");
    block.type = "button";
    block.style.background = "hsl(" + Math.round(270 - 270 * t) + ", 85%, 55%)";
    const label =
      "Frame " +
      (i + 1) +
      ": " +
      Number(frame.wavelength_um).toFixed(2) +
      " µm";
    block.title = label;
    block.setAttribute("aria-label", label);
    block.addEventListener("click", () => {
      pause();
      showFrame(i);
    });
    waveStrip.appendChild(block);
  });
  stripMin.textContent = low.toFixed(2) + " µm";
  stripMax.textContent = high.toFixed(2) + " µm";
}

// ---------------------------------------------------------------
// 10. Load the frames for a position (Tasks 3, 9, 11, 14, 16, 17)
// ---------------------------------------------------------------
// The settings that go to /api/frames (same names as the API).
function currentParams(ra, dec) {
  // URLSearchParams encodes special characters (like "+") for us.
  const params = new URLSearchParams({ ra: ra, dec: dec });
  if (fovSelect.value) params.set("fov", fovSelect.value);
  params.set("stretch", stretchSelect.value);
  params.set("mode", mode);
  params.set("match", matchToggle.checked ? "on" : "off");
  if (mode === "difference") params.set("ref", refSelect.value);
  if (mode === "stack") params.set("group", groupSelect.value);
  return params;
}

async function loadFrames(ra, dec) {
  const thisRequest = ++latestRequest;
  pause();
  setStatus("Loading...");
  spinner.hidden = false; // Task 14
  lastRa = ra;
  lastDec = dec;

  const params = currentParams(ra, dec);
  // Task 9: put the settings in the page address. "target" and "embed" are
  // only for this page; they are never sent to /api/frames.
  const pageParams = new URLSearchParams(params);
  if (currentTargetId) pageParams.set("target", currentTargetId);
  if (isEmbed) pageParams.set("embed", "1");
  history.replaceState(null, "", "?" + pageParams.toString());

  try {
    const data = await fetchJson("/api/frames?" + params.toString());
    if (thisRequest !== latestRequest) return;

    frames = data.frames;
    source = data.source;
    if (frames.length === 0) {
      throw new Error("No images were returned for this position.");
    }

    // Preload every picture so the animation does not flicker.
    frames.forEach((frame) => {
      const preload = new Image();
      preload.src = frame.image_url;
    });

    slider.max = String(frames.length - 1);
    slider.disabled = frames.length < 2;
    playButton.disabled = frames.length < 2;
    gifButton.disabled = false;

    buildStrip();
    buildBlinkChoices();
    showFrame(0);
    setStatus(
      "Loaded " + frames.length + " frames (source: " + data.source + ").",
    );
    loadExpected(); // Task 22 (does nothing if the toggle is off)
  } catch (error) {
    if (thisRequest !== latestRequest) return;
    frames = [];
    expectedPath = [];
    skyImage.hidden = true;
    stageMessage.hidden = false;
    stageMessage.textContent = "No image to show.";
    slider.disabled = true;
    playButton.disabled = true;
    gifButton.disabled = true;
    clearInfo();
    setStatus(error.message, true);
  } finally {
    if (thisRequest === latestRequest) spinner.hidden = true;
  }
}

// Load again with the same position but new settings (mode, stretch, ...).
function reload() {
  if (lastRa && lastDec) loadFrames(lastRa, lastDec);
}

coordForm.addEventListener("submit", (event) => {
  event.preventDefault();
  currentTargetId = null; // typed coordinates are not a preset
  loadFrames(raInput.value.trim(), decInput.value.trim());
});

// ---------------------------------------------------------------
// 11. Tasks 16-17: stretch, match background, mode buttons
// ---------------------------------------------------------------
function setMode(newMode) {
  mode = newMode;
  modeButtons.forEach((button) => {
    const active = button.dataset.mode === newMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  refRow.hidden = newMode !== "difference";
  groupRow.hidden = newMode !== "stack";
}

// API_GUIDE: in stack mode the frame list changes, so we always reload it.
modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.mode === mode) return;
    setMode(button.dataset.mode);
    reload();
  });
});
[stretchSelect, matchToggle, refSelect, groupSelect].forEach((el) => {
  el.addEventListener("change", reload);
});

// ---------------------------------------------------------------
// 12. Targets: name search (Task 4) and preset buttons (Task 8)
// ---------------------------------------------------------------
async function loadTargets() {
  try {
    const data = await fetchJson("/api/targets?year=2026");
    targets = data.targets;
  } catch (error) {
    setStatus("Targets are unavailable: " + error.message, true);
  }
}

function findTarget(typedName) {
  const wanted = simplifyName(typedName);
  if (!wanted) return null;
  return (
    targets.find(
      (t) =>
        simplifyName(t.id) === wanted ||
        simplifyName(t.label) === wanted ||
        simplifyName(t.simbad_name) === wanted,
    ) || null
  );
}

function goToTarget(target) {
  currentTargetId = target.id; // Task 22 needs this
  raInput.value = target.ra_deg;
  decInput.value = target.dec_deg;
  loadFrames(String(target.ra_deg), String(target.dec_deg));
}

nameForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const target = findTarget(nameInput.value);
  if (!target) {
    const known = targets.map((t) => t.label).join(", ");
    setStatus(
      "Name not found. For now only these targets work by name: " + known + ".",
      true,
    );
    return;
  }
  goToTarget(target);
});

// Task 8: one button per target, straight from /api/targets
function buildPresets() {
  presetList.replaceChildren();
  targets.forEach((target) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = target.label;
    if (target.note) button.title = target.note;
    button.addEventListener("click", () => goToTarget(target));
    presetList.appendChild(button);
  });
}

// ---------------------------------------------------------------
// 13. Task 11: field-of-view dropdown (limits come from /api/limits)
// ---------------------------------------------------------------
async function loadLimits() {
  try {
    const data = await fetchJson("/api/limits");
    const { min, max, default: def } = data.fov_arcmin;
    // Some handy sizes inside the allowed range, plus min, default and max.
    const sizes = [min, 3, def, 10, 15, max].filter(
      (v) => v >= min && v <= max,
    );
    const unique = Array.from(new Set(sizes)).sort((a, b) => a - b);
    fovSelect.replaceChildren();
    unique.forEach((value) => {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = value + (value === def ? " (default)" : "");
      fovSelect.appendChild(option);
    });
    fovSelect.value = String(def);
  } catch (error) {
    // Keep the single "Default" option; the server then uses its own default.
    setStatus("Zoom control unavailable: " + error.message, true);
  }
}

// Changing the size reloads the frames at the same position.
fovSelect.addEventListener("change", () => {
  if (raInput.value.trim() && decInput.value.trim()) {
    loadFrames(raInput.value.trim(), decInput.value.trim());
  }
});

// ---------------------------------------------------------------
// 14. Animation player (Tasks 5, 6, 7)
// ---------------------------------------------------------------
function nextFrame() {
  const last = frames.length - 1;
  if (currentIndex >= last && !loopToggle.checked) {
    pause(); // Task 6: loop is off, so stop at the end
    return;
  }
  showFrame((currentIndex + 1) % frames.length);
}

function play() {
  if (frames.length < 2) return;
  pause();
  // If loop is off and we are at the end, start again from the beginning.
  if (currentIndex >= frames.length - 1 && !loopToggle.checked) showFrame(0);
  timer = setInterval(nextFrame, Number(speedSelect.value));
  playButton.textContent = "Pause";
}

// pause() also stops blinking, so only one animation runs at a time.
function pause() {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
  playButton.textContent = "Play";
  stopBlink();
}

function togglePlay() {
  if (timer === null) play();
  else pause();
}

// Task 7: step one frame back (-1) or forward (+1), wrapping round.
function step(direction) {
  if (frames.length < 2) return;
  pause();
  showFrame((currentIndex + direction + frames.length) % frames.length);
}

playButton.addEventListener("click", togglePlay);

slider.addEventListener("input", () => {
  pause();
  showFrame(Number(slider.value));
});

speedSelect.addEventListener("change", () => {
  if (timer !== null) play();
});

// Task 7: keyboard. Space = play/pause, arrows = step.
document.addEventListener("keydown", (event) => {
  const el = event.target;
  // Leave typing boxes, dropdowns, checkboxes and the slider alone (they use these keys).
  if (
    el.matches(
      "input[type=text], input[type=range], input[type=checkbox], select, textarea",
    )
  )
    return;
  if (event.code === "Space") {
    if (el.tagName === "BUTTON") return; // a focused button handles Space itself
    event.preventDefault(); // stop the page from scrolling
    togglePlay();
  } else if (event.key === "ArrowRight") {
    step(1);
  } else if (event.key === "ArrowLeft") {
    step(-1);
  }
});

// Task 7: swipe on the picture (phones). Left = next, right = previous.
let touchStartX = null;
stage.addEventListener(
  "touchstart",
  (event) => {
    touchStartX = event.touches[0].clientX;
  },
  { passive: true },
);
stage.addEventListener("touchend", (event) => {
  if (touchStartX === null) return;
  const dx = event.changedTouches[0].clientX - touchStartX;
  touchStartX = null;
  if (Math.abs(dx) < 40) return; // too short: a tap, not a swipe
  step(dx < 0 ? 1 : -1);
});

// ---------------------------------------------------------------
// 15. Task 18: blink compare (flip between two chosen frames)
// ---------------------------------------------------------------
function buildBlinkChoices() {
  [blinkA, blinkB].forEach((select) => {
    select.replaceChildren();
    frames.forEach((frame, i) => {
      const option = document.createElement("option");
      option.value = String(i);
      option.textContent = String(i + 1);
      select.appendChild(option);
    });
  });
  blinkA.value = "0";
  blinkB.value = String(frames.length - 1);
  blinkButton.disabled = frames.length < 2;
}

const BLINK_MS = 400; // time each frame stays on screen (my choice)

function startBlink() {
  pause(); // stops the player and any old blink
  const a = Number(blinkA.value);
  const b = Number(blinkB.value);
  let showA = true;
  showFrame(a);
  blinkTimer = setInterval(() => {
    showA = !showA;
    showFrame(showA ? a : b);
  }, BLINK_MS);
  blinkButton.textContent = "Stop blink";
}

function stopBlink() {
  if (blinkTimer !== null) {
    clearInterval(blinkTimer);
    blinkTimer = null;
  }
  blinkButton.textContent = "Blink";
}

blinkButton.addEventListener("click", () => {
  if (blinkTimer === null) startBlink();
  else stopBlink();
});

// Task 25: download the animation as a GIF (calls /api/animation.gif)
gifButton.addEventListener("click", async () => {
  if (!lastRa || !lastDec) return;
  const params = currentParams(lastRa, lastDec);
  params.set("speed_ms", speedSelect.value); // 200, 500 or 1000: all allowed (20-5000)
  setStatus("Making the GIF...");
  try {
    const response = await fetch("/api/animation.gif?" + params.toString());
    if (!response.ok) {
      let message = "Could not make the GIF (code " + response.status + ").";
      try {
        message = (await response.json()).detail || message;
      } catch (e) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "sky-animation.gif";
    link.click();
    URL.revokeObjectURL(link.href);
    setStatus("GIF saved.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

// ---------------------------------------------------------------
// 16. Task 26: download the marker positions as a CSV (made in the browser)
// ---------------------------------------------------------------
csvButton.addEventListener("click", () => {
  if (!marker || frames.length === 0) {
    setStatus(
      "Click the picture to place a marker first, then download.",
      true,
    );
    return;
  }
  const rows = [
    "frame,obs_time,detector,wavelength_um,marker_ra_deg,marker_dec_deg",
  ];
  frames.forEach((frame, i) => {
    rows.push(
      [
        i + 1,
        frame.obs_time,
        frame.detector,
        frame.wavelength_um,
        marker.ra.toFixed(6),
        marker.dec.toFixed(6),
      ].join(","),
    );
  });
  const blob = new Blob([rows.join("\n") + "\n"], { type: "text/csv" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "sky-marker.csv";
  link.click();
  URL.revokeObjectURL(link.href);
  setStatus("CSV saved.");
});

// ---------------------------------------------------------------
// 17. Task 10: copy link
// ---------------------------------------------------------------
copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(window.location.href);
    setStatus("Link copied.");
  } catch (error) {
    // Clipboard can be blocked (for example on plain http outside localhost).
    setStatus(
      "Could not copy. Copy the address from the browser bar instead.",
      true,
    );
  }
});

// ---------------------------------------------------------------
// 18. When the page opens (Task 9 reads the URL here)
// ---------------------------------------------------------------
// Use a value from the link only if it is one of the dropdown choices.
function setSelectFromUrl(select, value) {
  if (value && Array.from(select.options).some((o) => o.value === value)) {
    select.value = value;
  }
}

async function start() {
  await Promise.all([loadTargets(), loadLimits()]);
  buildPresets();

  const url = new URLSearchParams(window.location.search);
  const ra = url.get("ra");
  const dec = url.get("dec");

  setSelectFromUrl(fovSelect, url.get("fov"));
  setSelectFromUrl(stretchSelect, url.get("stretch"));
  setSelectFromUrl(refSelect, url.get("ref"));
  setSelectFromUrl(groupSelect, url.get("group"));
  matchToggle.checked = url.get("match") === "on";
  const urlMode = url.get("mode");
  if (["normal", "difference", "stack"].includes(urlMode)) setMode(urlMode);

  // "target" is a page-only setting: it remembers which preset was used.
  const urlTarget = url.get("target");
  if (urlTarget && targets.some((t) => t.id === urlTarget))
    currentTargetId = urlTarget;

  if (ra && dec) {
    raInput.value = ra;
    decInput.value = dec;
    loadFrames(ra, dec);
  } else {
    // No coordinates in the link: show WISE 0855 so there is something to see.
    const wise = targets.find((t) => t.id === "wise0855");
    if (wise) goToTarget(wise);
  }
}
// ---------------------------------------------------------------
// 19. Task 30: reset view (puts every setting back to its start)
// ---------------------------------------------------------------
const resetButton = document.getElementById("reset-view");
const advancedPanel = document.getElementById("advanced");

resetButton.addEventListener("click", () => {
  pause();
  setMode("normal");
  stretchSelect.value = "sqrt"; // the default in index.html
  matchToggle.checked = false;
  refSelect.value = "first";
  groupSelect.value = "detector";
  // The FOV option that loadLimits() labelled "(default)"
  const defaultFov = Array.from(fovSelect.options).find((o) =>
    o.textContent.includes("(default)"),
  );
  if (defaultFov) fovSelect.value = defaultFov.value;
  marker = null;
  showExpected = false;
  expectedToggle.checked = false;
  magnifierToggle.checked = false;
  lens.hidden = true;
  reload(); // loads the same position with the starting settings
  setStatus("View reset.");
});

// ---------------------------------------------------------------
// 20. Task 32: guided mission (find the moving dot of WISE 0855)
// ---------------------------------------------------------------
const missionStart = document.getElementById("mission-start");
const missionBox = document.getElementById("mission-box");
const missionCount = document.getElementById("mission-count");
const missionTitle = document.getElementById("mission-title");
const missionText = document.getElementById("mission-text");
const missionBack = document.getElementById("mission-back");
const missionNext = document.getElementById("mission-next");
const missionExit = document.getElementById("mission-exit");

// Each step has a title, a text, and (optionally) "run": something the page
// does for you when you press Next to arrive at that step.
const MISSION_STEPS = [
  {
    title: "Your target",
    text: "WISE 0855 is a brown dwarf: a failed star, very faint and very close to us. It moves across the sky faster than almost anything else. Your mission is to see it move. Press Next and I will load it.",
    run: null,
  },
  {
    title: "Load the pictures",
    text: "I have loaded WISE 0855 with the normal view. Wait for the pictures to finish loading (the status line under the picture will say so).",
    run: () => {
      const wise = targets.find((t) => t.id === "wise0855");
      if (!wise) {
        setStatus("WISE 0855 is not available. Is the server running?", true);
        return;
      }
      setMode("normal");
      goToTarget(wise);
    },
  },
  {
    title: "Press Play",
    text: "Press Play (or the Space key). Most dots are stars and stay put. Look for the one dot that changes place from frame to frame.",
    run: null,
  },
  {
    title: "Go slowly",
    text: "Now step through one frame at a time with the left and right arrow keys, or drag the slider. Follow the dot with your eyes. Note: the practice (mock) data moves its dot about 10 times faster than the real star, so it is easy to see.",
    run: null,
  },
  {
    title: "Blink compare",
    text: "I opened Advanced tools for you. Under Blink compare, frame A is the first frame and B is the last. Press Blink: the moving dot seems to jump back and forth. Astronomers found Pluto this way.",
    run: () => {
      advancedPanel.open = true;
    },
  },
  {
    title: "Difference view",
    text: "I switched to Difference view. Grey means nothing changed. Stars vanish, and the mover shows up as a white or black spot. Press Play to watch it.",
    run: () => {
      setMode("difference");
      reload();
    },
  },
  {
    title: "Where should it be?",
    text: "I switched back to Normal and turned on Expected path. The dashed line shows where known motion says WISE 0855 should be. On the practice (mock) data the dot moves faster than the real star, so the line only matches the dot in the first frame. On real data they should line up.",
    run: () => {
      showExpected = true; // loadFrames() draws the path once the pictures are in
      expectedToggle.checked = true;
      setMode("normal");
      reload();
      advancedPanel.open = true;
    },
  },
  {
    title: "Is it real?",
    text: "Last check: look at 'Is it real?' in Frame info. Green is fine. Yellow means the detector or the colour changed, so a jump might come from the instrument and not from real motion. Well done, mission complete!",
    run: null,
  },
];

let missionIndex = 0;

function showMissionStep(index, runIt) {
  missionIndex = index;
  const step = MISSION_STEPS[index];
  missionCount.textContent =
    "Step " + (index + 1) + " of " + MISSION_STEPS.length;
  missionTitle.textContent = step.title;
  missionText.textContent = step.text;
  missionBack.disabled = index === 0;
  missionNext.textContent =
    index === MISSION_STEPS.length - 1 ? "Finish" : "Next";
  // Only run the action when moving forward, so Back never changes the page.
  if (runIt && step.run) step.run();
}

function closeMission() {
  missionBox.hidden = true;
  missionStart.hidden = false;
}

missionStart.addEventListener("click", () => {
  missionStart.hidden = true;
  missionBox.hidden = false;
  showMissionStep(0, false);
});
missionNext.addEventListener("click", () => {
  if (missionIndex >= MISSION_STEPS.length - 1) closeMission();
  else showMissionStep(missionIndex + 1, true);
});
missionBack.addEventListener("click", () => {
  if (missionIndex > 0) showMissionStep(missionIndex - 1, false);
});
missionExit.addEventListener("click", closeMission);
start();
