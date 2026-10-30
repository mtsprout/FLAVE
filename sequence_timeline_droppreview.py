# sequence_timeline_droppreview.py
# Drop preview boxes while footage from the Footage Manager is
# dragged over the Sequence Timeline. Preview only: drop_footage
# (sequence_timeline_sql.py) still decides everything. The math mirrors it:
#   row = table.rowAt(y); x_in_clips = x - Clips column position
#   start = max(0, view_start_frame + int(x_in_clips / pixels_per_frame))
#   (no snapping in drop_footage, so none here)
#   image footage -> image tracks only; video -> video; audio -> audio
# video length: footage_length_frames (footage.duration
#     else peaks, else 1 s) cut to the room before the next clip by
#     fit_video_drop; a linked audio clip (peaks exist and the sequence has
#     an audio track) goes on _nearest_free_track, below first, then above,
#     and the room on its track cuts the length too
#   audio length: _audio_length_frames (peaks, else footage.duration, 1 s)
#   refused (red): video drop frame inside a clip on its track, or no
#     audio track free there; image / audio drops have no overlap check in
#     drop_footage and are never shown red
# Footage facts are read once per drag (dragEnter); each move uses the
# table rows and clips_by_track already in memory (no database query).
# ASCII only.

import os
import sqlite3

from PySide6.QtCore import Qt, QRect


def _clips_col():
    from sequence_timeline_ruler import CLIPS_COL
    return CLIPS_COL


def footage_drag_info(tl, footage_id):
    # One query pass at dragEnter: {"footage_id", "accepts": {track_type},
    # "video_len", "audio_len", "linked_audio"} or None
    from sequence_timeline_sql import TRACK_FOOTAGE_EXTENSIONS
    try:
        project_db = tl._project_db()
        if not project_db or not os.path.isfile(project_db):
            return None
        conn = sqlite3.connect(project_db)
        try:
            cur = conn.cursor()
            cur.execute("SELECT filename, original_path FROM footage WHERE id = ?",
                        (int(footage_id),))
            frow = cur.fetchone()
            if not frow:
                return None
            accepts = set()
            for ttype, wanted in TRACK_FOOTAGE_EXTENSIONS.items():
                if any(v and str(v).lower().endswith(wanted) for v in frow):
                    accepts.add(ttype)
            fps = tl.fps
            video_len = max(1, int(round(fps)))
            linked = False
            has_audio = False
            if "video" in accepts:
                from sequence_timeline_sql import footage_length_frames
                peak_seconds = tl._peaks_seconds(cur, int(footage_id))
                video_len = footage_length_frames(cur, int(footage_id), fps,
                                                  peak_seconds)
                has_audio = peak_seconds > 0
                linked = (has_audio
                          and tl._first_audio_track_id(cur) is not None)
            audio_len = (tl._audio_length_frames(cur, int(footage_id))
                         if "audio" in accepts else None)
        finally:
            conn.close()
    except Exception:
        return None
    return {"footage_id": int(footage_id), "accepts": accepts,
            "video_len": video_len, "audio_len": audio_len, "linked_audio": linked,
            "has_audio": has_audio}


def track_rows(tl):
    # [(row, track_id, track_type)] in table order (= ORDER BY sort_order, id)
    out = []
    for r in range(tl.table.rowCount()):
        item = tl.table.item(r, 0)
        if item is None:
            continue
        tid = item.data(Qt.UserRole)
        if tid is None:
            continue
        out.append((r, int(tid), (item.data(Qt.UserRole + 4) or "").lower()))
    return out


class _MemCursor(object):
    # Answers _nearest_free_track's one tracks query from the table rows
    def __init__(self, rows):
        self._rows = [(tid, ttype) for _r, tid, ttype in rows]

    def execute(self, sql, params=()):
        return self

    def fetchall(self):
        return list(self._rows)


