# theme.py
# The look of the unified window (CPU backend / macOS): soft dark and light
# palettes instead of black-on-white-text, quiet table headers, rounded
# controls, thin separators, a system-blue accent. One application
# stylesheet; it follows macOS light / dark appearance, or is forced dark by
# the dark_mode setting. global_settings.apply_dark_mode calls apply() here
# when the unified window is on. ASCII only.

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

DARK = {
    "window": "#1c1c1e", "panel": "#232326", "raised": "#2c2c30",
    "input": "#161618", "border": "#38383d", "hover": "#2e2e33",
    "select": "#2c4a7a", "text": "#e4e4e8", "dim": "#9a9aa2",
    "accent": "#4c9aff", "title": "#2a2a2e",
}
LIGHT = {
    "window": "#ececef", "panel": "#ffffff", "raised": "#f6f6f8",
    "input": "#ffffff", "border": "#d2d2d8", "hover": "#eef0f6",
    "select": "#cfe0fb", "text": "#1d1d1f", "dim": "#6e6e76",
    "accent": "#0a64d6", "title": "#e2e2e6",
}

_state = {"force_dark": False, "hooked": False}


def system_is_dark():
    # macOS dark appearance: the Qt color scheme, else the palette
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        pass
    app = QApplication.instance()
    return bool(app and app.palette().color(QPalette.Window).lightness() < 128)


def is_dark():
    return _state["force_dark"] or system_is_dark()


def stylesheet(c):
    return """
    QMainWindow, QDialog, QDockWidget, QStackedWidget { background: %(window)s; }
    QWidget { color: %(text)s; }
    QMainWindow > QWidget, QMainWindow::separator { background: %(window)s; }
    QMainWindow::separator { width: 1px; height: 1px; background: %(border)s; }

    QLabel { background: transparent; }
    QStatusBar { background: %(window)s; color: %(dim)s; border-top: 1px solid %(border)s; }
    QStatusBar::item { border: none; }

    QDockWidget { color: %(dim)s; }
    QDockWidget::title { background: %(title)s; padding: 5px 8px;
        border-bottom: 1px solid %(border)s; text-align: left; }

    QTabWidget::pane { border: none; border-top: 1px solid %(border)s; }
    QTabBar { background: %(window)s; }
    QTabBar::tab { background: transparent; color: %(dim)s; padding: 5px 14px;
        border: none; border-bottom: 2px solid transparent; }
    QTabBar::tab:selected { color: %(text)s; border-bottom: 2px solid %(accent)s; }
    QTabBar::tab:hover:!selected { color: %(text)s; }

    QMenuBar { background: %(window)s; color: %(text)s; border-bottom: 1px solid %(border)s; }
    QMenuBar::item { background: transparent; padding: 4px 10px; border-radius: 4px; }
    QMenuBar::item:selected { background: %(hover)s; }
    QMenu { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s;
        padding: 4px; }
    QMenu::item { padding: 5px 22px 5px 14px; border-radius: 4px; }
    QMenu::item:selected { background: %(accent)s; color: white; }
    QMenu::item:disabled { color: %(dim)s; }
    QMenu::separator { height: 1px; background: %(border)s; margin: 4px 8px; }

    QToolBar { background: %(window)s; border: none; border-bottom: 1px solid %(border)s;
        spacing: 2px; padding: 2px 6px; }
    QToolButton { background: transparent; color: %(text)s; border: none;
        padding: 4px 9px; border-radius: 5px; }
    QToolButton:hover { background: %(hover)s; }
    QToolButton:pressed, QToolButton:checked { background: %(select)s; }
    QToolButton::menu-indicator { image: none; }

    QPushButton { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s;
        border-radius: 6px; padding: 5px 14px; }
    QPushButton:hover { background: %(hover)s; }
    QPushButton:pressed { background: %(select)s; }
    QPushButton:disabled { color: %(dim)s; }

    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background: %(input)s; color: %(text)s; border: 1px solid %(border)s;
        border-radius: 5px; padding: 3px 6px;
        selection-background-color: %(select)s; selection-color: %(text)s; }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border: 1px solid %(accent)s; }
    QComboBox QAbstractItemView { background: %(raised)s; color: %(text)s;
        border: 1px solid %(border)s; selection-background-color: %(accent)s; }
    QCheckBox, QRadioButton { background: transparent; spacing: 7px; }

    QTableWidget, QTableView, QTreeView, QListView { background: %(panel)s;
        alternate-background-color: %(panel)s; color: %(text)s; border: none;
        gridline-color: transparent; outline: 0;
        selection-background-color: %(select)s; selection-color: %(text)s; }
    QTableWidget, QTableView { font-size: 12px; }
    QTableWidget::item, QTableView::item { padding: 1px 5px; border: none;
        border-bottom: 1px solid %(border)s; }
    QTableWidget::item:hover { background: %(hover)s; }
    QTableWidget::item:selected { background: %(select)s; color: %(text)s; }
    QHeaderView { background: %(window)s; border: none; }
    QHeaderView::section { background: %(window)s; color: %(dim)s; border: none;
        border-bottom: 1px solid %(border)s; padding: 3px 6px; font-weight: 600;
        font-size: 11px; }
    QTableCornerButton::section { background: %(window)s; border: none; }
    QAbstractScrollArea { background: %(panel)s; }
    QScrollBar:vertical { background: transparent; width: 11px; margin: 0; }
    QScrollBar:horizontal { background: transparent; height: 11px; margin: 0; }
    QScrollBar::handle:vertical { background: %(border)s; min-height: 30px;
        border-radius: 4px; margin: 2px; }
    QScrollBar::handle:horizontal { background: %(border)s; min-width: 30px;
        border-radius: 4px; margin: 2px; }
    QScrollBar::handle:hover { background: %(dim)s; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QTabBar QToolButton { color: %(dim)s; padding: 0 4px; font-size: 15px; }
    QTabBar QToolButton:hover { color: %(text)s; background: %(hover)s; }
    QSlider::groove:horizontal { height: 4px; background: %(border)s; border-radius: 2px; }
    QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
    QSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0;
        background: %(text)s; border-radius: 6px; }
    QToolTip { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s;
        padding: 3px; }
    """ % c


def apply(force_dark=None):
    # (Re)apply the font and stylesheet. force_dark: the dark_mode setting.
    app = QApplication.instance()
    if app is None:
        return
    if force_dark is not None:
        _state["force_dark"] = bool(force_dark)
    font = QFont(app.font())
    font.setStyleStrategy(QFont.PreferAntialias)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    app.setStyleSheet(stylesheet(DARK if is_dark() else LIGHT))
    if not _state["hooked"]:
        _state["hooked"] = True
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(
                lambda *_: apply())
        except Exception:
            pass
