import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtGui import QColor, QImage, QPainter, QTransform  # noqa: E402




def test_every_control_hit_tests_to_itself(app):
    from ui import controller_art as art
    for target in ("A", "B", "X", "Y", "BACK", "START", "GUIDE", "LS_CLICK", "RS_CLICK",
                   "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"):
        assert art.hit_test(art.ANCHORS[target]) == target, target
    for target in ("LB", "RB", "LEFT_TRIGGER", "RIGHT_TRIGGER"):
        assert art.hit_test(art.ANCHORS[target]) == target, target


def test_projection_has_depth(app):
    from ui import controller_art as art
    from PyQt6.QtCore import QPointF
    c = QPointF(500, 430)
    # raising a point moves it up the screen; the front edge sits lower than the back
    assert art.project(c, 100).y() < art.project(c, 0).y()
    assert art.project(QPointF(500, 700), 0).y() > art.project(QPointF(500, 150), 0).y()


@pytest.mark.parametrize("dark", [True, False])
def test_renders_both_finishes(app, dark):
    from ui.controller_art import ControllerArt
    from virtual_controller import ControllerState, ControllerButton
    state = ControllerState()
    state.buttons[ControllerButton.A] = True
    state.left_stick = (0.5, -0.5)
    state.right_trigger = 0.4
    img = QImage(800, 560, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#202020"))
    p = QPainter(img)
    ControllerArt().paint(p, QTransform().scale(0.8, 0.8), dark, state,
                          active=lambda t: t == "A", emphasis=lambda t: "selected" if t == "Y" else "",
                          accent=QColor("#6ccb5f"), text=QColor("white"))
    p.end()
    # the controller body covers the centre of the image
    assert img.pixelColor(400, 330) != QColor("#202020")


def test_3d_renderer_draws_or_falls_back(app):
    from ui import controller_art_3d
    from ui.controller_diagram import ControllerDiagram
    d = ControllerDiagram()
    d.resize(900, 600)
    ok = d.use_vector("3d")
    assert ok == controller_art_3d.available()
    assert type(d._art).__name__ == ("ControllerArt3D" if ok else "ControllerArt")
    assert not d.grab().isNull()
    d.use_vector("2.5d")
    assert type(d._art).__name__ == "ControllerArt"
