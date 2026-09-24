import math

from mouse_controller import MouseController, MouseProfile, shape_output, response_curve_point


def _run(ctrl, dx, dy, dt=0.008, ticks=40):
    out = (0.0, 0.0)
    for _ in range(ticks):
        ctrl.add_delta(dx, dy)
        out = ctrl.compute(dt)
    return out


def test_mouse_up_pushes_stick_up():
    c = MouseController(MouseProfile(smoothing=0, deadzone=0))
    x, y = _run(c, 0, -2)          # moving the mouse away = negative screen y
    assert y > 0 and abs(x) < 1e-9


def test_output_is_rate_independent():
    p = MouseProfile(smoothing=0, deadzone=0)
    a = _run(MouseController(p), 4, 0, dt=0.008)      # 500 px/s at 125 Hz
    b = _run(MouseController(p), 2, 0, dt=0.004)      # 500 px/s at 250 Hz
    assert math.isclose(a[0], b[0], rel_tol=1e-6)


def test_decays_to_center_without_motion():
    c = MouseController(MouseProfile(smoothing=0.5, deadzone=0.02))
    _run(c, 5, 0)
    for _ in range(200):
        x, y = c.compute(0.008)
    assert (x, y) == (0.0, 0.0)


def test_invert_and_clamp():
    c = MouseController(MouseProfile(smoothing=0, invert_x=True, max_output=0.5))
    x, _ = _run(c, 50, 0)
    assert math.isclose(x, -0.5)


def test_precision_scale():
    p = MouseProfile(smoothing=0, deadzone=0, precision_scale=0.5)
    normal = _run(MouseController(p), 2, 0)
    c = MouseController(p)
    c.precision = True
    precise = _run(c, 2, 0)
    assert math.isclose(precise[0], normal[0] * 0.5, rel_tol=1e-6)


def test_shape_output_deadzone_and_anti_deadzone():
    assert shape_output(0.01, 0, 0.05, 0.0, 1.0) == (0.0, 0.0)
    x, _ = shape_output(0.06, 0, 0.05, 0.25, 1.0)
    assert 0.25 < x < 0.27
    # diagonal keeps its direction
    x, y = shape_output(0.5, 0.5, 0.0, 0.0, 1.0)
    assert math.isclose(x, y)


def test_curve_preview_monotonic():
    p = MouseProfile(response_curve="quadratic", deadzone=0.0)
    pts = [response_curve_point(i / 10, p) for i in range(11)]
    assert pts == sorted(pts) and math.isclose(pts[-1], 1.0)


def test_from_dict_rejects_bad_types():
    p = MouseProfile.from_dict({"sensitivity_x": "fast", "invert_y": 1, "response_curve": "zigzag", "bogus": 3})
    assert p.sensitivity_x == 1.0 and p.invert_y is False and p.response_curve == "linear"
