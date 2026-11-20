// The clicked wall as a grid of cells (floors x columns), and its hours of sun (Notebook 8, Step 9.2.4).
//
// As in the notebook (citymap/windows.py, window_grid): one row per floor (the building's floor plan,
// floors.js), columns of ~10 ft that fill the wall exactly, column 1 = leftmost as seen from outside,
// and a cell only where the wall really is.
// One difference: the wall = the clicked building's triangles in the SAME PLANE as the clicked one (facing
// within 15 degrees, at most 1.5 ft in front of or behind it). The notebook (walls.py) also joins neighbors
// around gentle curves, so on a curved facade the two can number columns differently.
import * as THREE from "three";
import { sunState } from "./sun.js";
import { hasFloors, floorLevels } from "./floors.js";

export const WALL_SETTINGS = { sameDirectionDeg: 15, samePlaneFt: 1.5, columnFt: 10, rowFt: 12, outFt: 2, drawOutFt: 0.6 };

// The cells of the wall at spot. Out: null, or { cells: [{ floor, column, s0, s1, z0, z1, center, corners }],
// columns, rows, byFloors, sMin, width, right } (rows = floors when the building has a floor plan, else ~12 ft).
export function wallCells(spot) {
  const { layer, buildingNumber, surfacePoint, normal, row } = spot;
  const position = layer.collision.geometry.attributes.position.array;
  const index = layer.collision.geometry.index.array;
  const right = new THREE.Vector3(-normal.y, normal.x, 0).normalize();   // to the right of someone facing the wall
  const cosLimit = Math.cos(THREE.MathUtils.degToRad(WALL_SETTINGS.sameDirectionDeg));
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), n = new THREE.Vector3();
  const flat = [];                                                        // the wall's triangles in (s, z)
  for (let t = 0; t < index.length; t += 3) {
    if (layer.building[index[t]] !== buildingNumber) continue;
    a.fromArray(position, index[t] * 3); b.fromArray(position, index[t + 1] * 3); c.fromArray(position, index[t + 2] * 3);
    n.subVectors(b, a).cross(c.clone().sub(a));
    if (n.lengthSq() < 1e-6) continue;
    n.normalize();
    if (Math.abs(n.dot(normal)) < cosLimit) continue;                    // faces another way
    if (Math.abs(a.clone().sub(surfacePoint).dot(normal)) > WALL_SETTINGS.samePlaneFt) continue;   // another plane
    flat.push([a, b, c].map((p) => [p.dot(right), p.z]));
  }
  if (flat.length === 0) return null;

  const all = flat.flat();
  const sMin = Math.min(...all.map((p) => p[0])), sMax = Math.max(...all.map((p) => p[0]));
  const zMin = Math.min(...all.map((p) => p[1])), zMax = Math.max(...all.map((p) => p[1]));
  const columns = Math.max(1, Math.round((sMax - sMin) / WALL_SETTINGS.columnFt));
  const width = (sMax - sMin) / columns;
  const sAtSpot = surfacePoint.dot(right);

  // The rows: the building's floors (as the notebook), or ~12 ft bands if it has no floor plan.
  const byFloors = hasFloors(row);
  let levels;
  if (byFloors) {
    levels = floorLevels(row);
  } else {
    const count = Math.max(1, Math.round((zMax - zMin) / WALL_SETTINGS.rowFt));
    const height = (zMax - zMin) / count;
    levels = Array.from({ length: count }, (_, i) => ({ floor: null, z0: zMin + i * height, z1: zMin + (i + 1) * height }));
  }

  // A point of the wall plane at (s, z), out ft in front of it.
  const wallPoint = (s, z, out) => surfacePoint.clone().addScaledVector(right, s - sAtSpot)
    .setZ(z).addScaledVector(normal, out);

  const cells = [];
  for (const { floor, z0, z1 } of levels) {
    for (let column = 0; column < columns; column++) {
      const s0 = sMin + column * width;
      const middle = [s0 + width / 2, (z0 + z1) / 2];
      if (!flat.some((triangle) => insideTriangle(middle, triangle))) continue;   // only where the wall really is
      cells.push({ floor, column: column + 1, s0, s1: s0 + width, z0, z1,
                   center: wallPoint(middle[0], middle[1], WALL_SETTINGS.outFt),
                   corners: [[s0, z0], [s0 + width, z0], [s0 + width, z1], [s0, z1]]
                     .map(([s, z]) => wallPoint(s, z, WALL_SETTINGS.drawOutFt)) });
    }
  }
  return { cells, columns, rows: levels.length, byFloors, sMin, width, right };
}

function insideTriangle([x, y], [[x1, y1], [x2, y2], [x3, y3]]) {
  const d1 = (x - x2) * (y1 - y2) - (x1 - x2) * (y - y2);
  const d2 = (x - x3) * (y2 - y3) - (x2 - x3) * (y - y3);
  const d3 = (x - x1) * (y3 - y1) - (x3 - x1) * (y - y1);
  return !((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0));
}

// Hours of sun ("sun" only) for every cell, on the day of steps. Works in small batches so the page stays responsive.
// onProgress(done, total) is called between batches.
export async function wallSunHours(world, spot, wall, steps, onProgress) {
  const stepHours = (steps[1].minutes - steps[0].minutes) / 60;
  const useful = steps.filter((step) => step.elevation > 0);
  for (let i = 0; i < wall.cells.length; i++) {
    const cell = wall.cells[i];
    let sun = 0;
    for (const step of useful) {
      if (sunState(world, cell.center, spot.normal, step.azimuth, step.elevation).state === "sun") sun += stepHours;
    }
    cell.sunHours = sun;
    if (i % 15 === 14) { onProgress(i + 1, wall.cells.length); await new Promise((r) => setTimeout(r, 0)); }
  }
  onProgress(wall.cells.length, wall.cells.length);
}

// Cividis-like colors: dark blue (no sun) -> yellow (most sun). value 0..1.
const STOPS = ["#00204c", "#3a4c6e", "#7c7b78", "#bcae6c", "#fee838"].map((hex) => new THREE.Color(hex));
export function hoursColor(value) {
  const x = Math.min(1, Math.max(0, value)) * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(x));
  return STOPS[i].clone().lerp(STOPS[i + 1], x - i);
}
export const HOURS_GRADIENT = `linear-gradient(to right, ${["#00204c", "#3a4c6e", "#7c7b78", "#bcae6c", "#fee838"].join(", ")})`;

// The cells as colored squares in front of the wall.
export function wallMesh(wall, maxHours) {
  const positions = [], colors = [];
  for (const cell of wall.cells) {
    const [p0, p1, p2, p3] = cell.corners;
    for (const p of [p0, p1, p2, p0, p2, p3]) positions.push(p.x, p.y, p.z);
    const color = hoursColor(maxHours > 0 ? cell.sunHours / maxHours : 0);
    for (let k = 0; k < 6; k++) colors.push(color.r, color.g, color.b);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
}
