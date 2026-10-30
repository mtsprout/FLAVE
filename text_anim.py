# text_anim.py
# Text animation, built from what already exists (no compositor change):
#   Reveals   Typewriter, Word by Word, Line by Line, Wipe In, Wipe Out for
#             the selected text clips. A reveal is an ordinary crop_edges
#             keyframe clip on the text layer (the layer is the sequence-size
#             text image, so crop values are sequence pixels): the right edge
#             uncovers the text left to right (the bottom edge uncovers it
#             top down for Line by Line). Steps are held keys with a one
#             frame ramp, so the project stays plain keyframes.
#   Titles    Add Title (centered, fades in and out) and Add Lower Third (a
#             name and a subtitle that slide in from the left), placed at the
#             playhead on a text track (made on top when none is free). The
#             text is "Title" / "Name" / "Subtitle"; change it afterwards in
#             the Text Style window like any text clip.
# One undo step per command. Unified window only. ASCII only.

import sqlite3

from PySide6.QtWidgets import QInputDialog

CPS_KEY = "text_reveal_cps"          # typing speed, characters per second
DEFAULT_CPS = 16.0
WORD_PAUSE = 0.12                    # seconds held after each word
LINE_SECONDS = 0.6                   # seconds per line (Line by Line)
LABELS = (("Typewriter", "typewriter"), ("Word by Word", "words"),
          ("Line by Line", "lines"), ("Wipe In", "wipe_in"),
          ("Wipe Out", "wipe_out"))
MODES = tuple(m for _l, m in LABELS)
TITLE_SECONDS = 4.0
LOWER_THIRD_SECONDS = 5.0


def reveal_cps():
    from global_settings import _get_global_setting
    try:
        return max(1.0, float(_get_global_setting(CPS_KEY, "") or DEFAULT_CPS))
    except ValueError:
        return DEFAULT_CPS


def ask_reveal_speed(parent):
    from global_settings import _set_global_setting
    val, ok = QInputDialog.getDouble(
        parent, "Typing Speed", "Characters per second:", reveal_cps(), 1.0, 200.0, 1)
    if ok:
        _set_global_setting(CPS_KEY, repr(float(val)))


def add_reveal_items(menu):
    return {menu.addAction(label): mode for label, mode in LABELS}


# ---------------------------------------------------------------- geometry

def _metrics(family, size):
    from PySide6.QtGui import QFontMetrics
    from text_clip import text_font
    return QFontMetrics(text_font(family, size))


def reveal_stops(text, family, size, x, y, mode):
    # Pure geometry. (axis, [(edge, weight)]): axis "x" = the right edge of
    # the revealed part in sequence px, "y" = the bottom edge; the list runs
    # from nothing shown to everything shown, weight = relative time the
    # step takes (a letter 1, a word's pause extra).
    from text_clip import text_box_rect
    box = text_box_rect(text, family, size, x, y)
    fm = _metrics(family, size)
    lines = (text or "").split("\n")
    if mode == "lines" or (mode in ("typewriter", "words") and len(lines) > 1):
        step = fm.lineSpacing()
        top = box.top()
        stops = [(top, 1.0)]
        for i in range(len(lines)):
            # a line takes about LINE_SECONDS whatever the typing speed
            stops.append((min(box.bottom() + 1, top + (i + 1) * step),
                          LINE_SECONDS * reveal_cps()))
        return "y", stops
    left = box.left()
    if mode == "typewriter":
        stops = [(left, 1.0)]
        for i in range(1, len(text) + 1):
            stops.append((left + fm.horizontalAdvance(text[:i]), 1.0))
        return "x", stops
    if mode == "words":
        stops = [(left, 1.0)]
        pos = 0
        for word in text.split(" "):
            pos += len(word)
            stops.append((left + fm.horizontalAdvance(text[:pos]),
                          max(1.0, len(word)) + WORD_PAUSE * reveal_cps()))
            pos += 1
        return "x", stops
    return "x", [(left, 1.0), (box.right() + 1, 1.0)]           # wipes


