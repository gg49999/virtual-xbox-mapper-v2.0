"""
BindingDialog
"Press a key..." capture dialog.

Capture is done entirely with Qt events (keyboard grabbed by the dialog,
mouse buttons and wheel captured inside a dedicated capture box), so
clicking the dialog's own buttons can never be recorded as a binding and
no background listener thread is left running. While the dialog is open
the engine is suspended, so the key being bound does not also press a
button on the virtual controller.

After a key is captured the dialog shows it, lists any conflicts, and
lets the user choose between moving the key here or keeping it on both
controls - all in one step.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, QEvent, QRectF, QTimer
from PyQt6.QtGui import QPainter, QPen, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QRadioButton, QButtonGroup, QMessageBox,
)

import keycodes
from profile_manager import TARGET_NAMES
from ui import theme
from ui.qt_keys import code_from_key_event, code_from_mouse_button
from ui.widgets import button, label


class _CaptureBox(QWidget):
    def __init__(self, on_code: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.on_code = on_code
        self.code: Optional[str] = None
        self._phase = 0.0
        self.setMinimumSize(380, 120)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Click here with any mouse button, or scroll the wheel, to bind it.")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.04) % 1.0
        if self.code is None:
            self.update()

    def mousePressEvent(self, e):
        code = code_from_mouse_button(e.button())
        if code:
            self.on_code(code)

    def wheelEvent(self, e):
        d = e.angleDelta()
        codes = keycodes.wheel_codes(d.x(), d.y())
        if codes:
            self.on_code(codes[0])

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        pen = QPen(theme.qcolor(t.accent if self.code is None else t.border), 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(self._phase * 16)
        p.setPen(pen)
        p.setBrush(theme.qcolor(t.accent_soft if self.code is None else t.control))
        p.drawRoundedRect(r, 8, 8)
        f = QFont(self.font())
        f.setPixelSize(15 if self.code is None else 22)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(theme.qcolor(t.text))
        text = "Press a key, click, or scroll here…" if self.code is None else keycodes.display_name(self.code)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class BindingDialog(QDialog):
    """exec() returns Accepted with `result_code` and `replace_conflicts` set."""

    def __init__(self, target: str, find_conflicts: Callable[[str], list], reserved: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self.target = target
        self.find_conflicts = find_conflicts
        self.reserved = reserved or {}      # code -> reason (e.g. hotkeys)
        self.result_code: Optional[str] = None
        self.replace_conflicts = False
        friendly = TARGET_NAMES.get(target, target)
        self.setWindowTitle(f"Bind {friendly}")
        self.setModal(True)
        self.setMinimumWidth(460)

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(12)
        v.addWidget(label(f"Bind {friendly}", "title"))
        v.addWidget(label("Press the key you want to use, or click / scroll inside the box to use a "
                          "mouse button. Press Esc to cancel.", "body2", wrap=True))
        self.box = _CaptureBox(self._on_code)
        v.addWidget(self.box)

        self.conflict_area = QWidget()
        cv = QVBoxLayout(self.conflict_area)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(6)
        self.conflict_label = label("", "warning", wrap=True)
        cv.addWidget(self.conflict_label)
        self.keep_both = QRadioButton("Keep it on both controls")
        self.move_here = QRadioButton()
        self._group = QButtonGroup(self)
        self._group.addButton(self.move_here)
        self._group.addButton(self.keep_both)
        self.move_here.setChecked(True)
        cv.addWidget(self.move_here)
        cv.addWidget(self.keep_both)
        self.conflict_area.hide()
        v.addWidget(self.conflict_area)

        self.reserved_label = label("", "warning", wrap=True)
        self.reserved_label.hide()
        v.addWidget(self.reserved_label)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.retry_btn = button("Try again", on_click=self._retry)
        self.retry_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.retry_btn.hide()
        row.addWidget(self.retry_btn)
        row.addStretch()
        self.cancel_btn = button("Cancel", on_click=self.reject)
        self.cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ok_btn = button("Bind", "primary", on_click=self._accept)
        self.ok_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ok_btn.setEnabled(False)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.ok_btn)
        v.addLayout(row)

    # Keyboard is grabbed while waiting so every key (Space, Enter, Tab,
    # arrows...) is captured instead of activating a button.
    def showEvent(self, e):
        super().showEvent(e)
        self.grabKeyboard()

    def done(self, r):
        self.releaseKeyboard()
        super().done(r)

    def event(self, e):
        if e.type() == QEvent.Type.KeyPress:
            if e.isAutoRepeat():
                return True
            if self.box.code is None:
                if e.key() == Qt.Key.Key_Escape:
                    self.reject()
                    return True
                code = code_from_key_event(e)
                if code:
                    self._on_code(code)
                return True
            # After capture: Enter confirms, Esc cancels.
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.ok_btn.isEnabled():
                self._accept()
                return True
            if e.key() == Qt.Key.Key_Escape:
                self.reject()
                return True
            return True
        if e.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyRelease):
            return True
        return super().event(e)

    def _on_code(self, code: str) -> None:
        if self.box.code is not None:
            return
        self.box.code = code
        self.box.update()
        self.ok_btn.setEnabled(True)
        self.retry_btn.show()
        conflicts = [c for c in self.find_conflicts(code) if c != self.target]
        if conflicts:
            names = ", ".join(TARGET_NAMES.get(c, c) for c in conflicts)
            self.conflict_label.setText(f"{keycodes.display_name(code)} is already assigned to {names}.")
            self.move_here.setText(f"Move it here (remove from {names})")
            self.conflict_area.show()
        else:
            self.conflict_area.hide()
        reason = self.reserved.get(code)
        if reason:
            self.reserved_label.setText(f"{keycodes.display_name(code)} is also the “{reason}” hotkey; "
                                        "the hotkey will take priority.")
            self.reserved_label.show()
        else:
            self.reserved_label.hide()
        self.adjustSize()

    def _retry(self) -> None:
        self.box.code = None
        self.box.update()
        self.ok_btn.setEnabled(False)
        self.retry_btn.hide()
        self.conflict_area.hide()
        self.reserved_label.hide()
        self.adjustSize()

    def _accept(self) -> None:
        if self.box.code is None:
            return
        self.result_code = self.box.code
        self.replace_conflicts = self.conflict_area.isVisible() and self.move_here.isChecked()
        self.accept()


def confirm(parent, title: str, text: str, ok_text: str = "OK", destructive: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if destructive else QMessageBox.Icon.Question)
    ok = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(ok if not destructive else box.buttons()[-1])
    box.exec()
    return box.clickedButton() is ok

