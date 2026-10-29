# sequence_player_cpu.py
# Sequence Player without CUDA / OpenGL (macOS): the same window, menus,
# geometry, preview audio and play clock as SequencePlayer, but the picture
# is a QImage painted on a raster backing store. Pictures come only from the
# preview db JPEGs (the worker's CpuComposer fills them), decoded by Qt.
# Everything GPU in SequencePlayer is overridden here; the rest is
# inherited. ASCII only.

import io
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QBackingStore, QColor, QImage, QPainter, QPalette,
                           QRegion, QSurfaceFormat, QWindow)
from PySide6.QtWidgets import QApplication, QWidget

from sequence_player import SequencePlayer, playback_rect
from sequence_player_gpu import _dark_mode


try:
    from PIL import Image as _PilImage
except ImportError:
    _PilImage = None

PLAY_DECODE_THREADS = 3
PICTURE_MARGIN = 8       # logical px between the player edge and the picture


def _theme_is_dark():
    # FLAVE's own dark mode (a black stylesheet), or a dark system palette
    # (macOS dark appearance)
    try:
        import theme
        if theme._state["hooked"]:
            return theme.is_dark()          # the unified window's theme
    except Exception:
        pass
    if _dark_mode():
        return True
    return QApplication.palette().color(QPalette.Window).lightness() < 128


def _decode_jpeg(jpeg):
    # Pillow when installed: it releases the GIL while it decodes, so the
    # window thread keeps running (Qt's JPEG decoder holds it). Else Qt.
    if _PilImage is not None:
        try:
            im = _PilImage.open(io.BytesIO(jpeg))
            im.load()
            if im.mode != "RGB":
                im = im.convert("RGB")
            raw = im.tobytes()
            img = QImage(raw, im.width, im.height, im.width * 3,
                         QImage.Format_RGB888)
            img._raw = raw          # the QImage reads these bytes in place
            return img
        except Exception:
            pass
    img = QImage()
    if not img.loadFromData(jpeg, "JPG") or img.isNull():
        raise RuntimeError("preview JPEG decode failed")
    return img.convertToFormat(QImage.Format_RGB888)


