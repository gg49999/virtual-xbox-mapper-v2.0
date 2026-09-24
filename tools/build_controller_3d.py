"""
Build the 3D controller model in Blender and render the assets used by the
app's "3D model" controller picture (src/ui/controller_art_3d.py).

    pip install bpy PyQt6          # bpy = Blender as a Python module (Python 3.11)
    python tools/build_controller_3d.py [--samples 96] [--width 2000] [--quick]

Everything is procedural: the shell, bumpers, triggers, D-pad, buttons and
sticks are built from the same plan-view outlines and heights as the 2.5D
renderer (src/ui/controller_art.py), and the Blender camera reproduces the
2.5D camera exactly. The rendered images therefore line up with the app's
existing anchors, hit-testing and live overlays pixel for pixel.

Outputs (assets/controller3d/):
    controller.glb                     the model (glTF binary, both finishes share geometry)
    {carbon,white}_base.png            everything except the stick caps, incl. soft shadows
    {carbon,white}_cap_{L,R}.png       each stick cap, cropped, incl. its contact shadow
    manifest.json                      bounds/scale/crop rectangles for the app
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import bpy  # noqa: E402
from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QPainter, QPainterPath, QPainterPathStroker, QTransform, QColor  # noqa: E402

import ui.controller_art as A  # noqa: E402

OUT = os.path.join(ROOT, "assets", "controller3d")
S = 0.01                       # plan units -> Blender units


# ---- geometry helpers --------------------------------------------------------------

def to_world(x: float, y: float) -> tuple[float, float]:
    return (x - A._CX) * S, -(y - A._CY) * S


def path_loops(path: QPainterPath) -> list[list[tuple[float, float]]]:
    """Flatten a QPainterPath into closed polygons (plan units)."""
    fine = QTransform.fromScale(20, 20).map(path)
    loops = []
    for poly in fine.toFillPolygons():
        pts = [(poly[i].x() / 20, poly[i].y() / 20) for i in range(poly.count())]
        if len(pts) > 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        # drop near-duplicate points (Blender's curve fill dislikes them)
        clean = []
        for pt in pts:
            if not clean or math.hypot(pt[0] - clean[-1][0], pt[1] - clean[-1][1]) > 0.35:
                clean.append(pt)
        if len(clean) > 2:
            loops.append(clean)
    return loops


def inset(path: QPainterPath, d: float) -> QPainterPath:
    if d <= 0:
        return path
    st = QPainterPathStroker()
    st.setWidth(2 * d)
    st.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return path.subtracted(st.createStroke(path)).simplified()


def chaikin(loop: list, iterations: int) -> list:
    """Corner-cutting smoothing of a closed polygon: rounds every corner so
    Blender's bevel never spikes out of an acute angle."""
    pts = loop
    for _ in range(iterations):
        out = []
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        pts = out
    return pts


def decimate(loop: list, min_step: float) -> list:
    out = []
    for pt in loop:
        if not out or math.hypot(pt[0] - out[-1][0], pt[1] - out[-1][1]) >= min_step:
            out.append(pt)
    return out


def circle_path(c: QPointF, r: float) -> QPainterPath:
    p = QPainterPath()
    p.addEllipse(c, r, r)
    return p


