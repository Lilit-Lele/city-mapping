// The web version of Notebook 6 (search, color menu, future buildings, click a building)
// plus Notebook 8: saved places (kept in the browser), street names, tallest building names, the show/hide controls,
// and Step 9 (view check and sun exposure for a spot on a wall).
// Reads the files made by export_web.py (in data/). Coordinates: feet, Z up, like the notebooks.
import * as THREE from "three";
import { MapControls } from "three/addons/controls/MapControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { buildCollision, buildTerrainCollision, pick, firstHit, viewCheck, rayLines, rayDirection, trueBearing,
         compassLabel, OUTCOME_COLORS } from "./rays.js";
import { sunSteps, exposure, hours, sunriseSunset, clockText, STATE_COLORS } from "./sun.js";
import { wallCells, wallSunHours, wallMesh, HOURS_GRADIENT } from "./wall.js";
import { floorAtHeight, spotText, countText, hasFloors } from "./floors.js";
import { attachBuildingUnits, unitAt, unitLines, buildingDetailLines, websiteLink } from "./units.js";

// ------------------------------------------------------------------ settings (Notebook 6's STYLE etc.)

const STYLE = {
  background: "#eceded",
  buildingColor: "#fbfaf6",
  highlightColor: "#fff59d",    // light yellow, so the red spot marker stands out
  groupColor: "#ff8c00",
  blockerColor: "#ff8c00",      // buildings that block the view (Step 9.1)
  shadeColor: "#7b61ff",        // buildings that shade the spot (Step 9.2)
  spotColor: "#ff0000",         // the spot marker: red
  startView: { position: [-10500, -9350, 4000], target: [-10900, -4900, 0] },
  overviewView: { position: [-12500, -34500, 20500], target: [-12500, -10000, 0] },
};

const MAX_SHOWN = 15;
const VERTICAL_LIMIT = 0.3;     // a face is a wall if its normal's up part is below this (as walls.py)
const SPOT_OUT_FT = 2;          // the spot sits 2 ft in front of the wall (as windows.locate)
const RESIDENTIAL_CODES = ["R1", "R2", "R3", "R4", "A", "CM", "RL - RL"];
const HEIGHT_CLASSES = [            // [from ft, up to ft, color, legend text]
  [0, 40, "#fde725", "under 40 ft"],
  [40, 60, "#7ad151", "40-60 ft"],
  [60, 100, "#22a884", "60-100 ft"],
  [100, 300, "#2a788e", "100-300 ft"],
  [300, 10000, "#440154", "300 ft and taller"],
];
const LAND_USE_GROUPS = [           // [group name, codes, color]
  ["Residential", RESIDENTIAL_CODES, "#f2c14e"],
  ["Mixed residential/commercial", ["RC"], "#f78154"],
  ["Commercial", ["C", "CC", "CL"], "#4d9de0"],
  ["Exempt (public, schools...)", ["E", "EA"], "#3bb273"],
  ["Industrial", ["I"], "#7768ae"],
];
const FUTURE_STATUS_COLORS = { "Board Approved": "#267300", "Under Construction": "#ed7894" };

const isBuilding = (row) => row.struct_type === "Building";
const COLOR_CHOICES = {
  "Normal": { color: () => STYLE.buildingColor, legend: [] },
  "By height": {
    color: (row) => {
      if (!isBuilding(row) || row.height_ft == null) return STYLE.buildingColor;
      const found = HEIGHT_CLASSES.find(([low, high]) => row.height_ft >= low && row.height_ft < high);
      return found ? found[2] : STYLE.buildingColor;
    },
    legend: HEIGHT_CLASSES.map(([, , color, label]) => [label, color]),
  },
  "By land use": {
    color: (row) => {
      if (!isBuilding(row)) return STYLE.buildingColor;
      const found = LAND_USE_GROUPS.find(([, codes]) => codes.includes(row.land_use_code));
      return found ? found[2] : STYLE.buildingColor;
    },
    legend: LAND_USE_GROUPS.map(([name, , color]) => [name, color]),
  },
  "Residential": {
    color: (row) => (isBuilding(row) && RESIDENTIAL_CODES.includes(row.land_use_code) ? STYLE.groupColor : STYLE.buildingColor),
    legend: [["Residential", STYLE.groupColor]],
  },
  "Taller than 300 ft": {
    color: (row) => (isBuilding(row) && row.height_ft > 300 ? STYLE.groupColor : STYLE.buildingColor),
    legend: [["Taller than 300 ft", STYLE.groupColor]],
  },
};

// ------------------------------------------------------------------ reading export_web.py's files

const ARRAY_TYPES = { uint8: Uint8Array, uint16: Uint16Array, uint32: Uint32Array, float32: Float32Array };

// One .bin.gz tile file -> { header, arrays }. The format is explained in export_web.py, write_tile_file.
async function readTileFile(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  let buffer = await response.arrayBuffer();
  const firstBytes = new Uint8Array(buffer, 0, 2);
  if (firstBytes[0] === 0x1f && firstBytes[1] === 0x8b) {        // gzip's signature: decompress it ourselves
    const stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"));
    buffer = await new Response(stream).arrayBuffer();
  }
  const headerLength = new DataView(buffer).getUint32(0, true);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 4, headerLength)));
  const arrays = {};
  for (const [name, d] of Object.entries(header.arrays)) {
    const count = d.shape.reduce((a, b) => a * b, 1);
    arrays[name] = new ARRAY_TYPES[d.dtype](buffer, 4 + headerLength + d.start, count);
  }
  return { header, arrays };
}

async function readBuildingTable(url) {
  const table = await (await fetch(url)).json();
  return table.rows.map((values) => Object.fromEntries(table.columns.map((column, i) => [column, values[i]])));
}

// ------------------------------------------------------------------ the 3D scene

const container = document.getElementById("view");
const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
container.appendChild(renderer.domElement);

// Text labels (street names, saved places, tallest buildings) are HTML elements placed over the 3D view at
// their 3D positions by CSS2DRenderer, like pyvista's point labels. They always face the camera.
const labelRenderer = new CSS2DRenderer({ element: document.getElementById("labels") });
labelRenderer.setSize(window.innerWidth, window.innerHeight);

