"""
VirtualController
Thin, swappable abstraction around the actual virtual-controller backend.
Today the backend is `vgamepad`, a Python wrapper around ViGEmBus - the
open-source Windows kernel driver used by tools such as reWASD and
DS4Windows to expose a real XInput-compatible Xbox 360 controller to
Windows and any game or service that reads controller input.

Everything outside this file talks to the controller only through the
methods below, so the backend can be swapped without touching mapping,
UI, or profile code.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from logger import get_logger

log = get_logger("VirtualController")

try:
    import vgamepad as vg
    VGAMEPAD_AVAILABLE = True
    VGAMEPAD_IMPORT_ERROR = ""
except Exception as _exc:  # ImportError, or OSError when the client DLL can't load
    vg = None
    VGAMEPAD_AVAILABLE = False
    VGAMEPAD_IMPORT_ERROR = str(_exc)


class ControllerButton(Enum):
    A = auto()
    B = auto()
    X = auto()
    Y = auto()
    LB = auto()
    RB = auto()
    BACK = auto()
    START = auto()
    LS_CLICK = auto()
    RS_CLICK = auto()
    DPAD_UP = auto()
    DPAD_DOWN = auto()
    DPAD_LEFT = auto()
    DPAD_RIGHT = auto()
    GUIDE = auto()


_VG_BUTTON_MAP = {}
if VGAMEPAD_AVAILABLE:
    _B = vg.XUSB_BUTTON
    _VG_BUTTON_MAP = {
        ControllerButton.A: _B.XUSB_GAMEPAD_A,
        ControllerButton.B: _B.XUSB_GAMEPAD_B,
        ControllerButton.X: _B.XUSB_GAMEPAD_X,
        ControllerButton.Y: _B.XUSB_GAMEPAD_Y,
        ControllerButton.LB: _B.XUSB_GAMEPAD_LEFT_SHOULDER,
        ControllerButton.RB: _B.XUSB_GAMEPAD_RIGHT_SHOULDER,
        ControllerButton.BACK: _B.XUSB_GAMEPAD_BACK,
        ControllerButton.START: _B.XUSB_GAMEPAD_START,
        ControllerButton.LS_CLICK: _B.XUSB_GAMEPAD_LEFT_THUMB,
        ControllerButton.RS_CLICK: _B.XUSB_GAMEPAD_RIGHT_THUMB,
        ControllerButton.DPAD_UP: _B.XUSB_GAMEPAD_DPAD_UP,
        ControllerButton.DPAD_DOWN: _B.XUSB_GAMEPAD_DPAD_DOWN,
        ControllerButton.DPAD_LEFT: _B.XUSB_GAMEPAD_DPAD_LEFT,
        ControllerButton.DPAD_RIGHT: _B.XUSB_GAMEPAD_DPAD_RIGHT,
        ControllerButton.GUIDE: getattr(_B, "XUSB_GAMEPAD_GUIDE", None),
    }


@dataclass
class ControllerState:
    """Plain-data snapshot used by the UI - decoupled from vgamepad."""
    buttons: dict = field(default_factory=lambda: {b: False for b in ControllerButton})
    left_stick: tuple = (0.0, 0.0)     # x, y in [-1, 1], +y = up
    right_stick: tuple = (0.0, 0.0)
    left_trigger: float = 0.0          # 0..1
    right_trigger: float = 0.0
    connected: bool = False
    rumble: tuple = (0, 0)             # large, small motor 0..255 (from the game)


class VirtualControllerError(Exception):
    pass


class VirtualController:
    """
    Wraps a single virtual Xbox 360 controller instance.
    Thread-safe: input arrives from listener threads and the engine's tick
    thread while the UI reads snapshots from the Qt thread.

    Every setter only talks to the driver when the value actually changes,
    and `batch()` lets the tick loop push several changes as a single
    report.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._pad = None
        self._state = ControllerState()
        self._connected = False
        self._batch_depth = 0
        self._dirty = False
        self._rumble = (0, 0)
        self._rumble_time = 0.0
        self.last_error = ""

    @property
    def is_available(self) -> bool:
        return VGAMEPAD_AVAILABLE

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Create the virtual pad. Raises VirtualControllerError on failure
        (most commonly: ViGEmBus driver not installed)."""
        if not VGAMEPAD_AVAILABLE:
            self.last_error = (
                "The virtual controller library (vgamepad) could not be loaded"
                + (f": {VGAMEPAD_IMPORT_ERROR}" if VGAMEPAD_IMPORT_ERROR else ".")
            )
            raise VirtualControllerError(self.last_error)
        with self._lock:
            if self._pad is not None:
                return
            try:
                self._pad = vg.VX360Gamepad()
            except Exception as exc:  # vgamepad raises plain Exception on driver errors
                self._pad = None
                self._connected = False
                self._state.connected = False
                self.last_error = (
                    "The ViGEmBus driver is not installed or not running, so the "
                    f"virtual controller could not be created ({exc})."
                )
                raise VirtualControllerError(self.last_error) from exc
            self._connected = True
            self._state.connected = True
            self.last_error = ""
            try:
                self._pad.register_notification(callback_function=self._on_notification)
            except Exception as exc:
                log.debug("Rumble notifications unavailable: %s", exc)
            self._push_full_state()
            log.info("Virtual Xbox 360 controller connected via ViGEmBus.")

    def disconnect(self) -> None:
        with self._lock:
            if self._pad is None:
                return
            try:
                self.release_all()
                try:
                    self._pad.unregister_notification()
                except Exception:
                    pass
                del self._pad
            except Exception as exc:
                log.warning("Error while disconnecting virtual controller: %s", exc)
            finally:
                self._pad = None
                self._connected = False
                self._state.connected = False
                log.info("Virtual controller disconnected.")

    # No annotations: vgamepad compares this signature to its own dummy_callback.
    def _on_notification(self, client, target, large_motor, small_motor, led_number, user_data):
        self._rumble = (int(large_motor), int(small_motor))
        self._rumble_time = time.monotonic()

    # ---- Batching ------------------------------------------------------

    class _Batch:
        def __init__(self, owner: "VirtualController"):
            self.owner = owner

        def __enter__(self):
            self.owner._lock.acquire()
            self.owner._batch_depth += 1
            return self.owner

        def __exit__(self, *exc):
            o = self.owner
            try:
                o._batch_depth -= 1
                if o._batch_depth == 0 and o._dirty:
                    o._flush()
            finally:
                o._lock.release()
            return False

    def batch(self) -> "VirtualController._Batch":
        return VirtualController._Batch(self)

    def _changed(self) -> None:
        self._dirty = True
        if self._batch_depth == 0:
            self._flush()

    def _flush(self) -> None:
        self._dirty = False
        if self._pad is None:
            return
        try:
            self._pad.update()
        except Exception as exc:
            log.error("Virtual controller update failed: %s", exc)

    def _push_full_state(self) -> None:
        if self._pad is None:
            return
        try:
            for button, pressed in self._state.buttons.items():
                flag = _VG_BUTTON_MAP.get(button)
                if flag is None:
                    continue
                (self._pad.press_button if pressed else self._pad.release_button)(button=flag)
            self._pad.left_joystick_float(x_value_float=self._state.left_stick[0],
                                          y_value_float=self._state.left_stick[1])
            self._pad.right_joystick_float(x_value_float=self._state.right_stick[0],
                                           y_value_float=self._state.right_stick[1])
            self._pad.left_trigger_float(value_float=self._state.left_trigger)
            self._pad.right_trigger_float(value_float=self._state.right_trigger)
            self._pad.update()
        except Exception as exc:
            log.error("Failed to push state to virtual controller: %s", exc)

    # ---- Buttons -----------------------------------------------------

    def set_button(self, button: ControllerButton, pressed: bool) -> None:
        with self._lock:
            if self._state.buttons.get(button) == pressed:
                return
            self._state.buttons[button] = pressed
            if self._pad is not None:
                flag = _VG_BUTTON_MAP.get(button)
                if flag is not None:
                    (self._pad.press_button if pressed else self._pad.release_button)(button=flag)
            self._changed()

    # ---- Sticks --------------------------------------------------------

    def set_left_stick(self, x: float, y: float) -> None:
        x, y = _clamp(x, -1, 1), _clamp(y, -1, 1)
        with self._lock:
            if self._state.left_stick == (x, y):
                return
            self._state.left_stick = (x, y)
            if self._pad is not None:
                self._pad.left_joystick_float(x_value_float=x, y_value_float=y)
            self._changed()

    def set_right_stick(self, x: float, y: float) -> None:
        x, y = _clamp(x, -1, 1), _clamp(y, -1, 1)
        with self._lock:
            if self._state.right_stick == (x, y):
                return
            self._state.right_stick = (x, y)
            if self._pad is not None:
                self._pad.right_joystick_float(x_value_float=x, y_value_float=y)
            self._changed()

    # ---- Triggers (0..1 analog) -----------------------------------------

    def set_left_trigger(self, value: float) -> None:
        value = _clamp(value, 0, 1)
        with self._lock:
            if self._state.left_trigger == value:
                return
            self._state.left_trigger = value
            if self._pad is not None:
                self._pad.left_trigger_float(value_float=value)
            self._changed()

    def set_right_trigger(self, value: float) -> None:
        value = _clamp(value, 0, 1)
        with self._lock:
            if self._state.right_trigger == value:
                return
            self._state.right_trigger = value
            if self._pad is not None:
                self._pad.right_trigger_float(value_float=value)
            self._changed()

    # ---- Feedback ------------------------------------------------------

    def get_vibration(self) -> tuple[int, int]:
        """(large_motor, small_motor) 0..255 as last requested by the game."""
        return self._rumble

    # ---- Bulk operations -------------------------------------------------

    def release_all(self) -> None:
        """Zero every button, stick, and trigger."""
        with self.batch():
            for button in ControllerButton:
                self.set_button(button, False)
            self.set_left_stick(0.0, 0.0)
            self.set_right_stick(0.0, 0.0)
            self.set_left_trigger(0.0)
            self.set_right_trigger(0.0)

    def snapshot(self) -> ControllerState:
        with self._lock:
            return ControllerState(
                buttons=dict(self._state.buttons),
                left_stick=self._state.left_stick,
                right_stick=self._state.right_stick,
                left_trigger=self._state.left_trigger,
                right_trigger=self._state.right_trigger,
                connected=self._connected,
                rumble=self._rumble,
            )


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))
