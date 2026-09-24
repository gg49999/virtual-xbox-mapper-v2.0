"""
SettingsManager
Application-wide preferences (as opposed to per-profile bindings and
tuning, which live in ProfileManager). Stored as JSON under
%APPDATA%\\VirtualXboxMapper\\settings.json.

Loading is defensive: unknown keys are kept, missing keys are filled from
DEFAULT_SETTINGS, and values of the wrong type are replaced by the default
so a hand-edited or older file can never crash the app.
"""
from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict

from logger import get_logger

log = get_logger("Settings")

SETTINGS_VERSION = 2

DEFAULT_SETTINGS: Dict[str, Any] = {
    "general": {
        "start_minimized": False,
        "start_with_windows": False,
        "minimize_to_tray": True,          # closing the window keeps the app in the tray
        "auto_enable_controller": True,    # connect the virtual pad on launch
        "emulation_on_launch": True,
        "auto_load_last_profile": True,
        "last_profile": "Default",
        "show_osd": True,                  # on-screen overlay for hotkey actions
        "tray_notifications": False,
    },
    # Defaults for profiles that don't override mouse tuning.
    "mouse": {
        "sensitivity_x": 1.0,
        "sensitivity_y": 1.0,
        "deadzone": 0.02,
        "anti_deadzone": 0.0,
        "response_curve": "linear",
        "smoothing": 0.35,
        "acceleration": 0.0,
        "max_output": 1.0,
        "invert_x": False,
        "invert_y": False,
        "raw_input": False,
        "precision_scale": 0.5,
    },
    # Defaults for profiles that don't override keyboard tuning.
    "keyboard": {
        "analog_simulation": True,
        "ramp_up_ms": 120,
        "ramp_down_ms": 90,
        "acceleration_curve": "ease_out",
        "deadzone": 0.0,
        "digital_stick_strength": 1.0,
        "walk_scale": 0.5,
    },
    "controller": {
        "tick_rate_hz": 125,
        "circular_sticks": True,
        "controller_enabled": True,
    },
    "capture": {
        "hide_cursor": True,
        "release_on_focus_change": True,
        "use_raw_input": True,
    },
    "hotkeys": {
        "toggle_emulation": "f9",
        "toggle_mouse_capture": "f8",
        "emergency_release": "f10",
        "open_app": "ctrl+alt+x",
        "next_profile": "ctrl+alt+right",
        "prev_profile": "ctrl+alt+left",
    },
    "appearance": {
        "theme": "dark",                   # dark | light | system
        "accent": "green",
        "diagram_style": "model3d",        # model3d | vector (2.5D) | photo | custom
        "show_callouts": True,
        "ui_refresh_hz": 60,
        "custom_image_path": "",
        "custom_calibration_path": "",
        "photo_calibration_path": "",
    },
    "advanced": {
        "log_level": "INFO",
    },
    "window": {
        "width": 1280,
        "height": 800,
        "x": None,
        "y": None,
        "maximized": False,
        "last_page": 0,
        "splitter": None,
    },
}

# Allowed values for enumerated settings.
CHOICES = {
    ("appearance", "theme"): ("dark", "light", "system"),
    ("appearance", "diagram_style"): ("model3d", "vector", "photo", "custom"),
    ("advanced", "log_level"): ("DEBUG", "INFO", "WARNING", "ERROR"),
}


def _coerce(default: Any, value: Any) -> Any:
    """Return `value` if its type is compatible with `default`, else `default`."""
    if default is None:
        return value
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, (int, float)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return type(default)(value) if isinstance(default, float) else int(value)
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    if isinstance(default, dict):
        return value if isinstance(value, dict) else default
    return value


class SettingsManager:
    def __init__(self, path: str | None = None, seed_path: str | None = None):
        self.seed_path = seed_path
        if path is None:
            from paths import roaming_dir
            path = os.path.join(roaming_dir(), "settings.json")
        self.path = path
        self.dir = os.path.dirname(path)
        os.makedirs(self.dir, exist_ok=True)
        self.settings: Dict[str, Any] = copy.deepcopy(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            # First run: start from the packaged defaults if present, so an
            # installer can ship customised defaults without code changes.
            if self.seed_path and os.path.exists(self.seed_path):
                try:
                    with open(self.seed_path, "r", encoding="utf-8") as f:
                        seed = json.load(f)
                    if isinstance(seed, dict):
                        self.settings = self._merge_defaults(seed)
                except (OSError, ValueError) as exc:
                    log.warning("Ignoring bundled default settings: %s", exc)
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("settings root is not an object")
            self.settings = self._merge_defaults(loaded)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            log.error("Failed to load settings (%s); using defaults.", exc)
            try:
                os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass
            self.settings = copy.deepcopy(DEFAULT_SETTINGS)
            self.save()

    @staticmethod
    def _merge_defaults(loaded: Dict) -> Dict:
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        for section, values in loaded.items():
            if section == "_version":
                continue
            if section in merged and isinstance(merged[section], dict):
                if not isinstance(values, dict):
                    continue
                for key, value in values.items():
                    default = merged[section].get(key)
                    value = _coerce(default, value)
                    allowed = CHOICES.get((section, key))
                    if allowed and value not in allowed:
                        value = default
                    merged[section][key] = value
            else:
                merged[section] = values
        # v1 stored a stale capture hotkey inside "mouse"; it now lives in hotkeys.
        merged["mouse"].pop("capture_hotkey", None)
        merged["mouse"].pop("active_profile_bindings", None)
        merged["controller"].pop("deadzone", None)
        merged["controller"].pop("trigger_threshold", None)
        merged["controller"].pop("vibration_enabled", None)
        return merged

    def save(self) -> None:
        try:
            data = dict(self.settings)
            data["_version"] = SETTINGS_VERSION
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("Failed to save settings: %s", exc)

    def get(self, section: str, key: str, default: Any = None) -> Any:
        value = self.settings.get(section, {}).get(key, None)
        if value is None:
            fallback = DEFAULT_SETTINGS.get(section, {}).get(key, None)
            return default if fallback is None else fallback
        return value

    def set(self, section: str, key: str, value: Any, autosave: bool = True) -> None:
        self.settings.setdefault(section, {})[key] = value
        if autosave:
            self.save()

    def section(self, section: str) -> Dict[str, Any]:
        return self.settings.setdefault(section, copy.deepcopy(DEFAULT_SETTINGS.get(section, {})))

    def reset_section(self, section: str) -> None:
        self.settings[section] = copy.deepcopy(DEFAULT_SETTINGS.get(section, {}))
        self.save()

    def reset_to_default(self) -> None:
        window = self.settings.get("window")
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        if isinstance(window, dict):
            self.settings["window"] = window
        self.save()
