"""
InputManager
Owns the global keyboard and mouse listeners (pynput) and mouse capture.

Emits normalised events (see keycodes.py for the code format):
  - on_input(code, pressed)    keys and mouse buttons
  - on_pulse(code)             momentary inputs (mouse-wheel notches)
  - on_mouse_delta(dx, dy)     relative motion, only while captured

While the mouse is captured the cursor is parked in the middle of the
game window. Motion comes from Raw Input when available (precise and
independent of the cursor), otherwise from the pynput hook by
re-centering the cursor after every move.

Callbacks fire on listener threads (keyboard/mouse buttons) or the GUI
thread (Raw Input); consumers must be thread-safe.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import keycodes
import win_input
from logger import get_logger
from win_input import CursorLock, RawMouse, IS_WINDOWS

log = get_logger("InputManager")

try:
    from pynput import keyboard, mouse
    PYNPUT_AVAILABLE = True
except Exception:  # ImportError, or no display server on Linux
    keyboard = mouse = None
    PYNPUT_AVAILABLE = False


class InputManager:
    def __init__(self):
        self.on_input: Optional[Callable[[str, bool], None]] = None
        self.on_pulse: Optional[Callable[[str], None]] = None
        self.on_mouse_delta: Optional[Callable[[float, float], None]] = None

        self._keyboard_listener = None
        self._mouse_listener = None
        self._cursor = CursorLock()
        self._raw = RawMouse(self._emit_delta)
        self._raw_active = False
        self._captured = False
        self._lock = threading.Lock()
        self._running = False
        self._last_pos = None

    @property
    def available(self) -> bool:
        return PYNPUT_AVAILABLE

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if not PYNPUT_AVAILABLE:
            raise RuntimeError(
                "Global keyboard/mouse capture is unavailable (the 'pynput' "
                "package is missing or no desktop session was found)."
            )
        if self._running:
            return
        self._keyboard_listener = keyboard.Listener(
            on_press=self._handle_key_press, on_release=self._handle_key_release
        )
        self._mouse_listener = mouse.Listener(
            on_click=self._handle_click, on_move=self._handle_move, on_scroll=self._handle_scroll
        )
        self._keyboard_listener.daemon = True
        self._mouse_listener.daemon = True
        self._keyboard_listener.start()
        self._mouse_listener.start()
        self._running = True
        log.info("Global keyboard/mouse listeners started.")

    def stop(self) -> None:
        self.set_mouse_captured(False)
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener:
                try:
                    listener.stop()
                except Exception:
                    pass
        self._keyboard_listener = self._mouse_listener = None
        if self._running:
            log.info("Global keyboard/mouse listeners stopped.")
        self._running = False

    # ---- Mouse capture ---------------------------------------------------

    @property
    def mouse_captured(self) -> bool:
        return self._captured

    @property
    def using_raw_input(self) -> bool:
        return self._raw_active

    def set_mouse_captured(self, captured: bool, *, hide_cursor: bool = True,
                           use_raw_input: bool = True) -> None:
        """Must be called on the GUI thread (Raw Input registration)."""
        with self._lock:
            if captured == self._captured:
                return
            self._captured = captured
            self._last_pos = None
            if captured:
                self._raw_active = bool(use_raw_input and IS_WINDOWS and self._raw.start())
                self._cursor.start(hide_cursor=hide_cursor, clip=self._raw_active)
            else:
                self._cursor.stop()
                if self._raw_active:
                    self._raw.stop()
                self._raw_active = False
        log.info("Mouse capture %s%s.", "ENABLED" if captured else "released",
                 " (Raw Input)" if captured and self._raw_active else "")

    def maintain_capture(self, release_on_focus_change: bool) -> bool:
        """Called periodically. Returns False if capture should end."""
        if not self._captured:
            return True
        return self._cursor.maintain(release_on_focus_change)

    # ---- pynput callbacks ------------------------------------------------

    def _emit(self, code: Optional[str], pressed: bool) -> None:
        if code and self.on_input:
            try:
                self.on_input(code, pressed)
            except Exception:
                log.exception("Input handler failed for %s", code)

    def _handle_key_press(self, key) -> None:
        self._emit(keycodes.from_pynput_key(key, prefer_vk=IS_WINDOWS), True)

    def _handle_key_release(self, key) -> None:
        self._emit(keycodes.from_pynput_key(key, prefer_vk=IS_WINDOWS), False)

    def _handle_click(self, x, y, button, pressed) -> None:
        self._emit(keycodes.from_pynput_button(button), pressed)

    def _handle_scroll(self, x, y, dx, dy) -> None:
        if not self.on_pulse:
            return
        for code in keycodes.wheel_codes(dx, dy):
            try:
                self.on_pulse(code)
            except Exception:
                log.exception("Wheel handler failed")

    def _handle_move(self, x, y) -> None:
        if not self._captured or self._raw_active:
            return
        if win_input.user32 is None:
            # No way to re-center the cursor (non-Windows dev builds):
            # derive motion from successive positions instead.
            last, self._last_pos = self._last_pos, (x, y)
            if last is not None:
                self._emit_delta(float(x - last[0]), float(y - last[1]))
            return
        cx, cy = self._cursor.center
        dx, dy = x - cx, y - cy
        if dx or dy:
            self._emit_delta(float(dx), float(dy))
            self._cursor.recenter()

    def _emit_delta(self, dx: float, dy: float) -> None:
        if self._captured and self.on_mouse_delta:
            self.on_mouse_delta(dx, dy)
