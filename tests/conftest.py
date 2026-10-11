import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    """Keep every test away from the real %APPDATA%."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    yield tmp_path


@pytest.fixture(scope="session")
def app():
    """One QApplication for the whole test session (Qt dislikes re-creating it)."""
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def fake_driver(monkeypatch):
    """A stand-in for vgamepad and for the installed driver.

    Patches `virtual_controller` so that connecting creates a fake pad
    which records what happens to it, and lets the test decide what the
    "installed driver" supports:

        fake_driver.driver["max"]      highest model the driver announces (0 = stock driver)
        fake_driver.driver["default"]  the driver's machine-wide default model
        fake_driver.events             ("set_vid", vid) / ("set_pid", pid) /
                                       ("plug", class name, vid, pid) / ("unplug", pid) / ("update",)
        fake_driver.fail               make plugging in fail, like a missing driver

    The fake behaves like vgamepad in the one way that matters here: the
    base class allocates the target and plugs it in inside its constructor.
    """
    import types

    import virtual_controller

    handle = types.SimpleNamespace(events=[], driver={"max": 0, "default": 0}, fail=False)
    events = handle.events

    class Target:
        def __init__(self):
            self.vid, self.pid = 0x045E, 0x028E

    def set_vid(target, vid):
        events.append(("set_vid", vid))
        target.vid = vid

    def set_pid(target, pid):
        events.append(("set_pid", pid))
        target.pid = pid

    vcli = types.SimpleNamespace(
        vigem_target_x360_alloc=lambda: Target(), vigem_target_set_vid=set_vid, vigem_target_set_pid=set_pid)

    class VX360Gamepad:
        def __init__(self):
            self._devicep = self.target_alloc()
            if handle.fail:
                raise AssertionError("The virtual device could not connect to ViGEmBus.")
            self._plugged = True
            events.append(("plug", type(self).__name__, self._devicep.vid, self._devicep.pid))

        def __del__(self):
            if getattr(self, "_plugged", False):
                events.append(("unplug", self._devicep.pid))

        def target_alloc(self):
            return vcli.vigem_target_x360_alloc()

        def press_button(self, button):
            pass

        def release_button(self, button):
            pass

        def left_joystick_float(self, x_value_float, y_value_float):
            pass

        def right_joystick_float(self, x_value_float, y_value_float):
            pass

        def left_trigger_float(self, value_float):
            pass

        def right_trigger_float(self, value_float):
            pass

        def update(self):
            events.append(("update",))

        def register_notification(self, callback_function):
            pass

        def unregister_notification(self):
            pass

    monkeypatch.setattr(virtual_controller, "vg", types.SimpleNamespace(VX360Gamepad=VX360Gamepad))
    monkeypatch.setattr(virtual_controller, "_vcli", vcli)
    monkeypatch.setattr(virtual_controller, "VGAMEPAD_AVAILABLE", True)
    monkeypatch.setattr(virtual_controller, "_VG_BUTTON_MAP", {})
    monkeypatch.setattr(virtual_controller, "_model_pad_class", None)
    monkeypatch.setattr(virtual_controller, "read_driver_max_model", lambda: handle.driver["max"])
    monkeypatch.setattr(virtual_controller, "read_driver_default_model", lambda: handle.driver["default"])
    handle.plugs = lambda: [e for e in events if e[0] == "plug"]
    return handle
