"""
ProfileManager
A profile is a complete, named layout: keyboard/mouse -> controller
bindings, per-control behaviour (hold / toggle / turbo), and the mouse,
keyboard and trigger tuning that goes with it. Profiles are plain JSON
files under %APPDATA%\\VirtualXboxMapper\\profiles\\<name>.json so they
are easy to back up, share, or hand-edit.
"""
from __future__ import annotations

import copy
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from logger import get_logger

log = get_logger("Profiles")

PROFILE_VERSION = 2
MAX_NAME_LENGTH = 48

# Controller targets a binding can point to, in display order.
BUTTON_TARGETS = ["A", "B", "X", "Y", "LB", "RB", "BACK", "START", "GUIDE", "LS_CLICK", "RS_CLICK"]
DPAD_TARGETS = ["DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"]
LEFT_STICK_TARGETS = ["LEFT_STICK_UP", "LEFT_STICK_DOWN", "LEFT_STICK_LEFT", "LEFT_STICK_RIGHT"]
RIGHT_STICK_TARGETS = ["RIGHT_STICK_UP", "RIGHT_STICK_DOWN", "RIGHT_STICK_LEFT", "RIGHT_STICK_RIGHT"]
TRIGGER_TARGETS = ["LEFT_TRIGGER", "RIGHT_TRIGGER"]
MODIFIER_TARGETS = ["WALK_MODIFIER", "PRECISION_AIM"]

CONTROLLER_TARGETS = (
    BUTTON_TARGETS + DPAD_TARGETS + LEFT_STICK_TARGETS + RIGHT_STICK_TARGETS
    + TRIGGER_TARGETS + MODIFIER_TARGETS
)

TARGET_NAMES = {
    "A": "A Button", "B": "B Button", "X": "X Button", "Y": "Y Button",
    "LB": "Left Bumper", "RB": "Right Bumper",
    "BACK": "View Button", "START": "Menu Button", "GUIDE": "Xbox Button",
    "LS_CLICK": "Left Stick Click", "RS_CLICK": "Right Stick Click",
    "DPAD_UP": "D-Pad Up", "DPAD_DOWN": "D-Pad Down",
    "DPAD_LEFT": "D-Pad Left", "DPAD_RIGHT": "D-Pad Right",
    "LEFT_STICK_UP": "Left Stick Up", "LEFT_STICK_DOWN": "Left Stick Down",
    "LEFT_STICK_LEFT": "Left Stick Left", "LEFT_STICK_RIGHT": "Left Stick Right",
    "RIGHT_STICK_UP": "Right Stick Up", "RIGHT_STICK_DOWN": "Right Stick Down",
    "RIGHT_STICK_LEFT": "Right Stick Left", "RIGHT_STICK_RIGHT": "Right Stick Right",
    "LEFT_TRIGGER": "Left Trigger", "RIGHT_TRIGGER": "Right Trigger",
    "WALK_MODIFIER": "Walk Modifier", "PRECISION_AIM": "Precision Aim",
}

TARGET_DESCRIPTIONS = {
    "WALK_MODIFIER": "While held, the keyboard-driven left stick is scaled down "
                     "(e.g. to walk instead of run). Set the scale on the Tuning page.",
    "PRECISION_AIM": "While held, mouse sensitivity is reduced for precise aiming. "
                     "Set the scale on the Tuning page.",
    "GUIDE": "Some games and the Xbox app reserve the Xbox button; it may not "
             "reach cloud-streamed games.",
}

TARGET_GROUPS = [
    ("Buttons", BUTTON_TARGETS),
    ("D-Pad", DPAD_TARGETS),
    ("Left Stick", LEFT_STICK_TARGETS),
    ("Right Stick", RIGHT_STICK_TARGETS),
    ("Triggers", TRIGGER_TARGETS),
    ("Modifiers", MODIFIER_TARGETS),
]

BINDING_MODES = ("hold", "toggle", "turbo")
MOUSE_TARGETS = ("right_stick", "left_stick", "none")

