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
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (QDockWidget, QLabel, QMenu, QStackedWidget,
                               QTabBar, QTabWidget, QToolButton, QWidget)

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
        # its menus live in the main menu bar (Workspace.sync_menus)
        win.menuBar().hide()
    except Exception:
        pass
    win._ws_embedded = True
    # The dock layout owns the size and place: a window's own geometry
    # memory (settings keys the separate-windows mode reads) stays as it was
    win._save_geometry = lambda *a, **k: None
    return win


def slim_title(dock, text):
    # A thin small-caps title instead of the stock bar with its buttons
    # (text None: no title at all, the tab bar under it is the header)
    if text is None:
        bar = QWidget()
        bar.setFixedHeight(0)
        dock.setTitleBarWidget(bar)
        return
    label = QLabel(text.upper())
    font = QFont(label.font())
    font.setPointSizeF(max(8.0, font.pointSizeF() - 2.0))
    font.setWeight(QFont.DemiBold)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    label.setFont(font)
    label.setStyleSheet("color: gray; padding: 5px 10px 3px 10px;")
    dock.setTitleBarWidget(label)


def manage_columns(table, key, default_hidden):
    # Columns a panel hides by default; a right-click on the header turns
    # any of them on or off, and the choice is remembered (setting key)
    from PySide6.QtWidgets import QMenu as _Menu
    from global_settings import _get_global_setting, _set_global_setting
    saved = _get_global_setting(key, None)
    raw = default_hidden if saved in (None, "") else saved
    hidden = set(int(v) for v in str(raw).split(",") if v.strip().isdigit())
    for col in range(table.columnCount()):
        table.setColumnHidden(col, col in hidden)
    header = table.horizontalHeader()
    header.setContextMenuPolicy(Qt.CustomContextMenu)

    def menu(pos):
        m = _Menu(table)
        for col in range(table.columnCount()):
            item = table.horizontalHeaderItem(col)
            if item is None or not item.text():
                continue
            act = m.addAction(item.text())
            act.setCheckable(True)
            act.setChecked(not table.isColumnHidden(col))
            act.setData(col)
        chosen = m.exec(header.mapToGlobal(pos))
        if chosen is None:
            return
        table.setColumnHidden(int(chosen.data()), not chosen.isChecked())
        now = [str(c) for c in range(table.columnCount()) if table.isColumnHidden(c)]
        _set_global_setting(key, ",".join(now) or "-")
    header.customContextMenuRequested.connect(menu)


def _placeholder(text):
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet("color: gray;")
    return label