class _MemTimeline(object):
    # sequence_id + _range_overlaps on clips_by_track (in memory), so the
    # drop's own _nearest_free_track runs unchanged without the database
    def __init__(self, tl):
        self.sequence_id = tl.sequence_id
        self._clips = tl.clips_by_track

    def _range_overlaps(self, cur, track_id, start, length):
        return mem_range_overlaps(self._clips, track_id, start, length)


def mem_next_room(clips_by_track, track_id, start):
    # Same as next_clip_room: frames to the next clip at or after start
    nxt = [c[2] for c in clips_by_track.get(track_id, []) if c[2] >= start]
    return min(nxt) - start if nxt else None


def mem_range_overlaps(clips_by_track, track_id, start, length):
    # Same test as _range_overlaps: [start, start + length) vs each clip
    for c in clips_by_track.get(track_id, []):
        if c[2] < start + length and c[2] + c[3] > start:
            return True
    return False


# A box is (row, start_frame, length_frames, refused, label, is_new). A row
# past the last real row is a track the drop would create (drawn dashed below
# the last track, "New video track").

MAX_FILES = 6                 # Finder files previewed (and probed) per drag


def file_drag_info(tl, paths):
    # {"chain": [info, ...]} for files dragged in from Finder (not in the
    # project yet): one info per file, same keys as footage_drag_info, from
    # the extension and a quick ffprobe (length, sound)
    from sequence_timeline_sql import TRACK_FOOTAGE_EXTENSIONS
    out = []
    conn = None
    try:
        project_db = tl._project_db()
        if project_db and os.path.isfile(project_db):
            conn = sqlite3.connect(project_db)
        known = {}
        if conn is not None:
            from footage_drop import _norm
            known = dict((_norm(op), int(fid)) for fid, op in conn.execute(
                "SELECT id, original_path FROM footage").fetchall())
        for path in list(paths)[:MAX_FILES]:
            fid = known.get(_norm_path(path))
            if fid is not None:
                # already imported: the drop reuses that item, so preview it
                # from the project's own facts
                info = footage_drag_info(tl, fid)
                if info is not None:
                    out.append(info)
                    continue
            name = os.path.basename(path)
            accepts = set()
            for ttype, wanted in TRACK_FOOTAGE_EXTENSIONS.items():
                if name.lower().endswith(wanted):
                    accepts.add(ttype)
            fps = float(tl.fps or 30)
            one_sec = max(1, int(round(fps)))
            seconds, has_audio = 0.0, False
            if "image" not in accepts:
                seconds, has_audio = _probe(path, "video" in accepts)
            frames = max(1, int(round(seconds * fps))) if seconds > 0 else one_sec
            linked = (has_audio and conn is not None
                      and tl._first_audio_track_id(conn.cursor()) is not None)
            out.append({"accepts": accepts, "video_len": frames,
                        "audio_len": frames, "linked_audio": linked,
                        "has_audio": has_audio})
    except Exception:
        out = []
    finally:
        if conn is not None:
            conn.close()
    return {"chain": out}       # never None: a failed probe is not retried per move


def _norm_path(path):
    from footage_drop import _norm
    return _norm(path)


def _probe(path, want_audio):
    # (seconds, has an audio stream) of a media file; (0, False) on failure
    import subprocess
    from footage_importer import _probe_duration
    seconds = _probe_duration(path)
    has_audio = False
    if want_audio:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                 "stream=codec_type", "-of", "csv=p=0", path],
                capture_output=True, text=True, timeout=10)
            has_audio = r.returncode == 0 and "audio" in r.stdout
        except Exception:
            has_audio = False
    return seconds, has_audio


def _new_track_kind(info):
    # The kind of track a drop onto no track creates (see _footage_track_type)
    for kind in ("video", "audio", "image"):
        if kind in info["accepts"]:
            return kind
    return None


def _guess_len(tl, info):
    return (info.get("video_len") if "video" in info["accepts"] else None) \
        or info.get("audio_len") or max(1, int(round(float(tl.fps or 30))))


def _tc(tl, frame):
    from transport import timecode
    return timecode(frame, tl.fps)