class SequencePlayerCpu(SequencePlayer):

    cpu_backend = True

    def __init__(self, timeline):
        super().__init__(timeline)
        self.setSurfaceType(QWindow.RasterSurface)
        self.setFormat(QSurfaceFormat())
        self._store = None
        self._img = None            # QImage of the shown frame (any size)
        self._pq_lock = threading.Lock()   # _play_queue / _play_pending
        self._play_pending = set()  # frames a background job is decoding
        self._play_gen = 0          # bumped when the queue is dropped
        self._play_pool = None

    # ---- setup / release (no device memory)
    def _setup(self):
        self._store = QBackingStore(self)
        self.ready = True

    def _release_gpu(self):
        self._release_gpu_locked()

    def _release_gpu_locked(self):
        self.ready = False
        self._release_play_bufs()
        pool, self._play_pool = self._play_pool, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
        self._img = None

    def _release_play_bufs(self):
        with self._pq_lock:
            self._play_gen += 1
            self._play_queue = []
            self._play_pending = set()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.ready and self.isExposed():
            self._present(_dark_mode(), self._img is not None)

    # ---- pictures
    def _show_jpeg(self, jpeg, dark):
        self._img = _decode_jpeg(jpeg)
        self._present(dark, True)

    def _show_device(self, img, dark):
        self._img = img
        self._present(dark, True)

    def redraw_edited(self, frame, snapshot):
        # The worker composites the edited frame (no GUI-thread decode)
        return False

    def frame_jpeg(self, frame, quality=90, snapshot=None, worker=False):
        return None

    def _present(self, dark, has_frame):
        store = self._store
        if store is None or not self.isExposed():
            return
        size = self.size()
        if size.isEmpty():
            return
        store.resize(size)
        rect = QRect(QPoint(0, 0), size)
        store.beginPaint(QRegion(rect))
        p = QPainter(store.paintDevice())
        try:
            self.paint_picture(p, size, dark, has_frame)
        finally:
            p.end()
        store.endPaint()
        store.flush(QRegion(rect))

    def paint_picture(self, p, size, dark, has_frame):
        # The picture letterboxed into size (logical px) on painter p, and
        # the captions over it. Used by the window and by the docked panel.
        rect = QRect(QPoint(0, 0), size)
        # The look of the surround follows the application's real theme
        # (macOS dark appearance), not only FLAVE's own dark_mode setting
        dark = _theme_is_dark()
        p.fillRect(rect, QColor(28, 28, 28) if dark else QColor(214, 214, 214))
        if not has_frame or self._img is None:
            return
        # The picture sits inside a small margin on every side, so its
        # outline is always visible, also at 100% (fill the player)
        margin = float(PICTURE_MARGIN)
        ww = float(size.width()) - 2.0 * margin
        wh = float(size.height()) - 2.0 * margin
        if ww < 16.0 or wh < 16.0:
            margin = 0.0
            ww, wh = float(size.width()), float(size.height())
        seq_aspect = self.seq_w / float(self.seq_h)
        win_aspect = ww / wh
        if win_aspect > seq_aspect:
            vh, vw = 1.0, seq_aspect / win_aspect
        else:
            vw, vh = 1.0, win_aspect / seq_aspect
        vw, vh = playback_rect(vw, vh, self._playback_pct)
        pw, ph = vw * ww, vh * wh
        target = QRectF(margin + (ww - pw) / 2.0, margin + (wh - ph) / 2.0, pw, ph)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(target, self._img)
        # A thin outline around the picture sets a dark frame apart from
        # the surround
        p.setPen(QColor(110, 110, 110) if dark else QColor(150, 150, 150))
        p.setBrush(Qt.NoBrush)
        p.drawRect(target.adjusted(-0.5, -0.5, 0.5, 0.5))
        try:
            self._paint_captions_cpu(p, target)
        except Exception as e:
            print(f"Sequence Player caption overlay failed: {e}")

    def _paint_captions_cpu(self, p, target):
        from player_captions import captions_at, caption_image
        snap = self._caption_snap()
        frame = int(self.timeline.current_frame)
        if not captions_at(snap, frame):
            return
        ratio = self.devicePixelRatio()
        pw = max(1, int(round(target.width() * ratio)))
        ph = max(1, int(round(target.height() * ratio)))
        img = caption_image(snap, frame, pw, ph, self.seq_w, self.seq_h)
        p.drawImage(target, img)

    # ---- playback: decoded QImages instead of device buffers
    def decode_play_batch(self, items):
        out = []
        for frame, jpeg in items:
            try:
                out.append((frame, _decode_jpeg(jpeg)))
            except Exception as e:
                print(f"Play decode failed: {e}")
        return out

    # Fill-ahead runs on background threads: the timeline's play tick (GUI
    # thread) only starts a job and picks up frames that are already decoded.
    def play_fill(self, start, n):
        start, n = int(start), int(n)
        with self._pq_lock:
            have = set(f for f, _img in self._play_queue) | self._play_pending
            want = [f for f in range(start, start + n) if f not in have]
            if not want:
                return 0
            self._play_pending.update(want)
            gen = self._play_gen
        if self._play_pool is None:
            self._play_pool = ThreadPoolExecutor(
                max_workers=PLAY_DECODE_THREADS, thread_name_prefix="PlayDec")
        self._play_pool.submit(self._fill_job, want, gen)
        return len(want)

    def _fill_job(self, want, gen):
        # Background thread: read the JPEGs of these frames, decode, queue
        from sequence_preview import preview_db_path, CLEAN_SQL
        from sequence_preview import PREVIEW_GUI_BUSY_SEC
        path = preview_db_path(self.timeline._project_db(), self.sequence_id)
        rows = {}
        try:
            conn = sqlite3.connect(path, timeout=PREVIEW_GUI_BUSY_SEC)
            try:
                conn.execute("PRAGMA query_only = ON")
                for f, blob in conn.execute(
                        "SELECT frame, jpeg FROM preview WHERE frame BETWEEN ? "
                        "AND ? AND jpeg IS NOT NULL AND " + CLEAN_SQL,
                        (min(want), max(want))):
                    rows[int(f)] = bytes(blob)
            finally:
                conn.close()
        except Exception as e:
            print(f"Play fill read failed: {e}")
        for f in want:
            img = None
            jpeg = rows.get(f)
            if jpeg and self._play_gen == gen:
                try:
                    img = _decode_jpeg(jpeg)
                except Exception as e:
                    print(f"Play decode failed: {e}")
            with self._pq_lock:
                if self._play_gen != gen:
                    return
                self._play_pending.discard(f)
                if img is not None:
                    self._play_queue.append((f, img))

    def play_has(self, frame):
        frame = int(frame)
        with self._pq_lock:
            return any(f == frame for f, _img in self._play_queue)

    def play_queue_hi(self):
        # Highest frame decoded or being decoded (so the tick does not
        # ask for the same frames again), None when nothing is queued
        with self._pq_lock:
            frames = [f for f, _img in self._play_queue]
            frames.extend(self._play_pending)
        return max(frames) if frames else None

    def play_show_at_most(self, frame):
        frame = int(frame)
        with self._pq_lock:
            best = max((f for f, _img in self._play_queue if f <= frame),
                       default=None)
        if best is not None and self.play_show(best):
            return best
        return None

    def play_show(self, frame):
        with self._pq_lock:
            for i, (f, img) in enumerate(self._play_queue):
                if f == frame:
                    del self._play_queue[i]
                    break
            else:
                return False
        self._img = img
        self._present(_dark_mode(), True)
        self.shown_frame = frame
        return True

    def play_drop_before(self, frame):
        with self._pq_lock:
            self._play_queue = [(f, b) for f, b in self._play_queue
                                if f >= frame]

    def close_play_conn(self):
        self._release_play_bufs()


