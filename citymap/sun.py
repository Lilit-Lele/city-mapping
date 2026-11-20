"""Where the sun is, and how many hours of direct sun a window gets (Notebook 8, Step 9.2).

    steps = sun.sun_steps(date(2026, 12, 21), latitude, longitude)        # every 10 minutes of that day
    timeline = sun.exposure(locators, tiles, area, spot, steps)            # sun / shade / ... per step
    sun.hours(timeline)                                                    # {"sun": 3.2, "shade": 1.5, ...}

The sun's position: NOAA's solar position equations (the "General Solar Position" spreadsheet of the
US National Oceanic and Atmospheric Administration), written out in numpy below; no extra library.
Accurate to well under a degree, plenty for "sun or shade". Times are local Boston time, with
daylight saving time, from Python's own zoneinfo.

Not included: refraction (near the horizon the air bends sunlight, so the sun looks ~0.5 degrees higher than
it is), trees, and buildings outside the loaded tiles (steps whose ray leaves our data low down are
marked "sun?" instead of "sun").
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyvista as pv

from citymap import rays, walls as walls_module

TIME_ZONE = ZoneInfo("America/New_York")

SUN_SETTINGS = {
    "step_minutes": 10,            # one sun position every 10 minutes
    "tallest_ft": 1_000.0,         # higher than every building in the model (tallest: ~800 ft): a ray above it is free
    "unknown_below_ft": 300.0,     # a ray that leaves our data below this height could be blocked by a building
                                   # we don't have (outside the tiles): marked "sun?" instead of "sun"
}

STATE_COLORS = {"sun": "#f2b705", "sun?": "#f7dc8a", "shade": "#5b6c8f", "behind wall": "#c9c9c9", "night": "#2b2b2b"}


# ---------------------------------------------------------------- the sun's position (NOAA)

def sun_position(when, latitude, longitude):
    """The sun's TRUE compass bearing (azimuth, 0 = north, 90 = east) and elevation (degrees above the horizon).

    In:  when, a datetime WITH a time zone (e.g. from sun_steps); latitude and longitude in degrees
         (longitude negative = west, Boston is about 42.35, -71.07).
    Out: (azimuth, elevation) in degrees.

    The steps (NOAA's spreadsheet, column by column): the time in Julian centuries since the year 2000,
    the sun's mean longitude and anomaly, the Earth's orbit eccentricity, the equation of center, the
    sun's apparent longitude, the Earth's tilt (obliquity), then the declination (how far north of the
    equator the sun stands) and the equation of time (how far sun time runs ahead of clock time).
    From those, the hour angle (how far the sun is from its highest point, in degrees) gives elevation
    and azimuth with standard spherical trigonometry.
    """
    utc = when.astimezone(ZoneInfo("UTC"))
    julian_day = utc.timestamp() / 86_400 + 2_440_587.5             # days since 4713 BC, the astronomers' clock
    t = (julian_day - 2_451_545.0) / 36_525                          # Julian centuries since 1 Jan 2000, noon

    mean_longitude = (280.46646 + t * (36_000.76983 + t * 0.0003032)) % 360
    mean_anomaly = 357.52911 + t * (35_999.05029 - 0.0001537 * t)
    eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    m = np.radians(mean_anomaly)
    center = (np.sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t))
              + np.sin(2 * m) * (0.019993 - 0.000101 * t) + np.sin(3 * m) * 0.000289)
    omega = np.radians(125.04 - 1_934.136 * t)
    apparent_longitude = mean_longitude + center - 0.00569 - 0.00478 * np.sin(omega)
    mean_obliquity = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    obliquity = np.radians(mean_obliquity + 0.00256 * np.cos(omega))
    declination = np.arcsin(np.sin(obliquity) * np.sin(np.radians(apparent_longitude)))

    y = np.tan(obliquity / 2) ** 2
    l0 = np.radians(mean_longitude)
    equation_of_time = 4 * np.degrees(                               # minutes
        y * np.sin(2 * l0) - 2 * eccentricity * np.sin(m) + 4 * eccentricity * y * np.sin(m) * np.cos(2 * l0)
        - 0.5 * y * y * np.sin(4 * l0) - 1.25 * eccentricity ** 2 * np.sin(2 * m))

    minutes_utc = utc.hour * 60 + utc.minute + utc.second / 60
    solar_minutes = (minutes_utc + equation_of_time + 4 * longitude) % 1_440      # local sun time
    hour_angle = np.radians(solar_minutes / 4 - 180)                 # 0 at solar noon, negative in the morning

    lat = np.radians(latitude)
    cos_zenith = np.sin(lat) * np.sin(declination) + np.cos(lat) * np.cos(declination) * np.cos(hour_angle)
    zenith = np.arccos(np.clip(cos_zenith, -1, 1))                   # angle from straight up
    elevation = 90 - np.degrees(zenith)

    cos_azimuth = (np.sin(lat) * np.cos(zenith) - np.sin(declination)) / (np.cos(lat) * np.sin(zenith))
    azimuth = np.degrees(np.arccos(np.clip(cos_azimuth, -1, 1)))     # from south, in the formula's convention
    azimuth = (azimuth + 180) % 360 if hour_angle > 0 else (540 - azimuth) % 360   # -> from north, clockwise
    return float(azimuth), float(elevation)


def sun_steps(day, latitude, longitude, step_minutes=None):
    """The sun's position every step_minutes over one day, in local time (daylight saving included).

    In:  day, a datetime.date; latitude, longitude.
    Out: a DataFrame: time (local datetime), azimuth, elevation.
    """
    step_minutes = step_minutes or SUN_SETTINGS["step_minutes"]
    midnight = datetime.combine(day, time(0, 0), tzinfo=TIME_ZONE)
    rows = []
    for k in range(24 * 60 // step_minutes):
        when = midnight + timedelta(minutes=k * step_minutes)
        azimuth, elevation = sun_position(when, latitude, longitude)
        rows.append({"time": when, "azimuth": azimuth, "elevation": elevation})
    return pd.DataFrame(rows)


def sunrise_sunset(day, latitude, longitude):
    """Sunrise and sunset to the minute, by the official definition (the top of the sun's disk on the horizon,
    with refraction: elevation -0.833 degrees). Used to check sun_position against published times."""
    steps = sun_steps(day, latitude, longitude, step_minutes=1)
    up = steps[steps["elevation"] > -0.833]
    return up["time"].iloc[0], up["time"].iloc[-1]


# ---------------------------------------------------------------- sun on a window (Step 9.2)

def sun_state(locators, tiles, area, start, wall_direction, azimuth, elevation):
    """Sun or not, at one spot, for one sun position. Out: (state, model_id of the shading building or None).

    States, in the order they are checked:
        "night"        the sun is below the horizon
        "behind wall"  the sun is on the other side of the wall (it can't shine on it)
        "shade"        a ray from the spot toward the sun meets a building
        "sun?"         no building in our data, but the ray leaves the loaded tiles below unknown_below_ft:
                       a building outside them could block it
        "sun"          direct sun
    """
    if elevation <= 0:
        return "night", None
    direction = rays.ray_direction(azimuth, elevation)
    if direction[:2] @ wall_direction <= 0:                           # the sun's horizontal direction vs the wall's
        return "behind wall", None
    to_edge = rays.distance_to_edge(area, start, direction)
    to_free = max(0.0, (SUN_SETTINGS["tallest_ft"] - start[2]) / direction[2])    # until above every building
    length = min(to_edge, to_free)
    hit = rays.first_hit(locators, tiles, start, start + length * direction)
    if hit is not None:
        return "shade", hit["model_id"]
    if to_edge < to_free and start[2] + to_edge * direction[2] < SUN_SETTINGS["unknown_below_ft"]:
        return "sun?", None
    return "sun", None


def exposure(locators, tiles, area, spot, steps):
    """The state of one annotated spot at every step of the day.

    In:  spot from windows.locate (its "point" is 2 ft in front of the wall, its "wall" has the bearing);
         steps from sun_steps.
    Out: steps plus two columns: state (see sun_state) and model_id (the building that shades it).
    """
    start = np.asarray(spot["point"], dtype=float)
    wall_direction = walls_module.direction_from_bearing(spot["wall"]["bearing"])
    states = [sun_state(locators, tiles, area, start, wall_direction, step["azimuth"], step["elevation"])
              for index, step in steps.iterrows()]
    timeline = steps.copy()
    timeline["state"] = [state for state, model_id in states]
    timeline["model_id"] = [model_id for state, model_id in states]
    return timeline


def hours(timeline):
    """Hours per state, e.g. {"sun": 3.2, "sun?": 0.0, "shade": 1.5, "behind wall": 4.5, "night": 14.8}."""
    step_hours = (timeline["time"].iloc[1] - timeline["time"].iloc[0]).total_seconds() / 3600
    counts = timeline["state"].value_counts()
    return {state: round(float(counts.get(state, 0) * step_hours), 2) for state in STATE_COLORS}


def timeline_html(timeline, width_px=720):
    """A colored bar, one slice per step, midnight to midnight, with hour marks. For ipywidgets.HTML / display."""
    n = len(timeline)
    slices = "".join(
        f'<div title="{step["time"]:%H:%M} {step["state"]}" style="flex:1;background:{STATE_COLORS[step["state"]]}"></div>'
        for index, step in timeline.iterrows())
    marks = "".join(f'<span style="position:absolute;left:{100 * h / 24:.2f}%;transform:translateX(-50%)">{h}</span>'
                    for h in range(0, 25, 3))
    legend = " ".join(f'<span style="display:inline-block;width:10px;height:10px;background:{color};'
                      f'border:1px solid #888;margin:0 3px 0 10px"></span>{state}' for state, color in STATE_COLORS.items())
    return (f'<div style="width:{width_px}px;font:12px sans-serif">'
            f'<div style="display:flex;height:22px;border:1px solid #888">{slices}</div>'
            f'<div style="position:relative;height:16px">{marks}</div><div>{legend}</div></div>')


# ---------------------------------------------------------------- the whole wall (Step 9.2, optional view)

def wall_sun_hours(locators, tiles, area, spot, steps):
    """Hours of direct sun ("sun" only) for every cell of the spot's wall, on the day of steps.

    In:  spot from windows.locate (needs "frame", "cells", "wall"); steps from sun_steps (20-minute steps
         are enough here and twice as fast as 10).
    Out: spot["cells"] plus columns sun_hours and unsure_hours ("sun?").
    Only the steps when the sun is up and in front of the wall are tested, for every cell.
    """
    from citymap import windows                                      # here, to avoid a circular import
    frame = spot["frame"]
    wall_direction = walls_module.direction_from_bearing(spot["wall"]["bearing"])
    step_hours = (steps["time"].iloc[1] - steps["time"].iloc[0]).total_seconds() / 3600
    useful = [(step["azimuth"], step["elevation"]) for index, step in steps.iterrows()
              if step["elevation"] > 0 and rays.ray_direction(step["azimuth"], step["elevation"])[:2] @ wall_direction > 0]
    cells = spot["cells"].copy()
    sun_hours, unsure_hours = [], []
    for index, cell in cells.iterrows():
        start = windows.wall_point(frame, (cell["left_s"] + cell["right_s"]) / 2, (cell["bottom"] + cell["top"]) / 2,
                                   windows.GRID_SETTINGS["marker_out_ft"])
        states = [sun_state(locators, tiles, area, start, wall_direction, azimuth, elevation)[0]
                  for azimuth, elevation in useful]
        sun_hours.append(states.count("sun") * step_hours)
        unsure_hours.append(states.count("sun?") * step_hours)
    cells["sun_hours"] = sun_hours
    cells["unsure_hours"] = unsure_hours
    return cells


def add_wall_hours(plotter, spot, cells, name="wall_sun"):
    """Color each cell of the wall by its hours of sun (dark = none, yellow = most), with a color bar."""
    from citymap import windows
    points, faces = [], []
    for index, cell in cells.iterrows():
        first = len(points)
        points.extend(windows.cell_corners(spot["frame"], cell, windows.GRID_SETTINGS["offset_ft"]))
        faces.extend([4, first, first + 1, first + 2, first + 3])
    mesh = pv.PolyData(np.array(points), faces=np.array(faces))
    mesh.cell_data["hours of sun"] = cells["sun_hours"].to_numpy()
    plotter.add_mesh(mesh, scalars="hours of sun", cmap="cividis", name=name, pickable=False,
                     scalar_bar_args={"title": "hours of direct sun"})
