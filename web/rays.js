// Ray tests against the buildings, and the view check: the browser version of citymap/rays.py (Notebook 8, Step 9.1).
//
// In Python, VTK's vtkModifiedBSPTree makes ray tests fast. Here the same job is done by three-mesh-bvh:
// a "bounding volume hierarchy" built once per tile, so a ray only checks the few triangles near it
// instead of all 2 million.
import * as THREE from "three";
import { MeshBVH } from "three-mesh-bvh";

export const RAY_SETTINGS = {
  skipNearFt: 0.5,           // hits closer than this to the start are ignored (the spot's own wall)
  maxViewFt: 10560,          // 2 miles: a view ray reaching this far without a hit is "open"
  fanStepDeg: 2,             // the view check's rays are this many degrees apart
  gridToTrueNorthDeg: 0.34,  // the map grid is turned 0.34 degrees clockwise from true north (Notebook 7b, 2.5)
};

export const OUTCOME_COLORS = { blocked: "#d62728", open: "#2ca02c", unknown: "#9a9a9a" };

// ------------------------------------------------------------------ search structures

// A copy of a tile's buildings in plain feet (Float32), with its search structure.
// (The drawn mesh keeps its 2-byte positions; the search structure needs real coordinates.)
// The points stay in the same order, so the building number of a hit is building[hit.face.a], as in app.js.
export function buildCollision(header, arrays) {
  const q = arrays.positions;
  const feet = new Float32Array(q.length);
  for (let i = 0; i < q.length; i += 3) {
    for (let k = 0; k < 3; k++) feet[i + k] = header.low[k] + (q[i + k] / 65535) * (header.high[k] - header.low[k]);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(feet, 3));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(arrays.triangles), 1));   // a copy: the BVH reorders it
  const bvh = new MeshBVH(geometry);
  geometry.computeBoundingBox();
  return { geometry, bvh, box: geometry.boundingBox };
}

// The same for a terrain mesh whose geometry is already in feet (see app.js, makeTerrain).
export function buildTerrainCollision(geometry) {
  const bvh = new MeshBVH(geometry);
  geometry.computeBoundingBox();
  return { geometry, bvh, box: geometry.boundingBox };
}

// ------------------------------------------------------------------ the first hit

const _ray = new THREE.Ray();
const _boxPoint = new THREE.Vector3();

function hitOne(collision, ray, near, far) {
  if (!collision.box.containsPoint(ray.origin)) {                 // quick: does the ray reach the tile's box in time?
    const entry = ray.intersectBox(collision.box, _boxPoint);
    if (!entry || ray.origin.distanceTo(entry) > far) return null;
  }
  return collision.bvh.raycastFirst(ray, THREE.DoubleSide, near, far);
}

// The first building on the line from start, along direction (length 1), within length ft.
// world.layers: the building layers (only visible ones count). Out: null or { layer, buildingNumber, point, distance, face }.
export function firstHit(world, start, direction, length) {
  _ray.set(start, direction);
  let best = null;
  for (const layer of world.layers) {
    if (!layer.mesh.visible) continue;
    const hit = hitOne(layer.collision, _ray, RAY_SETTINGS.skipNearFt, best ? best.distance : length);
    if (hit && (!best || hit.distance < best.distance)) {
      best = { layer, buildingNumber: layer.building[hit.face.a], point: hit.point.clone(), distance: hit.distance, face: hit.face };
    }
  }
  return best;
}

// What a click hits: the nearest visible building or terrain. Out: null, { terrain: true }, or a firstHit-like object.
export function pick(world, ray) {
  let best = null;
  for (const layer of world.layers) {
    if (!layer.mesh.visible) continue;
    const hit = hitOne(layer.collision, ray, 0, best ? best.distance : Infinity);
    if (hit && (!best || hit.distance < best.distance)) {
      best = { layer, buildingNumber: layer.building[hit.face.a], point: hit.point.clone(), distance: hit.distance,
               normal: hit.face.normal.clone() };
    }
  }
  for (const terrain of world.terrains) {
    const hit = hitOne(terrain, ray, 0, best ? best.distance : Infinity);
    if (hit && (!best || hit.distance < best.distance)) best = { terrain: true, distance: hit.distance };
  }
  return best;
}

// ------------------------------------------------------------------ directions and where the data ends

// A direction (length 1) from a TRUE compass bearing and an angle above level (the reverse of trueBearing).
export function rayDirection(bearing, elevation = 0) {
  const grid = THREE.MathUtils.degToRad(bearing - RAY_SETTINGS.gridToTrueNorthDeg);
  const up = THREE.MathUtils.degToRad(elevation);
  return new THREE.Vector3(Math.sin(grid) * Math.cos(up), Math.cos(grid) * Math.cos(up), Math.sin(up));
}

// The true compass bearing a surface faces (from its outward normal), 0-360 degrees.
export function trueBearing(normal) {
  const grid = THREE.MathUtils.radToDeg(Math.atan2(normal.x, normal.y));
  return (((grid + RAY_SETTINGS.gridToTrueNorthDeg) % 360) + 360) % 360;
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
export const compassLabel = (bearing) => COMPASS[Math.floor(((bearing + 22.5) % 360) / 45)];

// How far from start along direction before leaving the data area, seen from above (as rays.distance_to_edge).
export function distanceToEdge(area, start, direction) {
  const distances = [];
  for (const [value, step, low, high] of [[start.x, direction.x, area.xMin, area.xMax], [start.y, direction.y, area.yMin, area.yMax]]) {
    if (step > 1e-12) distances.push((high - value) / step);
    else if (step < -1e-12) distances.push((low - value) / step);
  }
  return distances.length ? Math.max(0, Math.min(...distances)) : Infinity;
}

// ------------------------------------------------------------------ the view check

// A fan of level rays from the spot over the half the wall faces (bearing - 88 to + 88), as rays.view_check.
// Out: [{ bearing, outcome: "blocked" | "open" | "unknown", hit, distance, end }].
export function viewCheck(world, spot, elevation = 0) {
  const results = [];
  for (let offset = -88; offset <= 88 + 1e-9; offset += RAY_SETTINGS.fanStepDeg) {
    const bearing = (((spot.bearing + offset) % 360) + 360) % 360;
    const direction = rayDirection(bearing, elevation);
    const edge = distanceToEdge(world.area, spot.point, direction);
    const length = Math.min(RAY_SETTINGS.maxViewFt, edge);
    const hit = firstHit(world, spot.point, direction, length);
    let outcome, distance;
    if (hit) [outcome, distance] = ["blocked", hit.distance];
    else if (edge < RAY_SETTINGS.maxViewFt) [outcome, distance] = ["unknown", edge];
    else [outcome, distance] = ["open", RAY_SETTINGS.maxViewFt];
    results.push({ bearing, outcome, hit, distance, end: spot.point.clone().addScaledVector(direction, distance) });
  }
  return results;
}

// The fan as colored line segments, ready to add to the scene.
export function rayLines(start, fan) {
  const positions = [];
  const colors = [];
  for (const ray of fan) {
    positions.push(start.x, start.y, start.z, ray.end.x, ray.end.y, ray.end.z);
    const color = new THREE.Color(OUTCOME_COLORS[ray.outcome]);
    colors.push(color.r, color.g, color.b, color.r, color.g, color.b);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ vertexColors: true, depthTest: false }));
}