const scene = new THREE.Scene();
scene.background = new THREE.Color(STYLE.background);

const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 5, 300000);
camera.up.set(0, 0, 1);
const controls = new MapControls(camera, renderer.domElement);   // left drag: pan, right drag: rotate, wheel: zoom
controls.maxPolarAngle = Math.PI / 2 - 0.05;
controls.enableDamping = true;

scene.add(new THREE.AmbientLight(0xffffff, 1.4));
const sunLight = new THREE.DirectionalLight(0xffffff, 2.0);
sunLight.position.set(-0.5, -0.8, 1);
scene.add(sunLight);

const buildingMaterial = new THREE.MeshPhongMaterial({ vertexColors: true, flatShading: true, shininess: 0, specular: 0x000000 });

function setView(view) {
  camera.position.set(...view.position);
  controls.target.set(...view.target);
  controls.update();
}

let flight = null;
function flyTo(view) {
  flight = {
    start: performance.now(),
    fromPosition: camera.position.clone(), fromTarget: controls.target.clone(),
    toPosition: new THREE.Vector3(...view.position), toTarget: new THREE.Vector3(...view.target),
  };
  render();
}

function buildingView(row, fromAngle = 20, downAngle = 30) {
  const [xMin, yMin, zMin, xMax, yMax, zMax] = row.box;
  const center = [(xMin + xMax) / 2, (yMin + yMax) / 2, (zMin + zMax) / 2];
  const distance = Math.max(2.5 * Math.max(zMax - zMin, xMax - xMin, yMax - yMin), 700);
  const side = THREE.MathUtils.degToRad(fromAngle);
  const down = THREE.MathUtils.degToRad(downAngle);
  const direction = [-Math.sin(side) * Math.cos(down), -Math.cos(side) * Math.cos(down), Math.sin(down)];
  return { position: center.map((c, i) => c + distance * direction[i]), target: center };
}

// A camera in front of the spot's wall, looking at it (like windows.wall_view), or from behind and above
// looking out over the view fan.
function spotView(spot, kind) {
  const out = new THREE.Vector3(spot.normal.x, spot.normal.y, 0).normalize();
  if (kind === "fan") {
    return { position: spot.point.clone().addScaledVector(out, -2500).add(new THREE.Vector3(0, 0, 5000)).toArray(),
             target: spot.point.clone().addScaledVector(out, 3000).toArray() };
  }
  return { position: spot.point.clone().addScaledVector(out, 900).add(new THREE.Vector3(0, 0, -40)).toArray(),
           target: spot.point.toArray() };
}

// ------------------------------------------------------------------ making meshes from the tile files

// Terrain: a flat grid lifted to the heights, with the aerial photo. The geometry is moved to its place in
// feet (instead of moving the mesh), so the click search structure can use it directly.
function makeTerrain(header, heights, photoUrl) {
  const t = header.terrain;
  const [left, right, bottom, top] = t.bounds;
  const geometry = new THREE.PlaneGeometry(right - left, top - bottom, t.columns - 1, t.rows - 1);
  const position = geometry.attributes.position;
  for (let i = 0; i < position.count; i++) position.setZ(i, t.low + (heights[i] / 65535) * (t.high - t.low));
  geometry.translate((left + right) / 2, (bottom + top) / 2, 0);
  const texture = new THREE.TextureLoader().load(photoUrl, () => render());
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ map: texture }));
}

function makeBuildings(header, arrays) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(arrays.positions, 3, true));
  geometry.setIndex(new THREE.BufferAttribute(arrays.triangles, 1));
  const colors = new Uint8Array(arrays.positions.length);
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3, true));
  const mesh = new THREE.Mesh(geometry, buildingMaterial);
  const [low, high] = [header.low, header.high];
  mesh.scale.set(high[0] - low[0], high[1] - low[1], high[2] - low[2]);
  mesh.position.set(...low);
  return { mesh, colors, building: arrays.building };
}

function paintLayer(layer) {
  const { colors, building, buildingColors } = layer;
  for (let p = 0; p < building.length; p++) {
    const b = building[p] * 3;
    colors[p * 3] = buildingColors[b];
    colors[p * 3 + 1] = buildingColors[b + 1];
    colors[p * 3 + 2] = buildingColors[b + 2];
  }
  layer.mesh.geometry.attributes.color.needsUpdate = true;
}

const colorCache = new Map();
function rgb255(hex) {
  if (!colorCache.has(hex)) {
    const c = new THREE.Color(hex);
    colorCache.set(hex, [c.r, c.g, c.b].map((v) => Math.round(v * 255)));
  }
  return colorCache.get(hex);
}

// ------------------------------------------------------------------ state

const world = { layers: [], terrains: [], area: null };   // what the rays test against (rays.js)
let currentRows = [];
let colorChoice = "Normal";
let highlighted = null;          // the highlighted row, or null
const marked = new Map();        // row -> color: blocking or shading buildings of the spot tools
let spot = null;                 // the clicked wall spot (Step 9), or null
const spotOverlay = new THREE.Group();   // the spot's marker, rays, sun line and wall cells
scene.add(spotOverlay);

function layerColor(layer, row) {
  if (row === highlighted) return STYLE.highlightColor;
  if (marked.has(row)) return marked.get(row);
  if (layer.kind === "future") return FUTURE_STATUS_COLORS[row.status] || STYLE.groupColor;
  return COLOR_CHOICES[colorChoice].color(row);
}

function recolor(layer) {
  layer.rows.forEach((row, i) => layer.buildingColors.set(rgb255(layerColor(layer, row)), i * 3));
  paintLayer(layer);
}

// ------------------------------------------------------------------ small page helpers

const $ = (id) => document.getElementById(id);
const say = (text) => { $("message").textContent = text; };
const feet = (value) => `${Math.round(value).toLocaleString()} ft`;
const nameOf = (row) => (row && row.name) || "(no name)";

// Make an element: el("td", { className: "num" }, "12")
function el(tag, props = {}, ...children) {
  const element = Object.assign(document.createElement(tag), props);
  element.append(...children);
  return element;
}

function swatch(color) { return el("span", { className: "swatch", style: `background:${color}` }); }

