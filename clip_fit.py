# clip_fit.py
# Fit scale of a timeline clip: footage larger than the sequence is shown
# scaled down to fit when it is dropped (CPU backend), instead of 1:1 and
# cropped. One REAL percent per clip in clips.fit_percent (NULL = none, the
# clip's base scale is 100). The timeline keeps {clip id: percent} for
# clips that have one (tl._clip_fits, load_clip_fits); the player snapshot
# copies it (snapshot[34]) and sequence_player._layer_items uses it as the
# clip's base scale: a scale keyframe is a percent of it. Older project
# files get the column on first load. ASCII only.

import sqlite3

FIT_COLUMN = "fit_percent"


def load_clip_fits(conn, sequence_id):
    # {clip id: fit percent} of this sequence's clips that have one.
    # Adds the column to a project file made before it existed.
    sql = ("SELECT c.id, c.%s FROM clips c JOIN tracks t ON t.id = c.track_id "
           "WHERE t.sequence_id = ? AND c.%s IS NOT NULL" % (FIT_COLUMN, FIT_COLUMN))
    try:
        rows = conn.execute(sql, (sequence_id,)).fetchall()
    except sqlite3.OperationalError:
        try:
            conn.execute("ALTER TABLE clips ADD COLUMN %s REAL" % FIT_COLUMN)
            conn.commit()
        except sqlite3.Error:
            pass
        return {}
    return dict((int(i), float(p)) for i, p in rows if p and float(p) != 100.0)


def fit_percent_for(seq_w, seq_h, w, h):
    # Percent that makes a w x h picture fit inside the sequence, or None
    # when it is not larger than the sequence in either direction
    try:
        seq_w, seq_h, w, h = float(seq_w), float(seq_h), float(w), float(h)
    except (TypeError, ValueError):
        return None
    if min(seq_w, seq_h, w, h) <= 0 or (w <= seq_w and h <= seq_h):
        return None
    return round(min(seq_w / w, seq_h / h) * 100.0, 4)


def store_fit(cur, clip_id, percent):
    cur.execute("UPDATE clips SET %s = ? WHERE id = ?" % FIT_COLUMN,
                (percent, int(clip_id)))


def copy_fit(cur, src_id, dst_id):
    # A new clip made from another (slice) keeps its fit
    try:
        cur.execute("UPDATE clips SET %s = (SELECT %s FROM clips WHERE id = ?) "
                    "WHERE id = ?" % (FIT_COLUMN, FIT_COLUMN),
                    (int(src_id), int(dst_id)))
    except sqlite3.OperationalError:
        pass
