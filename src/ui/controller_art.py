"""
ControllerArt
A high-detail, near-photoreal rendering of a modern Xbox-style wireless
controller (Series / Elite-generation), drawn entirely in code so it scales
to any size. Two finishes: a matte charcoal body with brushed-metal bumpers
(dark theme) and a robot-white body (light theme).

Rendering is split in two layers:

* a static *base*, rendered once per size/finish into a cached pixmap:
  contact shadow, triggers, shell with soft-touch grain, textured rubber
  grip panels behind a moulded seam, metal bumpers and the glossy centre
  strip (both cut from the shell's own outline, so nothing overhangs),
  blurred ambient-occlusion shadows under every raised part, stick
  collars, faceted metal D-pad, face buttons, small buttons, guide button;
* *live* overlays drawn every frame on top of it (stick caps that move,
  pressed-button lighting, trigger travel, selection rings).

All geometry is in a 1000 x 800 design space ("body coordinates");
ControllerDiagram maps that space into the widget. The artwork is
original; the guide button is a generic glowing dome, not a logo.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QTransform, QFont, QBrush, QConicalGradient, QPolygonF,
)

# ---- Design-space geometry ----------------------------------------------------
# Proportions were traced from a straight-on photo of a real controller
# (width 880 units, height ~620) so the silhouette and layout read true.


L_STICK = QPointF(270, 252)
R_STICK = QPointF(620, 396)
STICK_WELL_R = 70
STICK_CAP_R = 54
DPAD = QPointF(380, 396)
DPAD_DISH_R = 70
DPAD_ARM_W = 36
DPAD_ARM_L = 58          # centre -> tip
FACE = QPointF(730, 262)
FACE_OFF = 58
FACE_R = 27
VIEW = QPointF(440, 262)
MENU = QPointF(560, 262)
SHARE = QPointF(500, 318)
SMALL_R = 16
GUIDE = QPointF(500, 186)
GUIDE_R = 32

FACE_OFFSETS = {"Y": (0, -1), "X": (-1, 0), "B": (1, 0), "A": (0, 1)}
FACE_COLORS = {"A": "#5fbf3a", "B": "#e1423b", "X": "#2f8fe8", "Y": "#f3c21c"}


def face_center(name: str) -> QPointF:
    dx, dy = FACE_OFFSETS[name]
    return QPointF(FACE.x() + dx * FACE_OFF, FACE.y() + dy * FACE_OFF)


def _mirror_segments(right: list, start: tuple) -> QPainterPath:
    """Closed, left/right symmetric path from the right half's cubic
    segments (listed top-centre -> bottom-centre)."""
    p = QPainterPath(QPointF(*start))
    for c1, c2, end in right:
        p.cubicTo(QPointF(*c1), QPointF(*c2), QPointF(*end))
    starts = [start] + [seg[2] for seg in right[:-1]]
    for (c1, c2, _), s in reversed(list(zip(right, starts))):
        p.cubicTo(QPointF(1000 - c2[0], c2[1]), QPointF(1000 - c1[0], c1[1]), QPointF(1000 - s[0], s[1]))
    p.closeSubpath()
    return p


def _mirror(path: QPainterPath) -> QPainterPath:
    return QTransform(-1, 0, 0, 1, 1000, 0).map(path)


def _poly(points) -> QPainterPath:
    p = QPainterPath()
    p.addPolygon(QPolygonF([QPointF(*pt) for pt in points]))
    p.closeSubpath()
    return p


# Outer silhouette, including the bumpers (right half, clockwise).
_SHELL_RIGHT = [
    ((560, 126), (600, 127), (640, 128)),        # top edge
    ((724, 130), (796, 146), (840, 190)),        # shoulder
    ((874, 228), (912, 346), (932, 460)),        # outer flank
    ((950, 580), (928, 716), (860, 724)),        # grip tip
    ((800, 730), (766, 652), (740, 602)),        # inner grip
    ((715, 562), (690, 544), (650, 540)),        # under-belly
    ((600, 537), (550, 536), (500, 536)),        # flat bottom centre
]
SHELL = _mirror_segments(_SHELL_RIGHT, (500, 126))

# Everything within ~26 units of the top edge: bumpers + centre strip. Taking
# the shell minus a lowered copy of itself means the band follows the outline
# exactly and tapers away naturally down the flanks - no overhang anywhere.
_TOP_BAND = SHELL.subtracted(SHELL.translated(0, 30))

RB_PATH = _TOP_BAND.intersected(_poly([(654, 40), (1000, 40), (1000, 250), (930, 250), (860, 300), (644, 170)])).simplified()
LB_PATH = _mirror(RB_PATH)


def _centre_piece() -> QPainterPath:
    """Glossy strip between the bumpers that drops into a trapezoid around
    the guide button."""
    strip = _TOP_BAND.intersected(_poly([(360, 40), (640, 40), (632, 170), (368, 170)]))
    p = QPainterPath(QPointF(372, 140))
    p.lineTo(QPointF(628, 140))
    p.cubicTo(QPointF(636, 148), QPointF(634, 158), QPointF(626, 170))
    p.lineTo(QPointF(598, 214))
    p.cubicTo(QPointF(590, 226), QPointF(580, 230), QPointF(564, 230))
    p.lineTo(QPointF(436, 230))
    p.cubicTo(QPointF(420, 230), QPointF(410, 226), QPointF(402, 214))
    p.lineTo(QPointF(374, 170))
    p.cubicTo(QPointF(366, 158), QPointF(364, 148), QPointF(372, 140))
    p.closeSubpath()
    return strip.united(p).simplified()


CENTRE = _centre_piece()


def _trigger() -> QPainterPath:
    p = QPainterPath(QPointF(676, 132))
    p.cubicTo(QPointF(690, 112), QPointF(730, 102), QPointF(770, 104))
    p.cubicTo(QPointF(806, 106), QPointF(830, 124), QPointF(840, 170))
    p.cubicTo(QPointF(800, 146), QPointF(740, 136), QPointF(676, 136))
    p.closeSubpath()
    return p


RT_PATH = _trigger()
LT_PATH = _mirror(RT_PATH)
RT_VISIBLE = RT_PATH.subtracted(SHELL).simplified()      # the part peeking over the bumper
LT_VISIBLE = _mirror(RT_VISIBLE)


def _grip_panel() -> QPainterPath:
    """Textured rubber panel on the left grip, bounded by a moulded seam that
    sweeps from the outer shoulder down under the D-pad."""
    region = QPainterPath(QPointF(20, 300))
    region.cubicTo(QPointF(150, 318), QPointF(260, 420), QPointF(318, 520))
    region.cubicTo(QPointF(332, 548), QPointF(338, 600), QPointF(336, 800))
    region.lineTo(QPointF(0, 800))
    region.lineTo(QPointF(0, 300))
    region.closeSubpath()
    return SHELL.intersected(region).simplified()


LGRIP = _grip_panel()
RGRIP = _mirror(LGRIP)
GRIPS = LGRIP.united(RGRIP)


def _dpad_cross() -> QPainterPath:
    c, w, L = DPAD, DPAD_ARM_W, DPAD_ARM_L
    h = w / 2
    p = QPainterPath()
    p.addRoundedRect(QRectF(c.x() - h, c.y() - L, w, 2 * L), 8, 8)
    p.addRoundedRect(QRectF(c.x() - L, c.y() - h, 2 * L, w), 8, 8)
    return p.simplified()


DPAD_CROSS = _dpad_cross()
DPAD_ARMS = {
    "DPAD_UP": QRectF(DPAD.x() - DPAD_ARM_W / 2, DPAD.y() - DPAD_ARM_L, DPAD_ARM_W, DPAD_ARM_L - DPAD_ARM_W / 2),
    "DPAD_DOWN": QRectF(DPAD.x() - DPAD_ARM_W / 2, DPAD.y() + DPAD_ARM_W / 2, DPAD_ARM_W, DPAD_ARM_L - DPAD_ARM_W / 2),
    "DPAD_LEFT": QRectF(DPAD.x() - DPAD_ARM_L, DPAD.y() - DPAD_ARM_W / 2, DPAD_ARM_L - DPAD_ARM_W / 2, DPAD_ARM_W),
    "DPAD_RIGHT": QRectF(DPAD.x() + DPAD_ARM_W / 2, DPAD.y() - DPAD_ARM_W / 2, DPAD_ARM_L - DPAD_ARM_W / 2, DPAD_ARM_W),
}


def _share_path() -> QPainterPath:
    p = QPainterPath()
    p.addRoundedRect(QRectF(SHARE.x() - 15, SHARE.y() - 7, 30, 14), 7, 7)
    return p


SHARE_PATH = _share_path()

PLAN_ANCHORS = {
    "A": face_center("A"), "B": face_center("B"), "X": face_center("X"), "Y": face_center("Y"),
    "LB": QPointF(200, 156), "RB": QPointF(800, 156),
    "LEFT_TRIGGER": QPointF(236, 116), "RIGHT_TRIGGER": QPointF(764, 116),
    "BACK": VIEW, "START": MENU, "GUIDE": GUIDE,
    "LS_CLICK": L_STICK, "RS_CLICK": R_STICK,
    "LEFT_STICK_UP": L_STICK + QPointF(0, -STICK_WELL_R), "LEFT_STICK_DOWN": L_STICK + QPointF(0, STICK_WELL_R),
    "LEFT_STICK_LEFT": L_STICK + QPointF(-STICK_WELL_R, 0), "LEFT_STICK_RIGHT": L_STICK + QPointF(STICK_WELL_R, 0),
    "RIGHT_STICK_UP": R_STICK + QPointF(0, -STICK_WELL_R), "RIGHT_STICK_DOWN": R_STICK + QPointF(0, STICK_WELL_R),
    "RIGHT_STICK_LEFT": R_STICK + QPointF(-STICK_WELL_R, 0), "RIGHT_STICK_RIGHT": R_STICK + QPointF(STICK_WELL_R, 0),
    "DPAD_UP": DPAD_ARMS["DPAD_UP"].center(), "DPAD_DOWN": DPAD_ARMS["DPAD_DOWN"].center(),
    "DPAD_LEFT": DPAD_ARMS["DPAD_LEFT"].center(), "DPAD_RIGHT": DPAD_ARMS["DPAD_RIGHT"].center(),
}



# ---- 2.5D camera ------------------------------------------------------------------
# The plan above is the controller seen from directly overhead. It is placed in
# a scene where the face sits at height Z_FACE above the table and every part
# has its own height, then viewed by a perspective camera tilted ALPHA degrees
# toward the front. For any fixed height z the plan -> screen mapping is a
# plane homography, which QTransform represents exactly, so every flat shape
# (including gradients and text) can be drawn in true perspective simply by
# setting the painter transform for its height.

ALPHA = math.radians(24.0)
CAM_D = 2600.0
_CX, _CY = 500.0, 430.0

Z_FACE = 96.0                   # face plane (body thickness at the front edge)
Z_BUMPER = (Z_FACE - 4, Z_FACE + 4)
Z_TRIGGER = (Z_FACE - 12, Z_FACE + 46)
Z_COLLAR = Z_FACE + 7
Z_CAP = (Z_FACE + 9, Z_FACE + 42)
Z_DPAD_DISC = Z_FACE + 5
Z_DPAD_CROSS = Z_FACE + 11
Z_FACE_BTN = Z_FACE + 10
Z_SMALL = Z_FACE + 5
Z_GUIDE = Z_FACE + 5


def H(z: float) -> QTransform:
    """Plan -> screen homography for the plane at height z."""
    sa, ca = math.sin(ALPHA), math.cos(ALPHA)
    m33 = (CAM_D - z * ca + _CY * sa) / CAM_D
    persp = QTransform(1, 0, 0,
                       0, ca, -sa / CAM_D,
                       -_CX, -_CY * ca - z * sa, m33)
    return persp * QTransform.fromTranslate(_CX, _CY)


def project(pt: QPointF, z: float) -> QPointF:
    return H(z).map(pt)


def _projected_rect(path: QPainterPath, z: float) -> QRectF:
    return H(z).map(path).boundingRect()


BODY_BOUNDS = (_projected_rect(SHELL, 0).united(_projected_rect(SHELL, Z_FACE))
               .united(_projected_rect(RT_PATH, Z_TRIGGER[1])).united(_projected_rect(LT_PATH, Z_TRIGGER[1])))
BOUNDS = BODY_BOUNDS.adjusted(-40, -30, 40, 70)          # room for soft shadows

_ANCHOR_Z = {
    "A": Z_FACE_BTN, "B": Z_FACE_BTN, "X": Z_FACE_BTN, "Y": Z_FACE_BTN,
    "LB": Z_BUMPER[1], "RB": Z_BUMPER[1], "LEFT_TRIGGER": Z_TRIGGER[1], "RIGHT_TRIGGER": Z_TRIGGER[1],
    "BACK": Z_SMALL, "START": Z_SMALL, "GUIDE": Z_GUIDE, "LS_CLICK": Z_CAP[1], "RS_CLICK": Z_CAP[1],
}
ANCHORS = {k: project(v, _ANCHOR_Z.get(k, Z_COLLAR if "STICK" in k else Z_DPAD_CROSS))
           for k, v in PLAN_ANCHORS.items()}


def _plan_hit(pt: QPointF) -> Optional[str]:
    def near(c: QPointF, r: float) -> bool:
        return math.hypot(pt.x() - c.x(), pt.y() - c.y()) <= r

    for name in FACE_OFFSETS:
        if near(face_center(name), FACE_R + 4):
            return name
    for target, c, r in (("BACK", VIEW, SMALL_R + 6), ("START", MENU, SMALL_R + 6), ("GUIDE", GUIDE, GUIDE_R + 4)):
        if near(c, r):
            return target
    for target, rect in DPAD_ARMS.items():
        if rect.adjusted(-5, -5, 5, 5).contains(pt):
            return target
    for target, c in (("LS_CLICK", L_STICK), ("RS_CLICK", R_STICK)):
        if near(c, STICK_WELL_R):
            return target
    for target, path in (("LB", LB_PATH), ("RB", RB_PATH), ("LEFT_TRIGGER", LT_VISIBLE), ("RIGHT_TRIGGER", RT_VISIBLE)):
        if path.contains(pt):
            return target
    # generous fallback for the thin bumper / trigger shapes
    for target, c in (("LB", ANCHORS["LB"]), ("RB", ANCHORS["RB"])):
        if near(c, 26):
            return target
    for target, c in (("LEFT_TRIGGER", ANCHORS["LEFT_TRIGGER"]), ("RIGHT_TRIGGER", ANCHORS["RIGHT_TRIGGER"])):
        if near(c, 22):
            return target
    return None


def hit_test(screen_pt: QPointF) -> Optional[str]:
    """Which control is under a point in screen (projected) space. Each part
    is tested on the plane at its own height, front-most first."""
    for z, allowed in ((Z_CAP[1], ("LS_CLICK", "RS_CLICK")),
                       (Z_FACE_BTN, tuple(FACE_OFFSETS)),
                       (Z_DPAD_CROSS, tuple(DPAD_ARMS)),
                       (Z_SMALL, ("BACK", "START", "GUIDE")),
                       (Z_COLLAR, ("LS_CLICK", "RS_CLICK")),
                       (Z_BUMPER[1], ("LB", "RB")),
                       (Z_TRIGGER[1], ("LEFT_TRIGGER", "RIGHT_TRIGGER")),
                       (Z_TRIGGER[0] + 20, ("LEFT_TRIGGER", "RIGHT_TRIGGER"))):
        inv, ok = H(z).inverted()
        if not ok:
            continue
        hit = _plan_hit(inv.map(screen_pt))
        if hit in allowed:
            return hit
    return None


# ---- Finishes -------------------------------------------------------------------

@dataclass(frozen=True)
class Finish:
    dark: bool
    shell_top: str
    shell_mid: str
    shell_bottom: str
    grip: str               # rubber grip tint
    edge: str
    metal: tuple            # bumper gradient stops (top..bottom)
    centre_top: str         # glossy centre strip
    centre_bottom: str
    collar: str
    part_top: str           # triggers
    part_bottom: str
    cap_top: str
    cap_bottom: str
    cap_dish: str
    dpad_light: str
    dpad_dark: str
    face_top: str
    face_bottom: str
    letter_alpha: int
    small_top: str
    small_bottom: str
    glyph: str
    shadow_alpha: int
    ao_alpha: int


CARBON = Finish(
    dark=True,
    shell_top="#41464e", shell_mid="#2b2f35", shell_bottom="#181a1e", grip="#1e2125", edge="#07080a",
    metal=("#f2f3f5", "#a9adb4", "#6c7078", "#c8cbd1", "#8a8e95"),
    centre_top="#1c1d20", centre_bottom="#08090a", collar="#24272c",
    part_top="#3a3e45", part_bottom="#15171a",
    cap_top="#3b3f45", cap_bottom="#131417", cap_dish="#1c1e22",
    dpad_light="#8b9097", dpad_dark="#3c4046",
    face_top="#2f3236", face_bottom="#0c0d0f", letter_alpha=235,
    small_top="#303338", small_bottom="#101113", glyph="#b3b7be",
    shadow_alpha=170, ao_alpha=190,
)

ROBOT_WHITE = Finish(
    dark=False,
    shell_top="#ffffff", shell_mid="#f0f1f3", shell_bottom="#d3d5da", grip="#dfe1e5", edge="#9ea2a9",
    metal=("#ffffff", "#e3e5e9", "#b9bdc4", "#eef0f2", "#c9ccd2"),
    centre_top="#fdfdfe", centre_bottom="#d9dbe0", collar="#e6e8eb",
    part_top="#fbfbfc", part_bottom="#cdd0d5",
    cap_top="#fdfdfe", cap_bottom="#c6c9cf", cap_dish="#e4e6ea",
    dpad_light="#fbfbfc", dpad_dark="#b4b8bf",
    face_top="#f7f7f8", face_bottom="#cfd2d7", letter_alpha=255,
    small_top="#f8f8f9", small_bottom="#cdd0d5", glyph="#6d7079",
    shadow_alpha=90, ao_alpha=110,
)


def _c(hex_color: str, alpha: int | None = None) -> QColor:
    c = QColor(hex_color)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def _w(alpha: int) -> QColor:
    return QColor(255, 255, 255, max(0, min(255, int(alpha))))


def _k(alpha: int) -> QColor:
    return QColor(0, 0, 0, max(0, min(255, int(alpha))))


def blur_image(img: QImage, radius: float) -> QImage:
    """Approximate Gaussian blur: repeated smooth down/up-scaling."""
    if radius <= 0.5:
        return img
    w, h = img.width(), img.height()
    out = img
    for factor in (radius / 2.0, radius / 3.0, radius / 4.0):
        f = max(1.0, factor)
        sw, sh = max(1, int(w / f)), max(1, int(h / f))
        small = out.scaled(sw, sh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out = small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return out


def _noise_tile(px: int, alpha: int, seed: int) -> QImage:
    """Fine speckle for soft-touch plastic."""
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    rng = random.Random(seed)
    for _ in range(px * px // 6):
        x, y = rng.randrange(px), rng.randrange(px)
        a = rng.randint(alpha // 3, alpha)
        p.setPen(_w(a) if rng.random() < 0.5 else _k(a))
        p.drawPoint(x, y)
    p.end()
    return img


def _dot_tile(pitch_px: float, dark: bool) -> QImage:
    """Staggered raised-dot texture for the rubber grips (two dots per tile,
    each with a lit top-left and shadowed bottom-right)."""
    t = max(4, int(round(pitch_px * 2)))
    img = QImage(t, t, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = t * 0.13
    for cx, cy in ((t * 0.25, t * 0.25), (t * 0.75, t * 0.75), (t * 0.25 + t, t * 0.25), (t * 0.25, t * 0.25 + t),
                   (t * 0.75 - t, t * 0.75), (t * 0.75, t * 0.75 - t)):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_k(150 if dark else 60))
        p.drawEllipse(QPointF(cx + r * 0.35, cy + r * 0.45), r, r)
        g = QRadialGradient(QPointF(cx - r * 0.35, cy - r * 0.4), r * 1.3)
        g.setColorAt(0, _w(70 if dark else 255))
        g.setColorAt(1, _w(8 if dark else 120))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), r * 0.92, r * 0.92)
    p.end()
    return img


# ---- Renderer ----------------------------------------------------------------------

class ControllerArt:
    def __init__(self):
        # While True (e.g. during a window resize) a cached base of the
        # wrong size is stretched instead of re-rendered.
        self.defer_rebuild = False
        self._base_key = None
        self._base: Optional[QPixmap] = None
        self._sprite_key = None
        self._sprites: dict = {}
        self._dev = QTransform()

    # -- public -----------------------------------------------------------------------

    def paint(self, p: QPainter, transform: QTransform, dark: bool, state, *,
              active: Callable[[str], bool], emphasis: Callable[[str], str],
              accent: QColor, text: QColor) -> None:
        """`transform` maps screen (projected) space into the widget."""
        finish = CARBON if dark else ROBOT_WHITE
        scale = transform.m11()
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        key = (finish.dark, round(scale, 4), round(dpr, 2))
        p.save()
        p.resetTransform()
        if self.defer_rebuild and self._base is not None and self._base_key[0] == key[0] and key != self._base_key:
            target = QRectF(transform.map(BOUNDS.topLeft()), transform.map(BOUNDS.bottomRight()))
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(target, self._base, QRectF(self._base.rect()))
        else:
            p.drawPixmap(transform.map(BOUNDS.topLeft()), self._base_pixmap(finish, scale, dpr))
        p.restore()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_live(p, finish, state, active, emphasis, accent, transform, scale, dpr)
        p.restore()

    # -- caching ----------------------------------------------------------------------

    def _base_pixmap(self, finish: Finish, scale: float, dpr: float) -> QPixmap:
        key = (finish.dark, round(scale, 4), round(dpr, 2))
        if key != self._base_key or self._base is None:
            self._base = self._render_base(finish, scale, dpr)
            self._base_key = key
        return self._base

    def _at(self, p: QPainter, z: float) -> QTransform:
        """Point the painter at the plane of height z; returns the transform."""
        xf = H(z) * self._dev
        p.setTransform(xf)
        return xf

    def _render_base(self, f: Finish, scale: float, dpr: float) -> QPixmap:
        s = scale * dpr
        size = QSize(max(1, int(BOUNDS.width() * s)), max(1, int(BOUNDS.height() * s)))
        self._dev = QTransform(s, 0, 0, s, -BOUNDS.x() * s, -BOUNDS.y() * s)

        def layer() -> tuple[QImage, QPainter]:
            img = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            lp = QPainter(img)
            lp.setRenderHint(QPainter.RenderHint.Antialiasing)
            return img, lp

        img = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Shadows on the table (z = 0): wide ambient + tight contact.
        for grow, radius, alpha, dy in ((1.03, 34, f.shadow_alpha * 0.75, 18), (1.0, 8, f.shadow_alpha, 4)):
            sh, sp = layer()
            t = QTransform.fromTranslate(-_CX, -_CY) * QTransform.fromScale(grow, grow) \
                * QTransform.fromTranslate(_CX, _CY + dy)
            sp.setTransform(t * H(0) * self._dev)
            sp.setPen(Qt.PenStyle.NoPen)
            sp.setBrush(_k(alpha))
            sp.drawPath(SHELL)
            sp.end()
            p.drawImage(0, 0, blur_image(sh, radius * s))

        # 2. Back to front: triggers, body walls, bumpers, face, parts.
        self._triggers(p, f)
        self._walls(p, f)
        xf = self._at(p, Z_FACE)
        self._shell(p, f, s, xf)
        self._bumpers(p, f)
        self._at(p, Z_FACE)
        self._centre(p, f)

        # 3. Ambient occlusion on the face around every raised part.
        ao, ap = layer()
        ap.setTransform(H(Z_FACE) * self._dev)
        ap.setPen(Qt.PenStyle.NoPen)
        ap.setBrush(_k(f.ao_alpha))
        ap.translate(0, 7)
        for c in (L_STICK, R_STICK):
            ap.drawEllipse(c, STICK_WELL_R + 6, STICK_WELL_R + 6)
        ap.drawEllipse(DPAD, DPAD_DISH_R + 3, DPAD_DISH_R + 3)
        for name in FACE_OFFSETS:
            ap.drawEllipse(face_center(name), FACE_R + 3, FACE_R + 3)
        for c in (VIEW, MENU):
            ap.drawEllipse(c, SMALL_R + 2, SMALL_R + 2)
        ap.drawEllipse(GUIDE, GUIDE_R + 2, GUIDE_R + 2)
        ap.drawPath(SHARE_PATH)
        ap.end()
        p.save()
        p.resetTransform()
        p.drawImage(0, 0, blur_image(ao, 10 * s))
        p.restore()

        # 4. Raised parts, sorted back (small plan y) to front.
        parts = [
            (GUIDE.y(), lambda: self._round_part(p, f, GUIDE, GUIDE_R, Z_FACE, Z_GUIDE, f.small_bottom,
                                                 lambda: self._guide(p, f))),
            (VIEW.y(), lambda: self._round_part(p, f, VIEW, SMALL_R, Z_FACE, Z_SMALL, f.small_bottom,
                                                lambda: self._small_button(p, f, VIEW, "view"))),
            (MENU.y(), lambda: self._round_part(p, f, MENU, SMALL_R, Z_FACE, Z_SMALL, f.small_bottom,
                                                lambda: self._small_button(p, f, MENU, "menu"))),
            (SHARE.y(), lambda: self._share_part(p, f)),
            (L_STICK.y(), lambda: self._collar_part(p, f, L_STICK)),
            (R_STICK.y(), lambda: self._collar_part(p, f, R_STICK)),
            (DPAD.y(), lambda: self._dpad_part(p, f)),
        ]
        for name in FACE_OFFSETS:
            c = face_center(name)
            parts.append((c.y(), lambda c=c, name=name: self._round_part(
                p, f, c, FACE_R, Z_FACE, Z_FACE_BTN, f.face_bottom,
                lambda: self._face_button(p, f, name, lit=False))))
        for _, draw in sorted(parts, key=lambda t: t[0]):
            draw()
        p.end()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        return pm

    # -- 2.5D building blocks -----------------------------------------------------------

    def _extrude(self, p: QPainter, path: QPainterPath, z0: float, z1: float, brush_at, step: float = 1.6) -> None:
        """Sweep `path` from height z0 to z1; brush_at(t) gives the wall
        colour for t in 0 (bottom) .. 1 (top)."""
        n = max(1, int(math.ceil(abs(z1 - z0) / step)))
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n + 1):
            t = i / n
            self._at(p, z0 + (z1 - z0) * t)
            p.setBrush(brush_at(t))
            p.drawPath(path)

    @staticmethod
    def _side_brush(rect: QRectF, base: QColor, t: float, dark: bool) -> QBrush:
        """Cylindrical wall shading: lit toward the viewer, falling off to the
        sides, darker near the bottom."""
        g = QLinearGradient(rect.left(), 0, rect.right(), 0)
        lo = 0.55 + 0.45 * t
        edge = base.darker(int(260 / lo) if dark else int(150 / lo))
        mid = base.lighter(115 if dark else 102) if t > 0.8 else base.darker(int(100 / lo))
        g.setColorAt(0, edge)
        g.setColorAt(0.5, mid)
        g.setColorAt(1, edge)
        return QBrush(g)

    def _walls(self, p: QPainter, f: Finish) -> None:
        base = _c(f.shell_bottom) if f.dark else _c(f.shell_bottom).darker(108)
        # flat colour per slice (cheap), darker toward the table ...
        self._extrude(p, SHELL, 0, Z_FACE - 1,
                      lambda t: QBrush(base.darker(int(170 - 60 * t)) if f.dark else base.darker(int(128 - 22 * t))),
                      step=2.2)
        # ... then one pass of cylindrical side shading over the visible wall
        wall = H(0).map(SHELL).subtracted(H(Z_FACE).map(SHELL))
        p.setTransform(self._dev)
        wb = wall.boundingRect()
        side = QLinearGradient(wb.left(), 0, wb.right(), 0)
        side.setColorAt(0, _k(120 if f.dark else 60))
        side.setColorAt(0.25, _k(20))
        side.setColorAt(0.5, _w(14 if f.dark else 40))
        side.setColorAt(0.75, _k(20))
        side.setColorAt(1, _k(120 if f.dark else 60))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(side))
        p.drawPath(wall)
        # rounded top edge: a soft bright roll just under the face outline
        self._at(p, Z_FACE - 3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_w(40 if f.dark else 170), 5))
        p.drawPath(SHELL)

    def _round_part(self, p: QPainter, f: Finish, c: QPointF, r: float, z0: float, z1: float,
                    wall: str, top_draw) -> None:
        circle = QPainterPath()
        circle.addEllipse(c, r, r)
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        self._extrude(p, circle, z0, z1, lambda t: self._side_brush(rect, _c(wall), t, f.dark), step=1.8)
        self._at(p, z1)
        top_draw()

    def _share_part(self, p: QPainter, f: Finish) -> None:
        br = SHARE_PATH.boundingRect()
        self._extrude(p, SHARE_PATH, Z_FACE, Z_SMALL - 1,
                      lambda t: self._side_brush(br, _c(f.small_bottom), t, f.dark), step=1.8)
        self._at(p, Z_SMALL - 1)
        self._share(p, f)

    def _collar_part(self, p: QPainter, f: Finish, c: QPointF) -> None:
        circle = QPainterPath()
        circle.addEllipse(c, STICK_WELL_R, STICK_WELL_R)
        rect = circle.boundingRect()
        self._extrude(p, circle, Z_FACE, Z_COLLAR, lambda t: self._side_brush(rect, _c(f.collar), t, f.dark), 1.2)
        self._at(p, Z_COLLAR)
        self._stick_collar(p, f, c)

    def _dpad_part(self, p: QPainter, f: Finish) -> None:
        disc = QPainterPath()
        disc.addEllipse(DPAD, DPAD_DISH_R, DPAD_DISH_R)
        rect = disc.boundingRect()
        self._extrude(p, disc, Z_FACE, Z_DPAD_DISC,
                      lambda t: self._side_brush(rect, _c(f.dpad_dark), t, f.dark), 1.8)
        self._at(p, Z_DPAD_DISC)
        self._dpad_disc(p, f)
        crect = DPAD_CROSS.boundingRect()
        self._extrude(p, DPAD_CROSS, Z_DPAD_DISC, Z_DPAD_CROSS,
                      lambda t: self._side_brush(crect, _c(f.dpad_dark), t, f.dark), 1.0)
        self._at(p, Z_DPAD_CROSS)
        self._dpad_cross_top(p, f)

    # -- helpers ------------------------------------------------------------------------

    @staticmethod
    def _vertical(rect: QRectF, *stops) -> QLinearGradient:
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        n = len(stops)
        for i, col in enumerate(stops):
            g.setColorAt(i / (n - 1) if n > 1 else 0, _c(col) if isinstance(col, str) else col)
        return g

    @staticmethod
    def _fill_device(p: QPainter, path: QPainterPath, brush: QBrush, to_device: QTransform) -> None:
        """Fill `path` with a pixel-aligned (untransformed) texture brush."""
        p.save()
        p.resetTransform()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(brush)
        p.drawPath(to_device.map(path))
        p.restore()

    # -- static parts ---------------------------------------------------------------------

    def _triggers(self, p: QPainter, f: Finish) -> None:
        for path in (LT_PATH, RT_PATH):
            br = path.boundingRect()
            self._extrude(p, path, Z_TRIGGER[0], Z_TRIGGER[1],
                          lambda t, br=br: self._side_brush(br, _c(f.part_bottom), t, f.dark), 1.8)
            self._at(p, Z_TRIGGER[1])
            p.setPen(QPen(_c(f.edge), 1.4))
            p.setBrush(QBrush(self._vertical(br, f.part_top, f.part_bottom)))
            p.drawPath(path)
            p.save()
            p.setClipPath(path)
            sheen = self._vertical(br, _w(80 if f.dark else 170), _w(0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(sheen))
            p.drawRect(br)
            p.restore()

    def _shell(self, p: QPainter, f: Finish, s: float, to_device: QTransform) -> None:
        br = SHELL.boundingRect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._vertical(br, f.shell_top, f.shell_mid, f.shell_bottom)))
        p.drawPath(SHELL)

        p.save()
        p.setClipPath(SHELL)
        # soft-touch key light across the upper face
        key = QRadialGradient(QPointF(500, 200), 470)
        key.setColorAt(0, _w(34 if f.dark else 80))
        key.setColorAt(0.6, _w(10 if f.dark else 30))
        key.setColorAt(1, _w(0))
        p.setBrush(QBrush(key))
        p.drawRect(br)
        # form shading: the flanks and grip ends turn away from the light
        for cx in (70, 930):
            g = QRadialGradient(QPointF(cx, 470), 260)
            g.setColorAt(0, _k(70 if f.dark else 34))
            g.setColorAt(1, _k(0))
            p.setBrush(QBrush(g))
            p.drawRect(br)
        belly = QLinearGradient(QPointF(0, 470), QPointF(0, 740))
        belly.setColorAt(0, _k(0))
        belly.setColorAt(1, _k(90 if f.dark else 40))
        p.setBrush(QBrush(belly))
        p.drawRect(br)
        p.restore()

        # soft-touch grain over the whole shell
        noise = QPixmap.fromImage(_noise_tile(96, 16 if f.dark else 10, 11))
        self._fill_device(p, SHELL, QBrush(noise), to_device)

        # rubber grip panels: darker, dotted texture, recessed seam
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c(f.grip, 150 if f.dark else 120))
        p.drawPath(GRIPS)
        dots = QPixmap.fromImage(_dot_tile(7.0 * s, f.dark))
        self._fill_device(p, GRIPS, QBrush(dots), to_device)
        p.save()
        p.setClipPath(GRIPS)
        g_shade = QLinearGradient(QPointF(0, 300), QPointF(0, 740))
        g_shade.setColorAt(0, _w(18 if f.dark else 40))
        g_shade.setColorAt(1, _k(60 if f.dark else 20))
        p.setBrush(QBrush(g_shade))
        p.drawRect(br)
        p.restore()
        seam = GRIPS.subtracted(QPainterPath())  # copy
        p.save()
        p.setClipPath(SHELL)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_k(200 if f.dark else 70), 3.2))
        p.drawPath(seam)
        p.setPen(QPen(_w(40 if f.dark else 200), 1.4))
        p.drawPath(seam.translated(1.5, 2.2))
        p.restore()

        # edge treatment: bevel highlight along the top, occlusion along the bottom
        p.save()
        p.setClipPath(SHELL)
        top_edge = QLinearGradient(QPointF(0, br.top()), QPointF(0, br.top() + 220))
        top_edge.setColorAt(0, _w(90 if f.dark else 230))
        top_edge.setColorAt(1, _w(0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(top_edge), 6))
        p.drawPath(SHELL)
        p.restore()
        p.setPen(QPen(_c(f.edge), 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(SHELL)
        if f.dark:
            rim = QLinearGradient(QPointF(0, br.top()), QPointF(0, br.bottom()))
            rim.setColorAt(0, _w(50))
            rim.setColorAt(0.5, _w(16))
            rim.setColorAt(1, _w(6))
            p.setPen(QPen(QBrush(rim), 1.2))
            p.drawPath(SHELL.translated(0, -1.2))

    def _bumpers(self, p: QPainter, f: Finish) -> None:
        for path in (LB_PATH, RB_PATH):
            br = path.boundingRect()
            self._extrude(p, path, Z_BUMPER[0], Z_BUMPER[1],
                          lambda t, br=br: self._side_brush(br, _c(f.metal[2]), t, f.dark), 1.5)
            self._at(p, Z_BUMPER[1])
            # brushed metal: banded vertical gradient + fine horizontal streaks
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self._vertical(br, *f.metal)))
            p.drawPath(path)
            p.save()
            p.setClipPath(path)
            rng = random.Random(int(br.x()))
            for i in range(90):
                y = br.top() + rng.random() * br.height()
                p.setPen(QPen(_w(rng.randint(10, 45)) if rng.random() < 0.5 else _k(rng.randint(8, 30)), 0.7))
                p.drawLine(QPointF(br.left(), y), QPointF(br.right(), y + rng.uniform(-6, 6)))
            spec = QLinearGradient(br.topLeft(), br.topRight())
            for t, a in ((0.0, 0), (0.35, 110), (0.5, 0), (0.7, 70), (1.0, 0)):
                spec.setColorAt(t, _w(a))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(spec))
            p.drawRect(br)
            p.restore()
            # seam under the bumper
            p.setPen(QPen(_k(170 if f.dark else 80), 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

    def _centre(self, p: QPainter, f: Finish) -> None:
        br = CENTRE.boundingRect()
        p.setPen(QPen(_k(200 if f.dark else 70), 1.6))
        p.setBrush(QBrush(self._vertical(br, f.centre_top, f.centre_bottom)))
        p.drawPath(CENTRE)
        p.save()
        p.setClipPath(CENTRE)
        # glossy reflection: a bright band across the top, soft falloff
        gloss = self._vertical(br, _w(80 if f.dark else 200), _w(20 if f.dark else 60), _w(0), _w(0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gloss))
        p.drawRect(br)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_w(60 if f.dark else 220), 1.4))
        p.drawPath(CENTRE.translated(0, 1.6))
        p.restore()

    def _stick_collar(self, p: QPainter, f: Finish, c: QPointF) -> None:
        outer = STICK_WELL_R
        # raised collar ring
        ring = QLinearGradient(QPointF(c.x(), c.y() - outer), QPointF(c.x(), c.y() + outer))
        ring.setColorAt(0, _c(f.collar).lighter(150 if f.dark else 104))
        ring.setColorAt(0.5, _c(f.collar))
        ring.setColorAt(1, _c(f.collar).darker(170 if f.dark else 125))
        p.setPen(QPen(_c(f.edge), 1.4))
        p.setBrush(QBrush(ring))
        p.drawEllipse(c, outer, outer)
        # recessed opening with inner shadow (dark at the top lip)
        inner = outer - 9
        well = QRadialGradient(QPointF(c.x(), c.y() + 12), inner * 1.05)
        well.setColorAt(0, _c(f.collar).darker(160 if f.dark else 112))
        well.setColorAt(0.85, _c(f.collar).darker(260 if f.dark else 135))
        well.setColorAt(1, _c(f.collar).darker(400 if f.dark else 160))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(well))
        p.drawEllipse(c, inner, inner)
        p.setPen(QPen(_w(55 if f.dark else 220), 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - outer + 1.5, c.y() - outer + 1.5, 2 * outer - 3, 2 * outer - 3), 25 * 16, 130 * 16)

    def _dpad_disc(self, p: QPainter, f: Finish) -> None:
        c = DPAD
        R = DPAD_DISH_R
        # faceted metal disc (16 facets alternately catching the light)
        dish = QConicalGradient(c, 90)
        for i in range(17):
            col = _c(f.dpad_light) if i % 2 == 0 else _c(f.dpad_dark)
            if i in (3, 4, 5):        # facets facing the key light
                col = col.lighter(118)
            dish.setColorAt(i / 16, col)
        p.setPen(QPen(_c(f.edge), 1.6))
        p.setBrush(QBrush(dish))
        p.drawEllipse(c, R, R)
        bowl = QRadialGradient(QPointF(c.x(), c.y() - R * 0.3), R * 1.2)
        bowl.setColorAt(0, _w(40 if f.dark else 60))
        bowl.setColorAt(0.6, _w(0))
        bowl.setColorAt(1, _k(110 if f.dark else 40))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bowl))
        p.drawEllipse(c, R, R)
        # facet edges
        p.setPen(QPen(_k(60 if f.dark else 30), 0.9))
        for i in range(16):
            a = math.pi * 2 * i / 16
            p.drawLine(QPointF(c.x() + 18 * math.cos(a), c.y() + 18 * math.sin(a)),
                       QPointF(c.x() + (R - 2) * math.cos(a), c.y() + (R - 2) * math.sin(a)))
        # chamfered rim
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_w(90 if f.dark else 230), 1.6))
        p.drawArc(QRectF(c.x() - R + 2, c.y() - R + 2, 2 * R - 4, 2 * R - 4), 20 * 16, 140 * 16)

    def _dpad_cross_top(self, p: QPainter, f: Finish) -> None:
        c = DPAD
        # low-profile raised cross
        br = DPAD_CROSS.boundingRect()
        p.setPen(QPen(_k(150 if f.dark else 60), 1.2))
        cross_fill = self._vertical(br, _c(f.dpad_light).lighter(106), _c(f.dpad_dark))
        p.setBrush(QBrush(cross_fill))
        p.drawPath(DPAD_CROSS)
        p.save()
        p.setClipPath(DPAD_CROSS)
        hl = QRadialGradient(QPointF(c.x(), c.y() - 36), 64)
        hl.setColorAt(0, _w(70 if f.dark else 150))
        hl.setColorAt(1, _w(0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(hl))
        p.drawRect(br)
        dimple = QRadialGradient(QPointF(c.x(), c.y() + 3), 12)
        dimple.setColorAt(0, _k(90))
        dimple.setColorAt(1, _k(0))
        p.setBrush(QBrush(dimple))
        p.drawEllipse(c, 12, 12)
        p.restore()
        p.setPen(QPen(_w(80) if f.dark else _k(60), 2, cap=Qt.PenCapStyle.RoundCap))
        for target, rect in DPAD_ARMS.items():
            self._chevron(p, rect, target)

    def _chevron(self, p: QPainter, rect: QRectF, target: str) -> None:
        cx, cy = rect.center().x(), rect.center().y()
        d = 5
        pts = {
            "DPAD_UP": [(cx - d, cy + 2), (cx, cy - 3), (cx + d, cy + 2)],
            "DPAD_DOWN": [(cx - d, cy - 2), (cx, cy + 3), (cx + d, cy - 2)],
            "DPAD_LEFT": [(cx + 2, cy - d), (cx - 3, cy), (cx + 2, cy + d)],
            "DPAD_RIGHT": [(cx - 2, cy - d), (cx + 3, cy), (cx - 2, cy + d)],
        }[target]
        path = QPainterPath(QPointF(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(QPointF(*pt))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def _face_button(self, p: QPainter, f: Finish, name: str, lit: bool) -> None:
        c = face_center(name)
        color = _c(FACE_COLORS[name])
        dome = QRadialGradient(QPointF(c.x() - 7, c.y() - 9), FACE_R * 1.7)
        if lit:
            dome.setColorAt(0, color.lighter(150))
            dome.setColorAt(0.6, color)
            dome.setColorAt(1, color.darker(160))
        else:
            dome.setColorAt(0, _c(f.face_top).lighter(128))
            dome.setColorAt(0.55, _c(f.face_top))
            dome.setColorAt(1, _c(f.face_bottom))
        p.setPen(QPen(_c(f.edge), 1.3))
        p.setBrush(QBrush(dome))
        p.drawEllipse(c, FACE_R, FACE_R)
        # glossy specular + bottom rim light
        spec = QRadialGradient(QPointF(c.x() - 6, c.y() - 11), FACE_R * 0.75)
        spec.setColorAt(0, _w(140 if lit else (90 if f.dark else 200)))
        spec.setColorAt(1, _w(0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(spec))
        p.drawEllipse(c, FACE_R, FACE_R)
        p.setPen(QPen(_w(40 if f.dark else 150), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - FACE_R + 2, c.y() - FACE_R + 2, 2 * FACE_R - 4, 2 * FACE_R - 4), 220 * 16, 100 * 16)
        # coloured, slightly translucent letter with a soft glow
        font = QFont("Segoe UI", 1)
        font.setPixelSize(int(FACE_R * 1.2))
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        r = QRectF(c.x() - FACE_R, c.y() - FACE_R, 2 * FACE_R, 2 * FACE_R)
        if lit:
            p.setPen(_w(245))
        else:
            glow = QColor(color)
            glow.setAlpha(70)
            p.setPen(glow)
            p.drawText(r.translated(0, 1), Qt.AlignmentFlag.AlignCenter, name)
            letter = QColor(color)
            letter.setAlpha(f.letter_alpha)
            p.setPen(letter)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, name)

    def _small_button(self, p: QPainter, f: Finish, c: QPointF, glyph: str, r: float = SMALL_R) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_k(140 if f.dark else 50))
        p.drawEllipse(c, r + 2, r + 2)
        g = QRadialGradient(QPointF(c.x() - 3, c.y() - 5), r * 1.6)
        g.setColorAt(0, _c(f.small_top).lighter(125))
        g.setColorAt(1, _c(f.small_bottom))
        p.setPen(QPen(_c(f.edge), 1.1))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r, r)
        spec = QRadialGradient(QPointF(c.x() - 3, c.y() - 6), r * 0.8)
        spec.setColorAt(0, _w(70 if f.dark else 180))
        spec.setColorAt(1, _w(0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(spec))
        p.drawEllipse(c, r, r)
        self._glyph(p, c, glyph, _c(f.glyph))

    def _share(self, p: QPainter, f: Finish) -> None:
        br = SHARE_PATH.boundingRect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_k(140 if f.dark else 50))
        p.drawRoundedRect(br.adjusted(-2, -2, 2, 2), 9, 9)
        p.setPen(QPen(_c(f.edge), 1.1))
        p.setBrush(QBrush(self._vertical(br, _c(f.small_top).lighter(125), f.small_bottom)))
        p.drawPath(SHARE_PATH)
        p.setPen(QPen(_w(60 if f.dark else 200), 1))
        p.drawLine(QPointF(br.left() + 6, br.top() + 2), QPointF(br.right() - 6, br.top() + 2))

    def _glyph(self, p: QPainter, c: QPointF, glyph: str, color: QColor) -> None:
        p.setPen(QPen(color, 1.5, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        x, y = c.x(), c.y()
        if glyph == "view":
            p.drawRoundedRect(QRectF(x - 5.5, y - 4, 7, 6), 1, 1)
            p.drawRoundedRect(QRectF(x - 1.5, y - 1, 7, 6), 1, 1)
        elif glyph == "menu":
            for dy in (-3.5, 0, 3.5):
                p.drawLine(QPointF(x - 5, y + dy), QPointF(x + 5, y + dy))

    def _guide(self, p: QPainter, f: Finish, lit: bool = False, accent: QColor | None = None) -> None:
        c = GUIDE
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_k(160 if f.dark else 60))
        p.drawEllipse(QPointF(c.x(), c.y() + 2), GUIDE_R + 3, GUIDE_R + 3)
        bezel = QConicalGradient(c, 45)
        stops = ["#9a9ea5", "#2a2c30", "#dfe2e6", "#35373b", "#9a9ea5"] if f.dark else \
                ["#ffffff", "#b9bcc2", "#ffffff", "#c4c7cc", "#ffffff"]
        for i, col in enumerate(stops):
            bezel.setColorAt(i / (len(stops) - 1), _c(col))
        p.setPen(QPen(_c(f.edge), 1.2))
        p.setBrush(QBrush(bezel))
        p.drawEllipse(c, GUIDE_R, GUIDE_R)
        dome = QRadialGradient(QPointF(c.x() - 8, c.y() - 11), GUIDE_R * 1.5)
        dome.setColorAt(0, _c("#5a5d64") if f.dark else _c("#ffffff"))
        dome.setColorAt(0.6, _c("#1a1b1e") if f.dark else _c("#e3e5e8"))
        dome.setColorAt(1, _c("#08080a") if f.dark else _c("#bfc2c8"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(dome))
        p.drawEllipse(c, GUIDE_R - 4, GUIDE_R - 4)
        ring = QColor(accent) if (lit and accent) else (_w(215) if f.dark else QColor(60, 62, 68, 170))
        glow = QRadialGradient(c, GUIDE_R - 4)
        glow.setColorAt(0.5, QColor(ring.red(), ring.green(), ring.blue(), 0))
        glow.setColorAt(0.72, QColor(ring.red(), ring.green(), ring.blue(), 160 if lit else 70))
        glow.setColorAt(0.9, QColor(ring.red(), ring.green(), ring.blue(), 0))
        p.setBrush(QBrush(glow))
        p.drawEllipse(c, GUIDE_R - 4, GUIDE_R - 4)
        p.setPen(QPen(ring, 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, (GUIDE_R - 4) * 0.62, (GUIDE_R - 4) * 0.62)
        spec = QRadialGradient(QPointF(c.x() - 7, c.y() - 12), GUIDE_R * 0.7)
        spec.setColorAt(0, _w(120))
        spec.setColorAt(1, _w(0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(spec))
        p.drawEllipse(c, GUIDE_R - 4, GUIDE_R - 4)

    # -- live layer -------------------------------------------------------------------------

    def _cap_top(self, p: QPainter, f: Finish, c: QPointF) -> None:
        """Top of a stick cap (drawn on the plane the painter points at):
        knurled rubber ring, thin metal ring, concave dimpled dish."""
        R = STICK_CAP_R
        ring = QRadialGradient(QPointF(c.x() - 12, c.y() - 16), R * 1.6)
        ring.setColorAt(0, _c(f.cap_top))
        ring.setColorAt(1, _c(f.cap_bottom))
        p.setPen(QPen(_c(f.edge), 1.2))
        p.setBrush(QBrush(ring))
        p.drawEllipse(c, R, R)
        p.save()
        clip = QPainterPath()
        clip.addEllipse(c, R - 1.5, R - 1.5)
        hole = QPainterPath()
        hole.addEllipse(c, R - 15, R - 15)
        p.setClipPath(clip.subtracted(hole))
        for i in range(72):
            a = 2 * math.pi * i / 72
            lit = 0.5 - 0.5 * math.sin(a)
            p.setPen(QPen(_k(110 if f.dark else 45), 1.5))
            p.drawLine(QPointF(c.x() + (R - 16) * math.cos(a), c.y() + (R - 16) * math.sin(a)),
                       QPointF(c.x() + R * math.cos(a), c.y() + R * math.sin(a)))
            a2 = a + math.pi / 72
            p.setPen(QPen(_w((25 if f.dark else 150) * (0.3 + lit)), 1.0))
            p.drawLine(QPointF(c.x() + (R - 16) * math.cos(a2), c.y() + (R - 16) * math.sin(a2)),
                       QPointF(c.x() + R * math.cos(a2), c.y() + R * math.sin(a2)))
        p.restore()
        metal = QConicalGradient(c, 60)
        for t, col in ((0, "#e6e8eb"), (0.25, "#6f737a"), (0.5, "#d3d6da"), (0.75, "#5d6167"), (1, "#e6e8eb")):
            metal.setColorAt(t, _c(col))
        p.setOpacity(0.55 if f.dark else 0.8)
        p.setPen(QPen(QBrush(metal), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, R - 15.5, R - 15.5)
        p.setOpacity(1.0)
        top_r = R - 17
        concave = QLinearGradient(QPointF(c.x(), c.y() - top_r), QPointF(c.x(), c.y() + top_r))
        concave.setColorAt(0, _c(f.cap_dish).darker(150 if f.dark else 118))
        concave.setColorAt(0.6, _c(f.cap_dish))
        concave.setColorAt(1, _c(f.cap_dish).lighter(150 if f.dark else 104))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(concave))
        p.drawEllipse(c, top_r, top_r)
        rng = random.Random(3)
        for _ in range(160):
            a, rr = rng.uniform(0, 2 * math.pi), top_r * math.sqrt(rng.random()) * 0.92
            p.setBrush(_w(12) if f.dark else _k(12))
            p.drawEllipse(QPointF(c.x() + rr * math.cos(a), c.y() + rr * math.sin(a)), 0.9, 0.9)
        p.setPen(QPen(_w(70 if f.dark else 200), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - R + 2, c.y() - R + 2, 2 * R - 4, 2 * R - 4), 30 * 16, 120 * 16)

    def _stick_sprite(self, f: Finish, c: QPointF, scale: float, dpr: float) -> tuple[QPixmap, QPointF, QRectF]:
        """Render one upright stick cap (walls with rubber ridges + top) in
        screen space. Returns (pixmap, anchor, rect) where anchor is the
        projected cap-base centre and rect the sprite's screen rectangle."""
        key = (f.dark, round(scale, 4), round(dpr, 2))
        if key != self._sprite_key:
            self._sprites = {}
            self._sprite_key = key
        ck = (c.x(), c.y())
        if ck in self._sprites:
            return self._sprites[ck]
        circle = QPainterPath()
        circle.addEllipse(c, STICK_CAP_R, STICK_CAP_R)
        rect = _projected_rect(circle, Z_CAP[0]).united(_projected_rect(circle, Z_CAP[1])).adjusted(-16, -16, 16, 22)
        s = scale * dpr
        size = QSize(max(1, int(rect.width() * s)), max(1, int(rect.height() * s)))
        saved_dev = self._dev
        self._dev = QTransform(s, 0, 0, s, -rect.x() * s, -rect.y() * s)

        shadow = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        shadow.fill(Qt.GlobalColor.transparent)
        sp = QPainter(shadow)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing)
        sp.setTransform(H(Z_COLLAR) * self._dev)
        sp.setPen(Qt.PenStyle.NoPen)
        sp.setBrush(_k(210))
        sp.drawEllipse(QPointF(c.x(), c.y() + 8), STICK_CAP_R + 2, STICK_CAP_R + 2)
        sp.end()

        img = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawImage(0, 0, blur_image(shadow, 7 * s))
        br = circle.boundingRect()
        self._extrude(p, circle, Z_CAP[0], Z_CAP[1],
                      lambda t: self._side_brush(br, _c(f.cap_bottom).lighter(125 if f.dark else 100), t, f.dark), 1.0)
        # vertical grip ridges on the visible (front) half of the wall
        for i in range(48):
            a = math.pi * (i + 0.5) / 48          # 0..pi => front half (plan y > centre)
            pt = QPointF(c.x() + STICK_CAP_R * math.cos(a), c.y() + STICK_CAP_R * math.sin(a))
            b0, b1 = H(Z_CAP[0] + 3).map(pt), H(Z_CAP[1] - 3).map(pt)
            facing = math.sin(a)
            p.setTransform(self._dev)
            p.setPen(QPen(_k(int(90 * (0.5 + facing))) if f.dark else _k(int(40 * (0.5 + facing))), 1.1))
            p.drawLine(b0, b1)
            p.setPen(QPen(_w(int((22 if f.dark else 120) * facing)), 0.8))
            p.drawLine(b0 + QPointF(1.2, 0), b1 + QPointF(1.2, 0))
        self._at(p, Z_CAP[1])
        self._cap_top(p, f, c)
        p.end()
        self._dev = saved_dev
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        result = (pm, project(c, Z_CAP[0]), rect)
        self._sprites[ck] = result
        return result

    def _paint_live(self, p: QPainter, f: Finish, state, active, emphasis, accent: QColor,
                    transform: QTransform, scale: float, dpr: float) -> None:
        def at(z: float) -> None:
            p.setTransform(H(z) * transform)

        def glow(center: QPointF, radius: float, color: QColor, alpha: int = 150) -> None:
            g = QRadialGradient(center, radius)
            g.setColorAt(0, QColor(color.red(), color.green(), color.blue(), alpha))
            g.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(center, radius, radius)

        def ring_path(path: QPainterPath, target: str) -> None:
            e = emphasis(target)
            if not e:
                return
            col = QColor(accent) if e == "selected" else (_w(170) if f.dark else _k(120))
            p.setPen(QPen(col, 3.2 if e == "selected" else 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        at(Z_TRIGGER[1])
        for target, path, value in (("LEFT_TRIGGER", LT_PATH, state.left_trigger),
                                    ("RIGHT_TRIGGER", RT_PATH, state.right_trigger)):
            if value > 0.005:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), int(70 + 170 * value)))
                p.drawPath(path)
                glow(path.boundingRect().center(), 70, accent, int(40 + 80 * value))
            ring_path(path, target)

        at(Z_BUMPER[1])
        for target, path in (("LB", LB_PATH), ("RB", RB_PATH)):
            if active(target):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 210))
                p.drawPath(path)
                glow(path.boundingRect().center(), 70, accent, 45)
            ring_path(path, target)

        at(Z_SMALL)
        for target, c in (("BACK", VIEW), ("START", MENU)):
            if active(target):
                glow(c, SMALL_R * 2.8, accent, 170)
                p.setPen(QPen(accent, 2))
                p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 160))
                p.drawEllipse(c, SMALL_R, SMALL_R)
            self._ring(p, c, SMALL_R + 4, emphasis(target), accent, f)
        at(Z_GUIDE)
        if active("GUIDE"):
            glow(GUIDE, GUIDE_R * 2.4, accent, 170)
            self._guide(p, f, lit=True, accent=accent)
        self._ring(p, GUIDE, GUIDE_R + 4, emphasis("GUIDE"), accent, f)

        at(Z_DPAD_CROSS)
        for target, rect in DPAD_ARMS.items():
            if active(target):
                glow(rect.center(), 34, accent, 150)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 220))
                p.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 5, 5)
            e = emphasis(target)
            if e:
                p.setPen(QPen(QColor(accent) if e == "selected" else _w(150), 2.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        at(Z_FACE_BTN)
        for name in FACE_OFFSETS:
            c = face_center(name)
            if active(name):
                glow(c, FACE_R * 2.6, _c(FACE_COLORS[name]), 170)
                self._face_button(p, f, name, lit=True)
            self._ring(p, c, FACE_R + 3, emphasis(name), accent, f)

        travel = STICK_WELL_R - STICK_CAP_R + 6
        for target, center, value in (("LS_CLICK", L_STICK, state.left_stick),
                                      ("RS_CLICK", R_STICK, state.right_stick)):
            vx, vy = value
            moving = abs(vx) > 0.02 or abs(vy) > 0.02
            at(Z_COLLAR)
            if moving or active(target):
                glow(center, STICK_WELL_R + 14, accent, 110 if active(target) else 70)
            self._ring(p, center, STICK_WELL_R + 3, emphasis(target), accent, f)
            pos = QPointF(center.x() + vx * travel, center.y() - vy * travel)
            sprite, anchor, rect = self._stick_sprite(f, center, scale, dpr)
            delta = project(pos, Z_CAP[0]) - anchor
            p.setTransform(transform)
            if moving:
                # the shaft, visible under a deflected cap
                p.setPen(QPen(_c(f.cap_bottom).darker(130), STICK_CAP_R * 0.7, cap=Qt.PenCapStyle.RoundCap))
                p.drawLine(project(center, Z_COLLAR), project(pos, Z_CAP[0] + 4))
            p.drawPixmap(QRectF(rect.topLeft() + delta, rect.size()), sprite, QRectF(sprite.rect()))
            at(Z_CAP[1])
            if active(target):
                p.setPen(QPen(accent, 3))
                p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 70))
                p.drawEllipse(pos, STICK_CAP_R - 17, STICK_CAP_R - 17)
            if moving:
                p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 230), 3,
                              cap=Qt.PenCapStyle.RoundCap))
                p.drawLine(pos, QPointF(pos.x() + vx * 30, pos.y() - vy * 30))

    def _ring(self, p: QPainter, c: QPointF, r: float, e: str, accent: QColor, f: Finish) -> None:
        if not e:
            return
        col = QColor(accent) if e == "selected" else (_w(170) if f.dark else _k(120))
        p.setPen(QPen(col, 3.2 if e == "selected" else 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r, r)
