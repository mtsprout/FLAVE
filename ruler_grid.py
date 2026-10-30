# ruler_grid.py
# The timeline grid: which frames the ruler marks and the vertical grid lines
# sit on at a zoom, and snapping to those lines. Unified window only.
#
# Zoomed out (a second is narrower than 240 px) the marks are the old whole
# second ones (labels every 1, 5, 10 ... seconds). Zoomed in further they
# subdivide: labelled ticks every few frames (timecode labels, spaced at least
# LABEL_MIN_PX apart) with lighter ticks at the next finer step, so the ruler
# keeps showing useful marks right down to single frames.
#
# Snapping: while a clip is moved or trimmed, the playhead is scrubbed, or an
# In / Out mark is dragged, it jumps onto a grid line that is within
# GRID_SNAP_PX pixels (or the Pixel Snap-To setting when that is larger). On
# by default. Switch it off for every project with the global setting "Snap to
# Grid" (Global Settings), or for one project with the project setting
# GridSnap ("on" / "off", Project Settings or the Edit > Snap to Grid item
# and the S key); the project setting wins. ASCII only.

import math
import time

SUB_MIN_PX_PER_SECOND = 240.0     # a second this wide starts the subdivision
LABEL_MIN_PX = 96.0               # labelled sub-second ticks at least this far apart
MINOR_MIN_PX = 6.0                # finer ticks only when this far apart
GRID_SNAP_PX = 6
GLOBAL_KEY = "Snap to Grid"       # "1" / "0"
PROJECT_KEY = "GridSnap"          # "on" / "off" / missing = follow the global
_CACHE_SECONDS = 1.5


def enabled_ui():
    import workspace
    return workspace.get() is not None


def subsecond_layout(ppf, fps):
    # (label_step, minor_step) in frames when the ruler is zoomed in far
    # enough to subdivide the seconds (minor_step may be None), else None
    if fps <= 0 or ppf <= 0 or ppf * fps < SUB_MIN_PX_PER_SECOND:
        return None
    base = max(1, int(round(fps)))
    steps = sorted(set([1, 2, 5, 10, max(1, base // 2), base]))
    steps = [s for s in steps if s <= base]
    label = next((s for s in steps if s * ppf >= LABEL_MIN_PX), base)
    if label >= base:
        return None                 # whole seconds are the labels
    lower = ([s for s in steps if s < label and label % s == 0]
             or [s for s in steps if s < label])
    minor = lower[-1] if lower else None
    if minor is not None and minor * ppf < MINOR_MIN_PX:
        minor = None
    return label, minor


def grid_lines(ppf, fps, first, last):
    # [(frame, major)] of the vertical lines the grid draws between frames
    # first and last (the same lines _paint_grid draws)
    if ppf <= 0 or fps <= 0 or last < first:
        return []
    from sequence_timeline_ruler import ruler_label_interval
    out = {}
    interval = ruler_label_interval(ppf * fps)
    sec_step = 1 if ppf * fps >= 1 else max(1, interval)
    show_minor = ppf * fps * sec_step >= 16
    sec = int(math.ceil(max(0, first) / fps / sec_step)) * sec_step
    while True:
        f = int(math.ceil(sec * fps - 1e-9))
        if f > last:
            break
        numbered = interval > 0 and sec % interval == 0
        if numbered:
            out[f] = True
        elif show_minor:
            out.setdefault(f, False)
        sec += sec_step
    sub = subsecond_layout(ppf, fps)
    if sub is not None:
        label, minor = sub
        f = (max(0, first) + label - 1) // label * label
        while f <= last:
            out[f] = True
            f += label
        if minor is not None and minor * ppf >= 16:
            f = (max(0, first) + minor - 1) // minor * minor
            while f <= last:
                out.setdefault(f, False)
                f += minor
    return sorted(out.items())


# ---------------------------------------------------------------- the option

def _global_on():
    from global_settings import _get_global_setting
    return (_get_global_setting(GLOBAL_KEY, "1") or "1") != "0"


def project_value(project_db):
    # "on", "off" or "" (follow the global setting)
    if not project_db:
        return ""
    import sqlite3
    try:
        conn = sqlite3.connect(project_db)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?",
                               (PROJECT_KEY,)).fetchone()
        finally:
            conn.close()
    except Exception:
        return ""
    v = (row[0] if row else "") or ""
    return v if v in ("on", "off") else ""


def set_project_value(project_db, value):
    # value "on", "off" or "" (follow the global setting)
    import sqlite3
    conn = sqlite3.connect(project_db)
    try:
        if value in ("on", "off"):
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                         (PROJECT_KEY, value))
        else:
            conn.execute("DELETE FROM settings WHERE key = ?", (PROJECT_KEY,))
        conn.commit()
    finally:
        conn.close()


def snap_on(tl):
    # Whether grid snapping applies to this timeline's project (cached a
    # moment, since a scrub asks on every mouse move)
    if not enabled_ui():
        return False
    now = time.monotonic()
    cache = getattr(tl, "_grid_snap_cache", None)
    if cache is not None and now - cache[0] < _CACHE_SECONDS:
        return cache[1]
    try:
        v = project_value(tl._project_db())
        on = (v == "on") or (v == "" and _global_on())
    except Exception:
        on = False
    tl._grid_snap_cache = (now, on)
    return on


def forget(tl):
    tl._grid_snap_cache = None


def snap_px(tl):
    try:
        px = int(tl._snap_pixels())
    except Exception:
        px = 0
    return max(GRID_SNAP_PX, px)


def targets(tl, near_frame=None):
    # Grid line frames across the visible part of the timeline
    ppf, fps = float(tl.pixels_per_frame), float(tl.fps or 0)
    if ppf <= 0 or fps <= 0:
        return []
    first = max(0, int(tl.view_start_frame))
    last = min(int(tl.total_frames()) + int(10 * fps),
               first + int(tl.visible_frames()) + 2)
    return [f for f, _major in grid_lines(ppf, fps, first, last)]


def snap_frame(tl, frame):
    # frame (int or float) moved onto a grid line within the snap distance,
    # else unchanged: (frame, snapped bool)
    if not snap_on(tl):
        return frame, False
    ppf = float(tl.pixels_per_frame)
    best = None
    for t in targets(tl):
        dist = abs(t - frame) * ppf
        if dist <= snap_px(tl) and (best is None or dist < best[0]):
            best = (dist, t)
    if best is None:
        return frame, False
    return best[1], True


def toggle(tl):
    # Edit > Snap to Grid / the S key: sets the project's own on / off
    project_db = tl._project_db()
    if not project_db:
        return None
    now_on = snap_on(tl)
    set_project_value(project_db, "off" if now_on else "on")
    forget(tl)
    try:
        tl.status_bar.showMessage("Snap to grid %s" % ("off" if now_on else "on"), 3000)
    except Exception:
        pass
    return not now_on
