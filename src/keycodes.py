"""
Canonical input codes.

Every keyboard key and mouse button is identified by one stable,
lower-case string code ("w", "space", "f8", "mouse_left", "wheel_up",
...). These codes are what profiles store on disk, so the same code must
come out of every capture path:

  * the global pynput listeners (runtime input),
  * the Qt binding dialog (user presses a key to bind it),
  * the hotkey editor.

On Windows all three paths are normalised through the virtual-key code,
which is layout-independent and unaffected by Shift/Ctrl (pynput's
`char` is not: Ctrl+W reports '\\x17', Shift+1 reports '!').
"""
from __future__ import annotations

from typing import Iterable, Optional

MODIFIERS = ("ctrl", "alt", "shift", "win")

MOUSE_BUTTONS = ("mouse_left", "mouse_right", "mouse_middle", "mouse_x1", "mouse_x2")
WHEEL_CODES = ("wheel_up", "wheel_down", "wheel_left", "wheel_right")

# Windows virtual-key code -> canonical code.
VK_TO_CODE: dict[int, str] = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x10: "shift", 0x11: "ctrl",
    0x12: "alt", 0x13: "pause", 0x14: "caps_lock", 0x1B: "esc", 0x20: "space",
    0x21: "page_up", 0x22: "page_down", 0x23: "end", 0x24: "home",
    0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
    0x2C: "print_screen", 0x2D: "insert", 0x2E: "delete",
    0x5B: "win", 0x5C: "win", 0x5D: "menu",
    0x6A: "num_multiply", 0x6B: "num_add", 0x6D: "num_subtract",
    0x6E: "num_decimal", 0x6F: "num_divide",
    0x90: "num_lock", 0x91: "scroll_lock",
    0xA0: "shift", 0xA1: "shift", 0xA2: "ctrl", 0xA3: "ctrl", 0xA4: "alt", 0xA5: "alt",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
for _i in range(26):
    VK_TO_CODE[0x41 + _i] = chr(ord("a") + _i)
for _i in range(10):
    VK_TO_CODE[0x30 + _i] = str(_i)
    VK_TO_CODE[0x60 + _i] = f"num{_i}"
for _i in range(24):
    VK_TO_CODE[0x70 + _i] = f"f{_i + 1}"

# pynput Key-enum names that differ from our canonical codes.
_PYNPUT_ALIASES = {
    "shift_l": "shift", "shift_r": "shift",
    "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "cmd": "win", "cmd_l": "win", "cmd_r": "win",
    "escape": "esc", "return": "enter",
}

# Shifted characters (non-Windows fallback path only) -> unshifted key.
_SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]",
    "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
}

_DISPLAY = {
    "mouse_left": "Left Click", "mouse_right": "Right Click",
    "mouse_middle": "Middle Click", "mouse_x1": "Mouse 4", "mouse_x2": "Mouse 5",
    "wheel_up": "Wheel Up", "wheel_down": "Wheel Down",
    "wheel_left": "Wheel Left", "wheel_right": "Wheel Right",
    "esc": "Esc", "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win",
    "caps_lock": "Caps Lock", "page_up": "Page Up", "page_down": "Page Down",
    "print_screen": "Print Screen", "scroll_lock": "Scroll Lock", "num_lock": "Num Lock",
    "num_multiply": "Num *", "num_add": "Num +", "num_subtract": "Num -",
    "num_decimal": "Num .", "num_divide": "Num /",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "backspace": "Backspace", "enter": "Enter", "space": "Space", "tab": "Tab",
    "delete": "Delete", "insert": "Insert", "home": "Home", "end": "End",
    "menu": "Menu", "pause": "Pause",
}

_SHORT = {
    "mouse_left": "LMB", "mouse_right": "RMB", "mouse_middle": "MMB",
    "mouse_x1": "M4", "mouse_x2": "M5",
    "wheel_up": "Wheel↑", "wheel_down": "Wheel↓",
    "wheel_left": "Wheel←", "wheel_right": "Wheel→",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "backspace": "Bksp", "page_up": "PgUp", "page_down": "PgDn",
    "caps_lock": "Caps", "print_screen": "PrtSc", "delete": "Del", "insert": "Ins",
}


def from_vk(vk: Optional[int]) -> Optional[str]:
    if vk is None:
        return None
    return VK_TO_CODE.get(int(vk))


def from_pynput_key(key, prefer_vk: bool = True) -> Optional[str]:
    """Normalise a pynput `Key` / `KeyCode` into a canonical code."""
    if key is None:
        return None
    vk = getattr(key, "vk", None)
    if prefer_vk and vk is not None:
        code = from_vk(vk)
        if code:
            return code
    # Special keys (pynput.keyboard.Key members) carry a .name.
    name = getattr(key, "name", None)
    if name:
        return _PYNPUT_ALIASES.get(name, name)
    char = getattr(key, "char", None)
    if char:
        if len(char) == 1 and ord(char) < 32:
            # Control character (Ctrl+letter on some platforms).
            return chr(ord(char) + 96) if 1 <= ord(char) <= 26 else None
        c = char.lower()
        return _SHIFTED.get(c, c)
    return None


def from_pynput_button(button) -> Optional[str]:
    name = getattr(button, "name", None) or str(button).split(".")[-1]
    return {
        "left": "mouse_left", "right": "mouse_right", "middle": "mouse_middle",
        "x1": "mouse_x1", "x2": "mouse_x2",
        "button8": "mouse_x1", "button9": "mouse_x2",
    }.get(name)


def wheel_codes(dx: float, dy: float) -> list[str]:
    out = []
    if dy > 0:
        out.append("wheel_up")
    elif dy < 0:
        out.append("wheel_down")
    if dx > 0:
        out.append("wheel_right")
    elif dx < 0:
        out.append("wheel_left")
    return out


def is_modifier(code: str) -> bool:
    return code in MODIFIERS


def is_mouse(code: str) -> bool:
    return code in MOUSE_BUTTONS or code in WHEEL_CODES


def display_name(code: str) -> str:
    if not code:
        return ""
    if code in _DISPLAY:
        return _DISPLAY[code]
    if code.startswith("num") and code[3:].isdigit():
        return f"Num {code[3:]}"
    if len(code) == 1:
        return code.upper()
    if code.startswith("f") and code[1:].isdigit():
        return code.upper()
    return code.replace("_", " ").title()


def short_name(code: str) -> str:
    if code in _SHORT:
        return _SHORT[code]
    return display_name(code)


# ---- Hotkey combos ("ctrl+alt+x") ---------------------------------------

def parse_combo(combo: str) -> Optional[tuple[frozenset, str]]:
    """Return (modifiers, key) or None if the combo is empty/invalid.
    A combo must have exactly one non-modifier key."""
    if not combo:
        return None
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        return None
    mods = frozenset(p for p in parts if p in MODIFIERS)
    keys = [p for p in parts if p not in MODIFIERS]
    if len(keys) != 1:
        return None
    key = keys[0]
    if key not in VK_TO_CODE.values() and key not in MOUSE_BUTTONS:
        return None
    return mods, key


def format_combo(mods: Iterable[str], key: str) -> str:
    ordered = [m for m in MODIFIERS if m in set(mods)]
    return "+".join(ordered + [key])


def combo_display(combo: str) -> str:
    parsed = parse_combo(combo)
    if not parsed:
        return "Not set"
    mods, key = parsed
    return " + ".join([display_name(m) for m in MODIFIERS if m in mods] + [display_name(key)])
