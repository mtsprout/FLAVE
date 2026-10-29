# footage_drop.py
# Files dragged in from Finder: which dropped URLs are media, and importing
# them into the project (an item already imported from the same path is
# reused, not added twice). Used by the Footage pane, the timeline and the
# player panel. ASCII only.

import os
import sqlite3

from sequence_timeline_audio import AUDIO_EXTENSIONS
from sequence_timeline_image import IMAGE_EXTENSIONS
from sequence_timeline_video import VIDEO_EXTENSIONS

MEDIA_EXTENSIONS = tuple(IMAGE_EXTENSIONS) + tuple(VIDEO_EXTENSIONS) + tuple(AUDIO_EXTENSIONS)


def media_paths(mime):
    # Local media files in a drop's mime data (folders and other files are
    # ignored), in the order they were dropped
    out = []
    if mime is None or not mime.hasUrls():
        return out
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = url.toLocalFile()
        if os.path.isfile(path) and path.lower().endswith(MEDIA_EXTENSIONS):
            out.append(path)
    return out


def _norm(path):
    return os.path.normcase(os.path.abspath(path or ""))


def import_paths(project_db, paths):
    # [(path, footage_id)] for the files that are in the project afterwards
    from footage_importer import import_footage
    conn = sqlite3.connect(project_db)
    try:
        known = dict((_norm(p), i) for i, p in
                     conn.execute("SELECT id, original_path FROM footage"))
    finally:
        conn.close()
    out = []
    for path in paths:
        fid = known.get(_norm(path))
        if fid is None:
            fid = import_footage(project_db, path)
            if fid:
                known[_norm(path)] = fid
        if fid:
            out.append((path, int(fid)))
    return out


def refresh_footage_panes():
    # Every open Footage Manager reloads (new items show up)
    from PySide6.QtWidgets import QApplication
    for w in QApplication.allWidgets():
        if type(w).__name__ == "FootageManager":
            try:
                w.refresh()
            except Exception as e:
                print("Footage refresh failed: %s" % e)