function table(headers, rows, numeric = []) {
  return el("table", {},
    el("tr", {}, ...headers.map((h, i) => el("th", { className: numeric.includes(i) ? "num" : "" }, h))),
    ...rows.map((cells) => el("tr", {}, ...cells.map((c, i) => el("td", { className: numeric.includes(i) ? "num" : "" }, c)))));
}

function rowButton(row, text) {
  const button = el("button", {}, text);
  button.onclick = () => goTo(row);
  return el("li", {}, button);
}

function updateLegend() {
  const entries = [...COLOR_CHOICES[colorChoice].legend];
  if ($("future-box").checked) entries.push(...Object.entries(FUTURE_STATUS_COLORS));
  $("legend").replaceChildren(...entries.map(([label, color]) => el("div", {}, swatch(color), label)));
}

function buildingLines(row) {
  const show = (value, unknown = "not in city data") => (value == null ? unknown : value);
  return [
    `Height: ${row.height_ft == null ? "?" : Math.round(row.height_ft)} ft   Floors: ${show(row.floors)}`,
    `Type: ${show(row.struct_type, "?")}, use: ${show(row.struct_use, "unknown")}`,
    `Land use (parcel): ${show(row.land_use)}   Built: ${show(row.year_built)}`,
    `Status: ${show(row.status, "?")}`,
    `Tile: ${row.tile}   ID: ${row.id}`,
  ];
}

// The building's information; extra = more lines under it (the clicked spot, or a saved place's note).
let shownInfo = { row: null, extra: [] };       // what the box shows, to redraw it after Save
function showInfo(row, extra = []) {
  const info = $("info");
  shownInfo = { row, extra };
  if (!row) { info.style.display = "none"; return; }
  const close = el("button", { className: "close" }, "×");
  close.onclick = () => select(null);
  const floorsLine = hasFloors(row) ? [`Floors (estimated levels): ${countText(row)} (${row.floor_source})`] : [];
  info.replaceChildren(close, el("div", { className: "name" }, nameOf(row)),
    ...[...buildingLines(row), ...floorsLine].map((line) => el("div", { className: "small" }, line)));
  if (row.google_link) info.append(el("a", { href: row.google_link, target: "_blank", rel: "noopener" }, "Open in Google Maps"));
  if (row.unitsData) {                                             // extra details (data/buildings/, e.g. Ora Seaport)
    info.append(el("div", { className: "small detail-title" }, "Building details"),
      ...websiteLinkElements(row.unitsData), ...buildingDetailLines(row.unitsData).map(lineElement));
  }
  for (const [i, line] of [].concat(extra).filter(Boolean).entries()) {
    const element = lineElement(line);
    if (i === 0) element.style.marginTop = "6px";
    info.append(element);
  }
  info.append(saveButtons(row));
  info.style.display = "block";
}

// One line of the info box. ⚠ = the website contradicts itself (highlighted); ℹ / ? = a note about the
// 3D model or the city's data, or something nobody says (units.js, noteText).
function lineElement(line) {
  const className = line.startsWith("⚠") ? "small mismatch" : /^[ℹ?] /.test(line) ? "small data-note" : "small";
  return el("div", { className }, line);
}

// The building's website, to check the real, current information (an empty list if it has none).
function websiteLinkElements(building) {
  const link = websiteLink(building);
  return link ? [el("div", { className: "small" }, el("a", { href: link.href, target: "_blank", rel: "noopener" }, link.text))] : [];
}

function select(row, extra = []) {
  const previous = highlighted;
  highlighted = row;
  for (const layer of world.layers) {
    if ((previous && previous.layerRef === layer) || (row && row.layerRef === layer)) recolor(layer);
  }
  showInfo(row, extra);
  render();
}

function goTo(row) {
  select(row);
  flyTo(buildingView(row));
  say(`Showing: ${nameOf(row)}`);
}

// ------------------------------------------------------------------ Notebook 6: search, colors, future

const clean = (text) => text.split(/\s+/).filter(Boolean).join(" ").toLowerCase();

function search(text) {
  const wanted = clean(text);
  const list = $("results");
  list.replaceChildren();
  if (!wanted) { say("Type a name or an address first."); return; }
  const matches = currentRows.filter((row) => row.searchName.includes(wanted))
    .sort((a, b) => (b.height_ft ?? -1) - (a.height_ft ?? -1));
  if (matches.length === 0) {
    say("No building name contains that. Try a shorter piece, e.g. one word of the name or the street.");
    return;
  }
  list.append(...matches.slice(0, MAX_SHOWN).map((row) =>
    rowButton(row, `${row.name}  (${row.height_ft == null ? "?" : Math.round(row.height_ft)} ft, ${row.tile})`)));
  const shown = matches.length > MAX_SHOWN ? `, showing the ${MAX_SHOWN} tallest` : "";
  say(`${matches.length} matches${shown}. Click one to go there.`);
}

function setColorChoice(choice) {
  colorChoice = choice;
  for (const layer of world.layers) if (layer.kind === "current") recolor(layer);
  const colored = choice === "Normal" ? 0
    : currentRows.filter((row) => COLOR_CHOICES[choice].color(row) !== STYLE.buildingColor).length;
  updateLegend();
  say(choice === "Normal" ? "Color: Normal" : `Color: ${choice} (${colored.toLocaleString()} buildings colored)`);
  render();
}

function setFutureVisible(visible) {
  for (const layer of world.layers) if (layer.kind === "future") layer.mesh.visible = visible;
  if (!visible && highlighted && highlighted.layer === "future") select(null);
  updateLegend();
  say(visible ? "Future buildings shown (they also count in the view and sun checks)"
              : "Future buildings hidden");
  render();
}

$("search-form").addEventListener("submit", (event) => { event.preventDefault(); search($("search-text").value); });
for (const choice of Object.keys(COLOR_CHOICES)) $("color-menu").append(new Option(choice, choice));
$("color-menu").addEventListener("change", (event) => setColorChoice(event.target.value));
$("future-box").addEventListener("change", (event) => setFutureVisible(event.target.checked));
$("home-button").onclick = () => flyTo(STYLE.startView);
$("overview-button").onclick = () => flyTo(STYLE.overviewView);
$("clear-button").onclick = () => select(null);