def plan_reveal(stops, axis, start, end, seq_w, seq_h, mode, cps, fps):
    # Pure. (keys, f0, f1): keys [(frame, crop_edges tuple (top, bottom, left,
    # right))] for a text clip on frames start..end-1. In: from hidden to
    # shown over the typing time (at most 85% of the clip), held shown.
    # Out (wipe_out): shown, then wiped away over a second at the clip's end.
    last = end - 1
    if last - start < 2 or len(stops) < 2:
        return [], start, start
    full = float(seq_w if axis == "x" else seq_h)

    def crop(edge):
        v = max(0.0, full - float(edge))
        return (0.0, v, 0.0, 0.0) if axis == "y" else (0.0, 0.0, 0.0, v)

    if mode == "wipe_out":
        n = min(last - start, max(2, int(round(fps))))
        a, b = last - n, last
        keys = [(a, crop(stops[-1][0])), (b, crop(stops[0][0]))]
        return keys, a, b
    weights = [w for _e, w in stops[1:]]
    if mode in ("wipe_in",):
        frames = min(last - start, max(2, int(round(fps))))
    else:
        frames = int(round(sum(weights) / float(cps) * fps))
    frames = max(len(weights), min(frames, int((last - start) * 0.85)))
    keys = [(start, crop(stops[0][0]))]
    total = float(sum(weights))
    acc = 0.0
    f_prev = start
    for i, (edge, w) in enumerate(stops[1:]):
        acc += w
        f_i = start + int(round(frames * acc / total))
        f_i = max(f_prev + 1, min(f_i, last))
        if mode == "wipe_in":
            keys.append((f_i, crop(edge)))
        else:
            # hold the previous value until just before the step
            if f_i - 1 > keys[-1][0]:
                keys.append((f_i - 1, keys[-1][1]))
            keys.append((f_i, crop(edge)))
        f_prev = f_i
    return keys, start, f_prev


# ---------------------------------------------------------------- database

def _write_crop_keys(cur, kf_id, f0, f1, keys):
    cur.execute("DELETE FROM keyframe_crop_edges WHERE keyframe_clip_id = ? "
                "AND frame BETWEEN ? AND ?", (kf_id, int(f0), int(f1)))
    cur.executemany(
        "INSERT INTO keyframe_crop_edges (keyframe_clip_id, frame, top, bottom, "
        "left, right) VALUES (?, ?, ?, ?, ?, ?)",
        [(kf_id, int(f), *[float(v) for v in ce]) for f, ce in keys])


def _text_clips(tl):
    from text_clip import is_text_clip_id
    out = []
    for c in tl._selected_clips():
        if is_text_clip_id(c[0]):
            out.append((c, tl._clip_track_id(c)))
    return out


def apply_reveal(tl, mode):
    # The reveal for the selected text clips. Returns the number done.
    if mode not in MODES:
        return 0
    from sequence_timeline_captions import clip_table_and_id
    seq_w, seq_h = tl._sequence_size()
    cps, fps = reveal_cps(), float(tl.fps or 30)
    project_db = tl._project_db()
    conn = sqlite3.connect(project_db)
    todo = []
    try:
        for clip, tid in _text_clips(tl):
            _t, row = clip_table_and_id(clip[0])
            r = conn.execute("SELECT text, font_family, font_size, x, y FROM "
                             "text_clips WHERE id = ?", (int(row),)).fetchone()
            if r is None or not (r[0] or "").strip():
                continue
            axis, stops = reveal_stops(r[0], r[1], r[2] or 1, r[3] or 0, r[4] or 0, mode)
            start, end = int(clip[2]), int(clip[2]) + int(clip[3])
            keys, f0, f1 = plan_reveal(stops, axis, start, end, seq_w, seq_h,
                                       mode, cps, fps)
            if keys:
                todo.append((clip, tid, start, end, keys, f0, f1))
    finally:
        conn.close()
    if not todo:
        tl.status_bar.showMessage("Select a text clip with some text first "
                                  "(it must be longer than a few frames)", 4000)
        return 0
    from fades import _keyframe_clip_for
    from motion import _link_id
    from undo import push_undo
    push_undo(project_db, "Text reveal")
    conn = sqlite3.connect(project_db)
    try:
        cur = conn.cursor()
        for clip, tid, start, end, keys, f0, f1 in todo:
            link = _link_id(cur, clip[0])
            kf = _keyframe_clip_for(cur, tl.sequence_id, tid, link, "crop_edges",
                                    start, end)
            _write_crop_keys(cur, kf, f0, f1, keys)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    tl._after_clip_change("Text reveal: %d clip(s)" % len(todo))
    return len(todo)


