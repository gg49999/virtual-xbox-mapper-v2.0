from mapping_manager import MappingManager
from profile_manager import Profile
from virtual_controller import VirtualController, ControllerButton
from keyboard_controller import RampProfile
from mouse_controller import MouseProfile


def _mm(bindings=None, **kw):
    vc = VirtualController()
    mm = MappingManager(vc)
    p = Profile(name="T", bindings=bindings if bindings is not None else {
        "A": ["space", "enter"], "LEFT_STICK_UP": ["w"], "LEFT_STICK_RIGHT": ["d"],
        "RIGHT_TRIGGER": ["mouse_left"], "WALK_MODIFIER": ["alt"], "RB": ["wheel_up"],
    }, **kw)
    mm.load_profile(p)
    mm.apply_tuning(MouseProfile(), RampProfile(enabled=False))
    return mm, vc


def test_w_moves_left_stick_up():
    mm, vc = _mm()
    mm.on_input("w", True)
    mm.tick(0.01)
    assert vc.snapshot().left_stick == (0.0, 1.0)


def test_two_keys_same_button_do_not_release_each_other():
    mm, vc = _mm()
    mm.on_input("space", True)
    mm.on_input("enter", True)
    mm.on_input("space", False)
    assert vc.snapshot().buttons[ControllerButton.A] is True
    mm.on_input("enter", False)
    assert vc.snapshot().buttons[ControllerButton.A] is False


def test_autorepeat_is_ignored():
    mm, vc = _mm()
    mm.on_input("space", True)
    mm.on_input("space", True)
    mm.on_input("space", False)
    assert vc.snapshot().buttons[ControllerButton.A] is False


def test_diagonal_is_circular():
    mm, vc = _mm()
    mm.on_input("w", True)
    mm.on_input("d", True)
    mm.tick(0.01)
    x, y = vc.snapshot().left_stick
    assert abs((x * x + y * y) ** 0.5 - 1.0) < 1e-6


def test_walk_modifier_scales_left_stick():
    mm, vc = _mm()
    mm.on_input("w", True)
    mm.on_input("alt", True)
    mm.tick(0.01)
    assert abs(vc.snapshot().left_stick[1] - 0.5) < 1e-6


def test_toggle_mode():
    mm, vc = _mm(modes={"A": {"mode": "toggle"}})
    for pressed in (True, False):
        mm.on_input("space", pressed)
    assert vc.snapshot().buttons[ControllerButton.A] is True
    for pressed in (True, False):
        mm.on_input("space", pressed)
    assert vc.snapshot().buttons[ControllerButton.A] is False


def test_turbo_mode_pulses():
    mm, vc = _mm(modes={"A": {"mode": "turbo", "rate": 10}})
    mm.on_input("space", True, now=100.0)
    states = set()
    for i in range(1, 20):
        mm.tick(0.01, now=100.0 + i * 0.01)
        states.add(vc.snapshot().buttons[ControllerButton.A])
    assert states == {True, False}
    mm.on_input("space", False)
    assert vc.snapshot().buttons[ControllerButton.A] is False


def test_wheel_pulse_releases():
    mm, vc = _mm()
    mm.on_pulse("wheel_up")
    assert vc.snapshot().buttons[ControllerButton.RB] is True
    import time
    mm.tick(0.01, now=time.monotonic() + 1)
    assert vc.snapshot().buttons[ControllerButton.RB] is False


def test_trigger_strength_and_disable():
    mm, vc = _mm()
    mm.apply_tuning(MouseProfile(), RampProfile(enabled=False), right_trigger=0.6)
    mm.on_input("mouse_left", True)
    assert abs(vc.snapshot().right_trigger - 0.6) < 1e-6
    mm.set_enabled(False)
    assert vc.snapshot().right_trigger == 0.0
    mm.on_input("mouse_left", True)
    assert vc.snapshot().right_trigger == 0.0


def test_mouse_only_while_active():
    mm, vc = _mm()
    mm.on_mouse_delta(50, 0)
    mm.tick(0.01)
    assert vc.snapshot().right_stick == (0.0, 0.0)
    mm.mouse_active = True
    mm.on_mouse_delta(5, 0)
    mm.tick(0.01)
    assert vc.snapshot().right_stick[0] > 0


def test_rumble_callback_matches_vgamepad_signature():
    # vgamepad rejects callbacks whose inspect.signature differs from this.
    from inspect import signature

    def dummy_callback(client, target, large_motor, small_motor, led_number, user_data):
        pass

    assert signature(VirtualController()._on_notification) == signature(dummy_callback)