// ------------------------------------------------------------------ Notebook 8, Step 9: the spot

// Remove what the previous spot tool drew (rays, sun line, wall cells) and its marked buildings.
function clearSpotDrawings({ keepMarker = true } = {}) {
  for (const child of [...spotOverlay.children]) {
    if (keepMarker && child.userData.isMarker) continue;
    spotOverlay.remove(child);
    child.geometry?.dispose();
  }
  if (marked.size) {
    const layersToRecolor = new Set([...marked.keys()].map((row) => row.layerRef));
    marked.clear();
    for (const layer of layersToRecolor) recolor(layer);
  }
}

function clearSpot() {
  clearSpotDrawings({ keepMarker: false });
  spot = null;
  $("spot").style.display = "none";
  render();
}

// A click on a wall: the spot is 2 ft in front of it. The face's outward side is the side the click came from
// (you can only click a wall from outside), so no ray-counting is needed as in walls.make_outward.
// Returns the spot's description, or null for a roof or a ledge.
function setSpot(hit, row) {
  const normal = hit.normal.clone().normalize();
  if (normal.dot(camera.position.clone().sub(hit.point)) < 0) normal.negate();
  if (Math.abs(normal.z) >= VERTICAL_LIMIT) return null;            // a roof or a ledge: not a wall
  normal.z = 0;
  normal.normalize();                                              // a wall faces horizontally
  return setSpotFrom({ layer: hit.layer, buildingNumber: hit.buildingNumber, row, surfacePoint: hit.point.clone(), normal });
}

// The spot itself, from a click or from a saved spot. Describes it in words like the notebook
// (windows.spot_text): floor from the building's floor plan, wall direction, distance along this wall.
function setSpotFrom({ layer, buildingNumber, row, surfacePoint, normal, saved = null }) {
  clearSpotDrawings({ keepMarker: false });
  const bearing = trueBearing(normal);
  spot = { layer, buildingNumber, row, surfacePoint, point: surfacePoint.clone().addScaledVector(normal, SPOT_OUT_FT),
           normal, bearing, saved };
  spot.wall = wallCells(spot);                                     // this wall's grid: its column, and "Color the wall"

  let description;
  if (saved) {
    description = saved.description;                               // the words it was saved with
  } else if (hasFloors(row)) {
    const fromLeft = spot.wall ? surfacePoint.dot(spot.wall.right) - spot.wall.sMin : null;   // ft from the left end
    description = spotText(row, floorAtHeight(row, surfacePoint.z), compassLabel(bearing), bearing,
                           fromLeft, spot.wall ? spot.wall.width * spot.wall.columns : null);
  } else {                                                         // future buildings have no floor plan
    description = `About ${feet(surfacePoint.z - row.box[2])} above the building's base, ` +
                  `wall facing ${compassLabel(bearing)} (${Math.round(bearing)}°)`;
  }
  spot.description = description;

  // Buildings with apartment positions (data/buildings/): which apartment is this, and what doesn't match.
  spot.unitLines = [];
  if (row.unitsData && hasFloors(row)) {
    const floor = floorAtHeight(row, surfacePoint.z);
    spot.unitLines = unitLines(row.unitsData, unitAt(row.unitsData, surfacePoint, bearing, floor), floor);
  }

  const marker = new THREE.Mesh(new THREE.SphereGeometry(4, 16, 12), new THREE.MeshBasicMaterial({ color: STYLE.spotColor }));
  marker.position.copy(spot.point);
  marker.userData.isMarker = true;
  spotOverlay.add(marker);

  $("spot-text").replaceChildren(
    el("div", {}, el("b", {}, saved ? `★ ${saved.label}` : nameOf(row))),
    saved ? el("div", {}, nameOf(row)) : "",
    el("div", {}, description),
    ...spot.unitLines.map(lineElement),
    ...(spot.unitLines.length ? websiteLinkElements(row.unitsData) : []));
  for (const id of ["view-result", "sun-result", "wall-result"]) $(id).replaceChildren();
  $("spot").style.display = "block";
  return description;
}

$("spot-close").onclick = clearSpot;

// --- 9.1 view check

$("view-button").onclick = () => {
  if (!spot) return;
  clearSpotDrawings();
  const started = performance.now();
  const fan = viewCheck(world, spot);
  const milliseconds = performance.now() - started;
  spotOverlay.add(rayLines(spot.point, fan));

  const counts = { blocked: 0, open: 0, unknown: 0 };
  const blockers = new Map();                                      // row -> { rays, nearest, from, to }
  for (const ray of fan) {
    counts[ray.outcome] += 1;
    if (ray.outcome !== "blocked") continue;
    const row = ray.hit.layer.rows[ray.hit.buildingNumber];
    const entry = blockers.get(row) || { rays: 0, nearest: Infinity, from: ray.bearing, to: ray.bearing };
    entry.rays += 1;
    entry.nearest = Math.min(entry.nearest, ray.distance);
    entry.to = ray.bearing;
    blockers.set(row, entry);
  }
  for (const row of blockers.keys()) marked.set(row, STYLE.blockerColor);
  for (const layer of new Set([...blockers.keys()].map((row) => row.layerRef))) recolor(layer);

  const sorted = [...blockers.entries()].sort((a, b) => b[1].rays - a[1].rays);
  $("view-result").replaceChildren(
    el("div", { className: "small" }, `${fan.length} rays in ${Math.round(milliseconds)} ms: `,
      swatch(OUTCOME_COLORS.blocked), `${counts.blocked} blocked  `,
      swatch(OUTCOME_COLORS.open), `${counts.open} open  `,
      swatch(OUTCOME_COLORS.unknown), `${counts.unknown} unknown (beyond our data)`),
    el("div", { className: "small" }, swatch(STYLE.blockerColor), "Blocking buildings (click to go there):"),
    el("ul", { className: "list" }, ...sorted.map(([row, b]) =>
      rowButton(row, `${nameOf(row)}: ${b.rays * 2}° of the view (${Math.round(b.from)}°-${Math.round(b.to)}°), ` +
                     `${feet(b.nearest)} away, ${row.height_ft == null ? "?" : Math.round(row.height_ft)} ft tall`))));
  flyTo(spotView(spot, "fan"));
};

