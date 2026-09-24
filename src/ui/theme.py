"""
Theme system.

Colours are defined once as design tokens for a dark and a light theme
(Windows 11 / Fluent-inspired, original values) plus a set of accent
colours. `apply()` builds the application stylesheet from the tokens;
custom-painted widgets read the live tokens from `T` at paint time and
listen to `signals.changed` to repaint when the theme switches.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QGuiApplication, QFont


@dataclass(frozen=True)
class Tokens:
    dark: bool
    bg: str              # window background / navigation
    surface: str         # content area
    card: str
    card_hover: str
    control: str         # inputs, secondary buttons
    control_hover: str
    control_pressed: str
    border: str
    border_subtle: str
    text: str
    text_2: str
    text_3: str
    accent: str
    accent_hover: str
    accent_text: str     # text drawn on the accent colour
    accent_soft: str     # translucent accent for selections
    danger: str
    danger_soft: str
    warning: str
    warning_soft: str
    success: str
    success_soft: str
    info_soft: str
    # controller diagram
    body_top: str
    body_bottom: str
    body_outline: str
    body_detail: str
    well: str


_DARK = Tokens(
    dark=True,
    bg="#1b1b1f", surface="#202025", card="#2a2a30", card_hover="#303037",
    control="#34343b", control_hover="#3c3c44", control_pressed="#2c2c32",
    border="#40404a", border_subtle="#303038",
    text="#f3f3f5", text_2="#c8c8d0", text_3="#8e8e99",
    accent="#6ccb5f", accent_hover="#82d876", accent_text="#0b2107", accent_soft="rgba(108,203,95,0.16)",
    danger="#ff7b72", danger_soft="rgba(255,123,114,0.14)",
    warning="#f2c94c", warning_soft="rgba(242,201,76,0.14)",
    success="#6ccb5f", success_soft="rgba(108,203,95,0.14)",
    info_soft="rgba(96,165,250,0.14)",
    body_top="#3a3d44", body_bottom="#18191c", body_outline="#0b0b0d", body_detail="#26282d",
    well="#141518",
)

_LIGHT = Tokens(
    dark=False,
    bg="#eeeef1", surface="#f7f7f9", card="#ffffff", card_hover="#f6f6f8",
    control="#ffffff", control_hover="#f3f3f5", control_pressed="#ebebee",
    border="#d4d4da", border_subtle="#e6e6ea",
    text="#1b1b1f", text_2="#46464f", text_3="#6f6f7a",
    accent="#107c10", accent_hover="#0e6b0e", accent_text="#ffffff", accent_soft="rgba(16,124,16,0.12)",
    danger="#c42b1c", danger_soft="rgba(196,43,28,0.10)",
    warning="#9d5d00", warning_soft="rgba(157,93,0,0.12)",
    success="#107c10", success_soft="rgba(16,124,16,0.10)",
    info_soft="rgba(0,103,192,0.10)",
    body_top="#fbfbfc", body_bottom="#d9dade", body_outline="#9a9ba3", body_detail="#e4e5e9",
    well="#c8c9cf",
)

# name -> (label, light-theme accent, dark-theme accent)
ACCENTS = {
    "green": ("Xbox Green", "#107c10", "#6ccb5f"),
    "blue": ("Blue", "#0067c0", "#60cdff"),
    "purple": ("Purple", "#744da9", "#c3a6ff"),
    "orange": ("Orange", "#c34f00", "#ffa062"),
    "red": ("Red", "#c42b1c", "#ff99a4"),
    "teal": ("Teal", "#00797a", "#4fd8d2"),
}


def _hover(hex_color: str, dark: bool) -> str:
    c = QColor(hex_color)
    return (c.lighter(112) if dark else c.darker(112)).name()


def _soft(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def build_tokens(dark: bool, accent: str) -> Tokens:
    base = _DARK if dark else _LIGHT
    _, light_hex, dark_hex = ACCENTS.get(accent, ACCENTS["green"])
    a = dark_hex if dark else light_hex
    text_on = "#0b0b0d" if dark else "#ffffff"
    return replace(
        base,
        accent=a, accent_hover=_hover(a, dark), accent_text=text_on,
        accent_soft=_soft(a, 0.16 if dark else 0.12),
    )


class _Signals(QObject):
    changed = pyqtSignal()


signals = _Signals()
T: Tokens = build_tokens(True, "green")
_mode = "dark"
_accent = "green"


def qcolor(token_value: str, alpha: int | None = None) -> QColor:
    if token_value.startswith("rgba"):
        r, g, b, a = token_value[5:-1].split(",")
        c = QColor(int(r), int(g), int(b), int(float(a) * 255))
    else:
        c = QColor(token_value)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def system_is_dark() -> bool:
    try:
        from PyQt6.QtCore import Qt
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except Exception:
        pass
    return True


def current_mode() -> str:
    return _mode


def ui_font_family() -> str:
    from PyQt6.QtGui import QFontDatabase
    families = set(QFontDatabase.families())
    for fam in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans"):
        if fam in families:
            return fam
    return QFont().defaultFamily()


def apply(app, mode: str = "dark", accent: str = "green") -> None:
    """Build tokens for `mode` (dark | light | system) and restyle the app."""
    global T, _mode, _accent
    _mode, _accent = mode, accent
    dark = system_is_dark() if mode == "system" else mode != "light"
    T = build_tokens(dark, accent)

    pal = app.palette()
    roles = {
        QPalette.ColorRole.Window: T.bg, QPalette.ColorRole.Base: T.control,
        QPalette.ColorRole.AlternateBase: T.card, QPalette.ColorRole.Text: T.text,
        QPalette.ColorRole.WindowText: T.text, QPalette.ColorRole.Button: T.control,
        QPalette.ColorRole.ButtonText: T.text, QPalette.ColorRole.Highlight: T.accent,
        QPalette.ColorRole.HighlightedText: T.accent_text, QPalette.ColorRole.ToolTipBase: T.card,
        QPalette.ColorRole.ToolTipText: T.text, QPalette.ColorRole.PlaceholderText: T.text_3,
        QPalette.ColorRole.Link: T.accent,
    }
    for role, value in roles.items():
        pal.setColor(role, qcolor(value))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(T, _arrow_image(T.text_2)))
    signals.changed.emit()


def _arrow_image(color: str) -> str:
    """Render the combo-box chevron to a PNG (stylesheets need a file URL)."""
    try:
        import os
        from paths import local_dir
        from ui import icons
        folder = os.path.join(local_dir(), "theme")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"chevron_{color.strip('#')}.png")
        if not os.path.exists(path):
            icons.pixmap("chevron_down", color, 12).save(path)
        return path.replace("\\", "/")
    except Exception:
        return ""


def stylesheet(t: Tokens, arrow: str = "") -> str:
    font = ui_font_family()
    arrow_rule = (f"image: url('{arrow}'); width: 12px; height: 12px; margin-right: 8px;" if arrow else
                  "image: none; width: 0; height: 0;")
    return f"""