def slab(name: str, path: QPainterPath, z0: float, z1: float, bevel: float, mat, res: int = 5,
         collection=None, round_corners: float = 0.0, mesh_bevel: float = 0.0) -> bpy.types.Object:
    """Extrude a plan outline between heights z0..z1 with rounded edges.
    The outline is pre-inset by the bevel so the final footprint matches."""
    h = z1 - z0
    if mesh_bevel:
        bevel = 0.0          # round the edges with a Bevel modifier instead (robust on thin bands)
    bevel = min(bevel, h / 2 - 0.01) if h > 0.05 else 0
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.resolution_u = 1
    loops = path_loops(inset(path, bevel))
    if round_corners > 0:
        loops = [chaikin(decimate(lp, round_corners / 2), 3) for lp in loops]
    for loop in loops:
        sp = cu.splines.new("POLY")
        sp.points.add(len(loop) - 1)
        for p, (x, y) in zip(sp.points, loop):
            wx, wy = to_world(x, y)
            p.co = (wx, wy, 0, 1)
        sp.use_cyclic_u = True
    cu.extrude = max(0.0, (h / 2 - bevel)) * S
    cu.bevel_depth = bevel * S
    cu.bevel_resolution = res
    ob = bpy.data.objects.new(name, cu)
    ob.location = (0, 0, (z0 + z1) / 2 * S)
    (collection or bpy.context.scene.collection).objects.link(ob)
    if mat is not None:
        cu.materials.append(mat)
    if mesh_bevel:
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        mob = bpy.data.objects.new(name, me)
        mob.location = ob.location
        (collection or bpy.context.scene.collection).objects.link(mob)
        bpy.data.objects.remove(ob)
        mod = mob.modifiers.new("bevel", "BEVEL")
        mod.width = mesh_bevel * S
        mod.segments = 4
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(40)
        mod.harden_normals = False
        for poly in me.polygons:
            poly.use_smooth = True
        mob.modifiers.new("wn", "WEIGHTED_NORMAL").keep_sharp = True
        return mob
    return ob


def grip_drop(y_plan: float) -> float:
    """How far (plan units) the top surface falls away toward the grip tips."""
    t = max(0.0, min(1.0, (y_plan - 470.0) / 260.0))
    return 44.0 * t * t * (3 - 2 * t)


def shape_body(ob) -> bpy.types.Object:
    """Turn the extruded slab into a sculpted shell: voxel-remesh it into an
    even mesh, then bend the grips downward like a real controller."""
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    body = bpy.data.objects.new("body", me)
    body.location = ob.location
    bpy.context.scene.collection.objects.link(body)
    bpy.data.objects.remove(ob)
    rm = body.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = 2.4 * S
    rm.adaptivity = 0.0
    rm.use_smooth_shade = True
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(body.evaluated_get(dg))
    body.modifiers.clear()
    old = body.data
    body.data = me2
    bpy.data.meshes.remove(old)
    zc = body.location.z
    half = A.Z_FACE * S / 2
    for v in me2.vertices:
        y_plan = A._CY - v.co.y / S
        k = (v.co.z + half) / (2 * half)          # 0 at the bottom, 1 at the top
        v.co.z -= grip_drop(y_plan) * S * max(0.0, k)
    me2.update()
    for poly in me2.polygons:
        poly.use_smooth = True
    body.location.z = zc
    return body