// --- 9.2 sun

const sunLine = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: "#c77700", depthTest: false }));
let sunTimeline = null;

function showSunRay(step) {                                         // the ray of one time step, from the spot
  if (!spot) return;
  const direction = rayDirection(step.azimuth, Math.max(step.elevation, 0));
  const end = step.hit ? step.hit.point : spot.point.clone().addScaledVector(direction, 1500);
  sunLine.geometry.setFromPoints([spot.point, end]);
  sunLine.material.color.set(STATE_COLORS[step.state]);
  if (!sunLine.parent) spotOverlay.add(sunLine);
  render();
}

$("sun-date").value = "2026-12-21";
for (const button of document.querySelectorAll("[data-day]")) {
  button.onclick = () => {                                         // same year as the date field
    const year = ($("sun-date").value || "2026").slice(0, 4);
    $("sun-date").value = `${year}-${button.dataset.day}`;
    $("sun-button").click();
  };
}

$("sun-button").onclick = () => {
  if (!spot) return;
  clearSpotDrawings();
  const day = $("sun-date").value;
  if (!day) return;
  sunTimeline = exposure(world, spot, sunSteps(day));
  const total = hours(sunTimeline);
  const [sunrise, sunset] = sunriseSunset(day);

  const bar = el("div", { id: "timeline" }, ...sunTimeline.map((step, i) => {
    const slice = el("div", { style: `background:${STATE_COLORS[step.state]}` });
    slice.onmouseenter = () => {
      const by = step.hit ? ` by ${nameOf(step.hit.layer.rows[step.hit.buildingNumber])}` : "";
      $("timeline-hover").textContent = `${clockText(step.minutes)}  ${step.state}${by}  (sun at ${Math.round(step.azimuth)}°, ` +
        `${step.elevation.toFixed(1)}° high)`;
      showSunRay(step);
    };
    return slice;
  }));
  const marks = el("div", { id: "timeline-hours" },
    ...[0, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => el("span", { style: `left:${(100 * h) / 24}%` }, String(h))));

  const shaders = new Map();                                       // row -> [first, last, steps]
  for (const step of sunTimeline) {
    if (step.state !== "shade") continue;
    const row = step.hit.layer.rows[step.hit.buildingNumber];
    const entry = shaders.get(row) || [step.minutes, step.minutes, 0];
    entry[1] = step.minutes;
    entry[2] += 1;
    shaders.set(row, entry);
  }
  for (const row of shaders.keys()) marked.set(row, STYLE.shadeColor);
  for (const layer of new Set([...shaders.keys()].map((row) => row.layerRef))) recolor(layer);

  $("sun-result").replaceChildren(
    el("div", { className: "small" }, `${day}: sunrise ${sunrise}, sunset ${sunset} (Boston time)`),
    bar, marks,
    el("div", { id: "timeline-hover", className: "small" }, "Move the mouse over the bar to see each time and its sun ray."),
    el("div", { className: "small" }, ...Object.entries(STATE_COLORS).map(([state, color]) =>
      el("span", { style: "margin-right:8px" }, swatch(color), `${state} ${total[state].toFixed(1)} h`))),
    shaders.size ? el("div", { className: "small", style: "margin-top:4px" }, swatch(STYLE.shadeColor), "Shaded by:") : "",
    shaders.size ? el("ul", { className: "list" }, ...[...shaders.entries()].map(([row, [first, last, steps]]) =>
      rowButton(row, `${nameOf(row)}: ${clockText(first)}-${clockText(last + 10)}, ${(steps / 6).toFixed(1)} h`))) : "");
  render();
};

// --- 9.2.4 whole wall

$("wall-button").onclick = async () => {
  if (!spot) return;
  clearSpotDrawings();
  const result = $("wall-result");
  const wall = spot.wall;
  if (!wall || wall.cells.length === 0) { result.textContent = "Couldn't find this wall's outline."; return; }
  const day = $("sun-date").value;
  const button = $("wall-button");
  button.disabled = true;
  const started = performance.now();
  await wallSunHours(world, spot, wall, sunSteps(day, 20), (done, total) => {
    result.textContent = `Computing ${done} of ${total} cells…`;
  });
  button.disabled = false;
  const values = wall.cells.map((cell) => cell.sunHours);
  const most = Math.max(...values), least = Math.min(...values);
  spotOverlay.add(wallMesh(wall, most));
  result.replaceChildren(
    el("div", { className: "small" }, `${wall.cells.length} cells (${wall.columns} columns × ` +
      `${wall.byFloors ? `${countText(spot.row)} floors` : `${wall.rows} rows of ~12 ft`}) ` +
      `in ${((performance.now() - started) / 1000).toFixed(1)} s, on ${day}.`),
    el("div", { className: "gradient", style: `background:${HOURS_GRADIENT}` }),
    el("div", { className: "small", style: "display:flex;justify-content:space-between" },
      el("span", {}, "0 h"), el("span", {}, `hours of direct sun`), el("span", {}, `${most.toFixed(1)} h`)),
    el("div", { className: "small" }, `Least ${least.toFixed(1)} h, most ${most.toFixed(1)} h.`));
  flyTo(spotView(spot, "wall"));
};

// ------------------------------------------------------------------ Notebook 8: labels, controls, saved places

// What's drawn on top of the city: the notebook's DISPLAY (Step 6.4), changed by the controls (Step 8).
const DISPLAY = { saved: true, streetNames: true, majorOnly: true, minStreetLengthFt: 300, tallest: 0 };
const LABEL_SETTINGS = {
  streetAboveFt: 15,          // street names float 15 ft above the ground (as streets.add_street_labels)
  streetMaxDistanceFt: 9000,  // web only: farther street names are hidden, or the overview is a wall of text
  tallestAboveFt: 30,         // tallest building names 30 ft above the roof (as the notebook)
  savedAboveFt: 8,            // a saved spot's label 8 ft above its ball (as annotations.add_annotation_markers)
  savedAboveRoofFt: 15,       // a saved building's label 15 ft above its roof
  savedColor: "#e0218a",      // magenta, so saved balls don't look like the red spot marker
  markerRadiusFt: 5,
  clickNearFt: 15,            // a click this close to a saved spot's ball opens it (as annotations.nearest_annotation)
};