def boxes_at(tl, info, row, start, virtual_base=None, fresh=True):
    # Boxes for one footage dropped at table row (-1 = no track there) and
    # start frame: where drop_footage would put it, where it would make
    # tracks (rows from virtual_base, default the row after the last track;
    # fresh False = tracks an earlier file of the same drop already made, so
    # no "New ... track" label), or a red box where it would refuse
    rows = track_rows(tl)
    by_row = dict((r, (tid, tt)) for r, tid, tt in rows)
    tc = _tc(tl, start)
    if row not in by_row:
        kind = _new_track_kind(info)
        if kind is None:
            return []
        n = tl.table.rowCount() if virtual_base is None else virtual_base
        length = (info["video_len"] if kind == "video" else
                  info["audio_len"] if kind == "audio" else
                  max(1, int(round(float(tl.fps or 30)))))
        boxes = [(n, start, length, False,
                  ("New %s track  %s" % (kind, tc)) if fresh else tc, True)]
        if kind == "video" and info.get("has_audio"):
            boxes.append((n + 1, start, length, False,
                          "New audio track" if fresh else None, True))
        return boxes
    track_id, track_type = by_row[row]
    if track_type not in ("image", "video", "audio") or track_type not in info["accepts"]:
        return [(row, start, _guess_len(tl, info), True, "Can't drop here", False)]
    if track_type == "image":
        return [(row, start, max(1, int(round(tl.fps))), False, tc, False)]
    if track_type == "audio":
        return [(row, start, info["audio_len"] or max(1, int(round(tl.fps))),
                 False, tc, False)]
    from sequence_timeline_sql import fit_video_drop
    clips = tl.clips_by_track
    length, tid, why = fit_video_drop(
        _MemTimeline(tl), _MemCursor(rows), track_id, start, info["video_len"],
        info["linked_audio"], lambda t, st: mem_next_room(clips, t, st))
    refused = why is not None
    boxes = [(row, start, length, refused, "Can't drop here" if refused else tc, False)]
    if tid is not None:
        audio_row = [r for r, t, _tt in rows if t == tid][0]
        boxes.append((audio_row, start, length, refused, None, False))
    return boxes


def preview_boxes(tl, info, pos):
    # Boxes for the drop at pos (viewport point); [] where nothing would be
    # added (over the name column). A Finder drag ("chain") previews each
    # file one after another from the drop point, like drop_files places them.
    if not info:
        return []
    x_in_clips = pos.x() - tl.ruler.sectionViewportPosition(_clips_col())
    if x_in_clips < 0:
        return []
    row = tl.table.rowAt(pos.y())
    start = max(0, tl.view_start_frame + int(x_in_clips / tl.pixels_per_frame))
    if "chain" not in info:
        return boxes_at(tl, info, row, start)
    out = []
    first_row = None
    n_rows = tl.table.rowCount()
    next_virtual = n_rows           # first row not yet used by a new track
    for i, one in enumerate(info["chain"]):
        if i == 0:
            boxes = boxes_at(tl, one, row, start)
            if boxes:
                first_row = boxes[0][0]
        else:
            first = info["chain"][0]
            if first_row is not None and (
                    (first_row < n_rows and _row_type(tl, first_row) in one["accepts"])
                    or (first_row >= n_rows
                        and _new_track_kind(one) == _new_track_kind(first))):
                # same track as the first file (the track it makes, if new)
                boxes = boxes_at(tl, one, first_row, start,
                                 virtual_base=first_row, fresh=False)
            else:
                boxes = boxes_at(tl, one, -1, start, virtual_base=next_virtual)
        if not boxes or boxes[0][3]:
            out.extend(boxes)
            break
        out.extend(boxes)
        news = [b[0] for b in boxes if b[5]]
        if news:
            next_virtual = max(next_virtual, max(news) + 1)
        start = boxes[0][1] + boxes[0][2]
    return out


def _row_type(tl, row):
    for r, _tid, tt in track_rows(tl):
        if r == row:
            return tt
    return ""


