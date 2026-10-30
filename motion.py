# motion.py
# One-click motion presets for the selected clips, built like fades.py: each
# preset makes ordinary keyframe clips and keys (move / scale / opacity) on
# keyframe tracks above the clip, linked to it by link_id, in one undo step.
# Easing is baked into the keys (the curve sampled into SAMPLES linear
# segments), so the project format is unchanged and the original FLAVE reads
# these projects as plain keyframes.
#   Slide In / Slide Out  from / to the left, right, top, bottom
#   Pop In / Pop Out      scale with overshoot plus a quick fade
#   Zoom In / Zoom Out    slow push over the whole clip
#   Shake                 a decaying jitter from the clip start
# Works on video, image and WYSIWYG text clips (audio has no motion).
# Keys already in the changed range are replaced; other keys stay. The
# length (seconds) and easing are global settings. Unified window only.
# ASCII only.

import math
import sqlite3

from PySide6.QtWidgets import QInputDialog

SECONDS_KEY = "motion_seconds"
EASE_KEY = "motion_ease"
DEFAULT_SECONDS = 0.75
DEFAULT_EASE = "out"
SAMPLES = 8                      # linear segments per eased move
ZOOM_PERCENT = 115.0             # Zoom In ends / Zoom Out starts here
MOTION_TRACKS = ("video", "image", "text")

EASES = (("Ease out", "out"), ("Ease in and out", "inout"),
         ("Ease in", "in"), ("Overshoot", "back"), ("Linear", "linear"))

DIRECTIONS = (("Left", "left"), ("Right", "right"), ("Top", "top"),
              ("Bottom", "bottom"))
# (label, preset id); Slide In / Out are submenus over DIRECTIONS
PLAIN_PRESETS = (("Pop In", "pop_in"), ("Pop Out", "pop_out"),
                 ("Zoom In (whole clip)", "zoom_in"),
                 ("Zoom Out (whole clip)", "zoom_out"), ("Shake", "shake"))
PRESETS = (["slide_in_" + d for _l, d in DIRECTIONS]
           + ["slide_out_" + d for _l, d in DIRECTIONS]
           + [p for _l, p in PLAIN_PRESETS])


# ---------------------------------------------------------------- settings

def motion_seconds():
    from global_settings import _get_global_setting
    try:
        return max(0.1, float(_get_global_setting(SECONDS_KEY, "") or DEFAULT_SECONDS))
    except ValueError:
        return DEFAULT_SECONDS


def motion_ease():
    from global_settings import _get_global_setting
    name = _get_global_setting(EASE_KEY, "") or DEFAULT_EASE
    return name if name in dict((v, k) for k, v in EASES) else DEFAULT_EASE


def motion_frames(tl):
    return max(2, int(round(motion_seconds() * float(tl.fps or 30))))


def ask_motion_options(parent):
    # Length and easing of the presets
    from global_settings import _set_global_setting
    val, ok = QInputDialog.getDouble(
        parent, "Motion Options", "Length in seconds:", motion_seconds(),
        0.1, 30.0, 2)
    if not ok:
        return
    _set_global_setting(SECONDS_KEY, repr(float(val)))
    labels = [k for k, _v in EASES]
    cur = [k for k, v in EASES if v == motion_ease()][0]
    label, ok = QInputDialog.getItem(parent, "Motion Options", "Easing:",
                                     labels, labels.index(cur), False)
    if ok:
        _set_global_setting(EASE_KEY, dict(EASES)[label])


# ---------------------------------------------------------------- menus

def add_motion_items(menu):
    # {action: preset id} for every preset, added to menu
    acts = {}
    for title, prefix in (("Slide In", "slide_in_"), ("Slide Out", "slide_out_")):
        sub = menu.addMenu(title)
        for label, d in DIRECTIONS:
            acts[sub.addAction(label)] = prefix + d
    for label, preset in PLAIN_PRESETS:
        acts[menu.addAction(label)] = preset
    return acts


def add_motion_submenu(menu):
    return add_motion_items(menu.addMenu("Motion"))


# ---------------------------------------------------------------- curves

def ease(name, t):
    # 0..1 -> 0..1 (the "back" curve overshoots 1 on the way)
    t = max(0.0, min(1.0, float(t)))
    if name == "in":
        return t * t * t
    if name == "inout":
        return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2
    if name == "back":
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)
    if name == "linear":
        return t
    return 1 - pow(1 - t, 3)                        # "out"


def _ramp(f0, f1, a, b, name, samples=SAMPLES):
    # [(frame, value)]: a -> b over frames f0..f1 on the eased curve
    n = max(1, min(samples, f1 - f0))
    out = []
    for i in range(n + 1):
        t = i / float(n)
        f = f0 + int(round(t * (f1 - f0)))
        if out and f <= out[-1][0]:
            continue
        out.append((f, a + (b - a) * ease(name, t)))
    return out


# ---------------------------------------------------------------- planning