DEFAULT_BINDINGS: Dict[str, List[str]] = {
    "LEFT_STICK_UP": ["w"],
    "LEFT_STICK_DOWN": ["s"],
    "LEFT_STICK_LEFT": ["a"],
    "LEFT_STICK_RIGHT": ["d"],
    "A": ["space"],
    "B": ["shift"],
    "X": ["e"],
    "Y": ["q"],
    "LS_CLICK": ["ctrl"],
    "LEFT_TRIGGER": ["mouse_right"],
    "RIGHT_TRIGGER": ["mouse_left"],
    "RB": ["r"],
    "LB": ["f"],
    "DPAD_UP": ["up"],
    "DPAD_DOWN": ["down"],
    "DPAD_LEFT": ["left"],
    "DPAD_RIGHT": ["right"],
    "START": ["enter"],
    "BACK": ["backspace"],
}

_INVALID_NAME_CHARS = set('<>:"/\\|?*')
_RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def validate_profile_name(name: str) -> Optional[str]:
    """Return an error message, or None if `name` is usable as a profile name."""
    if name is None or not name.strip():
        return "Enter a profile name."
    name = name.strip()
    if len(name) > MAX_NAME_LENGTH:
        return f"Profile names can be at most {MAX_NAME_LENGTH} characters."
    if any(c in _INVALID_NAME_CHARS or ord(c) < 32 for c in name):
        return 'Profile names can\'t contain any of these characters: < > : " / \\ | ? *'
    if name.endswith("."):
        return "Profile names can't end with a period."
    if name.lower() in _RESERVED_NAMES:
        return "That name is reserved by Windows."
    return None


