// Floors of a building: the browser version of citymap/floors.py (Notebook 7).
// export_web.py gives every building of today's city its floor plan (from floors.floor_plan):
//   floor_ground   elevation where floor 1 starts (ft)       floor_count    number of floors
//   floor_first    height of floor 1 (ft)                     floor_typical  height of every other floor (ft)
//   floor_source   "manual" (your override file), "assessment" (the city's count) or "estimate" (from the height)
// Floor levels are always approximate: the 3D models have no floors.

export const hasFloors = (row) => row.floor_count != null;

// (bottom, top) elevation of floor n, like floors.floor_elevation. Floor 1 = ground floor.
export function floorElevation(row, n) {
  if (n === 1) return [row.floor_ground, row.floor_ground + row.floor_first];
  const bottom = row.floor_ground + row.floor_first + (n - 2) * row.floor_typical;
  return [bottom, bottom + row.floor_typical];
}

// The floor at elevation z, or null below floor 1 / above the top floor, like floors.floor_at_height.
export function floorAtHeight(row, z) {
  if (!hasFloors(row)) return null;
  for (let n = 1; n <= row.floor_count; n++) {
    const [bottom, top] = floorElevation(row, n);
    if (bottom <= z && z < top) return n;
  }
  return null;
}

// Every floor as { floor, z0, z1 }.
export function floorLevels(row) {
  return Array.from({ length: row.floor_count }, (_, i) => {
    const [z0, z1] = floorElevation(row, i + 1);
    return { floor: i + 1, z0, z1 };
  });
}

// "60" or "~50": an estimated count gets a "~", as in the notebooks.
export const countText = (row) => `${row.floor_source === "estimate" ? "~" : ""}${row.floor_count}`;

const COMPASS_WORDS = { N: "north", NE: "northeast", E: "east", SE: "southeast", S: "south", SW: "southwest", W: "west", NW: "northwest" };

// Where along a wall, like windows.along_wall_text: "about 165 ft from the wall's left end (wall ~340 ft wide)".
// Left = as seen from outside. Rounded to 5 ft (spots are only that exact). Not "column 17 of 34": the models
// have no windows, so a column number would look like a window.
export function alongWallText(fromLeftFt, wallWidthFt) {
  const width = Math.max(5, 5 * Math.round(wallWidthFt / 5));
  const distance = 5 * Math.round(Math.max(0, Math.min(fromLeftFt, wallWidthFt)) / 5);
  const where = distance === 0 ? "at the wall's left end"
    : distance >= width ? "at the wall's right end" : `about ${distance} ft from the wall's left end`;
  return `${where} (wall ~${width} ft wide)`;
}

// The words for a spot, like windows.spot_text: "Floor ~19 of 60 (manual count, level estimated),
// south-facing wall (159°), about 5 ft from the wall's left end (wall ~60 ft wide)".
export function spotText(row, floor, direction, bearing, fromLeftFt, wallWidthFt) {
  const wall = `${COMPASS_WORDS[direction]}-facing wall (${Math.round(bearing)}°)`;
  const where = fromLeftFt != null ? `, ${alongWallText(fromLeftFt, wallWidthFt)}` : "";
  if (floor == null) return `${wall}${where} (not on a floor: below floor 1 or roof structure)`;
  return `Floor ~${floor} of ${countText(row)} (${row.floor_source} count, level estimated), ${wall}${where}`;
}
