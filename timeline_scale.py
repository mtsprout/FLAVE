# timeline_scale.py
# The strip under the tracks in the unified window: a track-height slider on
# the left, and a zoom navigator on the right. The navigator shows the whole
# sequence as a bar with a lit window for the part the timeline shows. Drag
# the window to scroll, drag its ends to zoom, double-click to fit all.
# Everything goes through the timeline's own state (pixels_per_frame,
# view_start_frame, _update_clips_width). ASCII only.

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

import theme

TRACK_SCALE_KEY = "timeline_track_scale"     # percent of the saved track height
TRACK_SCALE_DEFAULT = 60
TRACK_SCALE_MIN, TRACK_SCALE_MAX = 38, 200   # 38% of a 64 px track = 24 px, the row floor
HANDLE = 7                                   # px: grab zone at each end


def apply_track_scale(tl, percent):
    # Every track row takes its saved height times percent (display only;
    # the saved heights are not changed)
    import sequence_timeline_sql as sql
    sql.TRACK_HEIGHT_SCALE[0] = max(TRACK_SCALE_MIN, min(TRACK_SCALE_MAX,
                                                         int(percent))) / 100.0
    from sequence_timeline_sql import ROLE_COLLAPSED, ROLE_OPEN_HEIGHT, track_row_height
    for r in range(tl.table.rowCount()):
        item = tl.table.item(r, 0)
        if item is None:
            continue
        tl.table.setRowHeight(r, track_row_height(
            item.data(ROLE_OPEN_HEIGHT), item.data(ROLE_COLLAPSED)))
    try:
        tl._clear_icon_misses()
    except Exception:
        pass
    tl.table.viewport().update()
    tl.ruler.viewport().update()


def prime_track_scale():
    # Read the remembered track height before a timeline builds its rows
    from global_settings import _get_global_setting
    import sequence_timeline_sql as sql
    try:
        val = int(_get_global_setting(TRACK_SCALE_KEY, "") or TRACK_SCALE_DEFAULT)
    except ValueError:
        val = TRACK_SCALE_DEFAULT
    sql.TRACK_HEIGHT_SCALE[0] = max(TRACK_SCALE_MIN, min(TRACK_SCALE_MAX, val)) / 100.0


class ZoomNavigator(QWidget):

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.tl = timeline
        self.setFixedHeight(20)
        self.setMouseTracking(True)
        self._mode = None
        self._press_x = 0.0
        self._start0 = 0.0
        self._vis0 = 0.0
        self._shown = None
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ---- geometry of the view in frames
    def _clips_w(self):
        from sequence_timeline_ruler import CLIPS_COL
        return max(1.0, float(self.tl.ruler.sectionSize(CLIPS_COL)))

    def _state(self):
        tl = self.tl
        total = max(1.0, float(tl.total_frames()))
        ppf = max(1e-6, float(tl.pixels_per_frame))
        vis = self._clips_w() / ppf
        start = max(0.0, float(tl.view_start_frame))
        span = max(total, start + vis)
        return start, vis, span

    def _poll(self):
        key = (self.tl.view_start_frame, self.tl.pixels_per_frame,
               self.tl.total_frames(), self._clips_w(), self.width())
        if key != self._shown:
            self._shown = key
            self.update()

    def _window_x(self):
        start, vis, span = self._state()
        w = float(self.width())
        x0 = start / span * w
        x1 = min(w, (start + vis) / span * w)
        return x0, max(x1, x0 + 2 * HANDLE)

    # ---- painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pal = theme.DARK if theme.is_dark() else theme.LIGHT
        r = QRectF(self.rect()).adjusted(0.5, 4.5, -0.5, -4.5)
        p.setPen(QColor(pal["border"]))
        p.setBrush(QColor(pal["input"]))
        p.drawRoundedRect(r, 5, 5)
        x0, x1 = self._window_x()
        win = QRectF(x0, 3, x1 - x0, self.height() - 6)
        accent = QColor(pal["accent"])
        fill = QColor(accent)
        fill.setAlpha(70)
        p.setPen(accent)
        p.setBrush(fill)
        p.drawRoundedRect(win, 4, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        for hx in (win.left(), win.right() - 3):        # the two grips
            p.drawRoundedRect(QRectF(hx, win.top() + 3, 3, win.height() - 6), 1.5, 1.5)
        p.end()

    # ---- mouse
    def _where(self, x):
        x0, x1 = self._window_x()
        if abs(x - x0) <= HANDLE:
            return "left"
        if abs(x - x1) <= HANDLE:
            return "right"
        if x0 < x < x1:
            return "pan"
        return "jump"

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self._mode is None:
            w = self._where(x)
            self.setCursor(Qt.SizeHorCursor if w in ("left", "right")
                           else Qt.OpenHandCursor if w == "pan" else Qt.ArrowCursor)
            return
        self._drag(x)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        x = event.position().x()
        self._mode = self._where(x)
        start, vis, span = self._state()
        self._press_x, self._start0, self._vis0 = x, start, vis
        if self._mode == "jump":
            # click outside the window: centre it there
            f = x / float(self.width()) * span
            self._set_view(f - vis / 2.0, vis)
            self._mode = "pan"
            self._start0 = max(0.0, f - vis / 2.0)
        if self._mode == "pan":
            self.setCursor(Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, event):
        self._mode = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event):
        # fit the whole sequence
        total = max(1.0, float(self.tl.total_frames()))
        self._set_view(0.0, total)

    def _drag(self, x):
        start0, vis0 = self._start0, self._vis0
        _s, _v, span = self._state()
        per_px = span / float(self.width())
        dx = (x - self._press_x) * per_px
        min_vis = 5.0
        if self._mode == "pan":
            self._set_view(start0 + dx, vis0)
        elif self._mode == "left":
            right = start0 + vis0
            new_start = max(0.0, min(right - min_vis, start0 + dx))
            self._set_view(new_start, right - new_start)
        elif self._mode == "right":
            new_vis = max(min_vis, min(span - start0, vis0 + dx))
            self._set_view(start0, new_vis)

    def _set_view(self, start, vis):
        # show frames start .. start + vis (zoom from vis, scroll from start)
        from sequence_timeline_ruler import clamp_zoom
        tl = self.tl
        vis = max(1.0, float(vis))
        tl.pixels_per_frame = clamp_zoom(self._clips_w() / vis)
        tl.view_start_frame = int(round(max(0.0, start)))
        tl._update_clips_width()
        tl._update_status()
        tl._save_view_state()
        self.update()


class TimelineScaleBar(QWidget):

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        from global_settings import _get_global_setting
        self.tl = timeline
        self.setFixedHeight(26)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 8, 2)
        lay.setSpacing(8)
        lbl = QLabel("Track height")
        lbl.setStyleSheet("color: gray; font-size: 11px;")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(TRACK_SCALE_MIN, TRACK_SCALE_MAX)
        self.slider.setFixedWidth(90)
        self.slider.setToolTip("Track height")
        try:
            val = int(_get_global_setting(TRACK_SCALE_KEY, "") or TRACK_SCALE_DEFAULT)
        except ValueError:
            val = TRACK_SCALE_DEFAULT
        self.slider.setValue(val)
        self.slider.valueChanged.connect(self._height_changed)
        lay.addWidget(lbl)
        lay.addWidget(self.slider)
        lay.addSpacing(10)
        lay.addWidget(ZoomNavigator(timeline), 1)
        apply_track_scale(timeline, val)

    def _height_changed(self, value):
        from global_settings import _set_global_setting
        _set_global_setting(TRACK_SCALE_KEY, str(int(value)))
        apply_track_scale(self.tl, value)
