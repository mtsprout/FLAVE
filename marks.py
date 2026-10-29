# marks.py
# In and Out points of a sequence: sequences.mark_in / mark_out (NULL = not
# set; older project files get the columns on first use). Both are frames
# and both are INCLUDED: rendering In to Out writes Out - In + 1 frames. With
# only In set the range runs to the end of the sequence, with only Out set
# it starts at frame 0. Used by the I / O keys, the Mark menu and the Render
# panel's Range choice. ASCII only.

import sqlite3

LISTENERS = {}          # sequence id -> callables told when the marks change


def ensure_columns(conn):
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sequences)")]
        for name in ("mark_in", "mark_out"):
            if cols and name not in cols:
                conn.execute("ALTER TABLE sequences ADD COLUMN %s INTEGER" % name)
        conn.commit()
    except sqlite3.Error:
        pass


def get(project_db, sequence_id):
    # (mark_in, mark_out), each a frame or None
    try:
        conn = sqlite3.connect(project_db)
        try:
            ensure_columns(conn)
            row = conn.execute("SELECT mark_in, mark_out FROM sequences WHERE id = ?",
                               (int(sequence_id),)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None, None
    if not row:
        return None, None
    return (None if row[0] is None else int(row[0]),
            None if row[1] is None else int(row[1]))


def _store(project_db, sequence_id, a, b):
    conn = sqlite3.connect(project_db)
    try:
        ensure_columns(conn)
        conn.execute("UPDATE sequences SET mark_in = ?, mark_out = ? WHERE id = ?",
                     (a, b, int(sequence_id)))
        conn.commit()
    finally:
        conn.close()
    for fn in list(LISTENERS.get(int(sequence_id), [])):
        try:
            fn()
        except Exception:
            pass


def _tc(tl, frame):
    from transport import timecode
    return timecode(frame, tl.fps)


def set_in(tl):
    a, b = get(tl._project_db(), tl.sequence_id)
    f = int(tl.current_frame)
    if b is not None and f > b:
        b = None                    # In moved past Out: Out is cleared
    _store(tl._project_db(), tl.sequence_id, f, b)
    tl.status_bar.showMessage("In set at %s" % _tc(tl, f), 3000)


def set_out(tl):
    a, b = get(tl._project_db(), tl.sequence_id)
    f = int(tl.current_frame)
    if a is not None and f < a:
        a = None                    # Out moved before In: In is cleared
    _store(tl._project_db(), tl.sequence_id, a, f)
    tl.status_bar.showMessage("Out set at %s" % _tc(tl, f), 3000)


def go_in(tl):
    a, _b = get(tl._project_db(), tl.sequence_id)
    if a is not None:
        tl._jump_to_frame(a)


def go_out(tl):
    _a, b = get(tl._project_db(), tl.sequence_id)
    if b is not None:
        tl._jump_to_frame(b)


def clear(tl):
    _store(tl._project_db(), tl.sequence_id, None, None)
    tl.status_bar.showMessage("In and Out cleared", 3000)


def span(project_db, sequence_id, total_frames):
    # (first frame, last frame) of the marked range, clamped to the sequence,
    # or None when no mark is set or the range is empty
    a, b = get(project_db, sequence_id)
    if a is None and b is None:
        return None
    first = 0 if a is None else max(0, a)
    last = total_frames - 1 if b is None else min(total_frames - 1, b)
    return (first, last) if last >= first else None


def text(tl, project_db=None):
    # "In 00:00:05:00   Out 00:00:12:00", or "" when none is set
    a, b = get(project_db or tl._project_db(), tl.sequence_id)
    parts = []
    if a is not None:
        parts.append("In " + _tc(tl, a))
    if b is not None:
        parts.append("Out " + _tc(tl, b))
    return "   ".join(parts)
