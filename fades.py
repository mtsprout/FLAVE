# fades.py
# One-click fades and dissolves. A fade is a keyframe clip: type opacity for
# video / image clips, volume for audio clips, on a keyframe track above the
# clip, linked to it by link_id, with keys at absolute sequence frames
# (0 .. 100, linear between keys, flat outside them). These presets make
# that clip and its keys for the selected clips, in one undo step:
#   Fade In, Fade Out, Fade In and Out  (the Fade Length setting, seconds)
#   Cross Dissolve  two selected clips that overlap in time on different
#                   tracks: over the overlap, the upper video clip fades
#                   (in when it comes in later, out when it ends first); both
#                   audio clips crossfade
# Keys already in the faded range are replaced; other keys stay. Unified
# window only (menus and the clip menu add the items there). ASCII only.

import sqlite3

from PySide6.QtWidgets import QInputDialog, QMenu

SETTING_KEY = "fade_seconds"
DEFAULT_SECONDS = 1.0
MODES = ("in", "out", "inout", "dissolve")
LABELS = (("Fade In", "in"), ("Fade Out", "out"),
          ("Fade In and Out", "inout"), ("Cross Dissolve", "dissolve"))
MEDIA_TRACKS = ("video", "image", "audio")


def fade_seconds():
    from global_settings import _get_global_setting
    try:
        return max(0.05, float(_get_global_setting(SETTING_KEY, "") or DEFAULT_SECONDS))
    except ValueError:
        return DEFAULT_SECONDS


def fade_frames(tl):
    return max(1, int(round(fade_seconds() * float(tl.fps or 30))))


def add_fade_items(menu):
    # {action: mode} for the four presets, added to menu
    return {menu.addAction(label): mode for label, mode in LABELS}


def add_fade_submenu(menu):
    sub = menu.addMenu("Fade")
    return add_fade_items(sub)


def ask_fade_length(parent, tl):
    from global_settings import _set_global_setting
    val, ok = QInputDialog.getDouble(
        parent, "Fade Length", "Seconds (fades and the dip ends):",
        fade_seconds(), 0.05, 30.0, 2)
    if ok:
        _set_global_setting(SETTING_KEY, repr(float(val)))


# ---------------------------------------------------------------- database

def _link_id(cur, clip_id):
    # The clip's link_id; a clip with none becomes its own link group
    cur.execute("SELECT link_id FROM clips WHERE id = ?", (int(clip_id),))
    row = cur.fetchone()
    if row is not None and row[0] is not None:
        return int(row[0])
    cur.execute("UPDATE clips SET link_id = ? WHERE id = ?",
                (int(clip_id), int(clip_id)))
    return int(clip_id)


def _sort_order(cur, track_id):
    cur.execute("SELECT sort_order FROM tracks WHERE id = ?", (int(track_id),))
    return int(cur.fetchone()[0])


def _new_keyframe_track_above(cur, sequence_id, clip_track_id):
    # A keyframe track right above the clip's track
    from track_names import next_default_name
    s = _sort_order(cur, clip_track_id)
    cur.execute("SELECT name FROM tracks WHERE sequence_id = ?", (sequence_id,))
    name = next_default_name("keyframe", [r[0] for r in cur.fetchall()])
    cur.execute("UPDATE tracks SET sort_order = sort_order + 1 "
                "WHERE sequence_id = ? AND sort_order >= ?", (sequence_id, s))
    cur.execute("INSERT INTO tracks (sequence_id, name, track_type, sort_order, "
                "language) VALUES (?, ?, 'keyframe', ?, '')", (sequence_id, name, s))
    return cur.lastrowid


def _keyframe_clip_for(cur, sequence_id, clip_track_id, link, ktype, start, end):
    # This clip's fade clip: an existing one of this type, linked to it,
    # above its track and covering all of it; else a new one on the nearest
    # free keyframe track above (or a new keyframe track)
    from keyframe import keyframe_range_overlaps
    s = _sort_order(cur, clip_track_id)
    cur.execute(
        "SELECT k.id FROM keyframe_clips k JOIN tracks t ON t.id = k.track_id "
        "WHERE k.sequence_id = ? AND k.type = ? AND k.link_id = ? "
        "AND k.in_frame <= ? AND k.out_frame >= ? AND t.sort_order < ? "
        "ORDER BY t.sort_order DESC LIMIT 1", (sequence_id, ktype, link, start, end, s))
    row = cur.fetchone()
    if row is not None:
        return int(row[0])
    cur.execute("SELECT id FROM tracks WHERE sequence_id = ? AND track_type = "
                "'keyframe' AND sort_order < ? ORDER BY sort_order DESC",
                (sequence_id, s))
    track_id = None
    for (tid,) in cur.fetchall():
        if not keyframe_range_overlaps(cur, tid, start, end - start):
            track_id = tid
            break
    if track_id is None:
        track_id = _new_keyframe_track_above(cur, sequence_id, clip_track_id)
    cur.execute("INSERT INTO keyframe_clips (sequence_id, track_id, type, link_id, "
                "in_frame, out_frame, name) VALUES (?, ?, ?, ?, ?, ?, 'Fade')",
                (sequence_id, track_id, ktype, link, start, end))
    return cur.lastrowid


