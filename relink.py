# relink.py
# Replace / relink footage: point a footage item at a different file (media
# that moved, a project made on another computer, a better copy) without
# touching its clips. The item keeps its id, so every clip, keyframe and
# marker stays; the file facts (size, duration, width, height, codec, frame
# rate, pixel aspect, field order), the thumbnails and the waveform are
# re-read from the new file. Other footage whose files are also missing and
# which sit in the same relative place are offered for relinking in the same
# step. Uses the importer's own probes. ASCII only.

import os
import sqlite3

from PySide6.QtWidgets import QFileDialog, QMessageBox


def _norm(path):
    return (path or "").replace("\\", "/")


def is_missing(path):
    return not (path and os.path.isfile(path))


def relink_one(project_db, footage_id, new_path):
    # Point the item at new_path and re-read the file's facts. Returns None
    # when the file is not there.
    from footage_importer import (IMAGE_EXTS, _VISUAL_EXTS, _probe_duration,
                                  store_footage_fps)
    if not os.path.isfile(new_path):
        return None
    filename = os.path.basename(new_path)
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    conn = sqlite3.connect(project_db)
    try:
        conn.execute(
            "UPDATE footage SET original_path = ?, filename = ?, size_bytes = ?, "
            "file_type = ?, duration = ?, width = NULL, height = NULL, "
            "codec = NULL, fps = NULL, pixel_aspect = NULL, field_order = NULL "
            "WHERE id = ?",
            (new_path, filename, os.path.getsize(new_path), ext,
             _probe_duration(new_path), int(footage_id)))
        conn.execute("DELETE FROM icons WHERE footage_id = ?", (int(footage_id),))
        conn.commit()
    finally:
        conn.close()
    if ext in _VISUAL_EXTS:
        try:
            from clip_proxy import probe_video_info
            info = probe_video_info(new_path)
            if info is not None:
                conn = sqlite3.connect(project_db)
                try:
                    conn.execute("UPDATE footage SET width = ?, height = ?, "
                                 "codec = ? WHERE id = ?",
                                 (info[0], info[1], info[2], int(footage_id)))
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass
    if ext in _VISUAL_EXTS and ext not in IMAGE_EXTS:
        store_footage_fps(project_db, footage_id, new_path)
        try:
            from clip_proxy import probe_video_sar, format_pixel_aspect
            sar = probe_video_sar(new_path)
            if sar is not None:
                conn = sqlite3.connect(project_db)
                try:
                    conn.execute("UPDATE footage SET pixel_aspect = ? WHERE id = ?",
                                 (format_pixel_aspect(sar[2], sar[3]), int(footage_id)))
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass
    if ext == "mkv":
        try:
            from footage_importer import probe_field_order
            order = probe_field_order(new_path)
            conn = sqlite3.connect(project_db)
            try:
                conn.execute("UPDATE footage SET field_order = ? WHERE id = ?",
                             (order, int(footage_id)))
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
    try:
        from peaks import ensure_audiotmp_db, store_peaks_for_footage
        ensure_audiotmp_db(project_db)
        store_peaks_for_footage(project_db, footage_id, new_path)
    except Exception:
        pass
    return footage_id


def find_siblings(project_db, footage_id, old_path, new_path):
    # [(footage id, new path)] for the OTHER footage whose files are missing
    # and that exist at the same place relative to the moved folder: the old
    # and new paths are compared from the end, and what differs at the front
    # is the moved root (/old/root/a/x.mov -> /new/root/a/x.mov); else the
    # same file name in the new file's folder.
    old_n, new_n = _norm(old_path), _norm(new_path)
    o, n = old_n.split("/"), new_n.split("/")
    k = 0
    while k < min(len(o), len(n)) and o[-1 - k] == n[-1 - k]:
        k += 1
    old_root = "/".join(o[:len(o) - k]) if k else ""
    new_root = "/".join(n[:len(n) - k]) if k else ""
    new_dir = os.path.dirname(new_path)
    conn = sqlite3.connect(project_db)
    try:
        rows = conn.execute("SELECT id, original_path FROM footage WHERE id <> ?",
                            (int(footage_id),)).fetchall()
    finally:
        conn.close()
    out = []
    for fid, path in rows:
        if not is_missing(path):
            continue
        cand = None
        pn = _norm(path)
        if old_root and pn.startswith(old_root + "/"):
            c = os.path.normpath(new_root + pn[len(old_root):])
            cand = c if os.path.isfile(c) else None
        if cand is None:
            c = os.path.join(new_dir, os.path.basename(pn))
            cand = c if os.path.isfile(c) else None
        if cand:
            out.append((int(fid), cand))
    return out


def replace_footage(manager, footage_id):
    # The Footage panel's Replace command (manager = the FootageManager)
    project_db = manager.project_db
    conn = sqlite3.connect(project_db)
    try:
        row = conn.execute("SELECT original_path, filename FROM footage WHERE id = ?",
                           (int(footage_id),)).fetchone()
    finally:
        conn.close()
    if row is None:
        return
    old_path, old_name = row[0], row[1] or ""
    start = os.path.dirname(old_path) if old_path and os.path.isdir(
        os.path.dirname(old_path)) else os.path.expanduser("~")
    new_path, _ = QFileDialog.getOpenFileName(
        manager, "Replace \"%s\" with..." % old_name, start)
    if not new_path:
        return
    from undo import push_undo
    push_undo(project_db, "Replace footage")
    if relink_one(project_db, footage_id, new_path) is None:
        QMessageBox.warning(manager, "Replace", "That file could not be read.")
        return
    done = 1
    sibs = find_siblings(project_db, footage_id, old_path, new_path)
    if sibs:
        reply = QMessageBox.question(
            manager, "Replace",
            "%d other missing file%s found in the same place. Relink %s too?"
            % (len(sibs), "s were" if len(sibs) != 1 else " was",
               "them" if len(sibs) != 1 else "it"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            for fid, path in sibs:
                if relink_one(project_db, fid, path) is not None:
                    done += 1
    _refresh_everything(manager)
    manager.status_bar.showMessage("Relinked %d footage item%s" % (
        done, "" if done == 1 else "s"), 5000)


def _refresh_everything(manager):
    # Footage list, then every open timeline: the picture and sound come
    # from the new file
    manager.refresh()
    try:
        import sequence_timeline
        for tl in list(sequence_timeline._open_windows.values()):
            try:
                tl.clear_preview_video()
                tl.clear_preview_audio()
                tl.refresh()
            except Exception as e:
                print("Relink refresh failed: %s" % e)
    except Exception as e:
        print("Relink refresh failed: %s" % e)
