# transport.py
# The transport bar under the player (unified window): slim drawn icons for
# Home, Previous edit, Play / Pause, Next edit and End, and a timecode
# readout. It drives the front timeline's own handlers (go_home,
# go_prev_edit, _toggle_play, go_next_edit, go_end), so the old row of big
# buttons in the timeline is hidden. Also the frame-step keys. ASCII only.

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QKeySequence, QPainter, QPainterPath,
                           QShortcut)
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QSizePolicy,
                               QWidget)

import theme


def timecode(frame, fps):
    # HH:MM:SS:FF at the nominal (rounded) frame rate
    base = max(1, int(round(float(fps or 30))))
    frame = max(0, int(frame))
    ff = frame % base
    secs = frame // base
    return "%02d:%02d:%02d:%02d" % (secs // 3600, (secs // 60) % 60, secs % 60, ff)


class IconButton(QAbstractButton):
    # kind: home, prev, play, pause, next, end

    def __init__(self, kind, tip, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setToolTip(tip)
        self.setFocusPolicy(Qt.NoFocus)         # keys stay with the timeline
        self.setCursor(Qt.ArrowCursor)
        big = kind in ("play", "pause")
        self.setFixedSize(40 if big else 32, 32)
        self._hover = False

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self.update()

    def sizeHint(self):
        return QSize(self.width(), self.height())

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pal = theme.DARK if theme.is_dark() else theme.LIGHT
        fg = QColor(pal["text"])
        if self._hover or self.isDown():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal["select"] if self.isDown() else pal["hover"]))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 7, 7)
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2.0, h / 2.0
        k = self.kind

        def tri(x, size, right=True):
            path = QPainterPath()
            d = size if right else -size
            path.moveTo(QPointF(x, cy - size))
            path.lineTo(QPointF(x + d, cy))
            path.lineTo(QPointF(x, cy + size))
            path.closeSubpath()
            p.drawPath(path)

        if k == "play":
            tri(cx - 4.5, 8.0)
        elif k == "pause":
            p.drawRoundedRect(QRectF(cx - 6, cy - 7, 4, 14), 1, 1)
            p.drawRoundedRect(QRectF(cx + 2, cy - 7, 4, 14), 1, 1)
        elif k in ("prev", "home"):
            bar = QRectF(cx - 8, cy - 6.5, 2.4, 13)
            p.drawRoundedRect(bar, 1, 1)
            tri(cx + 7, 6.5, right=False)
            if k == "home":
                tri(cx + 1, 6.5, right=False)
        elif k in ("next", "end"):
            bar = QRectF(cx + 5.6, cy - 6.5, 2.4, 13)
            p.drawRoundedRect(bar, 1, 1)
            tri(cx - 7, 6.5, right=True)
            if k == "end":
                tri(cx - 1, 6.5, right=True)
        p.end()


class TimecodeLabel(QWidget):
    # HH:MM:SS:FF drawn one character per fixed cell (digits all as wide as
    # the widest digit, separators narrower), so the readout never shifts
    # while it counts, whatever the font

    def __init__(self, text="00:00:00:00", point_size=16, bold=True, dim=False,
                 parent=None):
        super().__init__(parent)
        font = QFont(self.font())
        font.setPointSizeF(float(point_size))
        if bold:
            font.setWeight(QFont.DemiBold)
        self._font = font
        self._dim = dim
        self._text = text
        from PySide6.QtGui import QFontMetricsF
        fm = QFontMetricsF(font)
        self._cell = max(fm.horizontalAdvance(c) for c in "0123456789") + 1.0
        self._sep = fm.horizontalAdvance(":") + 1.0
        self._height = fm.height() + 2
        n_sep = len(text.replace(":", "")) , text.count(":")
        self.setFixedSize(int(n_sep[0] * self._cell + n_sep[1] * self._sep + 4),
                          int(self._height))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def text(self):
        return self._text

    def setText(self, text):
        if text != self._text:
            self._text = text
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setFont(self._font)
        pal = theme.DARK if theme.is_dark() else theme.LIGHT
        p.setPen(QColor(pal["dim"] if self._dim else pal["text"]))
        x = 2.0
        for ch in self._text:
            w = self._sep if ch == ":" else self._cell
            p.drawText(QRectF(x, 0, w, self.height()), Qt.AlignCenter, ch)
            x += w
        p.end()


class TransportBar(QWidget):

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.timeline = timeline
        self.setFixedHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(2)
        self.home = IconButton("home", "Jump to the start (Home)")
        self.prev = IconButton("prev", "Previous edit (Up)")
        self.play = IconButton("play", "Play / Pause (Space)")
        self.next = IconButton("next", "Next edit (Down)")
        self.end = IconButton("end", "Jump to the end (End)")
        self.home.clicked.connect(lambda: self._do("go_home"))
        self.prev.clicked.connect(lambda: self._do("go_prev_edit"))
        self.play.clicked.connect(lambda: self._do("_toggle_play"))
        self.next.clicked.connect(lambda: self._do("go_next_edit"))
        self.end.clicked.connect(lambda: self._do("go_end"))
        lay.addStretch(1)
        for b in (self.home, self.prev, self.play, self.next, self.end):
            lay.addWidget(b)
        lay.addSpacing(16)
        self.time_label = TimecodeLabel("00:00:00:00", 16, True)
        self.total_label = TimecodeLabel("00:00:00:00", 12, False, dim=True)
        lay.addWidget(self.time_label)
        lay.addSpacing(10)
        lay.addWidget(self.total_label)
        lay.addStretch(1)
        self._shown = None
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def _do(self, name):
        try:
            getattr(self.timeline, name)()
        except Exception as e:
            print("Transport %s failed: %s" % (name, e))

    def refresh(self):
        tl = self.timeline
        try:
            frame, fps = int(tl.current_frame), float(tl.fps)
            playing = bool(tl._playing or tl._play_filling or tl._play_mixing)
            total = int(tl.total_frames())
        except Exception:
            return
        self.play.set_kind("pause" if playing else "play")
        state = (frame, fps, total)
        if state != self._shown:
            self._shown = state
            self.time_label.setText(timecode(frame, fps))
            self.total_label.setText(timecode(total, fps))


def add_step_keys(widget, timeline):
    # Frame stepping while focus is in this widget (or its children): the
    # arrow keys step one frame (Shift: ten), Up / Down jump between edits,
    # K pauses, L plays. A table or text field with focus keeps its arrows.
    def step(n):
        def go():
            try:
                timeline.set_current_frame(
                    max(0, min(int(timeline.total_frames()) - 1,
                               int(timeline.current_frame) + n)))
            except Exception as e:
                print("Step failed: %s" % e)
        return go

    def call(name):
        return lambda: getattr(timeline, name)()

    keys = (("Left", step(-1)), ("Right", step(1)),
            ("Shift+Left", step(-10)), ("Shift+Right", step(10)),
            ("Up", call("go_prev_edit")), ("Down", call("go_next_edit")),
            ("K", lambda: timeline._on_play_control("Pause")),
            ("L", lambda: timeline._on_play_control("Play")))
    for seq, fn in keys:
        sc = QShortcut(QKeySequence(seq), widget)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(fn)