def dish_mesh(name: str, c: QPointF, r: float, z_top: float, depth: float, mat, segs=96, rings=14):
    """Concave (bowl) disc: rim at z_top, centre `depth` lower."""
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cx, cy = to_world(c.x(), c.y())
    centre = bm.verts.new((cx, cy, (z_top - depth) * S))
    rings_v = []
    for j in range(1, rings + 1):
        rr = r * j / rings
        z = z_top - depth * (1 - (rr / r) ** 2)
        ring = [bm.verts.new((cx + rr * S * math.cos(2 * math.pi * i / segs),
                              cy + rr * S * math.sin(2 * math.pi * i / segs), z * S)) for i in range(segs)]
        rings_v.append(ring)
    for i in range(segs):
        bm.faces.new((centre, rings_v[0][i], rings_v[0][(i + 1) % segs]))
    for j in range(rings - 1):
        a, b = rings_v[j], rings_v[j + 1]
        for i in range(segs):
            bm.faces.new((a[i], b[i], b[(i + 1) % segs], a[(i + 1) % segs]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat)
    return ob


def faceted_cone(name: str, c: QPointF, r_top: float, r_bottom: float, z_top: float, depth: float, sides: int, mat):
    bpy.ops.mesh.primitive_cone_add(vertices=sides, radius1=r_bottom * S, radius2=r_top * S, depth=depth * S,
                                    location=(*to_world(c.x(), c.y()), (z_top - depth / 2) * S))
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(mat)
    return ob


def torus(name: str, c: QPointF, R: float, r: float, z: float, mat):
    bpy.ops.mesh.primitive_torus_add(major_radius=R * S, minor_radius=r * S, major_segments=96, minor_segments=12,
                                     location=(*to_world(c.x(), c.y()), z * S))
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.shade_smooth()
    ob.data.materials.append(mat)
    return ob


def text_obj(name: str, body: str, c: QPointF, size: float, z: float, mat):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size * S
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = 0.25 * S
    ob = bpy.data.objects.new(name, cu)
    ob.location = (*to_world(c.x(), c.y()), z * S)
    bpy.context.scene.collection.objects.link(ob)
    cu.materials.append(mat)
    return ob


# ---- materials -----------------------------------------------------------------------

def _rgb(hex_color: str) -> tuple:
    c = QColor(hex_color)
    # sRGB -> linear
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (lin(c.red()), lin(c.green()), lin(c.blue()), 1.0)


def principled(name, color, rough=0.5, metal=0.0, coat=0.0, aniso=0.0, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = _rgb(color)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    if aniso:
        bsdf.inputs["Anisotropic"].default_value = aniso
    if emission:
        bsdf.inputs["Emission Color"].default_value = _rgb(emission)
        bsdf.inputs["Emission Strength"].default_value = strength
    return m


def _bump(m, height_socket, strength: float, distance: float = 0.02):
    nt = m.node_tree
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(height_socket, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    return bump


def body_material(name, plastic, rubber, grip_mask_path, dark: bool):
    """Soft-touch plastic on the face, dotted rubber on the grips (planar
    mask projected from above), both with micro-texture bump."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.1, 0.125, 1)
    mapping.inputs["Location"].default_value = (0.5, 0.4625, 0)
    nt.links.new(tex.outputs["Object"], mapping.inputs["Vector"])
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(grip_mask_path)
    img.image.colorspace_settings.name = "Non-Color"
    img.extension = "EXTEND"
    nt.links.new(mapping.outputs["Vector"], img.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = _rgb(plastic)
    mix.inputs["B"].default_value = _rgb(rubber)
    nt.links.new(img.outputs["Color"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.46 if dark else 0.38
    rough.inputs["To Max"].default_value = 0.78
    nt.links.new(img.outputs["Color"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    # regular dot grid for the rubber (Voronoi with no randomness)
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 11.0
    vor.inputs["Randomness"].default_value = 0.0
    nt.links.new(tex.outputs["Object"], vor.inputs["Vector"])
    dots = nt.nodes.new("ShaderNodeMapRange")
    dots.inputs["From Min"].default_value = 0.18
    dots.inputs["From Max"].default_value = 0.32
    dots.inputs["To Min"].default_value = 1.0
    dots.inputs["To Max"].default_value = 0.0
    nt.links.new(vor.outputs["Distance"], dots.inputs["Value"])
    # fine grain for the plastic
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 900.0
    noise.inputs["Detail"].default_value = 2.0
    nt.links.new(tex.outputs["Object"], noise.inputs["Vector"])
    grain = nt.nodes.new("ShaderNodeMath")
    grain.operation = "MULTIPLY"
    grain.inputs[1].default_value = 0.25
    nt.links.new(noise.outputs["Fac"], grain.inputs[0])
    height = nt.nodes.new("ShaderNodeMix")
    height.data_type = "FLOAT"
    nt.links.new(img.outputs["Color"], height.inputs["Factor"])
    nt.links.new(grain.outputs["Value"], height.inputs["A"])
    nt.links.new(dots.outputs["Result"], height.inputs["B"])
    _bump(m, height.outputs["Result"], 0.6, 0.006)
    return m


def brushed_metal(name, color, rough):
    m = principled(name, color, rough=rough, metal=1.0, aniso=0.7)
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 260.0, 1.0)      # streaks run along X
    nt.links.new(tex.outputs["Object"], mp.inputs["Vector"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(mp.outputs["Vector"], noise.inputs["Vector"])
    _bump(m, noise.outputs["Fac"], 0.08, 0.002)
    return m


def ribbed_rubber(name, color, rough, ribs=72):
    """Rubber with radial ribs around the object's local Z axis (stick caps)."""
    m = principled(name, color, rough=rough)
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tex.outputs["Object"], sep.inputs["Vector"])
    ang = nt.nodes.new("ShaderNodeMath")
    ang.operation = "ARCTAN2"
    nt.links.new(sep.outputs["Y"], ang.inputs[0])
    nt.links.new(sep.outputs["X"], ang.inputs[1])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = float(ribs)
    nt.links.new(ang.outputs["Value"], mul.inputs[0])
    sin = nt.nodes.new("ShaderNodeMath")
    sin.operation = "SINE"
    nt.links.new(mul.outputs["Value"], sin.inputs[0])
    _bump(m, sin.outputs["Value"], 0.55, 0.006)
    return m


FINISHES = {
    "carbon": dict(
        plastic="#2c2f35", rubber="#191b1e", bumper="#c9ccd2", bumper_rough=0.28,
        gloss="#0c0d0f", trigger="#26292e", collar="#2a2d33", well="#111214",
        cap="#23262a", cap_dish="#1b1d20", dpad="#3d4148", dpad_cross="#565b63",
        button="#141518", small="#1a1c1f", glyph="#b7bbc2", guide_ring="#ffffff",
        guide_ring_strength=6.0, letter_strength=2.2, dark=True,
    ),
    "white": dict(
        plastic="#f2f3f5", rubber="#dcdee2", bumper="#e9ebee", bumper_rough=0.3,
        gloss="#fbfbfc", trigger="#eceef0", collar="#e7e9ec", well="#b7bac0",
        cap="#f1f2f4", cap_dish="#e6e8eb", dpad="#d7dade", dpad_cross="#eceef1",
        button="#f7f7f8", small="#f4f5f6", glyph="#6d7079", guide_ring="#7a7e86",
        guide_ring_strength=0.0, letter_strength=0.6, dark=False,
    ),
}


# ---- scene ------------------------------------------------------------------------------

def grip_mask() -> str:
    """Plan-view mask of the rubber grip panels (white = rubber)."""
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "_grip_mask.png")
    img = QImage(1000, 800, QImage.Format.Format_RGB32)
    img.fill(QColor("black"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("white"))
    p.drawPath(A.GRIPS)
    p.end()
    img.save(path)
    return path


def build(finish: str, mask_path: str) -> dict:
    """Create all objects for one finish. Returns {'caps': {'L': [objs], 'R': [objs]},
    'collars': [objs]}."""
    F = FINISHES[finish]
    dark = F["dark"]
    mat_body = body_material(f"{finish}_body", F["plastic"], F["rubber"], mask_path, dark)
    mat_bumper = brushed_metal(f"{finish}_bumper", F["bumper"], F["bumper_rough"])
    mat_gloss = principled(f"{finish}_gloss", F["gloss"], rough=0.12, coat=1.0)
    mat_trigger = principled(f"{finish}_trigger", F["trigger"], rough=0.45)
    mat_collar = principled(f"{finish}_collar", F["collar"], rough=0.4)
    mat_well = principled(f"{finish}_well", F["well"], rough=0.6)
    mat_dpad = brushed_metal(f"{finish}_dpad", F["dpad"], 0.32)
    mat_dpad_cross = brushed_metal(f"{finish}_dpadx", F["dpad_cross"], 0.28)
    mat_button = principled(f"{finish}_button", F["button"], rough=0.18, coat=1.0)
    mat_small = principled(f"{finish}_small", F["small"], rough=0.22, coat=0.6)
    mat_glyph = principled(f"{finish}_glyph", F["glyph"], rough=0.4)
    mat_chrome = principled(f"{finish}_chrome", "#d9dce1" if dark else "#f2f3f5", rough=0.12, metal=1.0)
    mat_ring = principled(f"{finish}_ring", F["guide_ring"], rough=0.3, emission=F["guide_ring"],
                          strength=F["guide_ring_strength"])
    mat_cap = ribbed_rubber(f"{finish}_cap", F["cap"], 0.62)
    mat_cap_dish = principled(f"{finish}_capdish", F["cap_dish"], rough=0.7)
    mat_cap_metal = principled(f"{finish}_capmetal", "#c8cbd0", rough=0.25, metal=1.0)

    Zf = A.Z_FACE
    shape_body(slab("body", A.SHELL, 0, Zf, 16, mat_body, res=8))
    for side, path in (("L", A.LB_PATH), ("R", A.RB_PATH)):
        slab(f"bumper_{side}", path, Zf - 10, A.Z_BUMPER[1], 0, mat_bumper, round_corners=6, mesh_bevel=3)
    slab("centre", A.CENTRE, Zf - 4, Zf + 1.5, 0, mat_gloss, round_corners=4, mesh_bevel=1.5)
    for side, path in (("L", A.LT_PATH), ("R", A.RT_PATH)):
        slab(f"trigger_{side}", path, A.Z_TRIGGER[0], A.Z_TRIGGER[1], 0, mat_trigger, round_corners=12,
             mesh_bevel=8)

    # D-pad: faceted metal dish on a short disc, raised cross on top
    slab("dpad_disc", circle_path(A.DPAD, A.DPAD_DISH_R), Zf - 2, A.Z_DPAD_DISC - 2, 2, mat_dpad)
    faceted_cone("dpad_dish", A.DPAD, A.DPAD_DISH_R, 16, A.Z_DPAD_DISC, 5, 16, mat_dpad)
    slab("dpad_cross", A.DPAD_CROSS, A.Z_DPAD_DISC - 3, A.Z_DPAD_CROSS, 0, mat_dpad_cross, round_corners=4,
         mesh_bevel=2.5)

    # face buttons with coloured letters
    for name in A.FACE_OFFSETS:
        c = A.face_center(name)
        slab(f"btn_{name}", circle_path(c, A.FACE_R), Zf - 2, A.Z_FACE_BTN, 6, mat_button, res=6)
        letter = principled(f"{finish}_letter_{name}", A.FACE_COLORS[name], rough=0.3,
                            emission=A.FACE_COLORS[name], strength=F["letter_strength"])
        text_obj(f"lbl_{name}", name, c, A.FACE_R * 1.25, A.Z_FACE_BTN + 0.1, letter)

    # View / Menu / Share
    for nm, c in (("view", A.VIEW), ("menu", A.MENU)):
        slab(f"btn_{nm}", circle_path(c, A.SMALL_R), Zf - 2, A.Z_SMALL, 4, mat_small)
    glyphs = QPainterPath()
    x, y = A.VIEW.x(), A.VIEW.y()
    for rx, ry in ((x - 5.5, y - 4), (x - 1.5, y - 1)):
        outer = QPainterPath()
        outer.addRoundedRect(rx, ry, 7, 6, 1, 1)
        inner = QPainterPath()
        inner.addRoundedRect(rx + 1.3, ry + 1.3, 4.4, 3.4, 0.5, 0.5)
        glyphs = glyphs.united(outer.subtracted(inner))
    x, y = A.MENU.x(), A.MENU.y()
    for dy in (-3.5, 0, 3.5):
        bar = QPainterPath()
        bar.addRoundedRect(x - 5.5, y + dy - 0.7, 11, 1.4, 0.7, 0.7)
        glyphs = glyphs.united(bar)
    slab("glyphs", glyphs, A.Z_SMALL - 0.2, A.Z_SMALL + 0.4, 0, mat_glyph)
    slab("btn_share", A.SHARE_PATH, Zf - 2, A.Z_SMALL - 1, 0, mat_small, mesh_bevel=2)

    # guide: chrome bezel, glossy dome, backlit ring
    slab("guide_bezel", circle_path(A.GUIDE, A.GUIDE_R), Zf - 2, A.Z_GUIDE, 3, mat_chrome)
    slab("guide_dome", circle_path(A.GUIDE, A.GUIDE_R - 4), A.Z_GUIDE - 3, A.Z_GUIDE + 2.5, 5, mat_gloss, res=6)
    torus("guide_ring", A.GUIDE, (A.GUIDE_R - 4) * 0.62, 1.3, A.Z_GUIDE + 2.2, mat_ring)

    # stick collars (raised ring + dark recess + shaft)
    collars = []
    caps = {"L": [], "R": []}
    for side, c in (("L", A.L_STICK), ("R", A.R_STICK)):
        ring = circle_path(c, A.STICK_WELL_R).subtracted(circle_path(c, A.STICK_WELL_R - 9))
        collars.append(slab(f"collar_{side}", ring, Zf - 2, A.Z_COLLAR, 3, mat_collar))
        collars.append(slab(f"well_{side}", circle_path(c, A.STICK_WELL_R - 8), Zf - 2, A.Z_COLLAR - 3, 0, mat_well))
        collars.append(slab(f"shaft_{side}", circle_path(c, 13), A.Z_COLLAR - 3, A.Z_CAP[0] + 4, 2, mat_well))
        # the cap: ribbed annulus, metal ring, concave dish
        annulus = circle_path(c, A.STICK_CAP_R).subtracted(circle_path(c, A.STICK_CAP_R - 16))
        cap = slab(f"cap_{side}", annulus, A.Z_CAP[0], A.Z_CAP[1], 4.5, mat_cap, res=6)
        # object origin at the stick centre so the rib pattern is radial
        wx, wy = to_world(c.x(), c.y())
        cap.data.transform(__import__("mathutils").Matrix.Translation((-wx, -wy, 0)))
        cap.location = (wx, wy, cap.location.z)
        caps[side].append(cap)
        caps[side].append(torus(f"capring_{side}", c, A.STICK_CAP_R - 16, 1.0, A.Z_CAP[1] - 0.8, mat_cap_metal))
        caps[side].append(dish_mesh(f"capdish_{side}", c, A.STICK_CAP_R - 16, A.Z_CAP[1] - 0.8, 6, mat_cap_dish))
    return {"caps": caps, "collars": collars}


def setup_scene(width: int, samples: int, dark: bool) -> None:
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.use_adaptive_sampling = True
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.compression = 90
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0 if dark else -0.25
    B = A.BOUNDS
    sc.render.resolution_x = width
    sc.render.resolution_y = int(round(width * B.height() / B.width()))
    sc.render.resolution_percentage = 100

    # camera = the 2.5D camera: distance CAM_D, tilted ALPHA toward the front
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 50.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.sensor_width = 50.0 * B.width() / A.CAM_D
    cam_data.shift_x = (B.center().x() - A._CX) / B.width()
    cam_data.shift_y = -(B.center().y() - A._CY) / B.width()
    cam_data.clip_start = 1.0
    cam_data.clip_end = 200.0
    cam = bpy.data.objects.new("cam", cam_data)
    D = A.CAM_D * S
    cam.location = (0, -D * math.sin(A.ALPHA), D * math.cos(A.ALPHA))
    cam.rotation_euler = (A.ALPHA, 0, 0)
    sc.collection.objects.link(cam)
    sc.camera = cam

    # studio lighting: big soft key from above-front, rim from behind, side fill
    def area(name, loc, rot, size, power, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size
        ld.energy = power
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = rot
        sc.collection.objects.link(lo)

    area("key", (0.0, 1.5, 9.5), (math.radians(-9), 0, 0), (8.0, 4.0), 850 if dark else 650)
    area("rim", (0.0, 7.0, 4.0), (math.radians(-60), 0, 0), (10.0, 1.5), 700 if dark else 300)
    area("fill_l", (-9.0, -2.0, 4.0), (math.radians(60), 0, math.radians(-70)), (3.0, 5.0), 160 if dark else 120,
         (0.92, 0.95, 1.0))
    area("fill_r", (9.0, -2.0, 4.0), (math.radians(60), 0, math.radians(70)), (3.0, 5.0), 120 if dark else 100,
         (1.0, 0.97, 0.94))
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.11, 0.115, 0.125, 1) if dark else (0.6, 0.62, 0.65, 1)
    bg.inputs["Strength"].default_value = 1.0
    sc.world = world

    # softbox: seen only in reflections, gives metal and gloss something to mirror
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 3.0, 11.0))
    box = bpy.context.active_object
    box.name = "softbox"
    box.scale = (22, 9, 1)
    box.rotation_euler = (math.radians(-20), 0, 0)
    em = bpy.data.materials.new("softbox")
    em.use_nodes = True
    nt = em.node_tree
    out = nt.nodes["Material Output"]
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 2.2 if dark else 1.4
    grad = nt.nodes.new("ShaderNodeTexGradient")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Generated"], grad.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.25, 0.25, 0.25, 1)
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    box.data.materials.append(em)
    box.visible_camera = False
    box.visible_diffuse = False
    box.visible_shadow = False

    # table: catches shadows only
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    table = bpy.context.active_object
    table.name = "table"
    table.is_shadow_catcher = True