class Workspace(object):

    def __init__(self, pm):
        self.pm = pm
        self.panels = {}            # sequence id -> PlayerPanel
        self.pages = {}             # sequence id -> panel + transport bar
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
        slim_title(self.footage_dock, "Footage")
        slim_title(self.sequence_dock, "Sequences")
        pm.splitDockWidget(self.footage_dock, self.sequence_dock, Qt.Vertical)

        self.timeline_tabs = QTabWidget()
        self.timeline_tabs.setDocumentMode(True)
        self.timeline_tabs.tabCloseRequested.connect(self._close_timeline_tab)
        self.timeline_tabs.currentChanged.connect(self._timeline_tab_changed)
        self.timeline_dock = self._dock("timeline", "Timeline",
                                        Qt.BottomDockWidgetArea,
                                        self.timeline_tabs)

        self.render_tabs = QTabWidget()
        self.render_tabs.setDocumentMode(True)
        self.render_tabs.tabCloseRequested.connect(self._close_render_tab)
        self.render_dock = self._dock("render", "Render", Qt.RightDockWidgetArea,
                                      self.render_tabs)
        self.render_dock.hide()
        slim_title(self.timeline_dock, None)
        slim_title(self.render_dock, None)

        self._build_menus()
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

    # ---- one menu bar: the panels' menus live in the main (native) one
    def _build_menus(self):
        pm = self.pm
        bar = pm.menuBar()
        self._ctx = []              # actions added for the front timeline
        settings = [a for a in bar.actions() if a.text() == "Settings"]
        self._anchor = settings[0] if settings else None
        # File: Import / Render above Exit
        self.import_action = QAction("Import Footage...", pm)
        self.import_action.triggered.connect(self._import_footage)
        self.render_action = QAction("Render...", pm)
        self.render_action.triggered.connect(self._render_front)
        before = getattr(pm, "exit_action", None)
        pm.file_menu.insertAction(before, self.import_action)
        pm.file_menu.insertAction(before, self.render_action)
        pm.file_menu.insertSeparator(before)
        # Edit (Undo / Redo, then the front timeline's), Footage, Sequence
        self.edit_menu = QMenu("Edit", pm)
        self.footage_menu = QMenu("Footage", pm)
        self.sequence_menu = QMenu("Sequence", pm)
        for m in (self.edit_menu, self.footage_menu, self.sequence_menu):
            bar.insertMenu(self._anchor, m)
        self.sync_menus()

    def _front_timeline(self):
        tl = self.timeline_tabs.currentWidget()
        return tl if tl is not None and hasattr(tl, "sequence_id") else None

    def _import_footage(self):
        win = getattr(self.pm, "footage_window", None)
        if win is not None:
            win._import_footage()

    def _render_front(self):
        tl = self._front_timeline()
        if tl is not None:
            tl.open_render_manager()

    @staticmethod
    def _copy_actions(menu, source_menubar, skip=()):
        # Every item of a panel's own menu bar, as items of menu
        menu.clear()
        if source_menubar is None:
            return
        for a in source_menubar.actions():
            if a.text() in skip:
                continue
            if a.isSeparator():
                menu.addSeparator()
            else:
                menu.addAction(a)

    def sync_menus(self):
        # Rebuild the menus that follow the panels / the front timeline
        pm = self.pm
        bar = pm.menuBar()
        for a in self._ctx:
            bar.removeAction(a)
        self._ctx = []
        tl = self._front_timeline()
        self.render_action.setEnabled(tl is not None)
        footage = getattr(pm, "footage_window", None)
        has_footage = footage is not None and pm._alive(footage)
        self.import_action.setEnabled(has_footage)
        self.footage_menu.menuAction().setVisible(has_footage)
        if has_footage:
            self._copy_actions(self.footage_menu, footage.menuBar())
        seqs = getattr(pm, "sequence_window", None)
        has_seqs = seqs is not None and pm._alive(seqs)
        self.sequence_menu.menuAction().setVisible(has_seqs)
        if has_seqs:
            self._copy_actions(self.sequence_menu, seqs.menuBar())
        # Edit: Undo / Redo always, the timeline's clip editing with one
        self.edit_menu.clear()
        self.edit_menu.addAction(pm.undo_action)
        self.edit_menu.addAction(pm.redo_action)
        if tl is not None:
            self.edit_menu.addSeparator()
            for a in tl.menuBar().actions():
                if a.text() == "Edit" and a.menu() is not None:
                    self.edit_menu.addActions(a.menu().actions())
            # Tracks and Preview of the front timeline
            for a in tl.menuBar().actions():
                if a.menu() is not None and a.text() in ("Tracks", "Preview"):
                    bar.insertAction(self._anchor, a)
                    self._ctx.append(a)

    def _tab_close_button(self, tabs, widget):
        # A quiet close button (the stock one is a red icon)
        btn = QToolButton()
        btn.setText("\u00d7")
        btn.setAutoRaise(True)
        btn.setCursor(Qt.ArrowCursor)
        btn.setToolTip("Close")
        btn.clicked.connect(
            lambda: tabs.tabCloseRequested.emit(tabs.indexOf(widget)))
        tabs.tabBar().setTabButton(tabs.indexOf(widget), QTabBar.RightSide, btn)

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
        self.sync_menus()

    def open_footage(self, win):
        self._set_panel(self.footage_dock, win)
        # the proxy / size / codec / pixel-aspect columns start hidden (header
        # right-click turns them on); double-click adds the clip
        manage_columns(win.table, "footage_cols_hidden", "2,3,7,8,9,10")
        win.table.cellDoubleClicked.connect(
            lambda row, col, w=win: self._footage_double_clicked(w, row))

    def open_sequences(self, win):
        self._set_panel(self.sequence_dock, win)
        from PySide6.QtWidgets import QTableWidget
        # double-click opens the timeline (Enter / F2 renames)
        win.table.setEditTriggers(QTableWidget.EditKeyPressed)
        manage_columns(win.table, "sequence_cols_hidden", "6,8,9")
        win.table.cellDoubleClicked.connect(
            lambda row, col, w=win: self._sequence_double_clicked(w, row))

    def _sequence_double_clicked(self, win, row):
        sid = win.table._row_id(row)
        if sid is not None:
            self.open_timeline(int(sid))

    def _footage_double_clicked(self, win, row):
        item = win.table.item(row, 1)
        fid = item.data(Qt.UserRole) if item is not None else None
        if fid is not None:
            self.add_footage_at_playhead(int(fid))

    def add_footage_at_playhead(self, footage_id):
        # Double-click on footage: a clip at the playhead on the first track
        # of its kind that is free there, else on new track(s)
        import sqlite3
        from sequence_timeline_sql import _footage_track_type
        tl = self._front_timeline()
        if tl is None:
            self.pm.status_bar.showMessage(
                "Open a timeline first (double-click a sequence)", 4000)
            return
        conn = sqlite3.connect(tl._project_db())
        try:
            cur = conn.cursor()
            cur.execute("SELECT filename, original_path FROM footage WHERE id = ?",
                        (int(footage_id),))
            frow = cur.fetchone()
            kind = _footage_track_type(frow) if frow else None
            if kind is None:
                self.pm.status_bar.showMessage(
                    "That footage is not an image, video or audio file", 4000)
                return
            frame = int(tl.current_frame)
            tl._jump_to_frame(frame)            # the playhead is in view
            x = ((frame - tl.view_start_frame) * tl.pixels_per_frame
                 + tl.pixels_per_frame * 0.5)
            rows = []
            for r in range(tl.table.rowCount()):
                it = tl.table.item(r, 0)
                if it is not None and (it.data(Qt.UserRole + 4) or "").lower() == kind:
                    if not tl._range_overlaps(cur, it.data(Qt.UserRole), frame, 1):
                        rows.append(r)
        finally:
            conn.close()
        for r in rows + [-1]:
            if tl.drop_footage(int(footage_id), r, x):
                return

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
        # compact track labels: a narrower Name column, the Type column off
        # (the clips themselves show video / audio / image)
        win.ruler.resizeSection(0, min(win.ruler.sectionSize(0), 120))
        win.ruler.setSectionHidden(1, True)
        st._open_windows[sid] = win
        from sequence_timeline_sql import _load_sequence_name
        name = _load_sequence_name(sid) or "Sequence %d" % sid
        self.timeline_tabs.addTab(win, "%s #%d" % (name, sid))
        self._tab_close_button(self.timeline_tabs, win)
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
        page = self.pages.get(int(tl.sequence_id)) if tl is not None else None
        self.stack.setCurrentWidget(page if page is not None
                                    else self.stack.widget(0))
        self.sync_menus()
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
        self.panels.pop(sid, None)
        page = self.pages.pop(sid, None)
        if page is not None:
            self.stack.removeWidget(page)
            page.deleteLater()
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
            # the picture with a slim transport bar under it; the old row of
            # big buttons in the timeline goes away
            from PySide6.QtWidgets import QVBoxLayout
            from transport import TransportBar, add_step_keys
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            lay.addWidget(panel, 1)
            lay.addWidget(TransportBar(timeline))
            add_step_keys(page, timeline)
            add_step_keys(timeline, timeline)
            self.pages[sid] = page
            self.stack.addWidget(page)
            for btn in getattr(timeline, "_control_buttons", {}).values():
                btn.hide()
        player = SequencePlayerEmbedded(timeline, panel)
        timeline._player = player
        panel.set_logic(player)
        sp._add_open_player_id(sid)
        if self.timeline_tabs.currentWidget() is timeline:
            self.stack.setCurrentWidget(self.pages[sid])
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
            self._tab_close_button(self.render_tabs, win)
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
        self.sync_menus()
