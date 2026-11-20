// Extra details and apartment positions for some buildings (data/building_units.json, from
// data/buildings/ via export_web.py --with-units). Today: Ora Seaport.
//
// The building's own website is the authority (its floor plates list every apartment); the 3D model only
// says which way each wall faces and where along it a unit is. A unit's position is a stretch of one wall:
// from start to end ft, measured along the wall from its left end as seen from outside. A clicked spot is
// matched to a wall by direction (within 25 degrees) and distance (within 6 ft of the wall's line), then to
// the unit whose stretch holds it.
// Notes say WHO disagrees, by category:
//   website  the website contradicts itself (e.g. listed vs drawn size)   -> a warning (⚠)
//   model    the 3D model is too coarse to follow the website             -> a note (ℹ)
//   city     the city's data names or places it differently               -> a note (ℹ)
//   unknown  nobody says (windows, more floors, unlisted sizes)          -> (?)
// No three.js here, so this file can be tested on its own.

export const UNIT_SETTINGS = { sameDirectionDeg: 25, nearWallFt: 6, edgeSlackFt: 2 };

const CATEGORY_WORDS = { website: "⚠ Website inconsistency", model: "ℹ 3D model note", city: "ℹ City data note",
                         unknown: "? Not known" };

// One note as a line of text: "⚠ Website inconsistency (size): ..."
export function noteText(note) {
  return `${CATEGORY_WORDS[note.category] || "ℹ Note"} (${note.kind}): ${note.text}`;
}

// Hang each building's data on its row (row.unitsData), and let search find it by its other names.
export function attachBuildingUnits(data, rowsById, clean) {
  let attached = 0;
  for (const [id, building] of Object.entries(data.buildings || {})) {
    const row = rowsById.get(id);
    if (!row) continue;
    row.unitsData = building;
    const details = building.details || {};
    if (details.name) {
      row.catalogName = row.name;
      row.name = row.name && row.name !== details.name ? `${details.name} (${row.name})` : details.name;
    }
    row.searchName = clean([row.name, ...(details.also_known_as || [])].join(" "));
    attached += 1;
  }
  return attached;
}

function angleBetween(a, b) {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
}

// The wall of building at the clicked point (x, y, view feet) facing bearing (true degrees), and how far along it.
// Out: { wall, s, distance } or null.
export function wallAt(building, point, bearing) {
  let best = null;
  for (const wall of building.walls) {
    if (angleBetween(wall.bearing, bearing) > UNIT_SETTINGS.sameDirectionDeg) continue;
    const [ax, ay] = wall.left, [bx, by] = wall.right;
    const length = Math.hypot(bx - ax, by - ay);
    const ux = (bx - ax) / length, uy = (by - ay) / length;
    const s = (point.x - ax) * ux + (point.y - ay) * uy;                     // along the wall, from its left end
    if (s < -UNIT_SETTINGS.edgeSlackFt || s > length + UNIT_SETTINGS.edgeSlackFt) continue;
    const distance = Math.abs((point.x - ax) * uy - (point.y - ay) * ux);   // away from the wall's line
    if (distance > UNIT_SETTINGS.nearWallFt) continue;
    if (!best || distance < best.distance) best = { wall, s: Math.min(Math.max(s, 0), length), distance };
  }
  return best;
}

const edgeGap = (u, s) => Math.min(s - u.start, u.end - s);

// The unit on floor at this spot. Out: { wall, s, unit } (unit may be null), or null if no wall matches.
export function unitAt(building, point, bearing, floor) {
  const found = wallAt(building, point, bearing);
  if (!found) return null;
  const slack = UNIT_SETTINGS.edgeSlackFt;
  const inside = building.units.filter((u) => u.floor === floor && u.wall === found.wall.wall && u.start != null
                                              && u.start - slack <= found.s && found.s <= u.end + slack);
  inside.sort((a, b) => edgeGap(b, found.s) - edgeGap(a, found.s));   // on a shared edge: the unit that holds it
  return { ...found, unit: inside[0] || null };
}

// The website link to check the real, current info: { href, text } or null.
export function websiteLink(building) {
  const details = building.details || {};
  return details.website ? { href: details.website, text: details.website_text || details.website } : null;
}

const positionsChecked = (building, unit) =>
  unit.status === "checked" || (building.details || {}).positions_status === "checked";

// The building's own lines for the info box: details, where the data comes from and when, then its notes.
export function buildingDetailLines(building) {
  const details = building.details || {};
  const lines = [...(details.lines || [])];
  if (details.listing_fetched) {
    lines.push(`Listing (units for rent, rent, available date, bedrooms, listed sq ft) fetched from the website on ` +
               details.listing_fetched);
  }
  lines.push(...rentSummaryLines(building));
  lines.push(details.positions_status === "checked" ? "Unit positions: checked"
             : "Unit positions: DRAFT (fitted from the website's floor plates, not yet checked)");
  for (const note of details.notes || []) lines.push(noteText(note));
  return lines;
}