def render(path: str) -> None:
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def crop_alpha(path: str, px_per_unit: float) -> list:
    """Crop a render to its non-transparent pixels. Returns the crop rect in
    screen units [x, y, w, h]."""
    img = QImage(path).convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    xs, ys = [], []
    step = 2
    for y in range(0, h, step):
        for x in range(0, w, step):
            if (img.pixel(x, y) >> 24) & 0xFF > 3:
                xs.append(x)
                ys.append(y)
    x0, x1 = max(0, min(xs) - 4), min(w, max(xs) + 5)
    y0, y1 = max(0, min(ys) - 4), min(h, max(ys) + 5)
    img.copy(x0, y0, x1 - x0, y1 - y0).save(path)
    B = A.BOUNDS
    return [B.x() + x0 / px_per_unit, B.y() + y0 / px_per_unit, (x1 - x0) / px_per_unit, (y1 - y0) / px_per_unit]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--width", type=int, default=2000)
    ap.add_argument("--quick", action="store_true", help="low-res preview renders")
    ap.add_argument("--finish", choices=["carbon", "white", "both"], default="both")
    args = ap.parse_args()
    if args.quick:
        args.samples, args.width = 24, 900

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    os.makedirs(OUT, exist_ok=True)
    mask = grip_mask()
    manifest_path = os.path.join(OUT, "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    B = A.BOUNDS
    px_per_unit = args.width / B.width()
    manifest.update({"version": 1, "bounds": [B.x(), B.y(), B.width(), B.height()],
                     "alpha_deg": math.degrees(A.ALPHA), "cam_d": A.CAM_D})
    manifest.setdefault("finishes", {})

    finishes = ["carbon", "white"] if args.finish == "both" else [args.finish]
    for finish in finishes:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        dark = FINISHES[finish]["dark"]
        setup_scene(args.width, args.samples, dark)
        parts = build(finish, mask)
        cap_objs = parts["caps"]["L"] + parts["caps"]["R"]
        entry = {"base": f"{finish}_base.png", "px_per_unit": px_per_unit, "caps": {}}

        for ob in cap_objs:
            ob.hide_render = True
        render(os.path.join(OUT, entry["base"]))
        print(f"[{finish}] base rendered", flush=True)

        # caps: render each alone; the collars catch its shadow
        everything = [ob for ob in bpy.context.scene.objects
                      if ob.type in ("MESH", "CURVE", "FONT") and ob.name not in ("softbox", "table")]
        for side in ("L", "R"):
            for ob in everything:
                ob.hide_render = True
            for ob in parts["caps"][side]:
                ob.hide_render = False
            for ob in parts["collars"]:
                ob.hide_render = False
                ob.is_shadow_catcher = True
            bpy.context.scene.objects["table"].hide_render = False
            fname = f"{finish}_cap_{side}.png"
            out = os.path.join(OUT, fname)
            render(out)
            rect = crop_alpha(out, px_per_unit)
            centre = A.L_STICK if side == "L" else A.R_STICK
            anchor = A.project(centre, A.Z_CAP[0])
            entry["caps"][side] = {"file": fname, "rect": rect, "anchor": [anchor.x(), anchor.y()]}
            for ob in parts["collars"]:
                ob.is_shadow_catcher = False
            print(f"[{finish}] cap {side} rendered", flush=True)
        manifest["finishes"][finish] = entry

        if finish == "carbon":
            for ob in everything:
                ob.hide_render = False
            bpy.ops.object.select_all(action="DESELECT")
            for ob in everything:
                ob.select_set(True)
            bpy.context.view_layer.objects.active = everything[0]
            try:
                bpy.ops.object.convert(target="MESH")
                bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "controller.glb"), export_format="GLB",
                                          use_selection=True, export_apply=True)
            except Exception as exc:  # export is a convenience; renders are what the app needs
                print("glTF export skipped:", exc)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    os.remove(mask)
    print("done", flush=True)
    del app


if __name__ == "__main__":
    main()