* {{
    font-family: '{font}';
    font-size: 13px;
    color: {t.text};
}}
QMainWindow, QDialog {{ background: {t.bg}; }}
QWidget#contentArea {{ background: {t.surface}; border-top-left-radius: 8px; border-left: 1px solid {t.border_subtle}; border-top: 1px solid {t.border_subtle}; }}
QWidget#page, QScrollArea#pageScroll, QWidget#pageScrollBody {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QToolTip {{ background: {t.card}; color: {t.text}; border: 1px solid {t.border}; padding: 6px 8px; border-radius: 4px; }}

/* ---- Typography ---- */
QLabel {{ background: transparent; }}
QLabel[role="pageTitle"] {{ font-size: 26px; font-weight: 600; }}
QLabel[role="title"] {{ font-size: 18px; font-weight: 600; }}
QLabel[role="subtitle"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="body2"] {{ color: {t.text_2}; }}
QLabel[role="caption"] {{ color: {t.text_3}; font-size: 12px; }}
QLabel[role="section"] {{ color: {t.text_2}; font-size: 12px; font-weight: 600; letter-spacing: 0.4px; }}
QLabel[role="appTitle"] {{ font-size: 13px; font-weight: 600; }}
QLabel[role="mono"] {{ font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 12px; color: {t.text_2}; }}
QLabel[role="value"] {{ color: {t.text_2}; }}
QLabel[role="danger"] {{ color: {t.danger}; }}
QLabel[role="warning"] {{ color: {t.warning}; }}

/* ---- Cards ---- */
QFrame[card="true"] {{ background: {t.card}; border: 1px solid {t.border_subtle}; border-radius: 8px; }}
QFrame[divider="true"] {{ background: {t.border_subtle}; border: none; min-height: 1px; max-height: 1px; }}
QFrame[vdivider="true"] {{ background: {t.border_subtle}; border: none; min-width: 1px; max-width: 1px; }}

