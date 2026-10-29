# workspace.py
# One main window instead of a window per tool (CPU backend / macOS; the
# Windows CUDA build keeps its separate windows, FLAVE_UI=windows turns this
# off here too). The Project Manager is the shell:
#   left      Footage Manager over Sequence Manager (docks)
#   centre    the Sequence Player of the current timeline
#   bottom    Sequence Timelines, one tab per open sequence (dock)
#   right     Render Managers, one tab per sequence (dock, hidden until used)
# The existing windows are reused as they are: each QMainWindow becomes a
# plain child widget inside a dock (embed), and the places that opened a
# window (open_timeline, open_player_for, open_render_manager and the
# Project Manager's Windows menu) call the functions below instead. Layout
# (dock sizes and places) is remembered between runs. ASCII only.

import os

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtWidgets import (QDockWidget, QLabel, QStackedWidget,
                               QTabWidget, QWidget)

LAYOUT_KEY = "unified_layout_v1"
_WS = [None]


def enabled():
    # The unified window is used where the CPU backend is (see cpu_compositor)
    if os.environ.get("FLAVE_UI", "").lower() == "windows":
        return False
    from cpu_compositor import use_cpu_backend
    return use_cpu_backend()


def get():
    # The installed Workspace, or None in separate-windows mode
    return _WS[0]


def install(project_manager):
    _WS[0] = Workspace(project_manager)
    return _WS[0]


def embed(win):
    # A top-level QMainWindow becomes a plain widget that a dock / tab can
    # hold. Its menu bar stays inside it (not the application's native one).
    win.setWindowFlags(Qt.Widget)
    try:
        win.menuBar().setNativeMenuBar(False)
    except Exception:
        pass
    win._ws_embedded = True
    # The dock layout owns the size and place: a window's own geometry
    # memory (settings keys the separate-windows mode reads) stays as it was
    win._save_geometry = lambda *a, **k: None
    return win


def _placeholder(text):
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet("color: gray;")
    return label


