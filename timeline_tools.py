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


def _make(name):
    def activate(tl):
        import edit_tools
        edit_tools.set_tool(tl, name)
    return activate


def _is_current(name):
    def active(tl):
        import edit_tools
        return edit_tools.current(tl) == name and not getattr(tl, "_slice_mode", False)
    return active


def _razor_active(tl):
    return bool(getattr(tl, "_slice_mode", False))


TOOLS = (
    Tool("select", "Select (V)", _make("select"), _is_current("select")),
    Tool("razor", "Razor: click a clip to cut it (C). Stays on until you pick Select, "
                  "press V or Esc, or right-click", _make("razor"), _razor_active),
    Tool("ripple", "Ripple edit (B): drag a clip edge; what follows moves with it",
         _make("ripple"), _is_current("ripple")),
    Tool("roll", "Roll edit (N): drag the cut between two clips",
         _make("roll"), _is_current("roll")),
    Tool("slip", "Slip (Y): drag inside a clip to change what it shows",
         _make("slip"), _is_current("slip")),
)


def install_keys(tl):
    # B / N / Y, like the timeline's own C / V (window shortcuts; a text
    # field or item editor takes plain letters first)
    from PySide6.QtGui import QKeySequence, QShortcut
    import edit_tools
    for key, name in edit_tools.KEYS:
        QShortcut(QKeySequence(key), tl,
                  activated=lambda n=name: edit_tools.key_pressed(tl, n))


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
        elif self.tool.id in ("ripple", "roll", "slip"):
            p.setPen(Qt.NoPen)
            p.setBrush(fg)
            accent = QColor(pal["accent"])
            if self.tool.id == "ripple":
                # a bracket with a long arrow after it
                p.drawRoundedRect(QRectF(cx - 8, cy - 6, 2.4, 12), 1, 1)
                p.drawRect(QRectF(cx - 6, cy - 0.8, 9, 1.6))
                p.drawPolygon(QPolygonF([QPointF(cx + 3, cy - 4), QPointF(cx + 8, cy),
                                         QPointF(cx + 3, cy + 4)]))
            elif self.tool.id == "roll":
                # two brackets meeting at a cut, an arrow each way
                p.drawRoundedRect(QRectF(cx - 1.2, cy - 6, 2.4, 12), 1, 1)
                p.drawPolygon(QPolygonF([QPointF(cx - 3, cy - 4), QPointF(cx - 8, cy),
                                         QPointF(cx - 3, cy + 4)]))
                p.drawPolygon(QPolygonF([QPointF(cx + 3, cy - 4), QPointF(cx + 8, cy),
                                         QPointF(cx + 3, cy + 4)]))
            else:
                # a clip with arrows inside it
                p.setBrush(Qt.NoBrush)
                pen = QPen(fg)
                pen.setWidthF(1.3)
                p.setPen(pen)
                p.drawRoundedRect(QRectF(cx - 9, cy - 6, 18, 12), 2, 2)
                p.setPen(Qt.NoPen)
                p.setBrush(accent)
                p.drawPolygon(QPolygonF([QPointF(cx - 2, cy - 3), QPointF(cx - 6, cy),
                                         QPointF(cx - 2, cy + 3)]))
                p.drawPolygon(QPolygonF([QPointF(cx + 2, cy - 3), QPointF(cx + 6, cy),
                                         QPointF(cx + 2, cy + 3)]))
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