def _row_y(tl, row):
    # (y, height) of a table row; a row past the last one is where the new
    # track would be drawn, below the last track
    table = tl.table
    n = table.rowCount()
    if row < n:
        return table.rowViewportPosition(row), table.rowHeight(row)
    from sequence_timeline_sql import DEFAULT_TRACK_HEIGHT, track_row_height
    h = track_row_height(DEFAULT_TRACK_HEIGHT, False)
    base = (table.rowViewportPosition(n - 1) + table.rowHeight(n - 1)) if n else 0
    return base + (row - n) * h, h


def box_rect(tl, box):
    # Viewport QRect of one box, clipped to the Clips column; None if hidden
    row, start, length = box[0], box[1], box[2]
    table = tl.table
    left = table.columnViewportPosition(_clips_col())
    right = left + table.columnWidth(_clips_col())
    x0 = left + int((start - tl.view_start_frame) * tl.pixels_per_frame)
    x1 = left + int((start + length - tl.view_start_frame) * tl.pixels_per_frame)
    x0, x1 = max(x0, left), min(x1, right)
    if x1 <= x0:
        return None
    y, h = _row_y(tl, row)
    return QRect(x0, y, x1 - x0, max(1, h - 1))


def _boxes_region(tl, boxes):
    rect = QRect()
    for b in boxes or []:
        r = box_rect(tl, b)
        if r is not None:
            # room for the label pill that can stick out past a narrow box
            rect = rect.united(r.adjusted(-2, -2, 2, 2)).united(
                QRect(r.left(), r.top() - 2, 220, 22))
    return rect


def set_preview(tl, boxes):
    # Store boxes and repaint only the old and new box areas
    old = getattr(tl, "_drop_preview", None) or []
    boxes = boxes or []
    if old == boxes:
        return
    area = _boxes_region(tl, old).united(_boxes_region(tl, boxes))
    tl._drop_preview = boxes
    overlay = getattr(tl, "playhead_overlay", None)
    if overlay is not None and not area.isNull():
        overlay.update(area)


def drag_enter(tl, footage_id, pos):
    tl._drop_info = footage_drag_info(tl, footage_id)
    set_preview(tl, preview_boxes(tl, tl._drop_info, pos))


def drag_enter_files(tl, paths, pos):
    # Files from Finder
    tl._drop_info = file_drag_info(tl, paths)
    set_preview(tl, preview_boxes(tl, tl._drop_info, pos))


def drag_move(tl, pos):
    set_preview(tl, preview_boxes(tl, getattr(tl, "_drop_info", None), pos))


def drag_end(tl):
    # dragLeave (also Esc cancel), drop, or a drag this preview ignores
    tl._drop_info = None
    set_preview(tl, [])


def paint_preview(tl, painter):
    # Called from PlayheadOverlay.paintEvent (on top of the clips)
    from PySide6.QtGui import QColor, QFont, QPen
    for b in getattr(tl, "_drop_preview", None) or []:
        r = box_rect(tl, b)
        if r is None:
            continue
        refused, label, is_new = b[3], b[4], b[5]
        if refused:
            fill, edge = QColor(255, 60, 60, 60), QColor(255, 80, 80)
        elif is_new:
            fill, edge = QColor(90, 160, 255, 45), QColor(120, 180, 255)
        else:
            fill, edge = QColor(255, 255, 255, 40), QColor(255, 255, 255)
        painter.fillRect(r, fill)
        pen = QPen(edge)
        pen.setWidth(1)
        if is_new:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(r.adjusted(0, 0, -1, -1))
        if label:
            painter.save()
            font = QFont(painter.font())
            font.setPixelSize(11)
            painter.setFont(font)
            fm = painter.fontMetrics()
            w = fm.horizontalAdvance(label) + 10
            pill = QRect(r.left() + 2, r.top() + 2, w, fm.height() + 2)
            painter.fillRect(pill, QColor(20, 20, 20, 215))
            painter.setPen(QColor(255, 120, 120) if refused else QColor(235, 235, 235))
            painter.drawText(pill, Qt.AlignCenter, label)
            painter.restore()