def _set_ramp(cur, kf_id, f0, f1, direction):
    # keys in [f0, f1] replaced by a ramp 0 -> 100 (in) or 100 -> 0 (out)
    cur.execute("DELETE FROM keyframes WHERE keyframe_clip_id = ? "
                "AND frame BETWEEN ? AND ?", (kf_id, f0, f1))
    a, b = (0.0, 100.0) if direction == "in" else (100.0, 0.0)
    cur.executemany("INSERT INTO keyframes (keyframe_clip_id, frame, value) "
                    "VALUES (?, ?, ?)", [(kf_id, f0, a), (kf_id, f1, b)])


# ---------------------------------------------------------------- planning

def _media_clips(tl):
    # (clip, track id, track type) of the selected video / image / audio clips
    from keyframe import is_keyframe_clip_id
    out = []
    for c in tl._selected_clips():
        if c[0] <= 0 or is_keyframe_clip_id(c[0]):
            continue
        tid = tl._clip_track_id(c)
        ttype = (tl._track_type(tid) or "").lower()
        if ttype in MEDIA_TRACKS:
            out.append((c, tid, ttype))
    return out


def _row_of_track(tl, track_id):
    from PySide6.QtCore import Qt
    for r in range(tl.table.rowCount()):
        it = tl.table.item(r, 0)
        if it is not None and it.data(Qt.UserRole) == track_id:
            return r
    return 10 ** 6


def _plan(tl, mode, n):
    # [(clip, track id, track type, direction, f0, f1)]
    items = _media_clips(tl)
    plan = []
    if mode in ("in", "out", "inout"):
        for c, tid, tt in items:
            start, end = int(c[2]), int(c[2]) + int(c[3])
            room = (end - start - 1) // 2 if mode == "inout" else end - start - 1
            span = min(n, room)
            if span < 1:
                continue
            if mode in ("in", "inout"):
                plan.append((c, tid, tt, "in", start, start + span))
            if mode in ("out", "inout"):
                plan.append((c, tid, tt, "out", end - 1 - span, end - 1))
        return plan
    # Cross Dissolve: overlapping selected clips of the same kind
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            audio = a[2] == "audio"
            if audio != (b[2] == "audio") or a[1] == b[1]:
                continue
            o1 = max(int(a[0][2]), int(b[0][2]))
            o2 = min(int(a[0][2]) + int(a[0][3]), int(b[0][2]) + int(b[0][3]))
            if o2 - o1 < 2 or int(a[0][2]) == int(b[0][2]):
                continue
            inc, out = (a, b) if int(a[0][2]) > int(b[0][2]) else (b, a)
            if audio:
                plan.append((inc[0], inc[1], inc[2], "in", o1, o2 - 1))
                plan.append((out[0], out[1], out[2], "out", o1, o2 - 1))
            else:
                upper = a if _row_of_track(tl, a[1]) < _row_of_track(tl, b[1]) else b
                plan.append((upper[0], upper[1], upper[2],
                             "in" if upper is inc else "out", o1, o2 - 1))
    return plan


# ---------------------------------------------------------------- entry

def apply_fade(tl, mode):
    # The preset for the selected clips. Returns the number of fades made.
    if mode not in MODES:
        return 0
    project_db = tl._project_db()
    plan = _plan(tl, mode, fade_frames(tl))
    if not plan:
        tl.status_bar.showMessage(
            "Select two overlapping clips on different tracks for a Cross Dissolve"
            if mode == "dissolve" else
            "Select a clip first (it must be longer than the fade)", 4000)
        return 0
    from undo import push_undo
    push_undo(project_db, "Fade" if mode != "dissolve" else "Cross Dissolve")
    conn = sqlite3.connect(project_db)
    try:
        cur = conn.cursor()
        for clip, tid, ttype, direction, f0, f1 in plan:
            link = _link_id(cur, clip[0])
            ktype = "volume" if ttype == "audio" else "opacity"
            start, end = int(clip[2]), int(clip[2]) + int(clip[3])
            kf = _keyframe_clip_for(cur, tl.sequence_id, tid, link, ktype, start, end)
            _set_ramp(cur, kf, int(f0), int(f1), direction)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    names = {"in": "Fade in", "out": "Fade out", "inout": "Fade in and out",
             "dissolve": "Cross dissolve"}
    tl._after_clip_change("%s: %d keyframe clip(s) updated" % (names[mode], len(plan)))
    return len(plan)