const round = (v) => Math.round(v);
const dollars = (v) => `$${Math.round(v).toLocaleString("en-US")}`;

// The website's date "12/14/2026" -> a Date, or null.
function websiteDate(text) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(text || "").trim());
  return m ? new Date(Number(m[3]), Number(m[1]) - 1, Number(m[2])) : null;
}

// "available now (since 9/6/2026)" or "available from 12/14/2026", judged on the day the listing was fetched.
function availableText(unit, fetched) {
  const date = websiteDate(unit.available);
  if (!date) return unit.available ? `available ${unit.available}` : "available date not given";
  const fetchedDay = fetched ? new Date(`${fetched}T00:00:00`) : null;
  return fetchedDay && date <= fetchedDay ? `available now (since ${unit.available})` : `available from ${unit.available}`;
}

// One entry per apartment (a corner apartment has a row per wall).
function apartments(building) {
  const seen = new Map();
  for (const unit of building.units) if (!seen.has(unit.unit)) seen.set(unit.unit, unit);
  return [...seen.values()];
}

// The building box: how many apartments were for rent when the listing was fetched, and their rents by type.
function rentSummaryLines(building) {
  const all = apartments(building);
  const forRent = all.filter((unit) => unit.rent != null);
  const fetched = (building.details || {}).listing_fetched;
  if (!forRent.length) return [];
  const byType = new Map();
  for (const unit of forRent) {
    const type = unit.bedrooms || "?";
    if (!byType.has(type)) byType.set(type, []);
    byType.get(type).push(unit.rent);
  }
  const types = [...byType.entries()].sort((a, b) => Math.min(...a[1]) - Math.min(...b[1])).map(([type, rents]) => {
    const low = Math.min(...rents), high = Math.max(...rents);
    return `${type} ${low === high ? dollars(low) : `${dollars(low)}-${dollars(high)}`} (${rents.length})`;
  });
  return [`For rent${fetched ? ` on ${fetched}` : ""}: ${forRent.length} of ${all.length} apartments. ` +
            `Rent a month: ${types.join(", ")}`,
          "? Rents and availability change daily: these are from the listing fetch, check the website for today's"];
}

// What to say about a clicked spot: the apartment there, and its notes.
export function unitLines(building, found, floor) {
  const details = building.details || {};
  const floors = building.units.map((u) => u.floor);
  const lowest = Math.min(...floors), highest = Math.max(...floors);
  if (floor == null) return ["Apartments: this height is outside the building's floors."];
  if (floor < lowest || floor > highest) {
    return [`Apartments: none on floor ${floor} in the website's floor plates; they are on floors ${lowest}-${highest}.`];
  }
  if (!found) return ["Apartments: this wall has no apartments in the floor plates (another part of the building, " +
                      "e.g. the hotel, the podium or a rooftop structure)."];
  const { wall, s, unit } = found;
  if (!unit) return [`Apartments: no unit drawn here on floor ${floor}, ${round(s)} ft along wall ${wall.wall} (${wall.direction}).`];
  const size = unit.listed_sqft != null
    ? `${unit.bedrooms ? `${unit.bedrooms}, ` : ""}${round(unit.listed_sqft)} sq ft (website listing, fetched ${unit.listed_fetched || details.listing_fetched || "?"})`
    : `~${unit.drawn_sqft} sq ft measured from the floor plate (approximate)`;
  const fetched = unit.listed_fetched || details.listing_fetched;
  const onDay = fetched ? ` on ${fetched}` : "";
  const rent = unit.rent != null
    ? `For rent${onDay}: ${dollars(unit.rent)} a month, ${availableText(unit, fetched)}` +
      (unit.max_rent != null ? ` (the page's hidden "Max Rent" column: ${dollars(unit.max_rent)})` : "")
    : `Not for rent${onDay} (not in the website's availability list then)`;
  const lines = [
    `Apartment ${unit.unit}${positionsChecked(building, unit) ? "" : " (draft position)"}: floor ${unit.floor}, ${size}`,
    rent,
    `Its facade here: ${round(unit.start)}-${round(unit.end)} ft along wall ${wall.wall} (${wall.direction}), ` +
      "from the wall's left end seen from outside",
  ];
  const others = building.units.filter((u) => u.floor === unit.floor && u.unit === unit.unit && u.wall && u.wall !== unit.wall);
  if (others.length) lines.push(`Corner unit: also faces ${others.map((u) => `${u.direction} (${u.wall})`).join(", ")}`);
  for (const note of unit.notes || []) lines.push(noteText(note));
  return lines;
}
