// Where the sun is, and sun / shade per 10 minutes: the browser version of citymap/sun.py (Notebook 8, Step 9.2).
// Same NOAA formula, same states, same settings. Times are Boston clock time (daylight saving included).
import { rayDirection, distanceToEdge, firstHit } from "./rays.js";

export const SUN_SETTINGS = {
  stepMinutes: 10,          // one sun position every 10 minutes
  tallestFt: 1000,          // higher than every building in the model: a ray above it is free
  unknownBelowFt: 300,      // a ray leaving our data below this height could be blocked by a building we don't have
};

// Boston, at the Hancock tower (from the catalog, as in the notebook). Over our 4 x 3 miles the sun's position
// differs by far less than the 10-minute steps matter, so one point is enough.
export const LATITUDE = 42.3492;
export const LONGITUDE = -71.0752;

export const STATE_COLORS = {
  "sun": "#c77700", "sun?": "#e0a73a", "shade": "#5b6c8f", "behind wall": "#c9c9c9", "night": "#2b2b2b",
};

const rad = (degrees) => (degrees * Math.PI) / 180;
const deg = (radians) => (radians * 180) / Math.PI;

// ------------------------------------------------------------------ Boston clock time <-> UTC

// How many minutes Boston's clock is ahead of UTC at this instant: -300 in winter (EST), -240 in summer (EDT).
// The browser knows the time zone rules (Intl), like Python's zoneinfo.
const bostonClock = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York", hourCycle: "h23",
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});
function bostonOffsetMinutes(utcMs) {
  const parts = Object.fromEntries(bostonClock.formatToParts(new Date(utcMs)).map((p) => [p.type, p.value]));
  const clockAsUtc = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute);
  return Math.round((clockAsUtc - utcMs) / 60000);
}

// A Boston clock time (a day + minutes after midnight) -> the UTC instant, in milliseconds.
export function bostonToUtc(year, month, day, minutes) {
  const clockAsUtc = Date.UTC(year, month - 1, day, 0, minutes);
  let utc = clockAsUtc + 300 * 60000;                            // first guess: EST
  for (let i = 0; i < 2; i++) utc = clockAsUtc - bostonOffsetMinutes(utc) * 60000;
  return utc;
}

export const clockText = (minutes) =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

// ------------------------------------------------------------------ the sun's position (NOAA)

// The sun's TRUE compass bearing (azimuth, 0 = north, 90 = east) and elevation above the horizon, in degrees.
// The steps are explained in citymap/sun.py, sun_position (and Notebook 8, 9.2.1).
export function sunPosition(utcMs, latitude = LATITUDE, longitude = LONGITUDE) {
  const julianDay = utcMs / 86400000 + 2440587.5;
  const t = (julianDay - 2451545.0) / 36525;                    // Julian centuries since 1 Jan 2000, noon

  const meanLongitude = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360;
  const meanAnomaly = 357.52911 + t * (35999.05029 - 0.0001537 * t);
  const eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);
  const m = rad(meanAnomaly);
  const center = Math.sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t))
    + Math.sin(2 * m) * (0.019993 - 0.000101 * t) + Math.sin(3 * m) * 0.000289;
  const omega = rad(125.04 - 1934.136 * t);
  const apparentLongitude = meanLongitude + center - 0.00569 - 0.00478 * Math.sin(omega);
  const meanObliquity = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60;
  const obliquity = rad(meanObliquity + 0.00256 * Math.cos(omega));
  const declination = Math.asin(Math.sin(obliquity) * Math.sin(rad(apparentLongitude)));

  const y = Math.tan(obliquity / 2) ** 2;
  const l0 = rad(meanLongitude);
  const equationOfTime = 4 * deg(                               // minutes
    y * Math.sin(2 * l0) - 2 * eccentricity * Math.sin(m) + 4 * eccentricity * y * Math.sin(m) * Math.cos(2 * l0)
    - 0.5 * y * y * Math.sin(4 * l0) - 1.25 * eccentricity ** 2 * Math.sin(2 * m));

  const date = new Date(utcMs);
  const minutesUtc = date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  const solarMinutes = (((minutesUtc + equationOfTime + 4 * longitude) % 1440) + 1440) % 1440;
  const hourAngle = rad(solarMinutes / 4 - 180);                // 0 at solar noon

  const lat = rad(latitude);
  const cosZenith = Math.sin(lat) * Math.sin(declination) + Math.cos(lat) * Math.cos(declination) * Math.cos(hourAngle);
  const zenith = Math.acos(Math.min(1, Math.max(-1, cosZenith)));
  const elevation = 90 - deg(zenith);
  const cosAzimuth = (Math.sin(lat) * Math.cos(zenith) - Math.sin(declination)) / (Math.cos(lat) * Math.sin(zenith));
  let azimuth = deg(Math.acos(Math.min(1, Math.max(-1, cosAzimuth))));
  azimuth = hourAngle > 0 ? (azimuth + 180) % 360 : (540 - azimuth) % 360;
  return { azimuth, elevation };
}

// The sun every stepMinutes over one Boston day. day = "2026-12-21". Out: [{ minutes, utc, azimuth, elevation }].
export function sunSteps(day, stepMinutes = SUN_SETTINGS.stepMinutes) {
  const [year, month, date] = day.split("-").map(Number);
  const steps = [];
  for (let minutes = 0; minutes < 1440; minutes += stepMinutes) {
    const utc = bostonToUtc(year, month, date, minutes);
    steps.push({ minutes, utc, ...sunPosition(utc) });
  }
  return steps;
}

// Sunrise and sunset to the minute, by the official definition (elevation -0.833 degrees), as clock text.
export function sunriseSunset(day) {
  const up = sunSteps(day, 1).filter((step) => step.elevation > -0.833);
  return up.length ? [clockText(up[0].minutes), clockText(up[up.length - 1].minutes)] : ["-", "-"];
}

// ------------------------------------------------------------------ sun on a spot

// Sun or not at one spot for one sun position: { state, hit }. The same order of checks as sun.sun_state:
// night, behind wall (the sun on the other side of the surface), shade (a building in the way), sun? (the ray
// leaves our data low down), sun.
export function sunState(world, start, normal, azimuth, elevation) {
  if (elevation <= 0) return { state: "night", hit: null };
  const direction = rayDirection(azimuth, elevation);
  if (direction.dot(normal) <= 0) return { state: "behind wall", hit: null };
  const toEdge = distanceToEdge(world.area, start, direction);
  const toFree = Math.max(0, (SUN_SETTINGS.tallestFt - start.z) / direction.z);   // until above every building
  const hit = firstHit(world, start, direction, Math.min(toEdge, toFree));
  if (hit) return { state: "shade", hit };
  if (toEdge < toFree && start.z + toEdge * direction.z < SUN_SETTINGS.unknownBelowFt) return { state: "sun?", hit: null };
  return { state: "sun", hit: null };
}

// The state of a spot at every step of a day. Out: the steps, each with state and hit added.
export function exposure(world, spot, steps) {
  return steps.map((step) => ({ ...step, ...sunState(world, spot.point, spot.normal, step.azimuth, step.elevation) }));
}

// Hours per state, e.g. { sun: 8.3, "sun?": 0, shade: 0.5, "behind wall": 0, night: 15.2 }.
export function hours(timeline, stepMinutes = SUN_SETTINGS.stepMinutes) {
  const result = Object.fromEntries(Object.keys(STATE_COLORS).map((state) => [state, 0]));
  for (const step of timeline) result[step.state] += stepMinutes / 60;
  return result;
}