# ---------------------------------------------------------------- titles

def _text_track_for(cur, sequence_id, start, end):
    # A text track with room for start..end-1, else a new one on top
    cur.execute("SELECT id FROM tracks WHERE sequence_id = ? AND track_type = "
                "'text' ORDER BY sort_order", (sequence_id,))
    for (tid,) in cur.fetchall():
        cur.execute("SELECT COUNT(*) FROM text_clips WHERE track_id = ? AND "
                    "start_frame < ? AND start_frame + length_frames > ?",
                    (tid, end, start))
        if cur.fetchone()[0] == 0:
            return tid
    from track_names import next_default_name
    cur.execute("SELECT name FROM tracks WHERE sequence_id = ?", (sequence_id,))
    name = next_default_name("text", [r[0] for r in cur.fetchall()])
    cur.execute("UPDATE tracks SET sort_order = sort_order + 1 WHERE sequence_id = ?",
                (sequence_id,))
    cur.execute("INSERT INTO tracks (sequence_id, name, track_type, sort_order, "
                "language) VALUES (?, ?, 'text', 0, '')", (sequence_id, name))
    return cur.lastrowid


def _add_text(cur, tl, track_id, start, length, text, size, x, y, seq_w, seq_h):
    from text_clip import insert_text_clip, remembered_text_style, text_db_id
    mem = insert_text_clip(cur, tl.sequence_id, track_id, start, length, seq_w,
                           seq_h, style=remembered_text_style(seq_h))
    cur.execute("UPDATE text_clips SET text = ?, font_size = ?, x = ?, y = ? "
                "WHERE id = ?", (text, int(size), int(x), int(y), text_db_id(mem)))
    return mem


def _select(tl, mem_ids):
    tl._selection_order = list(mem_ids)
    try:
        tl.table.viewport().update()
    except Exception:
        pass


def add_title(tl, kind):
    # kind "title" or "lower_third": the clips at the playhead, then their
    # fades / slides. Returns the new clip ids.
    seq_w, seq_h = tl._sequence_size()
    fps = float(tl.fps or 30)
    start = max(0, int(tl.current_frame))
    secs = TITLE_SECONDS if kind == "title" else LOWER_THIRD_SECONDS
    length = max(8, int(round(secs * fps)))
    from undo import push_undo
    project_db = tl._project_db()
    push_undo(project_db, "Add title" if kind == "title" else "Add lower third")
    conn = sqlite3.connect(project_db)
    try:
        cur = conn.cursor()
        track = _text_track_for(cur, tl.sequence_id, start, start + length)
        if kind == "title":
            ids = [_add_text(cur, tl, track, start, length, "Title",
                             seq_h * 0.14, seq_w // 2, seq_h // 2, seq_w, seq_h)]
        else:
            left = int(seq_w * 0.07)
            from text_clip import text_box_rect
            name_size, sub_size = seq_h * 0.075, seq_h * 0.042
            ny, sy = int(seq_h * 0.80), int(seq_h * 0.875)
            # left aligned: the box is centered on x, so put its centre half
            # a default-text width right of the margin
            nw = text_box_rect("Name", None, name_size, 0, 0).width()
            sw = text_box_rect("Subtitle", None, sub_size, 0, 0).width()
            ids = [_add_text(cur, tl, track, start, length, "Name", name_size,
                             left + nw // 2, ny, seq_w, seq_h)]
            track2 = _text_track_for(cur, tl.sequence_id, start, start + length)
            ids.append(_add_text(cur, tl, track2, start, length, "Subtitle",
                                 sub_size, left + sw // 2, sy, seq_w, seq_h))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    tl._after_clip_change("Added %s at frame %d" % (
        "title" if kind == "title" else "lower third", start))
    from fades import apply_fade
    from motion import apply_motion
    for i, mem in enumerate(ids):
        _select(tl, [mem])
        if kind == "title":
            apply_fade(tl, "inout")
        else:
            apply_motion(tl, "slide_in_left")
            apply_fade(tl, "out")
    _select(tl, ids)
    tl.table.viewport().update()
    return ids
