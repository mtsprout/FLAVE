# timeline_tools.py
# The timeline's tool bar (unified window): one button per tool, above the
# tracks. Today: Select (V) and Razor (C, the slice tool). A tool is a
# Tool record, so more can be added to TOOLS later (a button appears, with
# its key hint in the tooltip). The keys themselves are the timeline's own
# shortcuts; the buttons follow the mode the keys set (tl._tool_listeners).
# ASCII only.

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QWidget

import theme


class Tool(object):
    # id: also the icon name; tip: tooltip; activate(tl): make it the tool;
    # active(tl): True while it is the tool
    def __init__(self, tool_id, tip, activate, active):
        self.id = tool_id
        self.tip = tip
        self.activate = activate
        self.active = active


def _select_on(tl):
    import sequence_timeline_slice as sl
    sl.exit_slice_mode(tl)


def _razor_on(tl):
    import sequence_timeline_slice as sl
    sl.enter_slice_mode(tl)


def _razor_active(tl):
    return bool(getattr(tl, "_slice_mode", False))


TOOLS = (
    Tool("select", "Select (V)", _select_on, lambda tl: not _razor_active(tl)),
    Tool("razor", "Razor: click a clip to cut it (C). Stays on until you pick Select, "
                  "press V or Esc, or right-click", _razor_on, _razor_active),
)


class ToolButton(QAbstractButton):

    def __init__(self, tool, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.setCheckable(True)
        self.setToolTip(tool.tip)
        self.setFocusPolicy(Qt.NoFocus)         # keys stay with the timeline
        self.setFixedSize(28, 24)
        self._hover = False

    def sizeHint(self):
        return QSize(28, 24)

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
        if self.isChecked() or self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal["select"] if self.isChecked() else pal["hover"]))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)
        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2.0, h / 2.0
        if self.tool.id == "select":
            # an arrow pointer
            poly = QPolygonF([QPointF(cx - 4, cy - 7), QPointF(cx - 4, cy + 5),
                              QPointF(cx - 1, cy + 2), QPointF(cx + 1.5, cy + 7.5),
                              QPointF(cx + 3.5, cy + 6.5), QPointF(cx + 1.2, cy + 1.5),
                              QPointF(cx + 5, cy + 1.5)])
            p.setPen(Qt.NoPen)
            p.setBrush(fg)
            p.drawPolygon(poly)
        elif self.tool.id == "razor":
            # a blade with a cut line through it
            path = QPainterPath()
            path.moveTo(QPointF(cx - 7, cy + 4))
            path.lineTo(QPointF(cx + 6, cy - 5))
            path.lineTo(QPointF(cx + 7, cy - 2))
            path.lineTo(QPointF(cx - 4, cy + 6))
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(fg)
            p.drawPath(path)
            pen = QPen(QColor(pal["accent"]))
            pen.setWidthF(1.4)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(cx + 1, cy - 9), QPointF(cx + 1, cy + 9))
        p.end()


class ToolBar(QWidget):

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.tl = timeline
        self.setFixedHeight(30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(4)
        self.buttons = []
        for tool in TOOLS:
            btn = ToolButton(tool)
            btn.clicked.connect(lambda checked=False, t=tool: self._pick(t))
            lay.addWidget(btn)
            self.buttons.append(btn)
        lay.addStretch(1)
        timeline.__dict__.setdefault("_tool_listeners", []).append(self.sync)
        self.sync()

    def _pick(self, tool):
        tool.activate(self.tl)
        self.sync()

    def sync(self):
        for btn in self.buttons:
            btn.setChecked(bool(btn.tool.active(self.tl)))
