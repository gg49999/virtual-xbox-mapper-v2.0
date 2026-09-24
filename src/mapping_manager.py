"""
MappingManager
The heart of the translation pipeline:

    Keyboard/Mouse -> InputManager -> MappingManager -> VirtualController

It owns the active Profile and decides, on every input event and every
engine tick, what the virtual controller's state should be.

* Each controller target tracks the *set* of inputs currently driving
  it, so two keys bound to the same button never release each other.
* Targets can behave as hold (default), toggle, or turbo.
* Stick directions are ramped through DigitalStickAxis pairs; mouse
  motion is blended into the stick chosen by the profile.
* Mouse-wheel "presses" are delivered as short pulses.

All public methods are thread-safe: key events arrive on pynput's
listener threads, mouse motion on the GUI thread (Raw Input) and ticks
on the engine's timing thread.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Dict, List, Optional, Set

from logger import get_logger
from virtual_controller import VirtualController, ControllerButton
from profile_manager import Profile
from keyboard_controller import DigitalStickAxis, RampProfile
from mouse_controller import MouseController, MouseProfile

log = get_logger("Mapping")

BUTTON_TARGETS = {
    "A": ControllerButton.A, "B": ControllerButton.B,
    "X": ControllerButton.X, "Y": ControllerButton.Y,
    "LB": ControllerButton.LB, "RB": ControllerButton.RB,
    "BACK": ControllerButton.BACK, "START": ControllerButton.START,
    "GUIDE": ControllerButton.GUIDE,
    "LS_CLICK": ControllerButton.LS_CLICK, "RS_CLICK": ControllerButton.RS_CLICK,
    "DPAD_UP": ControllerButton.DPAD_UP, "DPAD_DOWN": ControllerButton.DPAD_DOWN,
    "DPAD_LEFT": ControllerButton.DPAD_LEFT, "DPAD_RIGHT": ControllerButton.DPAD_RIGHT,
}

PULSE_SECONDS = 0.06   # how long a wheel notch "holds" its target


class MappingManager:
    def __init__(self, controller: VirtualController):
        self.controller = controller
        self.profile: Optional[Profile] = None
        self._enabled = True
        self._lock = threading.RLock()

        self._input_to_targets: Dict[str, List[str]] = {}
        self._held_inputs: Set[str] = set()
        self._target_sources: Dict[str, Set[str]] = {}
        self._target_output: Dict[str, bool] = {}
        self._toggle_state: Dict[str, bool] = {}
        self._turbo_start: Dict[str, float] = {}
        self._pulses: Dict[str, float] = {}      # input code -> release time

        ramp = RampProfile()
        self.left_x = DigitalStickAxis(ramp)
        self.left_y = DigitalStickAxis(ramp)
        self.right_x = DigitalStickAxis(ramp)
        self.right_y = DigitalStickAxis(ramp)

        self.mouse = MouseController(MouseProfile())
        self.mouse_active = False            # only feed mouse motion while captured
        self.mouse_target = "right_stick"
        self.circular_sticks = True
        self.walk_scale = 0.5
        self.left_trigger_strength = 1.0
        self.right_trigger_strength = 1.0

    # ---- Enable / disable ------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            if self._enabled == enabled:
                return
            self._enabled = enabled
            self._reset_runtime_state()
            self.controller.release_all()

    # ---- Profile / config ------------------------------------------------

    def load_profile(self, profile: Profile) -> None:
        with self._lock:
            self.profile = profile
            self.mouse_target = profile.mouse_target
            self._rebuild_input_map()
            self._reset_runtime_state()
            self.controller.release_all()
        log.info("Active profile: %s", profile.name)

    def refresh_bindings(self) -> None:
        """Call after the active profile's bindings/modes were edited."""
        with self._lock:
            if self.profile:
                self.mouse_target = self.profile.mouse_target
            self._rebuild_input_map()
            self._reset_runtime_state()
            self.controller.release_all()

    def apply_tuning(self, mouse: MouseProfile, ramp: RampProfile, *, walk_scale: float = 0.5,
                     left_trigger: float = 1.0, right_trigger: float = 1.0,
                     circular_sticks: bool = True) -> None:
        with self._lock:
            self.mouse.set_profile(mouse)
            for axis in (self.left_x, self.left_y, self.right_x, self.right_y):
                axis.set_profile(ramp)
            self.walk_scale = max(0.05, min(1.0, walk_scale))
            self.left_trigger_strength = max(0.05, min(1.0, left_trigger))
            self.right_trigger_strength = max(0.05, min(1.0, right_trigger))
            self.circular_sticks = circular_sticks
            for target, on in self._target_output.items():
                if on and target in ("LEFT_TRIGGER", "RIGHT_TRIGGER"):
                    self._apply_output(target, True)

    def _rebuild_input_map(self) -> None:
        self._input_to_targets.clear()
        if not self.profile:
            return
        for target, codes in self.profile.bindings.items():
            for code in codes:
                self._input_to_targets.setdefault(code, []).append(target)

    def _reset_runtime_state(self) -> None:
        self._held_inputs.clear()
        self._target_sources.clear()
        self._target_output.clear()
        self._toggle_state.clear()
        self._turbo_start.clear()
        self._pulses.clear()
        for axis in (self.left_x, self.left_y, self.right_x, self.right_y):
            axis.reset()
        self.mouse.reset()
        self.mouse.precision = False

    # ---- Queries ---------------------------------------------------------

    def find_conflicts(self, input_code: str, exclude_target: Optional[str] = None) -> List[str]:
        if not self.profile:
            return []
        return self.profile.find_conflicts(input_code, exclude_target)

    def is_target_active(self, target: str) -> bool:
        return self._target_output.get(target, False)

    def is_bound(self, input_code: str) -> bool:
        return input_code in self._input_to_targets

    # ---- Input entry points ----------------------------------------------

    def on_input(self, code: str, pressed: bool, now: Optional[float] = None) -> None:
        """A key or mouse button changed state."""
        with self._lock:
            if not self._enabled or not self.profile:
                return
            if pressed:
                if code in self._held_inputs:
                    return  # OS auto-repeat
                self._held_inputs.add(code)
            else:
                if code not in self._held_inputs:
                    return
                self._held_inputs.discard(code)
            targets = self._input_to_targets.get(code)
            if not targets:
                return
            now = time.monotonic() if now is None else now
            with self.controller.batch():
                for target in targets:
                    self._update_target(target, code, pressed, now)

    # Kept for API compatibility with the v1 pipeline.
    def on_key_event(self, code: str, pressed: bool) -> None:
        self.on_input(code, pressed)

    def on_mouse_button_event(self, code: str, pressed: bool) -> None:
        self.on_input(code, pressed)

    def on_pulse(self, code: str, duration: float = PULSE_SECONDS) -> None:
        """A momentary input such as a mouse-wheel notch."""
        with self._lock:
            if not self._enabled or code not in self._input_to_targets:
                return
            now = time.monotonic()
            if code not in self._held_inputs:
                self.on_input(code, True, now)
            self._pulses[code] = now + duration

    def on_mouse_delta(self, dx: float, dy: float) -> None:
        if self._enabled and self.mouse_active:
            self.mouse.add_delta(dx, dy)

    # ---- Target logic --------------------------------------------------------

    def _update_target(self, target: str, code: str, pressed: bool, now: float) -> None:
        sources = self._target_sources.setdefault(target, set())
        was_active = bool(sources)
        if pressed:
            sources.add(code)
        else:
            sources.discard(code)
        is_active = bool(sources)
        if was_active == is_active:
            return

        mode = self.profile.mode_for(target) if self.profile else "hold"
        if mode == "toggle":
            if is_active:  # rising edge flips the latch
                state = not self._toggle_state.get(target, False)
                self._toggle_state[target] = state
                self._apply_output(target, state)
        elif mode == "turbo":
            if is_active:
                self._turbo_start[target] = now
                self._apply_output(target, True)
            else:
                self._turbo_start.pop(target, None)
                self._apply_output(target, False)
        else:
            self._apply_output(target, is_active)

    def _apply_output(self, target: str, on: bool) -> None:
        self._target_output[target] = on
        button = BUTTON_TARGETS.get(target)
        if button is not None:
            self.controller.set_button(button, on)
        elif target == "LEFT_TRIGGER":
            self.controller.set_left_trigger(self.left_trigger_strength if on else 0.0)
        elif target == "RIGHT_TRIGGER":
            self.controller.set_right_trigger(self.right_trigger_strength if on else 0.0)
        elif target == "LEFT_STICK_LEFT":
            self.left_x.set_negative_held(on)
        elif target == "LEFT_STICK_RIGHT":
            self.left_x.set_positive_held(on)
        elif target == "LEFT_STICK_UP":
            self.left_y.set_positive_held(on)
        elif target == "LEFT_STICK_DOWN":
            self.left_y.set_negative_held(on)
        elif target == "RIGHT_STICK_LEFT":
            self.right_x.set_negative_held(on)
        elif target == "RIGHT_STICK_RIGHT":
            self.right_x.set_positive_held(on)
        elif target == "RIGHT_STICK_UP":
            self.right_y.set_positive_held(on)
        elif target == "RIGHT_STICK_DOWN":
            self.right_y.set_negative_held(on)
        elif target == "PRECISION_AIM":
            self.mouse.precision = on
        # WALK_MODIFIER is read in tick().

    # ---- Periodic update ---------------------------------------------------

    def tick(self, dt: float, now: Optional[float] = None) -> None:
        """Advance ramps, turbo, pulses and mouse processing by `dt` seconds."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if not self._enabled:
                return
            with self.controller.batch():
                for code, release_at in list(self._pulses.items()):
                    if now >= release_at:
                        del self._pulses[code]
                        self.on_input(code, False, now)

                if self.profile:
                    for target, start in self._turbo_start.items():
                        period = 1.0 / max(1.0, self.profile.turbo_rate(target))
                        on = ((now - start) % period) < period / 2
                        if self._target_output.get(target) != on:
                            self._apply_output(target, on)

                lx, ly = self.left_x.update(dt), self.left_y.update(dt)
                if self._target_output.get("WALK_MODIFIER"):
                    lx, ly = lx * self.walk_scale, ly * self.walk_scale
                rx, ry = self.right_x.update(dt), self.right_y.update(dt)

                mx, my = self.mouse.compute(dt) if self.mouse_active else (0.0, 0.0)
                if self.mouse_target == "right_stick":
                    rx, ry = rx + mx, ry + my
                elif self.mouse_target == "left_stick":
                    lx, ly = lx + mx, ly + my

                lx, ly = self._limit(lx, ly)
                rx, ry = self._limit(rx, ry)
                self.controller.set_left_stick(lx, ly)
                self.controller.set_right_stick(rx, ry)

    def _limit(self, x: float, y: float) -> tuple[float, float]:
        if self.circular_sticks:
            mag = math.hypot(x, y)
            if mag > 1.0:
                return x / mag, y / mag
        return max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))

    # ---- Safety --------------------------------------------------------------

    def emergency_release(self) -> None:
        with self._lock:
            self._reset_runtime_state()
            self.controller.release_all()
        log.warning("Emergency release - all inputs cleared.")
