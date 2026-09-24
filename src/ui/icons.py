"""
Line icons drawn with QPainter on a 24x24 grid, so the app needs no
icon files, stays crisp at any DPI, and recolours with the theme.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QIcon, QPainter, QPainterPath, QPen, QPixmap, QColor, QGuiApplication

from ui import theme


def _gamepad(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(7, 7)
    path.lineTo(17, 7)
    path.cubicTo(20.5, 7, 22, 10, 22.5, 14)
    path.cubicTo(23, 18, 21, 19.5, 19, 18)
    path.cubicTo(17.5, 16.8, 16.5, 15, 15, 15)
    path.lineTo(9, 15)
    path.cubicTo(7.5, 15, 6.5, 16.8, 5, 18)
    path.cubicTo(3, 19.5, 1, 18, 1.5, 14)
    path.cubicTo(2, 10, 3.5, 7, 7, 7)
    p.drawPath(path)
    p.drawLine(QPointF(5.5, 11), QPointF(9.5, 11))
    p.drawLine(QPointF(7.5, 9), QPointF(7.5, 13))
    p.drawPoint(QPointF(16, 10))
    p.drawPoint(QPointF(18, 12))


def _sliders(p: QPainter) -> None:
    for y, x in ((6, 15), (12, 8), (18, 13)):
        p.drawLine(QPointF(3, y), QPointF(21, y))
        p.setBrush(theme.qcolor(theme.T.bg))
        p.drawEllipse(QPointF(x, y), 2.3, 2.3)
        p.setBrush(Qt.BrushStyle.NoBrush)


def _pulse(p: QPainter) -> None:
    path = QPainterPath(QPointF(2, 12))
    for pt in ((6, 12), (9, 5), (13, 19), (16, 9), (18, 12), (22, 12)):
        path.lineTo(*pt)
    p.drawPath(path)


def _layers(p: QPainter) -> None:
    top = QPainterPath(QPointF(12, 3))
    for pt in ((21, 8), (12, 13), (3, 8)):
        top.lineTo(*pt)
    top.closeSubpath()
    p.drawPath(top)
    for dy in (4.5, 9):
        mid = QPainterPath(QPointF(3, 8 + dy))
        mid.lineTo(12, 13 + dy)
        mid.lineTo(21, 8 + dy)
        p.drawPath(mid)


def _gear(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 3.2, 3.2)
    path = QPainterPath()
    teeth = 8
    for i in range(teeth * 2):
        a = math.pi * 2 * i / (teeth * 2)
        r = 9.2 if i % 2 == 0 else 7.2
        for da in (-0.17, 0.17):
            pt = QPointF(12 + r * math.cos(a + da), 12 + r * math.sin(a + da))
            if path.elementCount() == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def _info(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    p.drawLine(QPointF(12, 11), QPointF(12, 16.5))
    p.drawPoint(QPointF(12, 7.8))


def _mouse(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(6.5, 2.5, 11, 19), 5.5, 5.5)
    p.drawLine(QPointF(12, 6), QPointF(12, 9.5))


def _keyboard(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(2, 6, 20, 12), 2, 2)
    for x in (6, 9.5, 13, 16.5):
        p.drawPoint(QPointF(x, 10))
    p.drawLine(QPointF(7, 14), QPointF(17, 14))


def _power(p: QPainter) -> None:
    p.drawArc(QRectF(4, 4.5, 16, 16), 125 * 16, 290 * 16)
    p.drawLine(QPointF(12, 2.5), QPointF(12, 11))


def _target(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 7.5, 7.5)
    for a, b in (((12, 1.5), (12, 6)), ((12, 18), (12, 22.5)), ((1.5, 12), (6, 12)), ((18, 12), (22.5, 12))):
        p.drawLine(QPointF(*a), QPointF(*b))
    p.drawPoint(QPointF(12, 12))


def _stop(p: QPainter) -> None:
    path = QPainterPath()
    for i in range(8):
        a = math.pi / 8 + i * math.pi / 4
        pt = QPointF(12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(8.5, 12), QPointF(15.5, 12))


def _alert(p: QPainter) -> None:
    path = QPainterPath(QPointF(12, 3))
    path.lineTo(22, 20.5)
    path.lineTo(2, 20.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(12, 9.5), QPointF(12, 14))
    p.drawPoint(QPointF(12, 17.3))


def _check(p: QPainter) -> None:
    path = QPainterPath(QPointF(4.5, 12.5))
    path.lineTo(9.5, 17.5)
    path.lineTo(19.5, 6.5)
    p.drawPath(path)


def _check_circle(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    path = QPainterPath(QPointF(8, 12.3))
    path.lineTo(11, 15.3)
    path.lineTo(16.5, 9)
    p.drawPath(path)


def _error(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    p.drawLine(QPointF(9, 9), QPointF(15, 15))
    p.drawLine(QPointF(15, 9), QPointF(9, 15))


def _close(p: QPainter) -> None:
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def _plus(p: QPainter) -> None:
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _more(p: QPainter) -> None:
    pen = p.pen()
    pen.setWidthF(pen.widthF() * 1.6)
    p.setPen(pen)
    for x in (6, 12, 18):
        p.drawPoint(QPointF(x, 12))


def _search(p: QPainter) -> None:
    p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
    p.drawLine(QPointF(15, 15), QPointF(20, 20))


def _trash(p: QPainter) -> None:
    p.drawLine(QPointF(4, 6.5), QPointF(20, 6.5))
    p.drawLine(QPointF(9.5, 6.5), QPointF(10, 3.5))
    p.drawLine(QPointF(10, 3.5), QPointF(14, 3.5))
    p.drawLine(QPointF(14, 3.5), QPointF(14.5, 6.5))
    path = QPainterPath(QPointF(6, 6.5))
    path.lineTo(7, 20.5)
    path.lineTo(17, 20.5)
    path.lineTo(18, 6.5)
    p.drawPath(path)


def _edit(p: QPainter) -> None:
    path = QPainterPath(QPointF(4, 20))
    path.lineTo(5, 15.5)
    path.lineTo(16, 4.5)
    path.lineTo(19.5, 8)
    path.lineTo(8.5, 19)
    path.closeSubpath()
    p.drawPath(path)


def _copy(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(8, 8, 12, 13), 2, 2)
    path = QPainterPath(QPointF(16, 5))
    path.lineTo(16, 3.5)
    path.lineTo(4, 3.5)
    path.lineTo(4, 17)
    path.lineTo(6, 17)
    p.drawPath(path)


def _download(p: QPainter) -> None:
    p.drawLine(QPointF(12, 3), QPointF(12, 15))
    path = QPainterPath(QPointF(7, 10))
    path.lineTo(12, 15)
    path.lineTo(17, 10)
    p.drawPath(path)
    p.drawLine(QPointF(4, 20.5), QPointF(20, 20.5))


def _upload(p: QPainter) -> None:
    p.drawLine(QPointF(12, 16), QPointF(12, 4))
    path = QPainterPath(QPointF(7, 9))
    path.lineTo(12, 4)
    path.lineTo(17, 9)
    p.drawPath(path)
    p.drawLine(QPointF(4, 20.5), QPointF(20, 20.5))


def _refresh(p: QPainter) -> None:
    p.drawArc(QRectF(4, 4, 16, 16), 60 * 16, 280 * 16)
    path = QPainterPath(QPointF(16.5, 2.5))
    path.lineTo(16.5, 6.5)
    path.lineTo(12.5, 6.5)
    p.drawPath(path)


def _folder(p: QPainter) -> None:
    path = QPainterPath(QPointF(2.5, 6))
    for pt in ((2.5, 19), (21.5, 19), (21.5, 8), (11.5, 8), (9.5, 5), (2.5, 5)):
        path.lineTo(*pt)
    path.closeSubpath()
    p.drawPath(path)


def _chevron(p: QPainter, left: bool) -> None:
    path = QPainterPath(QPointF(14.5 if left else 9.5, 5.5))
    path.lineTo(8 if left else 16, 12)
    path.lineTo(14.5 if left else 9.5, 18.5)
    p.drawPath(path)


def _chevron_down(p: QPainter) -> None:
    path = QPainterPath(QPointF(6, 9.5))
    path.lineTo(12, 15.5)
    path.lineTo(18, 9.5)
    p.drawPath(path)


def _link(p: QPainter) -> None:
    path = QPainterPath(QPointF(13, 4))
    path.lineTo(20, 4)
    path.lineTo(20, 11)
    p.drawPath(path)
    p.drawLine(QPointF(20, 4), QPointF(11, 13))
    path2 = QPainterPath(QPointF(17, 14))
    path2.lineTo(17, 20)
    path2.lineTo(4, 20)
    path2.lineTo(4, 7)
    path2.lineTo(10, 7)
    p.drawPath(path2)


def _home(p: QPainter) -> None:
    path = QPainterPath(QPointF(3, 11))
    path.lineTo(12, 3.5)
    path.lineTo(21, 11)
    p.drawPath(path)
    body = QPainterPath(QPointF(5.5, 9.5))
    for pt in ((5.5, 20.5), (18.5, 20.5), (18.5, 9.5)):
        body.lineTo(*pt)
    p.drawPath(body)


def _save(p: QPainter) -> None:
    path = QPainterPath(QPointF(4, 4))
    for pt in ((17, 4), (20, 7), (20, 20), (4, 20)):
        path.lineTo(*pt)
    path.closeSubpath()
    p.drawPath(path)
    p.drawRect(QRectF(8, 13, 8, 7))
    p.drawLine(QPointF(8, 4), QPointF(8, 8.5))
    p.drawLine(QPointF(8, 8.5), QPointF(15, 8.5))


def _star(p: QPainter) -> None:
    path = QPainterPath()
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = 9 if i % 2 == 0 else 4
        pt = QPointF(12 + r * math.cos(a), 12.5 + r * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def _hand(p: QPainter) -> None:  # "turbo" bolt
    path = QPainterPath(QPointF(13.5, 2.5))
    for pt in ((5, 13.5), (11.5, 13.5), (10.5, 21.5), (19, 10.5), (12.5, 10.5)):
        path.lineTo(*pt)
    path.closeSubpath()
    p.drawPath(path)


_DRAWERS = {
    "gamepad": _gamepad, "sliders": _sliders, "pulse": _pulse, "layers": _layers,
    "gear": _gear, "info": _info, "mouse": _mouse, "keyboard": _keyboard,
    "power": _power, "target": _target, "stop": _stop, "alert": _alert,
    "check": _check, "check_circle": _check_circle, "error": _error, "close": _close,
    "plus": _plus, "more": _more, "search": _search, "trash": _trash, "edit": _edit,
    "copy": _copy, "download": _download, "upload": _upload, "refresh": _refresh,
    "folder": _folder, "chevron_left": lambda p: _chevron(p, True),
    "chevron_right": lambda p: _chevron(p, False), "chevron_down": _chevron_down, "link": _link, "home": _home,
    "save": _save, "star": _star, "bolt": _hand,
}


def paint(p: QPainter, name: str, rect: QRectF, color: QColor, stroke: float = 1.6) -> None:
    drawer = _DRAWERS.get(name)
    if not drawer:
        return
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.x(), rect.y())
    p.scale(rect.width() / 24.0, rect.height() / 24.0)
    pen = QPen(color, stroke * 24.0 / max(rect.width(), 1) * (rect.width() / 20.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    drawer(p)
    p.restore()


def pixmap(name: str, color: QColor | str | None = None, size: int = 20) -> QPixmap:
    if color is None:
        color = theme.qcolor(theme.T.text)
    elif isinstance(color, str):
        color = theme.qcolor(color)
    ratio = 2.0
    app = QGuiApplication.instance()
    if app is not None and app.primaryScreen() is not None:
        ratio = max(2.0, app.primaryScreen().devicePixelRatio())
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint(p, name, QRectF(0, 0, size, size), color)
    p.end()
    return pm


def icon(name: str, color: QColor | str | None = None, size: int = 20) -> QIcon:
    return QIcon(pixmap(name, color, size))


def app_icon(accent: str | None = None) -> QIcon:
    """The application / tray icon: a gamepad on a rounded accent tile."""
    ic = QIcon()
    fill = theme.qcolor(accent or "#107c10")
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        r = size * 0.22
        p.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), r, r)
        inset = size * 0.14
        paint(p, "gamepad", QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
              QColor("#ffffff"), stroke=2.0)
        p.end()
        ic.addPixmap(pm)
    return ic


def status_icon(active: bool, captured: bool) -> QIcon:
    """Tray icon variant with a small status dot."""
    base = app_icon("#107c10" if active else "#6b6b75")
    if not captured:
        return base
    ic = QIcon()
    for size in (16, 24, 32, 48, 64):
        pm = base.pixmap(size, size)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = size * 0.42
        p.setBrush(QColor("#f2c94c"))
        p.setPen(QPen(QColor("#1b1b1f"), max(1.0, size / 24)))
        p.drawEllipse(QRectF(size - d - 0.5, size - d - 0.5, d, d))
        p.end()
        ic.addPixmap(pm)
    return ic