let streetLabels = [];        // [{ object, roadClass, lengthFt, behind }]
let tallestLabels = [];       // CSS2DObjects

function makeLabel(text, className, position, style = "") {
  const element = el("div", { className: `label ${className}` }, text);
  if (style) element.style.cssText = style;
  const object = new CSS2DObject(element);
  object.position.copy(position);
  scene.add(object);
  return object;
}

// --- street names (Step 7)

function loadStreets(data) {
  const at = Object.fromEntries(data.columns.map((column, i) => [column, i]));
  streetLabels = data.rows.map((r) => ({
    roadClass: r[at.road_class], lengthFt: r[at.length_ft], behind: false,
    object: makeLabel(r[at.name], "street-label", new THREE.Vector3(r[at.x], r[at.y], r[at.ground_ft] + LABEL_SETTINGS.streetAboveFt)),
  }));
}

// The labels the controls ask for (like streets.choose_labels): road class and minimum length.
const streetWanted = (label) => DISPLAY.streetNames && label.lengthFt >= DISPLAY.minStreetLengthFt
  && (!DISPLAY.majorOnly || label.roadClass === "highway" || label.roadClass === "major");

// Every frame: show a street label if it's wanted, not behind a building (last check) and not too far.
function updateLabelVisibility() {
  const maxSq = LABEL_SETTINGS.streetMaxDistanceFt ** 2;
  for (const label of streetLabels) {
    label.object.visible = streetWanted(label) && !label.behind && label.object.position.distanceToSquared(camera.position) < maxSq;
  }
}

// Behind a building? The notebook's labels hide themselves (always_visible=False). Here: when the camera
// stops, one ray from the camera to each nearby wanted label; if it meets a building first, the label is hidden.
let hiddenCheckTimer = null;
let lastHiddenCheck = "";
function scheduleHiddenCheck() {
  clearTimeout(hiddenCheckTimer);
  hiddenCheckTimer = setTimeout(checkHiddenLabels, 150);
}
function checkHiddenLabels() {
  const key = [camera.position.toArray(), controls.target.toArray(), Object.values(DISPLAY)].join("|");
  if (key === lastHiddenCheck || !world.area) return;              // nothing moved or changed since the last check
  lastHiddenCheck = key;
  const maxSq = LABEL_SETTINGS.streetMaxDistanceFt ** 2;
  const direction = new THREE.Vector3();
  let shown = 0, wanted = 0;
  for (const label of streetLabels) {
    if (!streetWanted(label)) continue;
    wanted += 1;
    const distanceSq = label.object.position.distanceToSquared(camera.position);
    if (distanceSq >= maxSq) continue;
    const distance = Math.sqrt(distanceSq);
    direction.subVectors(label.object.position, camera.position).divideScalar(distance);
    label.behind = firstHit(world, camera.position, direction, distance - 5) !== null;
    if (!label.behind) shown += 1;
  }
  $("labels-note").textContent = streetLabels.length === 0 ? "No street data exported."
    : `${wanted.toLocaleString()} street labels chosen, ${shown.toLocaleString()} in sight now ` +
      `(the rest are behind buildings or over ${(LABEL_SETTINGS.streetMaxDistanceFt / 5280).toFixed(1)} miles away).`;
  render();
}

// --- tallest building names (Step 8)

function updateTallestLabels() {
  for (const object of tallestLabels) scene.remove(object);
  const tallest = [...currentRows].filter((row) => row.height_ft != null)
    .sort((a, b) => b.height_ft - a.height_ft).slice(0, DISPLAY.tallest);
  tallestLabels = tallest.map((row) => {
    const [xMin, yMin, , xMax, yMax, zMax] = row.box;
    return makeLabel(nameOf(row), "tallest-label",
      new THREE.Vector3((xMin + xMax) / 2, (yMin + yMax) / 2, zMax + LABEL_SETTINGS.tallestAboveFt));
  });
}

// --- saved buildings and spots
//
// Kept in THIS browser only (localStorage): nothing is sent anywhere, other visitors and other devices don't
// see them, and clearing the browser's site data deletes them. A saved place:
//   { id, kind: "building" | "spot", key, label, created }        key = the building's Model_ID (savedKey)
//   a spot also has: point (the wall point, ft), bearing (the wall's outward direction), description

const SAVED_STORAGE_KEY = "boston3d.saved.v1";
let savedPlaces = [];
let savedItems = [];          // [{ place, row, point, label }]: what's drawn for each place
const savedGroup = new THREE.Group();
scene.add(savedGroup);
const rowsBySavedKey = new Map();

// Current buildings by their Model_ID (stable across exports); future ones by layer/tile/number.
const savedKey = (row) => (row.layer === "current" && row.id ? row.id : `${row.layer}/${row.tile}/${row.index}`);
const savedBuilding = (row) => savedPlaces.find((place) => place.kind === "building" && place.key === savedKey(row));
const nowText = () => new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

function readSaved() {
  try {
    const list = JSON.parse(localStorage.getItem(SAVED_STORAGE_KEY) || "[]");
    return Array.isArray(list) ? list : [];
  } catch { return []; }
}

function writeSaved() {
  try { localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(savedPlaces)); return true; }
  catch { say("Could not save: this browser blocks storage for this page (a private window?)."); return false; }
}

// The Save buttons at the bottom of the building box.
function saveButtons(row) {
  const box = el("div", { className: "save-buttons" });
  const building = savedBuilding(row);
  if (building) box.append(el("span", { className: "small" }, `★ Building saved as "${building.label}"`));
  else {
    const button = el("button", {}, "☆ Save building");
    button.onclick = () => saveBuilding(row);
    box.append(button);
  }
  if (spot && spot.row === row) {
    if (spot.saved) box.append(el("span", { className: "small" }, `★ Spot saved as "${spot.saved.label}"`));
    else {
      const button = el("button", {}, "☆ Save this spot");
      button.onclick = saveSpot;
      box.append(button);
    }
  }
  return box;
}

