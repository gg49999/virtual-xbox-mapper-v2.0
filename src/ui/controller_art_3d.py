"""
ControllerArt3D
The "3D model" controller picture: photoreal images of a real 3D model,
rendered offline in Blender by tools/build_controller_3d.py, composited
with the same live layer as the 2.5D renderer.

The Blender camera reproduces the 2.5D camera exactly (same tilt, distance
and screen bounds), so the renders line up with controller_art's anchors,
hit-testing and live overlays. This class therefore only replaces:

* the static base image (body, bumpers, buttons, shadows...),
* the stick-cap sprites (moved in perspective with stick input),
* the pressed look of face / guide buttons (an emissive glow instead of
  repainting a flat button over the photoreal one).

If the rendered assets are missing, `available()` is False and the app
falls back to the 2.5D renderer (see ControllerDiagram).
"""
from __future__ import annotations

import json
import os
from typing import Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient, QBrush, QPen

from logger import get_logger
from paths import resource_path
from ui import controller_art as art
from ui.controller_art import (
    BOUNDS, FACE_COLORS, FACE_R, GUIDE, GUIDE_R, L_STICK, ControllerArt, Finish, face_center,
)

log = get_logger("ControllerArt3D")

ASSET_DIR = resource_path("assets", "controller3d")
_MANIFEST = os.path.join(ASSET_DIR, "manifest.json")


def _load_manifest() -> Optional[dict]:
    try:
        with open(_MANIFEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        for finish in ("carbon", "white"):
            entry = data["finishes"][finish]
            files = [entry["base"]] + [entry["caps"][s]["file"] for s in ("L", "R")]
            if not all(os.path.exists(os.path.join(ASSET_DIR, fn)) for fn in files):
                return None
        return data
    except (OSError, KeyError, ValueError, TypeError):
        return None


def available() -> bool:
    return _load_manifest() is not None


class ControllerArt3D(ControllerArt):
    def __init__(self):
        super().__init__()
        self._manifest = _load_manifest() or {"finishes": {}}
        self._images: dict[str, QImage] = {}

    def _image(self, name: str) -> QImage:
        img = self._images.get(name)
        if img is None:
            img = QImage(os.path.join(ASSET_DIR, name))
            if img.isNull():
                log.warning("Missing 3D controller asset %s", name)
            self._images[name] = img
        return img

    def _entry(self, f: Finish) -> dict:
        return self._manifest["finishes"].get("carbon" if f.dark else "white", {})

    # -- base -----------------------------------------------------------------------------

    def _render_base(self, f: Finish, scale: float, dpr: float) -> QPixmap:
        s = scale * dpr
        size = QSize(max(1, int(BOUNDS.width() * s)), max(1, int(BOUNDS.height() * s)))
        out = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(Qt.GlobalColor.transparent)
        entry = self._entry(f)
        src = self._image(entry.get("base", ""))
        if not src.isNull():
            bx, by, bw, bh = self._manifest.get("bounds", [BOUNDS.x(), BOUNDS.y(), BOUNDS.width(), BOUNDS.height()])
            target = QRectF((bx - BOUNDS.x()) * s, (by - BOUNDS.y()) * s, bw * s, bh * s)
            p = QPainter(out)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(target, src, QRectF(src.rect()))
            # Fade the render out toward its borders: the soft ambient
            # shadow on the table otherwise shows the image's rectangle.
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            fade = max(8.0, min(target.width(), target.height()) * 0.09)
            for edge in ("left", "right", "top", "bottom"):
                if edge in ("left", "right"):
                    x0 = target.left() if edge == "left" else target.right()
                    g = QLinearGradient(x0, 0, x0 + (fade if edge == "left" else -fade), 0)
                else:
                    y0 = target.top() if edge == "top" else target.bottom()
                    g = QLinearGradient(0, y0, 0, y0 + (fade if edge == "top" else -fade))
                g.setColorAt(0, QColor(0, 0, 0, 0))
                g.setColorAt(1, QColor(0, 0, 0, 255))
                p.fillRect(QRectF(out.rect()), QBrush(g))
            p.end()
        pm = QPixmap.fromImage(out)
        pm.setDevicePixelRatio(dpr)
        return pm

    # -- stick caps -------------------------------------------------------------------------

    def _stick_sprite(self, f: Finish, c: QPointF, scale: float, dpr: float):
        key = (f.dark, round(scale, 4), round(dpr, 2))
        if key != self._sprite_key:
            self._sprites = {}
            self._sprite_key = key
        ck = (c.x(), c.y())
        if ck in self._sprites:
            return self._sprites[ck]
        side = "L" if (c.x(), c.y()) == (L_STICK.x(), L_STICK.y()) else "R"
        cap = self._entry(f).get("caps", {}).get(side)
        if not cap:
            return super()._stick_sprite(f, c, scale, dpr)
        src = self._image(cap["file"])
        x, y, w, h = cap["rect"]
        rect = QRectF(x, y, w, h)
        s = scale * dpr
        scaled = src.scaled(max(1, int(w * s)), max(1, int(h * s)), Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap.fromImage(scaled)
        pm.setDevicePixelRatio(dpr)
        result = (pm, QPointF(*cap["anchor"]), rect)
        self._sprites[ck] = result
        return result

    # -- pressed looks ------------------------------------------------------------------------

    def _face_button(self, p: QPainter, f: Finish, name: str, lit: bool) -> None:
        if not lit:
            return super()._face_button(p, f, name, lit)
        c = face_center(name)
        color = QColor(FACE_COLORS[name])
        # light the photoreal button from within: additive colour bloom +
        # a bright letter, so the render's shading shows through
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        g = QRadialGradient(c, FACE_R * 1.05)
        g.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 170))
        g.setColorAt(0.8, QColor(color.red(), color.green(), color.blue(), 110))
        g.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, FACE_R * 1.05, FACE_R * 1.05)
        p.restore()
        font = QFont("Segoe UI", 1)
        font.setPixelSize(int(FACE_R * 1.2))
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(c.x() - FACE_R, c.y() - FACE_R, 2 * FACE_R, 2 * FACE_R), Qt.AlignmentFlag.AlignCenter, name)

    def _guide(self, p: QPainter, f: Finish, lit: bool = False, accent: QColor | None = None) -> None:
        if not lit:
            return super()._guide(p, f, lit, accent)
        col = QColor(accent) if accent else QColor("#ffffff")
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        g = QRadialGradient(GUIDE, GUIDE_R)
        g.setColorAt(0.45, QColor(col.red(), col.green(), col.blue(), 0))
        g.setColorAt(0.62, QColor(col.red(), col.green(), col.blue(), 230))
        g.setColorAt(0.85, QColor(col.red(), col.green(), col.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(GUIDE, GUIDE_R, GUIDE_R)
        p.restore()
        p.setPen(QPen(col, 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(GUIDE, (GUIDE_R - 4) * 0.62, (GUIDE_R - 4) * 0.62)


__all__ = ["ControllerArt3D", "available", "art"]