def plan_preset(preset, start, end, n, seq_w, seq_h, ease_name):
    # Pure. The keys a preset makes for a clip on frames start..end-1:
    # {key type: (first frame, last frame, [key])}, with a key (frame, value)
    # for scale / opacity and (frame, (x, y)) for move (x, y the layer
    # center, so (seq_w / 2, seq_h / 2) is "no shift"). Empty when the clip
    # is too short for the preset.
    last = end - 1
    n = min(int(n), last - start)
    if n < 1:
        return {}
    cx, cy = seq_w / 2.0, seq_h / 2.0
    shifts = {"left": (-seq_w, 0), "right": (seq_w, 0),
              "top": (0, -seq_h), "bottom": (0, seq_h)}
    if preset.startswith("slide_"):
        sliding_in = preset.startswith("slide_in_")
        sx, sy = shifts[preset.rsplit("_", 1)[1]]
        if sliding_in:
            f0, f1, rev = start, start + n, True
        else:
            f0, f1, rev = last - n, last, False
        keys = []
        for f, w in _ramp(f0, f1, 1.0, 0.0, ease_name):
            w = w if rev else 1.0 - w                # 1 = fully off screen
            keys.append((f, (cx + sx * w, cy + sy * w)))
        return {"move": (f0, f1, keys)}
    if preset == "pop_in":
        f1 = start + n
        return {"scale": (start, f1, _ramp(start, f1, 40.0, 100.0, "back")),
                "opacity": (start, start + max(1, n // 2),
                            _ramp(start, start + max(1, n // 2), 0.0, 100.0, "out"))}
    if preset == "pop_out":
        f0 = last - n
        return {"scale": (f0, last, _ramp(f0, last, 100.0, 60.0, "in")),
                "opacity": (last - max(1, n // 2), last,
                            _ramp(last - max(1, n // 2), last, 100.0, 0.0, "in"))}
    if preset in ("zoom_in", "zoom_out"):
        a, b = (100.0, ZOOM_PERCENT) if preset == "zoom_in" else (ZOOM_PERCENT, 100.0)
        return {"scale": (start, last, _ramp(start, last, a, b, "inout"))}
    if preset == "shake":
        amp = seq_w * 0.012
        f1 = start + n
        keys = []
        steps = max(2, min(n, 12))
        for i in range(steps + 1):
            f = start + int(round(i * n / float(steps)))
            if keys and f <= keys[-1][0]:
                continue
            decay = 1.0 - i / float(steps)
            keys.append((f, (cx + amp * decay * math.sin(i * 2.7 + 0.5) * (1 if i % 2 else -1),
                             cy + amp * decay * math.cos(i * 3.9 + 1.1))))
        keys[-1] = (keys[-1][0], (cx, cy))
        return {"move": (start, f1, keys)}
    return {}


# ---------------------------------------------------------------- database

def _link_id(cur, mem_id):
    # The clip's link_id; a clip with none becomes its own link group (a
    # group id may be any member's id, text clips use their memory id)
    from sequence_timeline_captions import clip_table_and_id
    table, row = clip_table_and_id(mem_id)
    cur.execute("SELECT link_id FROM %s WHERE id = ?" % table, (int(row),))
    r = cur.fetchone()
    if r is not None and r[0] is not None:
        return int(r[0])
    cur.execute("UPDATE %s SET link_id = ? WHERE id = ?" % table,
                (int(mem_id), int(row)))
    return int(mem_id)


def _write_keys(cur, kf_id, ktype, f0, f1, keys):
    # keys in [f0, f1] replaced by these
    table = "keyframe_move" if ktype == "move" else "keyframes"
    cur.execute("DELETE FROM %s WHERE keyframe_clip_id = ? AND frame BETWEEN ? AND ?"
                % table, (kf_id, int(f0), int(f1)))
    if ktype == "move":
        cur.executemany("INSERT INTO keyframe_move (keyframe_clip_id, frame, x, y) "
                        "VALUES (?, ?, ?, ?)",
                        [(kf_id, int(f), float(v[0]), float(v[1])) for f, v in keys])
    else:
        cur.executemany("INSERT INTO keyframes (keyframe_clip_id, frame, value) "
                        "VALUES (?, ?, ?)",
                        [(kf_id, int(f), float(v)) for f, v in keys])


def _motion_clips(tl):
    # (clip, track id) of the selected video / image / text clips
    from keyframe import is_keyframe_clip_id
    from text_clip import is_text_clip_id
    out = []
    for c in tl._selected_clips():
        if is_keyframe_clip_id(c[0]):
            continue
        if c[0] <= 0 and not is_text_clip_id(c[0]):         # captions
            continue
        tid = tl._clip_track_id(c)
        if (tl._track_type(tid) or "").lower() in MOTION_TRACKS:
            out.append((c, tid))
    return out


def apply_motion(tl, preset):
    # The preset for the selected clips. Returns the number of keyframe
    # clips changed.
    if preset not in PRESETS:
        return 0
    items = _motion_clips(tl)
    n = motion_frames(tl)
    name = motion_ease()
    seq_w, seq_h = [float(v) for v in tl._sequence_size()]
    todo = []
    for clip, tid in items:
        start, end = int(clip[2]), int(clip[2]) + int(clip[3])
        keys = plan_preset(preset, start, end, n, seq_w, seq_h, name)
        if keys:
            todo.append((clip, tid, start, end, keys))
    if not todo:
        tl.status_bar.showMessage(
            "Select a video, image or text clip first (it must be longer "
            "than a few frames)", 4000)
        return 0
    from fades import _keyframe_clip_for
    from undo import push_undo
    project_db = tl._project_db()
    push_undo(project_db, "Motion")
    conn = sqlite3.connect(project_db)
    changed = 0
    try:
        cur = conn.cursor()
        for clip, tid, start, end, keys in todo:
            link = _link_id(cur, clip[0])
            for ktype, (f0, f1, ks) in keys.items():
                kf = _keyframe_clip_for(cur, tl.sequence_id, tid, link, ktype,
                                        start, end)
                _write_keys(cur, kf, ktype, f0, f1, ks)
                changed += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    tl._after_clip_change("Motion: %d keyframe clip(s) updated" % changed)
    return changed