function askLabel(suggestion) {
  const text = window.prompt("Save it under this name:", suggestion);
  return text === null ? null : text.trim() || suggestion;
}

function addSaved(place) {
  savedPlaces.push(place);
  if (!writeSaved()) { savedPlaces.pop(); return false; }
  savedChanged();
  say(`Saved: ${place.label}`);
  return true;
}

function saveBuilding(row) {
  const label = askLabel(nameOf(row));
  if (label === null) return;
  addSaved({ id: newId(), kind: "building", key: savedKey(row), label, created: nowText() });
}

function saveSpot() {
  if (!spot) return;
  const label = askLabel(nameOf(spot.row));
  if (label === null) return;
  const place = { id: newId(), kind: "spot", key: savedKey(spot.row), label, created: nowText(),
                  point: spot.surfacePoint.toArray().map((v) => Math.round(v * 100) / 100),
                  bearing: Math.round(spot.bearing * 100) / 100, description: spot.description };
  spot.saved = place;
  if (!addSaved(place)) spot.saved = null;
}

function renameSaved(place) {
  const text = window.prompt("New name:", place.label);
  if (text === null || !text.trim()) return;
  place.label = text.trim();
  writeSaved();
  savedChanged();
}

function removeSaved(place) {
  if (!window.confirm(`Remove "${place.label}" from Saved?`)) return;
  savedPlaces = savedPlaces.filter((p) => p !== place);
  writeSaved();
  if (spot && spot.saved === place) spot.saved = null;
  savedChanged();
}

function savedChanged() {
  drawSaved();
  if (shownInfo.row) showInfo(shownInfo.row, shownInfo.extra);     // its Save buttons change
  render();
}

// Where a saved spot is: its wall point and the wall's outward direction.
function savedSpotGeometry(place) {
  const normal = rayDirection(place.bearing, 0);
  return { normal, surfacePoint: new THREE.Vector3(...place.point) };
}

// Draw every saved place (a ball and a label for a spot, a label over the roof for a building) and list them.
function drawSaved() {
  for (const item of savedItems) scene.remove(item.label);
  for (const child of [...savedGroup.children]) { savedGroup.remove(child); child.geometry.dispose(); }
  savedItems = [];
  for (const place of savedPlaces) {
    const row = rowsBySavedKey.get(place.key);
    if (!row) { savedItems.push({ place, row: null }); continue; }  // its building isn't in this export
    let point;
    if (place.kind === "spot") {
      const { normal, surfacePoint } = savedSpotGeometry(place);
      point = surfacePoint.addScaledVector(normal, SPOT_OUT_FT);
      const marker = new THREE.Mesh(new THREE.SphereGeometry(LABEL_SETTINGS.markerRadiusFt, 16, 12),
                                    new THREE.MeshBasicMaterial({ color: LABEL_SETTINGS.savedColor }));
      marker.position.copy(point);
      savedGroup.add(marker);
    } else {
      const [xMin, yMin, , xMax, yMax, zMax] = row.box;
      point = new THREE.Vector3((xMin + xMax) / 2, (yMin + yMax) / 2, zMax);
    }
    const above = place.kind === "spot" ? LABEL_SETTINGS.savedAboveFt : LABEL_SETTINGS.savedAboveRoofFt;
    const label = makeLabel(`★ ${place.label}`, "saved-label", point.clone().add(new THREE.Vector3(0, 0, above)),
                            `border-left-color:${LABEL_SETTINGS.savedColor}`);
    label.visible = DISPLAY.saved;
    savedItems.push({ place, row, point, label });
  }

  $("saved-list").replaceChildren(...savedItems.map((item) => {
    const { place, row } = item;
    const what = place.kind === "spot" ? "spot" : "building";
    const go = el("button", { className: "go", title: row ? `${place.label}: ${nameOf(row)} (${what}, saved ${place.created})`
                                                           : "This building isn't in the map's data any more" },
                  swatch(LABEL_SETTINGS.savedColor), `${place.label} `, el("span", { className: "small" }, `(${what})`));
    go.disabled = !row;
    go.onclick = () => openSaved(item, true);
    const rename = el("button", { className: "tool", title: "Rename" }, "✎");
    rename.onclick = () => renameSaved(place);
    const remove = el("button", { className: "tool", title: "Remove from Saved" }, "×");
    remove.onclick = () => removeSaved(place);
    return el("li", {}, go, rename, remove);
  }));
  $("saved-note").textContent = savedPlaces.length === 0
    ? "Nothing saved yet: click a building, then ☆ Save building or ☆ Save this spot."
    : "Kept in this browser only: other devices and other visitors don't see them.";
}

// Open a saved place: a building is shown and highlighted; a spot also opens the spot tools exactly there.
function openSaved(item, fly) {
  const { place, row } = item;
  if (!row) return;
  if (place.kind === "spot") {
    const { normal, surfacePoint } = savedSpotGeometry(place);
    setSpotFrom({ layer: row.layerRef, buildingNumber: row.index, row, saved: place, normal, surfacePoint });
    select(row, [`★ ${place.label}`, place.description, `Saved ${place.created}`]);
    if (fly) flyTo(spotView(spot, "wall"));
  } else {
    select(row, [`★ ${place.label}`, `Saved ${place.created}`]);
    if (fly) flyTo(buildingView(row));
  }
  say(`Showing: ${place.label}`);
}

// A click this close to a saved spot's ball opens it.
function nearestSaved(point) {
  if (!DISPLAY.saved) return null;
  let best = null, bestDistance = LABEL_SETTINGS.clickNearFt;
  for (const item of savedItems) {
    if (item.place.kind !== "spot" || !item.row) continue;
    const distance = item.point.distanceTo(point);
    if (distance <= bestDistance) [best, bestDistance] = [item, distance];
  }
  return best;
}

// --- the controls (Step 8)

