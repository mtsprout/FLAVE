# footage_names.py
# A footage item's own name, different from its file name: footage.display_name
# (NULL / empty = show the file name). The file name column stays what the
# importer stored: the audio cache and the extension checks depend on it.
# Shown in the Footage pane and as the clip titles on the timeline. Older
# project files get the column on first use. ASCII only.

import sqlite3

COLUMN = "display_name"


def ensure_column(conn):
    # Add footage.display_name to a project file that lacks it
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(footage)")]
        if cols and COLUMN not in cols:
            conn.execute("ALTER TABLE footage ADD COLUMN %s TEXT" % COLUMN)
            conn.commit()
    except sqlite3.Error:
        pass


def set_display_name(project_db, footage_id, name):
    # name empty / None: back to the file name. Returns the stored value.
    name = (name or "").strip() or None
    conn = sqlite3.connect(project_db)
    try:
        ensure_column(conn)
        conn.execute("UPDATE footage SET %s = ? WHERE id = ?" % COLUMN,
                     (name, int(footage_id)))
        conn.commit()
    finally:
        conn.close()
    return name
