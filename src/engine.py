"""
Engine
Owns the whole input -> controller pipeline and is the only object the
UI talks to:

    InputManager ──▶ HotkeyManager ──▶ MappingManager ──▶ VirtualController
          ▲                                  ▲
       pynput / Raw Input              timing thread (tick)

Input and timing callbacks arrive on background threads. Anything that
must touch Qt objects is re-emitted through a Qt signal, which Qt queues
onto the GUI thread automatically - so no widget is ever touched from a
listener thread.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from logger import get_logger
from settings_manager import SettingsManager
from profile_manager import ProfileManager, Profile
from virtual_controller import VirtualController, VirtualControllerError
from mapping_manager import MappingManager
from input_manager import InputManager
from hotkey_manager import HotkeyManager
from mouse_controller import MouseProfile
from keyboard_controller import RampProfile
import keycodes

log = get_logger("Engine")

HOTKEY_ACTIONS = {
    "toggle_mouse_capture": "Capture / release mouse",
    "toggle_emulation": "Turn emulation on / off",
    "emergency_release": "Emergency release",
    "open_app": "Show this window",
    "next_profile": "Next profile",
    "prev_profile": "Previous profile",
}

TICK_RATES = (60, 125, 250, 500, 1000)


class _WinTimerResolution:
    """Ask Windows for 1 ms timer resolution while the engine runs so the
    tick thread can hit rates above 64 Hz."""

    def __init__(self):
        self._active = False

    def __enter__(self):
        if sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.WinDLL("winmm").timeBeginPeriod(1)
                self._active = True
            except Exception:
                pass
        return self

    def __exit__(self, *exc):
        if self._active:
            try:
                import ctypes
                ctypes.WinDLL("winmm").timeEndPeriod(1)
            except Exception:
                pass
        return False


class Engine(QObject):
    connection_changed = pyqtSignal(bool, str)
    emulation_changed = pyqtSignal(bool)
    capture_changed = pyqtSignal(bool)
    profile_changed = pyqtSignal(str)      # active profile loaded or its bindings changed
    tuning_changed = pyqtSignal()          # active profile's tuning changed
    profiles_changed = pyqtSignal()        # the list of profiles changed
    input_event = pyqtSignal(str, bool)
    notify = pyqtSignal(str, str, str)     # title, message, level
    osd = pyqtSignal(str, str)             # text, kind
    show_window_requested = pyqtSignal()

    _hotkey_fired = pyqtSignal(str)
    _capture_lost = pyqtSignal()

    def __init__(self, settings: SettingsManager, profiles: ProfileManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.profiles = profiles
        self.controller = VirtualController()
        self.mapping = MappingManager(self.controller)
        self.input = InputManager()
        self.hotkeys = HotkeyManager()

        self.suspended = False           # True while a binding dialog captures keys
        self._down: set[str] = set()
        self.input_error = ""
        self.measured_tick_hz = 0.0
        self._tick_thread: Optional[threading.Thread] = None
        self._tick_stop = threading.Event()
        self._tick_hz = self._valid_rate(settings.get("controller", "tick_rate_hz", 125))

        self.input.on_input = self._on_input
        self.input.on_pulse = self._on_pulse
        self.input.on_mouse_delta = self.mapping.on_mouse_delta
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_active_profile)
        self._hotkey_fired.connect(self._run_hotkey_action)
        self._capture_lost.connect(self._on_capture_lost)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._load_initial_profile()
        self.apply_controller_settings()
        if self.settings.get("general", "auto_enable_controller", True):
            self.connect_controller()
        else:
            self.connection_changed.emit(False, "Virtual controller is not connected.")
        self.mapping.set_enabled(bool(self.settings.get("general", "emulation_on_launch", True)))
        self.emulation_changed.emit(self.mapping.enabled)
        try:
            self.input.start()
            self.input_error = ""
        except RuntimeError as exc:
            self.input_error = str(exc)
            log.error("Input capture unavailable: %s", exc)
        self.reload_hotkeys()
        self._start_ticker()

    def shutdown(self) -> None:
        log.info("Engine shutting down...")
        self.flush_pending_save()
        self._stop_ticker()
        try:
            self.input.stop()
        except Exception as exc:
            log.warning("Input shutdown error: %s", exc)
        try:
            self.controller.release_all()
            self.controller.disconnect()
        except Exception as exc:
            log.warning("Controller shutdown error: %s", exc)

    # ---- Timing thread ---------------------------------------------------

    @staticmethod
    def _valid_rate(hz) -> int:
        try:
            hz = int(hz)
        except (TypeError, ValueError):
            return 125
        return max(30, min(1000, hz))

    @property
    def tick_rate(self) -> int:
        return self._tick_hz

    def set_tick_rate(self, hz: int) -> None:
        self._tick_hz = self._valid_rate(hz)
        self.settings.set("controller", "tick_rate_hz", self._tick_hz)

    def _start_ticker(self) -> None:
        self._tick_stop.clear()
        self._tick_thread = threading.Thread(target=self._tick_loop, name="EngineTick", daemon=True)
        self._tick_thread.start()

    def _stop_ticker(self) -> None:
        self._tick_stop.set()
        if self._tick_thread:
            self._tick_thread.join(timeout=1.0)
            self._tick_thread = None

    def _tick_loop(self) -> None:
        with _WinTimerResolution():
            last = time.perf_counter()
            next_at = last
            count, window_start = 0, last
            focus_check_at = last
            while not self._tick_stop.is_set():
                period = 1.0 / self._tick_hz
                now = time.perf_counter()
                dt = now - last
                last = now
                try:
                    self.mapping.tick(min(dt, 0.1))
                except Exception:
                    log.exception("Mapping tick failed")
                if now >= focus_check_at:
                    focus_check_at = now + 0.1
                    release = self.settings.get("capture", "release_on_focus_change", True)
                    if self.input.mouse_captured and not self.input.maintain_capture(release):
                        self._capture_lost.emit()
                count += 1
                if now - window_start >= 1.0:
                    self.measured_tick_hz = count / (now - window_start)
                    count, window_start = 0, now
                next_at += period
                delay = next_at - time.perf_counter()
                if delay < -5 * period:          # fell far behind; don't try to catch up
                    next_at = time.perf_counter()
                elif delay > 0:
                    self._tick_stop.wait(delay)

    # ------------------------------------------------------------------
    # Input routing (background threads)
    # ------------------------------------------------------------------

    def _on_input(self, code: str, pressed: bool) -> None:
        # Report state changes only (not OS auto-repeat) to the UI.
        if pressed != (code in self._down):
            (self._down.add if pressed else self._down.discard)(code)
            self.input_event.emit(code, pressed)
        if self.suspended:
            return
        if not keycodes.is_mouse(code) and self.hotkeys.feed(code, pressed):
            return
        self.mapping.on_input(code, pressed)

    def _on_pulse(self, code: str) -> None:
        self.input_event.emit(code, True)
        if not self.suspended:
            self.mapping.on_pulse(code)

    def set_suspended(self, suspended: bool) -> None:
        """Pause the controller output while the user is capturing a new
        binding, so the key they press doesn't also reach the game."""
        self.suspended = suspended
        if suspended:
            self.mapping.emergency_release()
        self.hotkeys.reset()

    # ------------------------------------------------------------------
    # Virtual controller
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.controller.is_connected

    def connect_controller(self) -> bool:
        try:
            self.controller.connect()
            self.connection_changed.emit(True, "Virtual Xbox 360 controller connected.")
            return True
        except VirtualControllerError as exc:
            log.error("%s", exc)
            self.connection_changed.emit(False, str(exc))
            return False

    def disconnect_controller(self) -> None:
        self.controller.disconnect()
        self.connection_changed.emit(False, "Virtual controller disconnected.")

    def reconnect_controller(self) -> bool:
        self.controller.disconnect()
        return self.connect_controller()

    # ------------------------------------------------------------------
    # Emulation & capture
    # ------------------------------------------------------------------

    @property
    def emulation_enabled(self) -> bool:
        return self.mapping.enabled

    def set_emulation(self, enabled: bool) -> None:
        if enabled == self.mapping.enabled:
            return
        self.mapping.set_enabled(enabled)
        if not enabled:
            self.set_capture(False)
        self.settings.set("controller", "controller_enabled", enabled)
        self.emulation_changed.emit(enabled)
        self.osd.emit("Emulation on" if enabled else "Emulation off", "on" if enabled else "off")

    def toggle_emulation(self) -> None:
        self.set_emulation(not self.mapping.enabled)

    @property
    def captured(self) -> bool:
        return self.input.mouse_captured

    def set_capture(self, captured: bool) -> None:
        if captured == self.input.mouse_captured:
            return
        if captured and not self.mapping.enabled:
            self.notify.emit("Emulation is off", "Turn emulation on before capturing the mouse.", "warning")
            return
        if captured and not self.input.running:
            self.notify.emit("Mouse capture unavailable", self.input_error or "Input capture is not running.", "error")
            return
        cap = self.settings.section("capture")
        self.mapping.mouse.reset()
        self.input.set_mouse_captured(
            captured,
            hide_cursor=bool(cap.get("hide_cursor", True)),
            use_raw_input=bool(cap.get("use_raw_input", True)),
        )
        self.mapping.mouse_active = captured
        self.capture_changed.emit(captured)
        release = keycodes.combo_display(self.settings.get("hotkeys", "toggle_mouse_capture", "f8"))
        self.osd.emit(f"Mouse captured — press {release} to release" if captured else "Mouse released",
                      "on" if captured else "off")

    def toggle_capture(self) -> None:
        self.set_capture(not self.input.mouse_captured)

    def _on_capture_lost(self) -> None:
        if self.input.mouse_captured:
            log.info("Foreground window changed; releasing mouse capture.")
            self.set_capture(False)

    def emergency_release(self) -> None:
        self.set_capture(False)
        self.mapping.emergency_release()
        self.hotkeys.reset()
        self.osd.emit("All inputs released", "warn")

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------

    def reload_hotkeys(self) -> list[str]:
        combos = {a: self.settings.get("hotkeys", a, "") for a in HOTKEY_ACTIONS}
        callbacks = {a: (lambda a=a: self._hotkey_fired.emit(a)) for a in HOTKEY_ACTIONS}
        return self.hotkeys.set_bindings(combos, callbacks)

    def _run_hotkey_action(self, action: str) -> None:
        if action == "toggle_mouse_capture":
            self.toggle_capture()
        elif action == "toggle_emulation":
            self.toggle_emulation()
        elif action == "emergency_release":
            self.emergency_release()
        elif action == "open_app":
            self.show_window_requested.emit()
        elif action == "next_profile":
            self.cycle_profile(1)
        elif action == "prev_profile":
            self.cycle_profile(-1)

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    @property
    def profile(self) -> Optional[Profile]:
        return self.mapping.profile

    def _load_initial_profile(self) -> None:
        available = self.profiles.list_profiles()
        last = self.settings.get("general", "last_profile", "Default")
        if not self.settings.get("general", "auto_load_last_profile", True):
            last = "Default"
        name = last if last in available else (available[0] if available else None)
        if name is None or not self.load_profile(name, announce=False):
            profile = Profile(name=self.profiles.unique_name("Default"))
            self.profiles.save(profile)
            self._activate(profile, announce=False)

    def load_profile(self, name: str, announce: bool = True) -> bool:
        self.flush_pending_save()
        try:
            profile = self.profiles.load(name)
        except (OSError, ValueError) as exc:
            log.error("Could not load profile %s: %s", name, exc)
            self.notify.emit("Couldn't load profile", f"'{name}': {exc}", "error")
            return False
        self._activate(profile, announce)
        return True

    def _activate(self, profile: Profile, announce: bool) -> None:
        self.mapping.load_profile(profile)
        self.apply_profile_tuning()
        self.settings.set("general", "last_profile", profile.name)
        self.profile_changed.emit(profile.name)
        if announce:
            self.osd.emit(f"Profile: {profile.name}", "profile")

    def cycle_profile(self, step: int) -> None:
        names = self.profiles.list_profiles()
        if not names:
            return
        current = self.profile.name if self.profile else names[0]
        idx = names.index(current) if current in names else 0
        self.load_profile(names[(idx + step) % len(names)])

    def effective_mouse(self, profile: Optional[Profile] = None) -> MouseProfile:
        profile = profile or self.profile
        base = dict(self.settings.section("mouse"))
        if profile:
            base.update(profile.mouse)
        return MouseProfile.from_dict(base)

    def effective_keyboard(self, profile: Optional[Profile] = None) -> dict:
        profile = profile or self.profile
        base = dict(self.settings.section("keyboard"))
        if profile:
            base.update(profile.keyboard)
        return base

    def apply_profile_tuning(self) -> None:
        profile = self.profile
        kb = self.effective_keyboard(profile)
        trig = profile.triggers if profile else {}
        self.mapping.apply_tuning(
            self.effective_mouse(profile),
            RampProfile.from_settings(kb),
            walk_scale=float(kb.get("walk_scale", 0.5)),
            left_trigger=float(trig.get("left_strength", 1.0)),
            right_trigger=float(trig.get("right_strength", 1.0)),
            circular_sticks=bool(self.settings.get("controller", "circular_sticks", True)),
        )

    def apply_controller_settings(self) -> None:
        self._tick_hz = self._valid_rate(self.settings.get("controller", "tick_rate_hz", 125))
        if self.profile:
            self.apply_profile_tuning()

    def save_active_profile(self) -> bool:
        if not self.profile:
            return False
        try:
            self.profiles.save(self.profile)
            return True
        except (OSError, ValueError) as exc:
            self.notify.emit("Couldn't save profile", str(exc), "error")
            return False

    def bindings_edited(self) -> None:
        """The UI changed the active profile's bindings or modes."""
        self.mapping.refresh_bindings()
        self.save_active_profile()
        self.profile_changed.emit(self.profile.name if self.profile else "")

    def tuning_edited(self) -> None:
        """The UI changed the active profile's tuning values."""
        self.apply_profile_tuning()
        self._save_timer.start()      # debounce disk writes while a slider is dragged
        self.tuning_changed.emit()

    def flush_pending_save(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.save_active_profile()