# ---- docked player: the same logic, painted by a normal widget

class SequencePlayerEmbedded(SequencePlayerCpu):
    # Never shown as a window: a PlayerPanel (workspace.py) paints it and
    # forwards the mouse. Everything that asks the window about itself
    # (exposed, size, cursor, global position) answers for the panel.

    panel = None

    def __init__(self, timeline, panel):
        super().__init__(timeline)
        self.panel = panel
        self._dark = True
        self._has_frame = False
        self._setup()                   # ready: no window expose to wait for

    # window questions answered for the panel
    def isExposed(self):
        return self.panel is not None and self.panel.isVisible()

    def isVisible(self):
        return self.isExposed()

    def visibility(self):
        return QWindow.Windowed

    def size(self):
        return self.panel.size() if self.panel is not None else super().size()

    def width(self):
        return self.panel.width() if self.panel is not None else super().width()

    def height(self):
        return self.panel.height() if self.panel is not None else super().height()

    def devicePixelRatio(self):
        return (self.panel.devicePixelRatioF() if self.panel is not None
                else super().devicePixelRatio())

    def mapToGlobal(self, pos):
        return self.panel.mapToGlobal(pos)

    def setCursor(self, cursor):
        self.panel.setCursor(cursor)

    def unsetCursor(self):
        self.panel.unsetCursor()

    def raise_(self):
        pass

    def requestActivate(self):
        pass

    def show(self):
        pass

    def _save_geometry(self):
        pass

    def _setup(self):
        self.ready = True

    def _present(self, dark, has_frame):
        self._dark, self._has_frame = dark, has_frame
        if self.panel is not None:
            self.panel.update()

    def close(self):
        if self.closed:
            return True
        self._on_close()
        if self.panel is not None:
            self.panel.set_logic(None)
        return True


class PlayerPanel(QWidget):
    # The Sequence Player of one timeline inside the main window
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logic = None
        self.setMinimumSize(200, 120)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setAcceptDrops(True)       # files / footage: added at the playhead
        self.on_drop = None             # set by the workspace

    def dragEnterEvent(self, event):
        from footage_drop import media_paths
        mime = event.mimeData()
        if media_paths(mime) or (mime.hasText() and mime.text().startswith("footage:")):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if self.on_drop is None:
            event.ignore()
            return
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.on_drop(event.mimeData())

    def set_logic(self, logic):
        self.logic = logic
        self.update()
        if logic is not None:
            QTimer.singleShot(0, self._first_frame)

    def _first_frame(self):
        lg = self.logic
        if lg is not None and not lg.closed:
            lg.request_frame(force=True)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._first_frame)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            lg = self.logic
            if lg is None or lg.closed:
                dark = _theme_is_dark()
                p.fillRect(self.rect(), QColor(28, 28, 28) if dark
                           else QColor(214, 214, 214))
                p.setPen(QColor(150, 150, 150))
                p.drawText(self.rect(), Qt.AlignCenter, "No sequence open")
            else:
                lg.paint_picture(p, self.size(), lg._dark, lg._has_frame)
        finally:
            p.end()

    # the player's own mouse handling (text clip move / edit, size menu)
    def _forward(self, name, event):
        lg = self.logic
        if lg is None or lg.closed:
            event.ignore()
            return
        getattr(lg, name)(event)

    def mousePressEvent(self, event):
        self._forward("mousePressEvent", event)

    def mouseMoveEvent(self, event):
        self._forward("mouseMoveEvent", event)

    def mouseReleaseEvent(self, event):
        self._forward("mouseReleaseEvent", event)

    def mouseDoubleClickEvent(self, event):
        self._forward("mouseDoubleClickEvent", event)