/* ---- Buttons ---- */
QPushButton, QToolButton {{
    background: {t.control}; border: 1px solid {t.border}; border-radius: 5px;
    padding: 6px 14px; min-height: 20px; color: {t.text};
}}
QPushButton:hover, QToolButton:hover {{ background: {t.control_hover}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t.control_pressed}; color: {t.text_2}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.text_3}; background: {t.control_pressed}; border-color: {t.border_subtle}; }}
QPushButton:focus, QToolButton:focus {{ border: 1px solid {t.accent}; }}
QPushButton[kind="primary"] {{ background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[kind="primary"]:disabled {{ background: {t.control_pressed}; color: {t.text_3}; border-color: {t.border_subtle}; }}
QPushButton[kind="danger"] {{ color: {t.danger}; }}
QPushButton[kind="danger"]:hover {{ background: {t.danger_soft}; border-color: {t.danger}; }}
QPushButton[kind="subtle"], QToolButton[kind="subtle"] {{ background: transparent; border: 1px solid transparent; }}
QToolButton[kind="subtle"] {{ padding: 4px; }}
QPushButton[kind="subtle"]:hover, QToolButton[kind="subtle"]:hover {{ background: {t.control_hover}; }}
QPushButton[kind="subtle"]:focus, QToolButton[kind="subtle"]:focus {{ border: 1px solid {t.accent}; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {t.accent}; padding: 2px 0; text-align: left; }}
QPushButton[kind="link"]:hover {{ color: {t.accent_hover}; }}
QPushButton[kind="toggleOn"] {{ background: {t.accent_soft}; border: 1px solid {t.accent}; color: {t.text}; font-weight: 600; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* ---- Inputs ---- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {t.control}; border: 1px solid {t.border}; border-bottom: 1px solid {t.text_3};
    border-radius: 5px; padding: 5px 8px; selection-background-color: {t.accent}; selection-color: {t.accent_text};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ background: {t.control_hover}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border-bottom: 2px solid {t.accent}; }}
QComboBox {{ padding-right: 24px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ {arrow_rule} }}
QComboBox QAbstractItemView {{ background: {t.card}; border: 1px solid {t.border}; border-radius: 6px; padding: 4px; selection-background-color: {t.accent_soft}; selection-color: {t.text}; outline: none; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}

/* ---- Lists ---- */
QListWidget, QTreeWidget, QTableWidget {{ background: transparent; border: none; }}
QListWidget::item, QTreeWidget::item {{ padding: 6px 8px; border-radius: 5px; margin: 1px 0; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {t.control_hover}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}

/* ---- Slider ---- */
QSlider {{ min-height: 22px; background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {t.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {t.accent}; border: 4px solid {t.control}; width: 12px; height: 12px;
    margin: -8px 0; border-radius: 10px; }}
QSlider::handle:horizontal:hover {{ border-width: 3px; }}
QSlider::sub-page:horizontal:disabled, QSlider::handle:horizontal:disabled {{ background: {t.text_3}; }}

/* ---- Checkbox / radio ---- */
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; border: 1px solid {t.text_3}; background: {t.control}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 10px; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QRadioButton::indicator:checked {{ background: {t.accent}; border: 1px solid {t.accent}; }}

/* ---- Menus ---- */
QMenu {{ background: {t.card}; border: 1px solid {t.border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 4px; background: transparent; }}
QMenu::item:selected {{ background: {t.control_hover}; }}
QMenu::item:disabled {{ color: {t.text_3}; }}
QMenu::separator {{ height: 1px; background: {t.border_subtle}; margin: 4px 6px; }}
QMenu::icon {{ padding-left: 8px; }}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {t.text_3}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 3px; min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Splitter ---- */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 8px; }}

/* ---- Status bar ---- */
QStatusBar {{ background: {t.bg}; color: {t.text_3}; border-top: 1px solid {t.border_subtle}; }}
QStatusBar QLabel {{ color: {t.text_3}; font-size: 12px; padding: 0 6px; }}
QStatusBar::item {{ border: none; }}

/* ---- Tabs (segmented) ---- */
QTabBar::tab {{ background: transparent; border: none; padding: 6px 12px; color: {t.text_2}; }}
QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; }}
"""
