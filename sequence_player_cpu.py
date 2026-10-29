# sequence_player_cpu.py
# Sequence Player without CUDA / OpenGL (macOS): the same window, menus,
# geometry, preview audio and play clock as SequencePlayer, but the picture
# is a QImage painted on a raster backing store. Pictures come only from the
# preview db JPEGs (the worker's CpuComposer fills them), decoded by Qt.
# Everything GPU in SequencePlayer is overridden here; the rest is
# inherited. ASCII only.

from PySide6.QtCore import QPoint, QRect, QRectF
from PySide6.QtGui import (QBackingStore, QColor, QImage, QPainter, QRegion,
                           QSurfaceFormat, QWindow)

from sequence_player import SequencePlayer, playback_rect
from sequence_player_gpu import _dark_mode


def _decode_jpeg(jpeg):
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

    # ---- setup / release (no device memory)
    def _setup(self):
        self._store = QBackingStore(self)
        self.ready = True

    def _release_gpu(self):
        self._release_gpu_locked()

    def _release_gpu_locked(self):
        self.ready = False
        self._play_queue = []
        self._img = None

    def _release_play_bufs(self):
        self._play_queue = []

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
            p.fillRect(rect, QColor(0, 0, 0) if dark else QColor(255, 255, 255))
            if has_frame and self._img is not None:
                ww, wh = float(size.width()), float(size.height())
                seq_aspect = self.seq_w / float(self.seq_h)
                win_aspect = ww / wh
                if win_aspect > seq_aspect:
                    vh, vw = 1.0, seq_aspect / win_aspect
                else:
                    vw, vh = 1.0, win_aspect / seq_aspect
                vw, vh = playback_rect(vw, vh, self._playback_pct)
                pw, ph = vw * ww, vh * wh
                target = QRectF((ww - pw) / 2.0, (wh - ph) / 2.0, pw, ph)
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p.drawImage(target, self._img)
                try:
                    self._paint_captions_cpu(p, target)
                except Exception as e:
                    print(f"Sequence Player caption overlay failed: {e}")
        finally:
            p.end()
        store.endPaint()
        store.flush(QRegion(rect))

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

    def play_show(self, frame):
        for i, (f, img) in enumerate(self._play_queue):
            if f == frame:
                break
        else:
            return False
        _f, img = self._play_queue.pop(i)
        self._img = img
        self._present(_dark_mode(), True)
        self.shown_frame = frame
        return True

    def play_drop_before(self, frame):
        self._play_queue = [(f, b) for f, b in self._play_queue if f >= frame]