@dataclass
class Profile:
    name: str = "Default"
    description: str = ""
    # controller_target -> list of input codes
    bindings: Dict[str, List[str]] = field(default_factory=lambda: copy.deepcopy(DEFAULT_BINDINGS))
    # controller_target -> {"mode": "toggle"} / {"mode": "turbo", "rate": 10.0}
    modes: Dict[str, Dict] = field(default_factory=dict)
    mouse: Dict = field(default_factory=dict)      # overrides for settings["mouse"]
    keyboard: Dict = field(default_factory=dict)   # overrides for settings["keyboard"]
    triggers: Dict = field(default_factory=dict)   # left_strength / right_strength
    mouse_target: str = "right_stick"
    modified: float = 0.0

    def to_dict(self) -> dict:
        return {
            "version": PROFILE_VERSION,
            "name": self.name,
            "description": self.description,
            "bindings": {t: list(c) for t, c in self.bindings.items() if c},
            "modes": copy.deepcopy(self.modes),
            "mouse": dict(self.mouse),
            "keyboard": dict(self.keyboard),
            "triggers": dict(self.triggers),
            "mouse_target": self.mouse_target,
            "modified": self.modified,
        }

    @staticmethod
    def from_dict(d: dict) -> "Profile":
        """Build a profile from untrusted JSON, dropping anything malformed."""
        if not isinstance(d, dict):
            raise ValueError("Profile file does not contain a JSON object.")
        raw_bindings = d.get("bindings", DEFAULT_BINDINGS)
        if not isinstance(raw_bindings, dict):
            raise ValueError("Profile 'bindings' must be an object.")
        bindings: Dict[str, List[str]] = {}
        for target, codes in raw_bindings.items():
            if target not in CONTROLLER_TARGETS:
                log.warning("Ignoring unknown controller target '%s' in profile.", target)
                continue
            if isinstance(codes, str):
                codes = [codes]
            if not isinstance(codes, list):
                continue
            clean = []
            for c in codes:
                if isinstance(c, str) and c.strip() and c.strip().lower() not in clean:
                    clean.append(c.strip().lower())
            if clean:
                bindings[target] = clean

        modes: Dict[str, Dict] = {}
        raw_modes = d.get("modes", {})
        if isinstance(raw_modes, dict):
            for target, spec in raw_modes.items():
                if target in CONTROLLER_TARGETS and isinstance(spec, dict) and spec.get("mode") in BINDING_MODES:
                    entry = {"mode": spec["mode"]}
                    if spec["mode"] == "turbo":
                        try:
                            entry["rate"] = max(1.0, min(30.0, float(spec.get("rate", 10.0))))
                        except (TypeError, ValueError):
                            entry["rate"] = 10.0
                    if entry["mode"] != "hold":
                        modes[target] = entry

        def _dict(key):
            v = d.get(key, {})
            return dict(v) if isinstance(v, dict) else {}

        name = d.get("name", "Default")
        if not isinstance(name, str) or validate_profile_name(name):
            name = "Imported Profile"
        mouse_target = d.get("mouse_target", "right_stick")
        if mouse_target not in MOUSE_TARGETS:
            mouse_target = "right_stick"
        description = d.get("description", "")
        modified = d.get("modified", 0.0)
        return Profile(
            name=name.strip(),
            description=description if isinstance(description, str) else "",
            bindings=bindings,
            modes=modes,
            mouse=_dict("mouse"),
            keyboard=_dict("keyboard"),
            triggers=_dict("triggers"),
            mouse_target=mouse_target,
            modified=float(modified) if isinstance(modified, (int, float)) else 0.0,
        )

    # ---- Bindings --------------------------------------------------------

    def inputs_for(self, target: str) -> List[str]:
        return list(self.bindings.get(target, []))

    def bind(self, target: str, input_code: str, replace_others_of_input: bool = False) -> None:
        """Assign `input_code` to `target`. If replace_others_of_input, the
        input is first removed from every other target."""
        if replace_others_of_input:
            for other_target, codes in self.bindings.items():
                if other_target != target and input_code in codes:
                    codes.remove(input_code)
        codes = self.bindings.setdefault(target, [])
        if input_code not in codes:
            codes.append(input_code)

    def unbind(self, target: str, input_code: str) -> None:
        if target in self.bindings and input_code in self.bindings[target]:
            self.bindings[target].remove(input_code)

    def clear(self, target: str) -> None:
        self.bindings.pop(target, None)

    def find_conflicts(self, input_code: str, exclude_target: Optional[str] = None) -> List[str]:
        return [
            t for t, codes in self.bindings.items()
            if input_code in codes and t != exclude_target
        ]

    def binding_count(self) -> int:
        return sum(len(c) for c in self.bindings.values())

    # ---- Modes -----------------------------------------------------------

    def mode_for(self, target: str) -> str:
        return self.modes.get(target, {}).get("mode", "hold")

    def turbo_rate(self, target: str) -> float:
        return float(self.modes.get(target, {}).get("rate", 10.0))

    def set_mode(self, target: str, mode: str, rate: Optional[float] = None) -> None:
        if mode not in BINDING_MODES or mode == "hold":
            self.modes.pop(target, None)
            return
        entry = {"mode": mode}
        if mode == "turbo":
            entry["rate"] = float(rate if rate is not None else self.turbo_rate(target))
        self.modes[target] = entry


