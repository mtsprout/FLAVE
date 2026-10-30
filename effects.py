# effects.py
# One-click effects for the selected video, image and text clips (CPU
# backend, unified window), built like fades.py and motion.py: ordinary
# keyframe clips (types blur and shadow, keyframe.py) above the clip, linked
# to it, in one undo step.
#   Drop Shadow       a soft shadow behind the layer (strength 100), whole clip
#   Blur...           a constant blur of the radius you type (sequence px)
#   Focus In / Out    blur eased from blurred to sharp over the motion length
#                     at the clip's start (In), or sharp to blurred at its end
#   Remove Blur and Shadow   deletes those keyframe clips of the clips
# The keys can be edited like any keyframes afterward. The Windows GPU kernel
# does not draw these. ASCII only.

import sqlite3

from PySide6.QtWidgets import QInputDialog

FOCUS_RADIUS = 40.0
DEFAULT_BLUR = 20.0
EFFECT_TYPES = ("blur", "shadow")
LABELS = (("Drop Shadow", "shadow"), ("Blur...", "blur"), ("Focus In", "focus_in"),
          ("Focus Out", "focus_out"), ("Remove Blur and Shadow", "remove"))


def add_effect_items(menu):
    return {menu.addAction(label): name for label, name in LABELS}


def _plan(name, start, end, n, value):
    # Pure. {key type: (first frame, last frame, [(frame, value)])}
    last = end - 1
    if name == "shadow":
        return {"shadow": (start, last, [(start, 100.0)])}
    if name == "blur":
        return {"blur": (start, last, [(start, float(value))])}
    n = min(int(n), last - start)
    if n < 1:
        return {}
    from motion import _ramp
    if name == "focus_in":
        return {"blur": (start, start + n,
                         _ramp(start, start + n, FOCUS_RADIUS, 0.0, "out"))}
    if name == "focus_out":
        return {"blur": (last - n, last,
                         _ramp(last - n, last, 0.0, FOCUS_RADIUS, "in"))}
    return {}


def _remove(cur, sequence_id, link, start, end):
    cur.execute("SELECT id FROM keyframe_clips WHERE sequence_id = ? AND link_id = ? "
                "AND type IN ('blur', 'shadow') AND in_frame < ? AND out_frame > ?",
                (sequence_id, link, end, start))
    ids = [r[0] for r in cur.fetchall()]
    for kid in ids:
        cur.execute("DELETE FROM keyframes WHERE keyframe_clip_id = ?", (kid,))
        cur.execute("DELETE FROM keyframe_clips WHERE id = ?", (kid,))
    return len(ids)


def apply_effect(tl, name, parent=None):
    # The effect for the selected clips. Returns the number of keyframe
    # clips made or removed.
    from motion import MOTION_TRACKS, _link_id, _motion_clips, _write_keys, motion_frames
    value = None
    if name == "blur":
        value, ok = QInputDialog.getDouble(parent, "Blur", "Radius (sequence pixels):",
                                           DEFAULT_BLUR, 0.5, 300.0, 1)
        if not ok:
            return 0
    items = _motion_clips(tl)
    if not items:
        tl.status_bar.showMessage("Select a video, image or text clip first", 4000)
        return 0
    n = motion_frames(tl)
    project_db = tl._project_db()
    from undo import push_undo
    push_undo(project_db, "Effect")
    conn = sqlite3.connect(project_db)
    changed = 0
    try:
        cur = conn.cursor()
        from fades import _keyframe_clip_for
        for clip, tid in items:
            start, end = int(clip[2]), int(clip[2]) + int(clip[3])
            link = _link_id(cur, clip[0])
            if name == "remove":
                changed += _remove(cur, tl.sequence_id, link, start, end)
                continue
            for ktype, (f0, f1, keys) in _plan(name, start, end, n, value).items():
                kf = _keyframe_clip_for(cur, tl.sequence_id, tid, link, ktype,
                                        start, end)
                _write_keys(cur, kf, ktype, f0, f1, keys)
                changed += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    tl._after_clip_change("Effect: %d keyframe clip(s) %s" % (
        changed, "removed" if name == "remove" else "updated"))
    return changed