function controlsChanged() {
  DISPLAY.saved = $("saved-box").checked;
  DISPLAY.streetNames = $("streets-box").checked;
  DISPLAY.majorOnly = $("major-box").checked;
  DISPLAY.minStreetLengthFt = Number($("length-slider").value);
  DISPLAY.tallest = Number($("tallest-slider").value);
  $("length-value").textContent = `${DISPLAY.minStreetLengthFt.toLocaleString()} ft`;
  $("tallest-value").textContent = String(DISPLAY.tallest);
  savedGroup.visible = DISPLAY.saved;
  for (const item of savedItems) if (item.label) item.label.visible = DISPLAY.saved;
  if (tallestLabels.length !== DISPLAY.tallest) updateTallestLabels();
  for (const label of streetLabels) label.behind = false;          // re-checked once the controls settle
  lastHiddenCheck = "";                                            // (even if the camera hasn't moved)
  scheduleHiddenCheck();
  render();
}
for (const id of ["saved-box", "streets-box", "major-box", "length-slider", "tallest-slider"]) {
  $(id).addEventListener("input", controlsChanged);
}

// ------------------------------------------------------------------ clicking

const raycaster = new THREE.Raycaster();
let pointerDown = null;
renderer.domElement.addEventListener("pointerdown", (event) => { pointerDown = [event.clientX, event.clientY]; });
renderer.domElement.addEventListener("pointerup", (event) => {
  if (!pointerDown) return;
  const moved = Math.hypot(event.clientX - pointerDown[0], event.clientY - pointerDown[1]);
  pointerDown = null;
  if (moved > 5) return;                                         // a drag (pan / rotate), not a click
  const pointer = new THREE.Vector2((event.clientX / window.innerWidth) * 2 - 1, -(event.clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hit = pick(world, raycaster.ray);
  if (!hit || hit.terrain) { select(null); return; }             // the ground or the sky
  const near = nearestSaved(hit.point);                          // a saved ball: the click lands on the wall behind it
  if (near) { openSaved(near, false); return; }
  const row = hit.layer.rows[hit.buildingNumber];
  const description = setSpot(hit, row);
  select(row, description ? [description, ...(spot?.unitLines || []), "Spot set here: see the panel on the right."]
                          : ["That's a roof or a ledge: click a wall to check its view and sun."]);
});

// ------------------------------------------------------------------ drawing

let renderRequested = false;
function render() {
  if (renderRequested) return;
  renderRequested = true;
  requestAnimationFrame(frame);
}

function frame(now) {
  renderRequested = false;
  if (flight) {
    const t = Math.min((now - flight.start) / 800, 1);
    const eased = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
    camera.position.lerpVectors(flight.fromPosition, flight.toPosition, eased);
    controls.target.lerpVectors(flight.fromTarget, flight.toTarget, eased);
    if (t === 1) flight = null;
  }
  const moving = controls.update();
  updateLabelVisibility();
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
  if (flight || moving) render();
  else scheduleHiddenCheck();                                    // the camera stopped: which labels are behind buildings?
}

controls.addEventListener("change", render);
window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  labelRenderer.setSize(window.innerWidth, window.innerHeight);
  render();
});

// ------------------------------------------------------------------ loading

function addLayer(kind, tile, header, arrays, rowsByKey) {
  const { mesh, colors, building } = makeBuildings(header, arrays);
  let rowCount = 0;
  for (let p = 0; p < building.length; p++) rowCount = Math.max(rowCount, building[p] + 1);
  const layer = { kind, tile, mesh, colors, building, buildingColors: new Uint8Array(rowCount * 3), rows: [],
                  collision: buildCollision(header, arrays) };
  for (let i = 0; i < rowCount; i++) {
    const row = rowsByKey.get(`${kind}/${tile}/${i}`);
    row.layerRef = layer;
    layer.rows.push(row);
  }
  mesh.visible = kind === "current" || $("future-box").checked;
  world.layers.push(layer);
  recolor(layer);
  scene.add(mesh);
}

async function main() {
  setView(STYLE.startView);
  render();
  const loading = $("loading");
  const [manifest, rows] = await Promise.all([
    fetch("data/manifest.json").then((response) => response.json()),
    readBuildingTable("data/buildings.json"),
  ]);
  const rowsByKey = new Map();
  for (const row of rows) {
    row.searchName = clean(row.name || "");
    rowsByKey.set(`${row.layer}/${row.tile}/${row.index}`, row);
  }
  currentRows = rows.filter((row) => row.layer === "current");
  updateLegend();

  let done = 0;
  loading.textContent = `Loading tiles: 0 of ${manifest.tiles.length}`;
  const area = { xMin: Infinity, xMax: -Infinity, yMin: Infinity, yMax: -Infinity };
  await Promise.all(manifest.tiles.map(async (tile) => {
    const { header, arrays } = await readTileFile(`data/${tile.file}`);
    const terrain = makeTerrain(header, arrays.terrain_heights, `data/${tile.photo}`);
    world.terrains.push(buildTerrainCollision(terrain.geometry));
    scene.add(terrain);
    const [left, right, bottom, top] = header.terrain.bounds;     // the data area = the box around all tiles
    Object.assign(area, { xMin: Math.min(area.xMin, left), xMax: Math.max(area.xMax, right),
                          yMin: Math.min(area.yMin, bottom), yMax: Math.max(area.yMax, top) });
    addLayer("current", tile.name, header, arrays, rowsByKey);
    if (tile.future_file) {
      const future = await readTileFile(`data/${tile.future_file}`);
      addLayer("future", tile.name, future.header, future.arrays, rowsByKey);
    }
    done += 1;
    loading.textContent = `Loading tiles: ${done} of ${manifest.tiles.length}`;
    render();
  }));
  world.area = area;

  // Notebook 8's extras, if export_web.py wrote them.
  if (manifest.streets) loadStreets(await (await fetch(`data/${manifest.streets}`)).json());
  for (const row of rows) rowsBySavedKey.set(savedKey(row), row);  // the places saved in this browser
  savedPlaces = readSaved();
  drawSaved();
  if (manifest.building_units) {                                   // export_web.py --with-units
    const rowsById = new Map(currentRows.map((row) => [row.id, row]));
    attachBuildingUnits(await (await fetch(`data/${manifest.building_units}`)).json(), rowsById, clean);
  }
  controlsChanged();

  loading.style.display = "none";
  say(`${currentRows.length.toLocaleString()} buildings. Search by name, or click a wall.`);
}

main().catch((error) => {
  $("loading").textContent = `Could not load the map: ${error.message}`;
  console.error(error);
});
