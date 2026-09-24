"""
On-screen display: a small, click-through toast at the top of the screen
that confirms hotkey actions (mouse captured, profile switched, ...)
while a game or browser has focus. It never takes focus.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRectF
from PyQt6.QtGui import QPainter, QFont, QFontMetrics, QGuiApplication, QPen
from PyQt6.QtWidgets import QWidget

from ui import theme, icons

_KIND_ICON = {"on": "check_circle", "off": "power", "warn": "alert", "profile": "layers"}


class OSD(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._text, self._kind = "", "on"
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(220)
        self._anim.finished.connect(self._on_anim_done)

    def _font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(15)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    def show_message(self, text: str, kind: str = "on", duration_ms: int = 1600) -> None:
        self._text, self._kind = text, kind
        fm = QFontMetrics(self._font())
        w, h = fm.horizontalAdvance(text) + 76, 48
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.setGeometry(geo.x() + (geo.width() - w) // 2, geo.y() + 36, w, h)
        self._anim.stop()
        self.setWindowOpacity(0.0 if not self.isVisible() else self.windowOpacity())
        self.show()
        self.raise_()
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._hide_timer.start(duration_ms)
        self.update()

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_done(self) -> None:
        if self.windowOpacity() <= 0.01:
            self.hide()

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(QPen(theme.qcolor(t.border), 1))
        p.setBrush(theme.qcolor(t.card, 245))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        color = {"on": t.accent, "off": t.text_2, "warn": t.warning, "profile": t.accent}.get(self._kind, t.accent)
        icons.paint(p, _KIND_ICON.get(self._kind, "info"), QRectF(20, (self.height() - 22) / 2, 22, 22),
                    theme.qcolor(color), 1.8)
        p.setFont(self._font())
        p.setPen(theme.qcolor(t.text))
        p.drawText(r.adjusted(52, 0, -18, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        p.end()
