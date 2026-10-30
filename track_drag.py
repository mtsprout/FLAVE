# track_drag.py
# Grab a track's name cell and slide it up or down to reorder the tracks
# (unified window). A line shows where it will land and the track being moved
# is shaded; letting go saves the order (one undo step, "Reorder track",
# renumbering sort_order like Move > Up / Down). A plain click, a double-click
# and the right-click menu are untouched: the drag starts only after the mouse
# has moved a few pixels with the button down. ASCII only.

import sqlite3

from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget


def new_order(ids, track_id, y, centers):
    # Pure. ids: track ids top to bottom; centers: the y centre of each row
    # in the same order; y: the pointer. Returns (order, slot) with the
    # track moved to just before the first other track whose centre is below
    # y (else the end); slot is its index in the new order.
    rest = [(t, c) for t, c in zip(ids, centers) if t != track_id]
    slot = sum(1 for _t, c in rest if c < y)
    order = [t for t, _c in rest]
    order.insert(slot, track_id)
    return order, slot


class _Marker(QWidget):
    # Transparent layer over the track table: shades the dragged row and
    # draws the landing line
    def __init__(self, viewport):
        super().__init__(viewport)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.row_rect = None
        self.line_y = None
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        if self.row_rect is not None:
            p.fillRect(self.row_rect, QColor(120, 170, 255, 50))
        if self.line_y is not None:
            p.fillRect(0, self.line_y - 1, self.width(), 3, QColor(120, 180, 255))
        p.end()


class TrackDrag(QObject):

    def __init__(self, timeline):
        super().__init__(timeline)
        self.tl = timeline
        self.table = timeline.table
        self._press = None          # (pos, track id)
        self._active = False
        self._order = None
        self._marker = _Marker(self.table.viewport())
        self.table.viewport().installEventFilter(self)

    # ---- helpers
    def _rows(self):
        # [(row, track id)] top to bottom
        from sequence_timeline_droppreview import track_rows
        return [(r, tid) for r, tid, _tt in track_rows(self.tl)]

    def _track_at(self, pos):
        if self.table.columnAt(pos.x()) != 0:
            return None
        row = self.table.rowAt(pos.y())
        for r, tid in self._rows():
            if r == row:
                return tid
        return None

    def _update(self, pos):
        rows = self._rows()
        ids = [t for _r, t in rows]
        centers = [self.table.rowViewportPosition(r) + self.table.rowHeight(r) / 2.0
                   for r, _t in rows]
        self._order, slot = new_order(ids, self._press[1], pos.y(), centers)
        by_id = dict((t, r) for r, t in rows)
        # the landing line: top of the row now at slot + 1, else the bottom
        others = [t for t in self._order if t != self._press[1]]
        if slot < len(others):
            y = self.table.rowViewportPosition(by_id[others[slot]])
        else:
            last = rows[-1][0]
            y = self.table.rowViewportPosition(last) + self.table.rowHeight(last)
        drow = by_id[self._press[1]]
        self._marker.row_rect = QRect(0, self.table.rowViewportPosition(drow),
                                      self.table.viewport().width(),
                                      self.table.rowHeight(drow))
        self._marker.line_y = y
        self._marker.setGeometry(self.table.viewport().rect())
        self._marker.raise_()
        self._marker.show()
        self._marker.update()

    def _finish(self):
        order, tid = self._order, self._press[1]
        self._active = False
        self._press = None
        self._order = None
        self._marker.hide()
        self.table.viewport().unsetCursor()
        if not order:
            return
        ids = [t for _r, t in self._rows()]
        if order != ids:
            self._save(order)

    def _save(self, order):
        tl = self.tl
        project_db = tl._project_db()
        from undo import push_undo
        push_undo(project_db, "Reorder track")
        conn = sqlite3.connect(project_db)
        try:
            for n, tid in enumerate(order):
                conn.execute("UPDATE tracks SET sort_order = ? WHERE id = ?", (n, tid))
            conn.commit()
        finally:
            conn.close()
        tl._after_track_change()

    # ---- events
    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            tid = self._track_at(pos)
            self._press = (pos, tid) if tid is not None else None
            self._active = False
            return False
        if t == QEvent.MouseMove and self._press is not None:
            if not (event.buttons() & Qt.LeftButton):
                self._press = None
                return False
            pos = event.position().toPoint()
            if not self._active:
                d = pos - self._press[0]
                if abs(d.y()) < QApplication.startDragDistance():
                    return False
                self._active = True
                self.table.viewport().setCursor(Qt.ClosedHandCursor)
            self._update(pos)
            return True
        if t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._active:
                self._finish()
                return True
            self._press = None
            return False
        if t == QEvent.KeyPress and self._active and event.key() == Qt.Key_Escape:
            self._active = False
            self._press = None
            self._marker.hide()
            self.table.viewport().unsetCursor()
            return True
        return False


def install(timeline):
    drag = TrackDrag(timeline)
    timeline._track_drag = drag
    return drag
