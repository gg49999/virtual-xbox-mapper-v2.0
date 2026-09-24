"""
ControllerDiagram
Interactive, live controller diagram used by the Mapping and Live Test
pages. Two renderers share one widget:

* "vector" - an original, custom-painted Xbox-style controller that
  follows the theme (dark body in dark mode, white body in light mode).
* "image"  - any controller photo plus a calibration file (normalised
  0..1 coordinates per control), e.g. the bundled reference photo or a
  photo the user calibrated themselves.

Bindings are shown as callout labels arranged in two columns beside the
controller. Columns are laid out so labels never overlap, and every
label is connected to its control by a leader line. Controls (and their
labels) are hoverable and clickable.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QFontMetrics, QRadialGradient,
    QPainterPath, QPixmap, QTransform,
)
from PyQt6.QtWidgets import QWidget, QToolTip

import keycodes
from logger import get_logger
from profile_manager import TARGET_NAMES
from virtual_controller import ControllerButton, ControllerState
from ui import theme
from ui import controller_art as art

log = get_logger("Diagram")

BUTTON_ENUM = {
    "A": ControllerButton.A, "B": ControllerButton.B, "X": ControllerButton.X, "Y": ControllerButton.Y,
    "LB": ControllerButton.LB, "RB": ControllerButton.RB, "BACK": ControllerButton.BACK,
    "START": ControllerButton.START, "GUIDE": ControllerButton.GUIDE,
    "LS_CLICK": ControllerButton.LS_CLICK, "RS_CLICK": ControllerButton.RS_CLICK,
    "DPAD_UP": ControllerButton.DPAD_UP, "DPAD_DOWN": ControllerButton.DPAD_DOWN,
    "DPAD_LEFT": ControllerButton.DPAD_LEFT, "DPAD_RIGHT": ControllerButton.DPAD_RIGHT,
}

SHORT_TAGS = {
    "A": "A", "B": "B", "X": "X", "Y": "Y", "LB": "LB", "RB": "RB",
    "LEFT_TRIGGER": "LT", "RIGHT_TRIGGER": "RT", "BACK": "View", "START": "Menu", "GUIDE": "Xbox",
    "LS_CLICK": "LS Click", "RS_CLICK": "RS Click",
    "LEFT_STICK_UP": "LS ↑", "LEFT_STICK_DOWN": "LS ↓",
    "LEFT_STICK_LEFT": "LS ←", "LEFT_STICK_RIGHT": "LS →",
    "RIGHT_STICK_UP": "RS ↑", "RIGHT_STICK_DOWN": "RS ↓",
    "RIGHT_STICK_LEFT": "RS ←", "RIGHT_STICK_RIGHT": "RS →",
    "DPAD_UP": "D-Pad ↑", "DPAD_DOWN": "D-Pad ↓",
    "DPAD_LEFT": "D-Pad ←", "DPAD_RIGHT": "D-Pad →",
    "WALK_MODIFIER": "Walk", "PRECISION_AIM": "Precision",
}

LEFT_SIDE = ["LEFT_TRIGGER", "LB", "BACK", "LEFT_STICK_UP", "LEFT_STICK_LEFT", "LEFT_STICK_RIGHT",
             "LEFT_STICK_DOWN", "LS_CLICK", "DPAD_UP", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_DOWN"]
RIGHT_SIDE = ["RIGHT_TRIGGER", "RB", "GUIDE", "START", "Y", "X", "B", "A", "RIGHT_STICK_UP",
              "RIGHT_STICK_LEFT", "RIGHT_STICK_RIGHT", "RIGHT_STICK_DOWN", "RS_CLICK"]


# ---- Vector artwork -----------------------------------------------------------
BODY_BOUNDS = art.BODY_BOUNDS        # the controller in projected (2.5D) space; art.BOUNDS adds shadow room
VECTOR_ANCHORS = art.ANCHORS

# Image mode: stick/D-pad directions radiate from one calibrated point.
_IMAGE_OFFSETS = {
    "LEFT_STICK_UP": ("LS_CLICK", (0, -1)), "LEFT_STICK_DOWN": ("LS_CLICK", (0, 1)),
    "LEFT_STICK_LEFT": ("LS_CLICK", (-1, 0)), "LEFT_STICK_RIGHT": ("LS_CLICK", (1, 0)),
    "RIGHT_STICK_UP": ("RS_CLICK", (0, -1)), "RIGHT_STICK_DOWN": ("RS_CLICK", (0, 1)),
    "RIGHT_STICK_LEFT": ("RS_CLICK", (-1, 0)), "RIGHT_STICK_RIGHT": ("RS_CLICK", (1, 0)),
    "DPAD_UP": ("DPAD", (0, -0.7)), "DPAD_DOWN": ("DPAD", (0, 0.7)),
    "DPAD_LEFT": ("DPAD", (-0.7, 0)), "DPAD_RIGHT": ("DPAD", (0.7, 0)),
}


@dataclass
class _Callout:
    target: str
    anchor: QPointF
    tag: str
    text: str
    extra: str
    rect: QRectF = field(default_factory=QRectF)


class ControllerDiagram(QWidget):
    target_clicked = pyqtSignal(str)

    def __init__(self, parent=None, interactive: bool = True):
        super().__init__(parent)
        self.interactive = interactive
        self.show_callouts = True
        self._state = ControllerState()
        self._bindings: dict[str, list[str]] = {}
        self._modes: dict[str, str] = {}
        self._mouse_target = "right_stick"
        self._selected: Optional[str] = None
        self._pulse: Optional[str] = None
        self._hover: Optional[str] = None
        self._callouts: list[_Callout] = []
        self._mode = "vector"
        self._pixmap: Optional[QPixmap] = None
        self._points: dict[str, tuple] = {}
        self._hit_frac = 0.035
        self._art = art.ControllerArt()
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(140)
        self._resize_timer.timeout.connect(self._resize_settled)
        self.setMouseTracking(True)
        self.setMinimumSize(360, 260)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        theme.signals.changed.connect(self.update)

    # ---- Public API ------------------------------------------------------

    def resizeEvent(self, e) -> None:
        # Stretch the cached artwork while the user drags, re-render when they stop.
        if e.oldSize().isValid() and e.oldSize().width() > 0:
            self._art.defer_rebuild = True
            self._resize_timer.start()
        super().resizeEvent(e)

    def _resize_settled(self) -> None:
        self._art.defer_rebuild = False
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(820, 520)

    def use_vector(self, renderer: str = "2.5d") -> bool:
        """Draw the controller in code: "2.5d" (perspective illustration) or
        "3d" (pre-rendered 3D model). Returns False if 3D assets are missing,
        in which case the 2.5D renderer is used."""
        ok = True
        if renderer == "3d":
            from ui import controller_art_3d
            ok = controller_art_3d.available()
            want = controller_art_3d.ControllerArt3D if ok else art.ControllerArt
        else:
            want = art.ControllerArt
        if type(self._art) is not want:
            self._art = want()
        self._mode = "vector"
        self._pixmap = None
        self.update()
        return ok

    def use_image(self, image_path: str, calibration_path: str) -> bool:
        try:
            pix = QPixmap(image_path)
            if pix.isNull():
                raise ValueError(f"could not decode image {image_path}")
            with open(calibration_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            points = {k: (float(v[0]), float(v[1])) for k, v in data.get("points", {}).items()
                      if isinstance(v, (list, tuple)) and len(v) == 2}
            if not points:
                raise ValueError("calibration has no points")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            log.warning("Could not load controller image: %s", exc)
            return False
        self._pixmap = pix
        self._points = points
        self._hit_frac = float(data.get("hit_radius_frac", 0.035))
        self._mode = "image"
        self.update()
        return True

    def set_state(self, state: ControllerState) -> None:
        self._state = state
        self.update()

    def set_profile(self, bindings: dict, modes: dict | None = None, mouse_target: str = "right_stick") -> None:
        self._bindings = {k: list(v) for k, v in bindings.items()}
        self._modes = {k: v.get("mode", "hold") for k, v in (modes or {}).items()}
        self._mouse_target = mouse_target
        self.update()

    # Backwards-compatible alias.
    def set_bindings(self, bindings: dict) -> None:
        self.set_profile(bindings, self._modes_as_dict(), self._mouse_target)

    def _modes_as_dict(self) -> dict:
        return {k: {"mode": v} for k, v in self._modes.items()}

    def set_selected(self, target: Optional[str]) -> None:
        self._selected = target
        self.update()

    def set_highlight(self, target: Optional[str]) -> None:
        self._pulse = target
        self.update()

    def set_show_callouts(self, show: bool) -> None:
        self.show_callouts = show
        self.update()

    # ---- Geometry --------------------------------------------------------

    def _column_width(self) -> float:
        if not self.show_callouts:
            return 0.0
        fm = QFontMetrics(self._label_font())
        widest = 0
        for target, codes in self._bindings.items():
            if codes and target in SHORT_TAGS:
                mode = self._modes.get(target, "hold")
                text = " / ".join(keycodes.short_name(c) for c in codes)
                extra = "" if mode == "hold" else "  Toggle"
                widest = max(widest, fm.horizontalAdvance(SHORT_TAGS[target]) + fm.horizontalAdvance(text + extra) + 30)
        widest = max(widest, 96)
        return float(min(widest, max(96.0, self.width() * 0.24)))

    def _stage(self) -> QRectF:
        col = self._column_width()
        pad = 8.0
        gap = 18.0 if col else 0.0
        legend = 26.0
        return QRectF(col + pad + gap, pad, max(10.0, self.width() - 2 * (col + pad + gap)),
                      max(10.0, self.height() - pad * 2 - legend))

    def _vector_transform(self) -> QTransform:
        stage = self._stage()
        s = min(stage.width() / BODY_BOUNDS.width(), stage.height() / BODY_BOUNDS.height())
        s = max(s, 0.05)
        tr = QTransform()
        tr.translate(stage.center().x(), stage.center().y())
        tr.scale(s, s)
        tr.translate(-BODY_BOUNDS.center().x(), -BODY_BOUNDS.center().y())
        return tr

    def _image_rect(self) -> QRectF:
        stage = self._stage()
        if not self._pixmap:
            return stage
        pw, ph = self._pixmap.width(), self._pixmap.height()
        s = min(stage.width() / pw, stage.height() / ph)
        w, h = pw * s, ph * s
        return QRectF(stage.center().x() - w / 2, stage.center().y() - h / 2, w, h)

    def _img_pt(self, fx: float, fy: float) -> QPointF:
        r = self._image_rect()
        return QPointF(r.x() + fx * r.width(), r.y() + fy * r.height())

    def _img_radius(self) -> float:
        return self._hit_frac * self._image_rect().width()

    def anchor(self, target: str) -> Optional[QPointF]:
        """Widget-space point that a callout for `target` points to."""
        if self._mode == "vector":
            pt = VECTOR_ANCHORS.get(target)
            return self._vector_transform().map(pt) if pt is not None else None
        key = target
        if target in _IMAGE_OFFSETS:
            parent, (ox, oy) = _IMAGE_OFFSETS[target]
            if parent not in self._points:
                return None
            c = self._img_pt(*self._points[parent])
            r = self._img_radius()
            return QPointF(c.x() + ox * r, c.y() + oy * r)
        if key.startswith("DPAD"):
            key = "DPAD"
        if key not in self._points:
            return None
        return self._img_pt(*self._points[key])

    # ---- State helpers ---------------------------------------------------

    def _active(self, target: str) -> bool:
        if target in BUTTON_ENUM:
            return bool(self._state.buttons.get(BUTTON_ENUM[target], False))
        if target == "LEFT_TRIGGER":
            return self._state.left_trigger > 0.02
        if target == "RIGHT_TRIGGER":
            return self._state.right_trigger > 0.02
        return False

    def _emphasis(self, target: str) -> str:
        if target in (self._selected, self._pulse):
            return "selected"
        if target == self._hover and self.interactive:
            return "hover"
        return ""

    # ---- Painting ---------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._mode == "image" and self._pixmap:
            self._paint_image(p)
        else:
            t = theme.T
            self._art.paint(p, self._vector_transform(), t.dark, self._state, active=self._active,
                            emphasis=self._emphasis, accent=theme.qcolor(t.accent), text=theme.qcolor(t.text))
        if self.show_callouts:
            self._paint_callouts(p)
        self._paint_legend(p)
        p.end()

    # -- vector body --

    def _glow(self, p: QPainter, center: QPointF, radius: float, color: QColor, alpha: int = 110) -> None:
        g = QRadialGradient(center, radius)
        g.setColorAt(0, QColor(color.red(), color.green(), color.blue(), alpha))
        g.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(center, radius, radius)

    # -- image mode --

    def _paint_image(self, p: QPainter) -> None:
        t = theme.T
        accent = theme.qcolor(t.accent)
        rect = self._image_rect()
        p.drawPixmap(rect, self._pixmap, QRectF(self._pixmap.rect()))
        r = self._img_radius()
        for key in ("A", "B", "X", "Y", "LB", "RB", "BACK", "START", "GUIDE", "LEFT_TRIGGER", "RIGHT_TRIGGER"):
            if key not in self._points:
                continue
            c = self._img_pt(*self._points[key])
            value = {"LEFT_TRIGGER": self._state.left_trigger, "RIGHT_TRIGGER": self._state.right_trigger}.get(key)
            if self._active(key):
                self._glow(p, c, r * 2.2, accent, int(90 + 140 * (value if value is not None else 1.0)))
                p.setPen(QPen(accent, 2.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, r * 0.9, r * 0.9)
            self._image_emphasis(p, c, r, key)
            if value is not None and value > 0.01:
                pill = QRectF(c.x() - 22, c.y() - r - 22, 44, 18)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.qcolor(t.card, 230))
                p.drawRoundedRect(pill, 9, 9)
                f = QFont(self.font())
                f.setPixelSize(11)
                f.setWeight(QFont.Weight.Bold)
                p.setFont(f)
                p.setPen(accent)
                p.drawText(pill, Qt.AlignmentFlag.AlignCenter, f"{value * 100:.0f}%")
        if "DPAD" in self._points:
            c = self._img_pt(*self._points["DPAD"])
            for target, (_, (ox, oy)) in _IMAGE_OFFSETS.items():
                if not target.startswith("DPAD"):
                    continue
                pt = QPointF(c.x() + ox * r, c.y() + oy * r)
                if self._active(target):
                    self._glow(p, pt, r * 1.2, accent, 180)
                self._image_emphasis(p, pt, r * 0.45, target)
        for key, value in (("LS_CLICK", self._state.left_stick), ("RS_CLICK", self._state.right_stick)):
            if key not in self._points:
                continue
            c = self._img_pt(*self._points[key])
            vx, vy = value
            dot = QPointF(c.x() + vx * r * 0.9, c.y() - vy * r * 0.9)
            moving = abs(vx) > 0.02 or abs(vy) > 0.02
            if self._active(key):
                self._glow(p, c, r * 2, accent, 140)
            self._image_emphasis(p, c, r, key)
            if moving or self._active(key):
                p.setPen(QPen(accent, 2.4))
                p.drawLine(c, dot)
                p.setPen(QPen(theme.qcolor(t.card), 1.5))
                p.setBrush(accent)
                p.drawEllipse(dot, r * 0.3, r * 0.3)

    def _image_emphasis(self, p: QPainter, c: QPointF, r: float, target: str) -> None:
        e = self._emphasis(target)
        if not e:
            return
        p.setPen(QPen(theme.qcolor(theme.T.accent if e == "selected" else theme.T.text_2), 2.4 if e == "selected" else 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r, r)

    # -- callouts --

    def _label_font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(12)
        return f

    def _build_callouts(self) -> list[_Callout]:
        items: list[_Callout] = []
        for side_targets in (LEFT_SIDE, RIGHT_SIDE):
            for target in side_targets:
                codes = self._bindings.get(target) or []
                if not codes:
                    continue
                anchor = self.anchor(target)
                if anchor is None:
                    continue
                mode = self._modes.get(target, "hold")
                extra = "" if mode == "hold" else ("Toggle" if mode == "toggle" else "Turbo")
                items.append(_Callout(target, anchor, SHORT_TAGS.get(target, target),
                                      " / ".join(keycodes.short_name(c) for c in codes), extra))
        stick_key = {"right_stick": "RS_CLICK", "left_stick": "LS_CLICK"}.get(self._mouse_target)
        if stick_key:
            anchor = self.anchor(stick_key)
            if anchor is not None:
                items.append(_Callout("MOUSE", anchor, "RS" if stick_key == "RS_CLICK" else "LS", "Mouse", ""))
        return items

    def _layout_column(self, items: list[_Callout], left: bool, fm: QFontMetrics, h: float) -> None:
        if not items:
            return
        col_w = self._column_width()
        spacing = h + 4
        top, bottom = 10 + h / 2, self.height() - 36 - h / 2
        items.sort(key=lambda c: c.anchor.y())
        ys = []
        for c in items:
            y = max(c.anchor.y(), top, (ys[-1] + spacing) if ys else top)
            ys.append(y)
        if ys and ys[-1] > bottom:
            ys[-1] = bottom
            for i in range(len(ys) - 2, -1, -1):
                ys[i] = min(ys[i], ys[i + 1] - spacing)
        for c, y in zip(items, ys):
            tag_w = fm.horizontalAdvance(c.tag) + 12
            text_w = fm.horizontalAdvance(c.text) + (fm.horizontalAdvance("  " + c.extra) if c.extra else 0)
            w = min(col_w, tag_w + text_w + 18)
            x = (12 + col_w - w) if left else (self.width() - 12 - col_w)
            c.rect = QRectF(x, y - h / 2, w, h)

    def _paint_callouts(self, p: QPainter) -> None:
        t = theme.T
        font = self._label_font()
        fm = QFontMetrics(font)
        items = self._build_callouts()
        mid = self.width() / 2
        left = [c for c in items if c.target in LEFT_SIDE or (c.target == "MOUSE" and c.anchor.x() < mid)]
        right = [c for c in items if c not in left]
        # Fit the tallest column into the available height: shrink the
        # labels first, and if that's still too tight only label the
        # hovered / selected control.
        rows = max(len(left), len(right), 1)
        available = self.height() - 46
        h = fm.height() + 10
        if rows * (h + 4) > available:
            font.setPixelSize(11)
            fm = QFontMetrics(font)
            h = max(fm.height() + 2, available / rows - 3)
            if available / rows - 3 < fm.height() + 2:
                keep = {self._selected, self._hover, self._pulse}
                left = [c for c in left if c.target in keep]
                right = [c for c in right if c.target in keep]
                h = fm.height() + 8
        self._layout_column(left, True, fm, h)
        self._layout_column(right, False, fm, h)
        self._callouts = left + right
        p.setFont(font)
        for c, is_left in [(c, True) for c in left] + [(c, False) for c in right]:
            target = "RS_CLICK" if c.target == "MOUSE" else c.target
            emph = self._emphasis(c.target) or self._emphasis(target) if c.target != "MOUSE" else ""
            live = self._active(c.target)
            line_col = theme.qcolor(t.accent) if (emph == "selected" or live) else theme.qcolor(t.text_3, 150)
            start = QPointF(c.rect.right() if is_left else c.rect.left(), c.rect.center().y())
            elbow = QPointF(start.x() + (14 if is_left else -14), start.y())
            path = QPainterPath(start)
            path.lineTo(elbow)
            path.lineTo(c.anchor)
            p.setPen(QPen(line_col, 1.8 if emph == "selected" else 1.1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(line_col)
            p.drawEllipse(c.anchor, 3, 3)

            bg = theme.qcolor(t.accent_soft) if emph == "selected" else theme.qcolor(t.card)
            border = theme.qcolor(t.accent) if emph == "selected" else (
                theme.qcolor(t.text_3) if emph == "hover" else theme.qcolor(t.border))
            p.setPen(QPen(border, 1))
            p.setBrush(theme.qcolor(t.card))
            p.drawRoundedRect(c.rect, 6, 6)
            if emph == "selected" or live:
                p.setBrush(bg if not live else theme.qcolor(t.accent, 60))
                p.drawRoundedRect(c.rect, 6, 6)
            tag_w = fm.horizontalAdvance(c.tag) + 12
            tag_rect = QRectF(c.rect.x() + 4, c.rect.y() + 4, tag_w, c.rect.height() - 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(t.accent, 40 if t.dark else 30))
            p.drawRoundedRect(tag_rect, 4, 4)
            tf = QFont(font)
            tf.setWeight(QFont.Weight.Bold)
            p.setFont(tf)
            p.setPen(theme.qcolor(t.accent))
            p.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, c.tag)
            p.setFont(font)
            text_rect = QRectF(tag_rect.right() + 7, c.rect.y(), c.rect.right() - tag_rect.right() - 12, c.rect.height())
            text = fm.elidedText(c.text, Qt.TextElideMode.ElideRight,
                                 int(text_rect.width() - (fm.horizontalAdvance("  " + c.extra) if c.extra else 0)))
            p.setPen(theme.qcolor(t.text))
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            if c.extra:
                p.setPen(theme.qcolor(t.warning))
                p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, c.extra)

    def _paint_legend(self, p: QPainter) -> None:
        t = theme.T
        parts = []
        for target in ("WALK_MODIFIER", "PRECISION_AIM"):
            codes = self._bindings.get(target)
            if codes:
                parts.append(f"{SHORT_TAGS[target]}: " + " / ".join(keycodes.short_name(c) for c in codes))
        if self._mouse_target == "none":
            parts.insert(0, "Mouse movement: not mapped")
        if not parts:
            return
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(theme.qcolor(t.text_3))
        p.drawText(QRectF(0, self.height() - 28, self.width(), 22), Qt.AlignmentFlag.AlignCenter,
                   "     •     ".join(parts))

    # ---- Interaction -------------------------------------------------------

    def target_at(self, pos: QPointF) -> Optional[str]:
        for c in self._callouts:
            if c.rect.contains(pos):
                return "RS_CLICK" if c.target == "MOUSE" and c.tag == "RS" else (
                    "LS_CLICK" if c.target == "MOUSE" else c.target)
        if self._mode == "image" and self._pixmap:
            return self._image_hit(pos)
        inv, ok = self._vector_transform().inverted()
        if not ok:
            return None
        return art.hit_test(inv.map(pos))

    def _image_hit(self, pos: QPointF) -> Optional[str]:
        r = self._img_radius()
        best, best_d = None, None
        for key, frac in self._points.items():
            c = self._img_pt(*frac)
            d = math.hypot(pos.x() - c.x(), pos.y() - c.y())
            if d <= r * 1.1 and (best_d is None or d < best_d):
                best, best_d = key, d
        if best == "DPAD":
            c = self._img_pt(*self._points["DPAD"])
            dx, dy = pos.x() - c.x(), pos.y() - c.y()
            if abs(dx) > abs(dy):
                return "DPAD_RIGHT" if dx > 0 else "DPAD_LEFT"
            return "DPAD_DOWN" if dy > 0 else "DPAD_UP"
        return best

    def mouseMoveEvent(self, e) -> None:
        if not self.interactive:
            return
        target = self.target_at(e.position())
        if target != self._hover:
            self._hover = target
            self.setCursor(Qt.CursorShape.PointingHandCursor if target else Qt.CursorShape.ArrowCursor)
            self.update()
            if target:
                codes = self._bindings.get(target) or []
                bound = ", ".join(keycodes.display_name(c) for c in codes) or "Not bound"
                QToolTip.showText(e.globalPosition().toPoint(),
                                  f"<b>{TARGET_NAMES.get(target, target)}</b><br>{bound}<br>"
                                  f"<span style='color:gray'>Click to edit</span>", self)
            else:
                QToolTip.hideText()

    def leaveEvent(self, e) -> None:
        if self._hover:
            self._hover = None
            self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        if not self.interactive or e.button() != Qt.MouseButton.LeftButton:
            return
        target = self.target_at(e.position())
        if target:
            self.target_clicked.emit(target)
