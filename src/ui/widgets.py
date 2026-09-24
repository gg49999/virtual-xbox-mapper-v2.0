"""
Reusable, theme-aware widgets used across every page: cards, setting
rows, toggle switches, sliders with value read-outs, key chips, a hotkey
recorder, status pills, in-app notifications, and live meters.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QSize, QTimer, pyqtSignal, pyqtProperty, QPropertyAnimation,
    QEasingCurve, QEvent,
)
from PyQt6.QtGui import QPainter, QPen, QFont, QFontMetrics, QPainterPath, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QAbstractButton, QSlider,
    QPushButton, QSizePolicy, QGraphicsOpacityEffect, QToolButton, QGridLayout,
)

import keycodes
from ui import theme, icons
from ui.qt_keys import code_from_key_event


def set_role(label: QLabel, role: str) -> QLabel:
    label.setProperty("role", role)
    return label


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def button(text: str = "", kind: str | None = None, icon: str | None = None,
           tooltip: str = "", on_click: Callable | None = None) -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setProperty("kind", kind)
    if icon:
        btn.setProperty("iconName", icon)
        _refresh_button_icon(btn)
        theme.signals.changed.connect(lambda b=btn: _refresh_button_icon(b))
    if tooltip:
        btn.setToolTip(tooltip)
    if on_click:
        btn.clicked.connect(lambda *_: on_click())
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def _refresh_button_icon(btn: QAbstractButton) -> None:
    try:
        name = btn.property("iconName")
    except RuntimeError:
        return
    if not name:
        return
    kind = btn.property("kind")
    color = theme.T.accent_text if kind == "primary" else (theme.T.danger if kind == "danger" else theme.T.text)
    btn.setIcon(icons.icon(name, color, 16))
    btn.setIconSize(QSize(16, 16))


def icon_button(icon: str, tooltip: str, on_click: Callable | None = None, size: int = 32) -> QToolButton:
    btn = QToolButton()
    btn.setProperty("kind", "subtle")
    btn.setProperty("iconName", icon)
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    btn.setFixedSize(size, size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    _refresh_button_icon(btn)
    theme.signals.changed.connect(lambda b=btn: _refresh_button_icon(b))
    if on_click:
        btn.clicked.connect(lambda *_: on_click())
    return btn


def divider(vertical: bool = False) -> QFrame:
    f = QFrame()
    f.setProperty("vdivider" if vertical else "divider", True)
    return f


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class Card(QFrame):
    """Rounded surface with an optional header (icon, title, subtitle, actions)."""

    def __init__(self, title: str = "", subtitle: str = "", icon: str | None = None, parent=None,
                 padding: int = 16):
        super().__init__(parent)
        self.setProperty("card", True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(12)
        self.header_actions: Optional[QHBoxLayout] = None
        if title:
            head = QHBoxLayout()
            head.setSpacing(10)
            if icon:
                ic = IconLabel(icon, 20, accent=True)
                head.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
            text_box = QVBoxLayout()
            text_box.setSpacing(2)
            self.title_label = label(title, "subtitle")
            text_box.addWidget(self.title_label)
            if subtitle:
                self.subtitle_label = label(subtitle, "caption", wrap=True)
                text_box.addWidget(self.subtitle_label)
            head.addLayout(text_box, 1)
            self.header_actions = QHBoxLayout()
            self.header_actions.setSpacing(6)
            head.addLayout(self.header_actions)
            self._layout.addLayout(head)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._layout.addWidget(widget, stretch)
        return widget


class IconLabel(QWidget):
    def __init__(self, name: str, size: int = 20, accent: bool = False, color_token: str | None = None, parent=None):
        super().__init__(parent)
        self._name, self._size, self._accent, self._token = name, size, accent, color_token
        self.setFixedSize(size, size)
        theme.signals.changed.connect(self.update)

    def set_icon(self, name: str, color_token: str | None = None) -> None:
        self._name = name
        self._token = color_token
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        color = theme.T.accent if self._accent else getattr(theme.T, self._token or "text")
        icons.paint(p, self._name, QRectF(0, 0, self._size, self._size), theme.qcolor(color))
        p.end()


class SettingRow(QWidget):
    """Title + description on the left, a control on the right."""

    def __init__(self, title: str, description: str = "", control: QWidget | None = None,
                 icon: str | None = None, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 4, 0, 4)
        h.setSpacing(12)
        if icon:
            h.addWidget(IconLabel(icon, 18, color_token="text_2"), 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = label(title)
        text.addWidget(self.title)
        if description:
            self.description = label(description, "caption", wrap=True)
            text.addWidget(self.description)
        h.addLayout(text, 1)
        if control is not None:
            h.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.control = control
        if control is not None:
            control.setAccessibleName(title)
            if description:
                control.setAccessibleDescription(description)


class ToggleSwitch(QAbstractButton):
    """Fluent-style on/off switch."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        theme.signals.changed.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(44, 22)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = pyqtProperty(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def set_checked_silent(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._pos = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, 40, 20)
        on = self.isChecked()
        enabled = self.isEnabled()
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(t.accent if enabled else t.text_3))
        else:
            p.setPen(QPen(theme.qcolor(t.text_2 if enabled else t.text_3), 1))
            p.setBrush(theme.qcolor(t.control))
        p.drawRoundedRect(r, 10, 10)
        d = 12 if not self.underMouse() else 14
        cx = r.left() + 10 + self._pos * 20
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(t.accent_text if on else t.text_2))
        p.drawEllipse(QPointF(cx, r.center().y()), d / 2, d / 2)
        if self.hasFocus():
            p.setPen(QPen(theme.qcolor(t.text), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 11, 11)
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class LabeledToggle(QWidget):
    """Toggle switch with an On/Off caption to its left (Windows Settings style)."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False, on_text: str = "On", off_text: str = "Off", parent=None):
        super().__init__(parent)
        self._on, self._off = on_text, off_text
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.caption = label(on_text if checked else off_text, "body2")
        self.switch = ToggleSwitch(checked)
        h.addWidget(self.caption)
        h.addWidget(self.switch)
        self.switch.toggled.connect(self._changed)

    def _changed(self, on: bool) -> None:
        self.caption.setText(self._on if on else self._off)
        self.toggled.emit(on)

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def setChecked(self, on: bool, silent: bool = True) -> None:
        if silent:
            self.switch.set_checked_silent(on)
            self.caption.setText(self._on if on else self._off)
        else:
            self.switch.setChecked(on)

    def setAccessibleName(self, name: str) -> None:
        self.switch.setAccessibleName(name)


class SliderRow(QWidget):
    """Title/description, a slider, and a formatted value read-out.
    Emits `valueChanged(float)` in real units."""
    valueChanged = pyqtSignal(float)

    def __init__(self, title: str, lo: float, hi: float, value: float, step: float = 0.01,
                 fmt: Callable[[float], str] | str = "{:.2f}", description: str = "", parent=None):
        super().__init__(parent)
        self._lo, self._hi, self._step = lo, hi, step
        self._fmt = fmt if callable(fmt) else (lambda v, f=fmt: f.format(v))
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = label(title)
        head.addWidget(self.title, 1)
        self.value_label = label("", "value")
        self.value_label.setMinimumWidth(56)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.value_label)
        v.addLayout(head)
        if description:
            v.addWidget(label(description, "caption", wrap=True))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max(1, round((hi - lo) / step)))
        self.slider.setSingleStep(1)
        self.slider.setPageStep(max(1, round(self.slider.maximum() / 10)))
        self.slider.setAccessibleName(title)
        self.slider.valueChanged.connect(self._on_slider)
        v.addWidget(self.slider)
        self.set_value(value)

    def value(self) -> float:
        return round(self._lo + self.slider.value() * self._step, 6)

    def set_value(self, value: float) -> None:
        value = max(self._lo, min(self._hi, float(value)))
        self.slider.blockSignals(True)
        self.slider.setValue(round((value - self._lo) / self._step))
        self.slider.blockSignals(False)
        self.value_label.setText(self._fmt(self.value()))

    def _on_slider(self, _pos: int) -> None:
        v = self.value()
        self.value_label.setText(self._fmt(v))
        self.slider.setAccessibleDescription(self._fmt(v))
        self.valueChanged.emit(v)


class KeyChip(QWidget):
    """A keycap-style pill showing one binding, with an optional remove button."""
    removeRequested = pyqtSignal(str)

    def __init__(self, code: str, removable: bool = False, small: bool = False, parent=None):
        super().__init__(parent)
        self.code = code
        self._removable = removable
        self._small = small
        self._hover_x = False
        self.setMouseTracking(True)
        self.setToolTip(keycodes.display_name(code) + ("  (click × to remove)" if removable else ""))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        theme.signals.changed.connect(self.update)

    def _font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(11 if self._small else 12)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    def _text(self) -> str:
        return keycodes.short_name(self.code) if self._small else keycodes.display_name(self.code)

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self._font())
        w = fm.horizontalAdvance(self._text()) + (18 if self._small else 22)
        if self._removable:
            w += 18
        return QSize(max(w, 26), 22 if self._small else 26)

    def _x_rect(self) -> QRectF:
        return QRectF(self.width() - 20, (self.height() - 14) / 2, 14, 14)

    def mouseMoveEvent(self, e):
        hover = self._removable and self._x_rect().adjusted(-3, -3, 3, 3).contains(e.position())
        if hover != self._hover_x:
            self._hover_x = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover_x = False
        self.update()

    def mousePressEvent(self, e):
        if self._removable and self._x_rect().adjusted(-3, -3, 3, 3).contains(e.position()):
            self.removeRequested.emit(self.code)

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 2)
        p.setPen(QPen(theme.qcolor(t.border), 1))
        p.setBrush(theme.qcolor(t.control))
        p.drawRoundedRect(r, 5, 5)
        # keycap bottom edge
        p.setPen(QPen(theme.qcolor(t.border), 2))
        p.drawLine(QPointF(r.left() + 4, r.bottom()), QPointF(r.right() - 4, r.bottom()))
        p.setFont(self._font())
        p.setPen(theme.qcolor(t.text))
        text_rect = r.adjusted(0, 0, -18 if self._removable else 0, 0)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._text())
        if self._removable:
            xr = self._x_rect()
            if self._hover_x:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.qcolor(t.danger_soft))
                p.drawEllipse(xr.adjusted(-2, -2, 2, 2))
            icons.paint(p, "close", xr, theme.qcolor(t.danger if self._hover_x else t.text_3), 1.4)
        p.end()


class FlowLayoutWidget(QWidget):
    """Lays child widgets out left-to-right, wrapping to new lines."""

    def __init__(self, spacing: int = 6, parent=None):
        super().__init__(parent)
        self._items: list[QWidget] = []
        self._spacing = spacing
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def clear(self) -> None:
        for w in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items = []
        self.updateGeometry()

    def add(self, w: QWidget) -> None:
        w.setParent(self)
        w.show()
        self._items.append(w)
        self._relayout()
        self.updateGeometry()

    def _relayout(self, width: int | None = None) -> int:
        width = width or max(self.width(), 1)
        x = y = 0
        line_h = 0
        for w in self._items:
            hint = w.sizeHint()
            if x > 0 and x + hint.width() > width:
                x = 0
                y += line_h + self._spacing
                line_h = 0
            w.setGeometry(x, y, hint.width(), hint.height())
            x += hint.width() + self._spacing
            line_h = max(line_h, hint.height())
        return y + line_h

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        x = y = line_h = 0
        for w in self._items:
            hint = w.sizeHint()
            if x > 0 and x + hint.width() > width:
                x = 0
                y += line_h + self._spacing
                line_h = 0
            x += hint.width() + self._spacing
            line_h = max(line_h, hint.height())
        return y + line_h

    def sizeHint(self) -> QSize:
        return QSize(200, max(self.heightForWidth(max(self.width(), 200)), 0))

    def minimumSizeHint(self) -> QSize:
        return QSize(40, self.heightForWidth(max(self.width(), 200)))

    def resizeEvent(self, e):
        self._relayout(e.size().width())
        super().resizeEvent(e)


class HotkeyEdit(QPushButton):
    """Click, then press a key combination. Esc cancels, Backspace clears."""
    comboChanged = pyqtSignal(str)
    recording = pyqtSignal(bool)

    def __init__(self, combo: str = "", parent=None):
        super().__init__(parent)
        self._combo = combo
        self._recording = False
        self.setMinimumWidth(170)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click, then press the new key combination.\nEsc cancels • Backspace clears")
        self.clicked.connect(self._start)
        self._render()

    def combo(self) -> str:
        return self._combo

    def set_combo(self, combo: str) -> None:
        self._combo = combo
        self._render()

    def _render(self) -> None:
        if self._recording:
            self.setText("Press keys…")
            self.setProperty("kind", "toggleOn")
        else:
            self.setText(keycodes.combo_display(self._combo) if self._combo else "Not set")
            self.setProperty("kind", None)
        repolish(self)

    def _start(self) -> None:
        self._recording = True
        self._render()
        self.grabKeyboard()
        self.recording.emit(True)

    def _stop(self) -> None:
        self._recording = False
        self.releaseKeyboard()
        self._render()
        self.recording.emit(False)

    def focusOutEvent(self, e):
        if self._recording:
            self._stop()
        super().focusOutEvent(e)

    def event(self, e):
        if self._recording and e.type() == QEvent.Type.KeyPress:
            self._handle_key(e)
            return True
        if self._recording and e.type() in (QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride):
            return True
        return super().event(e)

    def _handle_key(self, e: QKeyEvent) -> None:
        if e.isAutoRepeat():
            return
        key = e.key()
        mods = e.modifiers()
        if key == Qt.Key.Key_Escape and not mods:
            self._stop()
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not mods:
            self._combo = ""
            self._stop()
            self.comboChanged.emit("")
            return
        code = code_from_key_event(e)
        if not code or keycodes.is_modifier(code):
            return  # wait for the main key
        held = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            held.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            held.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            held.append("shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            held.append("win")
        self._combo = keycodes.format_combo(held, code)
        self._stop()
        self.comboChanged.emit(self._combo)


class StatusPill(QWidget):
    """Dot + text in a rounded pill; state: ok | warn | error | off."""
    clicked = pyqtSignal()

    def __init__(self, text: str = "", state: str = "off", parent=None):
        super().__init__(parent)
        self._text, self._state = text, state
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        theme.signals.changed.connect(self.update)

    def set_status(self, text: str, state: str) -> None:
        self._text, self._state = text, state
        self.setAccessibleName(text)
        self.updateGeometry()
        self.update()

    def _font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    def sizeHint(self) -> QSize:
        return QSize(QFontMetrics(self._font()).horizontalAdvance(self._text) + 34, 26)

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, _):
        t = theme.T
        color = {"ok": t.success, "warn": t.warning, "error": t.danger}.get(self._state, t.text_3)
        soft = {"ok": t.success_soft, "warn": t.warning_soft, "error": t.danger_soft}.get(self._state, t.control)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(theme.qcolor(color, 90), 1))
        p.setBrush(theme.qcolor(soft))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(color))
        p.drawEllipse(QPointF(14, r.center().y()), 4, 4)
        p.setPen(theme.qcolor(t.text))
        p.setFont(self._font())
        p.drawText(r.adjusted(24, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        p.end()


class InfoBar(QFrame):
    """Inline message bar (info / success / warning / error) with actions."""
    closed = pyqtSignal()

    _ICONS = {"info": "info", "success": "check_circle", "warning": "alert", "error": "error"}

    def __init__(self, title: str, message: str = "", level: str = "info", closable: bool = True, parent=None):
        super().__init__(parent)
        self._level = level
        self.setObjectName("infoBar")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 10, 8, 10)
        h.setSpacing(10)
        self.icon = IconLabel(self._ICONS.get(level, "info"), 18, color_token=self._token())
        h.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = label(title)
        f = self.title_label.font()
        f.setWeight(QFont.Weight.DemiBold)
        self.title_label.setFont(f)
        self.title_label.setStyleSheet("font-weight: 600;")
        text.addWidget(self.title_label)
        self.message_label = label(message, "body2", wrap=True)
        self.message_label.setVisible(bool(message))
        text.addWidget(self.message_label)
        h.addLayout(text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        h.addLayout(self.actions)
        if closable:
            h.addWidget(icon_button("close", "Dismiss", self._close, 28), 0, Qt.AlignmentFlag.AlignTop)
        self._restyle()
        theme.signals.changed.connect(self._restyle)

    def _token(self) -> str:
        return {"success": "success", "warning": "warning", "error": "danger"}.get(self._level, "accent")

    def _restyle(self) -> None:
        t = theme.T
        soft = {"success": t.success_soft, "warning": t.warning_soft, "error": t.danger_soft}.get(self._level, t.info_soft)
        border = getattr(t, self._token())
        c = theme.qcolor(border, 90)
        self.setStyleSheet(
            f"QFrame#infoBar {{ background: {soft}; border: 1px solid rgba({c.red()},{c.green()},{c.blue()},0.35);"
            f" border-radius: 6px; }}"
        )

    def set_content(self, title: str, message: str, level: str | None = None) -> None:
        if level and level != self._level:
            self._level = level
            self.icon.set_icon(self._ICONS.get(level, "info"), self._token())
            self._restyle()
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))

    def add_action(self, text: str, on_click: Callable, kind: str | None = None) -> QPushButton:
        btn = button(text, kind, on_click=on_click)
        self.actions.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return btn

    def clear_actions(self) -> None:
        while self.actions.count():
            item = self.actions.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _close(self) -> None:
        self.hide()
        self.closed.emit()


class ToastHost(QWidget):
    """Stacks transient InfoBars in the top-right corner of its parent."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(0, 0, 0, 0)
        self._v.setSpacing(8)
        self._v.addStretch()
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.Resize:
            self._place()
        return False

    def _place(self) -> None:
        parent = self.parentWidget()
        w = min(400, parent.width() - 32)
        h = self._v.sizeHint().height()
        self.setGeometry(parent.width() - w - 16, 16, w, h)
        self.raise_()

    def show_toast(self, title: str, message: str = "", level: str = "info", timeout_ms: int = 4000,
                   action: tuple[str, Callable] | None = None) -> None:
        bar = InfoBar(title, message, level, closable=True, parent=self)
        if action:
            text, cb = action
            bar.add_action(text, lambda b=bar, cb=cb: (cb(), b._close()), "subtle")
            timeout_ms = max(timeout_ms, 6000)
        bar.setAutoFillBackground(True)
        t = theme.T
        bar.setStyleSheet(bar.styleSheet().replace("background:", f"background: {t.card}; background:"))
        eff = QGraphicsOpacityEffect(bar)
        bar.setGraphicsEffect(eff)
        eff.setOpacity(1.0)
        self._v.insertWidget(self._v.count() - 1, bar)
        while self._v.count() > 4:  # keep at most 3 toasts
            item = self._v.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        bar.closed.connect(lambda b=bar: self._remove(b))
        self.show()
        self._place()
        QTimer.singleShot(timeout_ms, lambda b=bar: self._fade(b))

    def _fade(self, bar: InfoBar) -> None:
        try:
            eff = bar.graphicsEffect()
        except RuntimeError:
            return
        if eff is None:
            return
        anim = QPropertyAnimation(eff, b"opacity", bar)
        anim.setDuration(250)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(lambda b=bar: self._remove(b))
        anim.start()

    def _remove(self, bar: InfoBar) -> None:
        try:
            self._v.removeWidget(bar)
            bar.deleteLater()
        except RuntimeError:
            return
        if self._v.count() <= 1:
            self.hide()
        else:
            self._place()


class SegmentedControl(QWidget):
    """Row of mutually exclusive buttons."""
    changed = pyqtSignal(str)

    def __init__(self, options: list[tuple[str, str]], value: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self._buttons: dict[str, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._select(k, emit=True))
            h.addWidget(b)
            self._buttons[key] = b
        self._value = ""
        self._select(value, emit=False)

    def value(self) -> str:
        return self._value

    def set_value(self, key: str) -> None:
        self._select(key, emit=False)

    def _select(self, key: str, emit: bool) -> None:
        if key not in self._buttons:
            return
        self._value = key
        for k, b in self._buttons.items():
            b.setChecked(k == key)
            b.setProperty("kind", "toggleOn" if k == key else None)
            repolish(b)
        if emit:
            self.changed.emit(key)


# ---- Live visualisations ---------------------------------------------------

class StickPad(QWidget):
    """Circular XY read-out for an analog stick."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._x = self._y = 0.0
        self._pressed = False
        self._trail: list[tuple[float, float]] = []
        self.setMinimumSize(140, 170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.signals.changed.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(160, 180)

    def set_value(self, x: float, y: float, pressed: bool = False) -> None:
        if (x, y, pressed) == (self._x, self._y, self._pressed) and not self._trail:
            return
        self._x, self._y, self._pressed = x, y, pressed
        self._trail.append((x, y))
        self._trail = self._trail[-14:]
        if len(self._trail) > 1 and self._trail[-1] == self._trail[0] and all(t == self._trail[0] for t in self._trail):
            self._trail = []
        self.update()

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height() - 26)
        r = size / 2 - 4
        c = QPointF(self.width() / 2, r + 4)
        p.setPen(QPen(theme.qcolor(t.border), 1))
        p.setBrush(theme.qcolor(t.control))
        p.drawEllipse(c, r, r)
        p.setPen(QPen(theme.qcolor(t.border_subtle), 1, Qt.PenStyle.DashLine))
        p.drawEllipse(c, r / 2, r / 2)
        p.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - r), QPointF(c.x(), c.y() + r))
        accent = theme.qcolor(t.accent)
        for i, (tx, ty) in enumerate(self._trail[:-1]):
            a = int(20 + 100 * i / max(1, len(self._trail)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(t.accent, a))
            p.drawEllipse(QPointF(c.x() + tx * r, c.y() - ty * r), 3, 3)
        dot = QPointF(c.x() + self._x * r, c.y() - self._y * r)
        p.setPen(QPen(accent, 2))
        p.drawLine(c, dot)
        p.setPen(QPen(theme.qcolor(t.card), 2))
        p.setBrush(accent if (abs(self._x) > 0.01 or abs(self._y) > 0.01 or self._pressed) else theme.qcolor(t.text_3))
        p.drawEllipse(dot, 8 if self._pressed else 6, 8 if self._pressed else 6)
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(theme.qcolor(t.text_2))
        p.drawText(QRectF(0, self.height() - 20, self.width(), 18), Qt.AlignmentFlag.AlignCenter,
                   f"{self._title}   X {self._x:+.2f}   Y {self._y:+.2f}")
        p.end()


class MeterBar(QWidget):
    """Horizontal 0..1 meter with a caption and percentage."""

    def __init__(self, title: str, parent=None, color_token: str = "accent"):
        super().__init__(parent)
        self._title, self._value, self._token = title, 0.0, color_token
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.signals.changed.connect(self.update)

    def set_value(self, v: float) -> None:
        v = max(0.0, min(1.0, v))
        if abs(v - self._value) > 1e-4:
            self._value = v
            self.update()

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(theme.qcolor(t.text_2))
        p.drawText(QRectF(0, 0, self.width(), 16), Qt.AlignmentFlag.AlignLeft, self._title)
        p.drawText(QRectF(0, 0, self.width(), 16), Qt.AlignmentFlag.AlignRight, f"{self._value * 100:.0f}%")
        bar = QRectF(0, 22, self.width(), 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(t.control_hover))
        p.drawRoundedRect(bar, 4, 4)
        if self._value > 0:
            p.setBrush(theme.qcolor(getattr(t, self._token)))
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), max(8, bar.width() * self._value), bar.height()), 4, 4)
        p.end()


class CurvePreview(QWidget):
    """Plots stick output against mouse speed for the current tuning."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fn: Callable[[float], float] = lambda x: x
        self._live = 0.0
        self.setMinimumSize(180, 150)
        self.setToolTip("Stick output (up) versus mouse speed (right).\nThe dot shows the current output.")
        theme.signals.changed.connect(self.update)

    def set_function(self, fn: Callable[[float], float]) -> None:
        self._fn = fn
        self.update()

    def set_live(self, v: float) -> None:
        v = max(0.0, min(1.0, v))
        if abs(v - self._live) > 0.002:
            self._live = v
            self.update()

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(28, 8, self.width() - 36, self.height() - 30)
        p.setPen(QPen(theme.qcolor(t.border_subtle), 1))
        p.setBrush(theme.qcolor(t.control))
        p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 4, 4)
        for i in range(1, 4):
            x = r.left() + r.width() * i / 4
            y = r.top() + r.height() * i / 4
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(QPen(theme.qcolor(t.text_3), 1, Qt.PenStyle.DashLine))
        p.drawLine(r.bottomLeft(), r.topRight())
        path = QPainterPath()
        steps = 80
        for i in range(steps + 1):
            x = i / steps
            y = max(0.0, min(1.0, self._fn(x)))
            pt = QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.setPen(QPen(theme.qcolor(t.accent), 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        if self._live > 0:
            lx = self._live
            ly = max(0.0, min(1.0, self._fn(lx)))
            p.setPen(QPen(theme.qcolor(t.card), 2))
            p.setBrush(theme.qcolor(t.accent))
            p.drawEllipse(QPointF(r.left() + lx * r.width(), r.bottom() - ly * r.height()), 5, 5)
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(theme.qcolor(t.text_3))
        p.drawText(QRectF(r.left(), r.bottom() + 4, r.width(), 14), Qt.AlignmentFlag.AlignCenter, "Mouse speed →")
        p.save()
        p.translate(12, r.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-r.height() / 2, -8, r.height(), 14), Qt.AlignmentFlag.AlignCenter, "Stick →")
        p.restore()
        p.end()


class ResponsiveColumns(QWidget):
    """Places cards in two columns when wide enough, otherwise one."""

    def __init__(self, breakpoint: int = 900, parent=None):
        super().__init__(parent)
        self._bp = breakpoint
        self._cards: list[QWidget] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(16)
        self._cols = 0

    def add(self, w: QWidget) -> None:
        self._cards.append(w)
        self._reflow(force=True)

    def resizeEvent(self, e):
        self._reflow()
        super().resizeEvent(e)

    def _reflow(self, force: bool = False) -> None:
        cols = 2 if self.width() >= self._bp else 1
        if cols == self._cols and not force:
            return
        self._cols = cols
        for w in self._cards:
            self._grid.removeWidget(w)
        heights = [0] * cols
        rows = [0] * cols
        for w in self._cards:
            col = heights.index(min(heights)) if cols > 1 else 0
            self._grid.addWidget(w, rows[col], col, Qt.AlignmentFlag.AlignTop)
            rows[col] += 1
            heights[col] += w.sizeHint().height()
        for c in range(2):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)
        self._grid.setRowStretch(max(rows) if rows else 0, 1)


def format_percent(v: float) -> str:
    return f"{v * 100:.0f}%"


def format_multiplier(v: float) -> str:
    return f"{v:.2f}×"


def format_ms(v: float) -> str:
    return f"{v:.0f} ms"


def format_hz(v: float) -> str:
    return f"{v:.0f} Hz"


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))