class Workspace(object):

    def __init__(self, pm):
        self.pm = pm
        self.panels = {}            # sequence id -> PlayerPanel
        pm.setDockNestingEnabled(True)
        # The bottom dock runs the full width under the left column
        pm.setCorner(Qt.BottomLeftCorner, Qt.BottomDockWidgetArea)
        pm.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)

        # centre: the player of the current timeline, else the old status
        # label (project path / "No project open")
        self.stack = QStackedWidget()
        status = pm.takeCentralWidget()
        self.stack.addWidget(status)
        pm.setCentralWidget(self.stack)

        self.footage_dock = self._dock("footage", "Footage", Qt.LeftDockWidgetArea,
                                       _placeholder("No project open"))
        self.sequence_dock = self._dock("sequences", "Sequences",
                                        Qt.LeftDockWidgetArea,
                                        _placeholder("No project open"))
        pm.splitDockWidget(self.footage_dock, self.sequence_dock, Qt.Vertical)

        self.timeline_tabs = QTabWidget()
        self.timeline_tabs.setTabsClosable(True)
        self.timeline_tabs.setDocumentMode(True)
        self.timeline_tabs.tabCloseRequested.connect(self._close_timeline_tab)
        self.timeline_tabs.currentChanged.connect(self._timeline_tab_changed)
        self.timeline_dock = self._dock("timeline", "Timeline",
                                        Qt.BottomDockWidgetArea,
                                        self.timeline_tabs)

        self.render_tabs = QTabWidget()
        self.render_tabs.setTabsClosable(True)
        self.render_tabs.setDocumentMode(True)
        self.render_tabs.tabCloseRequested.connect(self._close_render_tab)
        self.render_dock = self._dock("render", "Render", Qt.RightDockWidgetArea,
                                      self.render_tabs)
        self.render_dock.hide()

        pm.resizeDocks([self.footage_dock], [440], Qt.Horizontal)
        pm.resizeDocks([self.timeline_dock], [380], Qt.Vertical)
        self._default_state = pm.saveState()
        self._restore_layout()

    def _dock(self, name, title, area, widget):
        dock = QDockWidget(title, self.pm)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.pm.addDockWidget(area, dock)
        return dock

    # ---- layout memory
    def _restore_layout(self):
        from global_settings import _get_global_setting
        raw = _get_global_setting(LAYOUT_KEY, "")
        if raw:
            try:
                self.pm.restoreState(QByteArray.fromBase64(raw.encode("ascii")))
            except Exception:
                pass
        self.render_dock.hide()         # opened by the Render menu only

    def save_layout(self):
        from global_settings import _set_global_setting
        try:
            raw = bytes(self.pm.saveState().toBase64()).decode("ascii")
            _set_global_setting(LAYOUT_KEY, raw)
        except Exception as e:
            print("Layout not saved: %s" % e)

    def reset_layout(self):
        self.pm.restoreState(self._default_state)
        self.render_dock.hide()

    # ---- footage and sequence managers
    def _set_panel(self, dock, win):
        old = dock.widget()
        embed(win)
        dock.setWidget(win)
        win.show()
        dock.show()
        dock.raise_()
        if old is not None and old is not win:
            old.deleteLater()

    def open_footage(self, win):
        self._set_panel(self.footage_dock, win)

    def open_sequences(self, win):
        self._set_panel(self.sequence_dock, win)

    def show_dock(self, dock):
        dock.show()
        dock.raise_()

    # ---- timelines (tabs), each with its player in the centre
    def open_timeline(self, sequence_id):
        import sequence_timeline as st
        sid = int(sequence_id)
        win = st._open_windows.get(sid)
        if win is not None and getattr(win, "_ws_embedded", False):
            self.timeline_tabs.setCurrentWidget(win)
            self.show_dock(self.timeline_dock)
            return win
        win = st.SequenceTimeline(self.pm, sid)
        win._geometry_ready = False         # the layout remembers the sizes
        embed(win)
        st._open_windows[sid] = win
        from sequence_timeline_sql import _load_sequence_name
        name = _load_sequence_name(sid) or "Sequence %d" % sid
        self.timeline_tabs.addTab(win, "%s #%d" % (name, sid))
        self.timeline_tabs.setCurrentWidget(win)
        win.show()
        self.show_dock(self.timeline_dock)
        self.open_player(win)
        return win

    def _timeline_of(self, index):
        w = self.timeline_tabs.widget(index)
        return w if w is not None and hasattr(w, "sequence_id") else None

    def _timeline_tab_changed(self, index):
        tl = self._timeline_of(index)
        panel = self.panels.get(int(tl.sequence_id)) if tl is not None else None
        self.stack.setCurrentWidget(panel if panel is not None
                                    else self.stack.widget(0))
        if tl is not None:
            # The preview worker follows the tab in front (a window used to
            # do this when it was activated)
            try:
                tl._retarget_preview(force=True)
            except Exception as e:
                print("Preview retarget failed: %s" % e)

    def retitle(self, sequence_id, name):
        # A sequence was renamed: its tab follows
        for i in range(self.timeline_tabs.count()):
            tl = self._timeline_of(i)
            if tl is not None and int(tl.sequence_id) == int(sequence_id):
                self.timeline_tabs.setTabText(i, "%s #%d" % (name, int(sequence_id)))

    def _close_timeline_tab(self, index):
        tl = self._timeline_of(index)
        if tl is None:
            return
        sid = int(tl.sequence_id)
        try:
            tl.close()                  # closeEvent: saves state, closes player
        except RuntimeError:
            pass
        self.timeline_tabs.removeTab(self.timeline_tabs.indexOf(tl))
        tl.deleteLater()
        panel = self.panels.pop(sid, None)
        if panel is not None:
            self.stack.removeWidget(panel)
            panel.deleteLater()
        self._timeline_tab_changed(self.timeline_tabs.currentIndex())

    # ---- player
    def open_player(self, timeline):
        # The timeline's player (made once; a new logic object when the
        # sequence size changed and the old one was closed)
        from sequence_player_cpu import PlayerPanel, SequencePlayerEmbedded
        import sequence_player as sp
        sid = int(timeline.sequence_id)
        player = getattr(timeline, "_player", None)
        if player is not None and not player.closed:
            return player
        panel = self.panels.get(sid)
        if panel is None:
            panel = PlayerPanel()
            self.panels[sid] = panel
            self.stack.addWidget(panel)
        player = SequencePlayerEmbedded(timeline, panel)
        timeline._player = player
        panel.set_logic(player)
        sp._add_open_player_id(sid)
        if self.timeline_tabs.currentWidget() is timeline:
            self.stack.setCurrentWidget(panel)
        return player

    # ---- render managers
    def open_render(self, timeline):
        import render_manager as rm
        sid = int(timeline.sequence_id)
        win = rm._open_windows.get(sid)
        if win is None:
            if not rm._window_class:
                rm._window_class.append(rm._make_window_class())
            win = rm._window_class[0](timeline)
            rm._open_windows[sid] = win
            embed(win)
            self.render_tabs.addTab(win, "Render #%d" % sid)
            win.show()
        else:
            win.refresh_output_path()
        self.render_tabs.setCurrentWidget(win)
        self.show_dock(self.render_dock)
        return win

    def _close_render_tab(self, index):
        win = self.render_tabs.widget(index)
        if win is None:
            return
        try:
            win.close()                 # cancels a running render
        except RuntimeError:
            pass
        self.render_tabs.removeTab(self.render_tabs.indexOf(win))
        win.deleteLater()
        if self.render_tabs.count() == 0:
            self.render_dock.hide()

    # ---- project closed: every project panel goes
    def project_closed(self):
        for i in range(self.render_tabs.count() - 1, -1, -1):
            self._close_render_tab(i)
        for i in range(self.timeline_tabs.count() - 1, -1, -1):
            self._close_timeline_tab(i)
        for dock in (self.footage_dock, self.sequence_dock):
            old = dock.widget()
            dock.setWidget(_placeholder("No project open"))
            if old is not None:
                old.deleteLater()
        self.stack.setCurrentIndex(0)
