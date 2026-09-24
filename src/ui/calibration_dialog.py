"""
CalibrationDialog
A guided "click each control" wizard that records where every button,
stick, D-pad and trigger sits on a user-supplied controller photo, and
writes the result as a normalised-coordinate JSON file consumed by
ControllerDiagram's image mode. This is what makes the photo diagram
work with *any* image, not just the bundled one.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPixmap, QPen, QBrush, QFont
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QWidget, QProgressBar

from ui import theme
from ui.widgets import button, label

# Walked through top to bottom.
CALIBRATION_STEPS = [
    ("LS_CLICK", "Left Stick", "Click the centre of the LEFT analog stick."),
    ("RS_CLICK", "Right Stick", "Click the centre of the RIGHT analog stick."),
    ("DPAD", "D-Pad", "Click the centre of the D-pad."),
    ("A", "A Button", "Click the A button."),
    ("B", "B Button", "Click the B button."),
    ("X", "X Button", "Click the X button."),
    ("Y", "Y Button", "Click the Y button."),
    ("BACK", "View Button", "Click the small View button (left of centre)."),
    ("START", "Menu Button", "Click the small Menu button (right of centre)."),
    ("GUIDE", "Xbox Button", "Click the Xbox / Guide button."),
    ("LB", "Left Bumper", "Click the left bumper (top edge, left side)."),
    ("RB", "Right Bumper", "Click the right bumper (top edge, right side)."),
    ("LEFT_TRIGGER", "Left Trigger", "Click the left trigger (above the left bumper)."),
    ("RIGHT_TRIGGER", "Right Trigger", "Click the right trigger (above the right bumper)."),
]


class _ClickCanvas(QWidget):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self.setMinimumSize(520, 360)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.points: dict[str, tuple] = {}
        self.on_click = None

    def _image_rect(self) -> QRectF:
        w, h = self.width(), self.height()
        pw, ph = max(1, self._pixmap.width()), max(1, self._pixmap.height())
        scale = min(w / pw, h / ph) * 0.96
        dw, dh = pw * scale, ph * scale
        return QRectF((w - dw) / 2, (h - dh) / 2, dw, dh)

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setPen(QPen(theme.qcolor(t.border_subtle), 1))
        p.setBrush(theme.qcolor(t.control))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)
        rect = self._image_rect()
        p.drawPixmap(rect, self._pixmap, QRectF(self._pixmap.rect()))
        f = QFont(self.font())
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        for key, (fx, fy) in self.points.items():
            c = QPointF(rect.x() + fx * rect.width(), rect.y() + fy * rect.height())
            p.setPen(QPen(theme.qcolor(t.card), 2))
            p.setBrush(QBrush(theme.qcolor(t.accent)))
            p.drawEllipse(c, 7, 7)
            p.setPen(theme.qcolor(t.text))
            p.drawText(QRectF(c.x() + 10, c.y() - 8, 120, 16), Qt.AlignmentFlag.AlignLeft, key)
        p.end()

    def mousePressEvent(self, event):
        rect = self._image_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        pos = event.position()
        if not rect.contains(pos):
            return
        fx = (pos.x() - rect.x()) / rect.width()
        fy = (pos.y() - rect.y()) / rect.height()
        if self.on_click:
            self.on_click(max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy)))


class CalibrationDialog(QDialog):
    """On accept(), `points` holds {target: [x_frac, y_frac]} for every
    step that wasn't skipped."""

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrate Controller Image")
        self.setMinimumSize(780, 640)
        self.points: dict[str, list] = {}
        self._step = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        self.instruction = label("", "title")
        v.addWidget(self.instruction)
        self.subtext = label("", "body2", wrap=True)
        v.addWidget(self.subtext)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(CALIBRATION_STEPS))
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: {theme.T.control_hover}; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {theme.T.accent}; border-radius: 2px; }}")
        v.addWidget(self.progress)

        self.canvas = _ClickCanvas(QPixmap(image_path))
        self.canvas.on_click = self._on_click
        v.addWidget(self.canvas, 1)

        row = QHBoxLayout()
        self.skip_btn = button("Skip this control", on_click=self._skip)
        row.addWidget(self.skip_btn)
        row.addStretch()
        self.back_btn = button("Back", on_click=self._back)
        row.addWidget(self.back_btn)
        row.addWidget(button("Cancel", on_click=self.reject))
        v.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        if self._step >= len(CALIBRATION_STEPS):
            self.accept()
            return
        _, title, hint = CALIBRATION_STEPS[self._step]
        self.instruction.setText(f"Step {self._step + 1} of {len(CALIBRATION_STEPS)}: {title}")
        self.subtext.setText(hint + " Click directly on the image, or skip it if it isn't visible.")
        self.back_btn.setEnabled(self._step > 0)
        self.progress.setValue(self._step)

    def _on_click(self, fx: float, fy: float) -> None:
        key = CALIBRATION_STEPS[self._step][0]
        self.points[key] = [round(fx, 4), round(fy, 4)]
        self.canvas.points[key] = (fx, fy)
        self.canvas.update()
        self._step += 1
        self._refresh()

    def _skip(self) -> None:
        self._step += 1
        self._refresh()

    def _back(self) -> None:
        if self._step > 0:
            self._step -= 1
            key = CALIBRATION_STEPS[self._step][0]
            self.points.pop(key, None)
            self.canvas.points.pop(key, None)
            self.canvas.update()
            self._refresh()

    def save_to(self, image_filename: str, calibration_path: str) -> None:
        data = {"image_file": image_filename, "hit_radius_frac": 0.036, "points": self.points}
        with open(calibration_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