class ProfileManager:
    def __init__(self, profiles_dir: Optional[str] = None, seed_dir: Optional[str] = None):
        if profiles_dir is None:
            from paths import profiles_dir as _pd
            profiles_dir = _pd()
        self.dir = profiles_dir
        os.makedirs(self.dir, exist_ok=True)
        self._seed(seed_dir)

    # ---- Paths -----------------------------------------------------------

    def _path_for(self, name: str) -> str:
        return os.path.join(self.dir, f"{name.strip()}.json")

    def exists(self, name: str) -> bool:
        target = name.strip().lower()
        return any(n.lower() == target for n in self.list_profiles())

    def _seed(self, seed_dir: Optional[str]) -> None:
        """On first run, copy the bundled example profiles into the user's
        profile folder; always guarantee at least one profile exists."""
        if self.list_profiles():
            return
        if seed_dir and os.path.isdir(seed_dir):
            for fname in sorted(os.listdir(seed_dir)):
                if not fname.lower().endswith(".json"):
                    continue
                try:
                    with open(os.path.join(seed_dir, fname), "r", encoding="utf-8") as f:
                        profile = Profile.from_dict(json.load(f))
                    if not self.exists(profile.name):
                        self.save(profile)
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    log.warning("Skipping bundled profile %s: %s", fname, exc)
        if not self.list_profiles():
            self.save(Profile(name="Default", description="WASD movement, mouse look."))

    # ---- Queries ---------------------------------------------------------

    def list_profiles(self) -> List[str]:
        try:
            files = os.listdir(self.dir)
        except OSError:
            return []
        names = [os.path.splitext(f)[0] for f in files if f.lower().endswith(".json")]
        return sorted(names, key=str.lower)

    def load(self, name: str) -> Profile:
        path = self._path_for(name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Profile '{name}' does not exist.")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = Profile.from_dict(data)
        # The file name is the source of truth for the profile's identity.
        profile.name = os.path.splitext(os.path.basename(path))[0]
        if not profile.modified:
            try:
                profile.modified = os.path.getmtime(path)
            except OSError:
                pass
        return profile

    def unique_name(self, base: str) -> str:
        base = base.strip() or "Profile"
        if not self.exists(base):
            return base
        i = 2
        while self.exists(f"{base} ({i})"):
            i += 1
        return f"{base} ({i})"

    # ---- Mutations -------------------------------------------------------

    def save(self, profile: Profile) -> None:
        err = validate_profile_name(profile.name)
        if err:
            raise ValueError(err)
        profile.name = profile.name.strip()
        profile.modified = time.time()
        path = self._path_for(profile.name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2)
        os.replace(tmp, path)
        log.debug("Saved profile '%s'.", profile.name)

    def create(self, name: str, description: str = "") -> Profile:
        self._require_new_name(name)
        profile = Profile(name=name.strip(), description=description)
        self.save(profile)
        return profile

    def save_as(self, profile: Profile, new_name: str) -> Profile:
        self._require_new_name(new_name)
        new_profile = copy.deepcopy(profile)
        new_profile.name = new_name.strip()
        self.save(new_profile)
        return new_profile

    def duplicate(self, name: str, new_name: str) -> Profile:
        return self.save_as(self.load(name), new_name)

    def rename(self, old_name: str, new_name: str) -> Profile:
        new_name = new_name.strip()
        err = validate_profile_name(new_name)
        if err:
            raise ValueError(err)
        profile = self.load(old_name)
        case_only = old_name.lower() == new_name.lower()
        if not case_only and self.exists(new_name):
            raise ValueError(f"A profile named '{new_name}' already exists.")
        old_path = self._path_for(old_name)
        profile.name = new_name
        if case_only:
            # Case-insensitive filesystems: write via a temp name so the
            # final file really carries the new casing.
            tmp_path = old_path + ".rename"
            os.replace(old_path, tmp_path)
            try:
                self.save(profile)
            except Exception:
                os.replace(tmp_path, old_path)
                raise
            os.remove(tmp_path)
        else:
            self.save(profile)
            os.remove(old_path)
        return profile

    def delete(self, name: str) -> None:
        if len(self.list_profiles()) <= 1:
            raise ValueError("You can't delete the last remaining profile.")
        path = self._path_for(name)
        if os.path.exists(path):
            os.remove(path)
            log.info("Deleted profile '%s'.", name)

    def import_profile(self, source_path: str) -> Profile:
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = Profile.from_dict(data)
        if profile.name == "Imported Profile":
            stem = os.path.splitext(os.path.basename(source_path))[0]
            if not validate_profile_name(stem):
                profile.name = stem
        profile.name = self.unique_name(profile.name)
        self.save(profile)
        return profile

    def export_profile(self, name: str, dest_path: str) -> None:
        profile = self.load(name)
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2)

    def reset_to_default(self, name: str) -> Profile:
        old = self.load(name) if self.exists(name) else None
        profile = Profile(name=name, description=old.description if old else "")
        self.save(profile)
        return profile

    def _require_new_name(self, name: str) -> None:
        err = validate_profile_name(name)
        if err:
            raise ValueError(err)
        if self.exists(name):
            raise ValueError(f"A profile named '{name.strip()}' already exists.")
