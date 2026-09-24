"""
HotkeyManager
Global hotkeys (F8 = capture mouse, F10 = emergency release, ...) that
work while a game has focus.

Rather than installing a second keyboard hook, the manager is fed the
same normalised key stream as the mapping engine (`feed()`), so hotkey
names and binding names always agree. A combo fires on the key-down of
its main key when exactly its modifiers are held; auto-repeat is
ignored. On Windows the modifier state is read from the OS, so a missed
key-up (e.g. after Win+L) can never leave a modifier "stuck".
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, Optional, Set, Tuple

import keycodes
from logger import get_logger
from win_input import modifier_down

log = get_logger("Hotkeys")


class HotkeyManager:
    def __init__(self, use_os_modifier_state: bool = True):
        """use_os_modifier_state: on Windows, read Ctrl/Alt/Shift/Win from the
        OS (robust against missed key-ups). Tests turn this off so only the
        fed events count."""
        self._use_os = use_os_modifier_state
        self._lock = threading.Lock()
        # action -> (modifiers, key)
        self._combos: Dict[str, Tuple[frozenset, str]] = {}
        self._callbacks: Dict[str, Callable[[], None]] = {}
        self._held: Set[str] = set()
        self.enabled = True

    def set_bindings(self, combos: Dict[str, str], callbacks: Dict[str, Callable[[], None]]) -> list[str]:
        """Replace all hotkeys. Returns the actions whose combo was invalid."""
        invalid = []
        parsed: Dict[str, Tuple[frozenset, str]] = {}
        for action, combo in combos.items():
            if not combo:
                continue
            p = keycodes.parse_combo(combo)
            if p is None:
                invalid.append(action)
                log.warning("Ignoring invalid hotkey for %s: %r", action, combo)
                continue
            parsed[action] = p
        with self._lock:
            self._combos = parsed
            self._callbacks = dict(callbacks)
        return invalid

    def keys(self) -> Set[str]:
        with self._lock:
            return {key for _, key in self._combos.values()}

    def _modifier_held(self, name: str) -> bool:
        real = modifier_down(name) if self._use_os else None
        return real if real is not None else name in self._held

    def feed(self, code: str, pressed: bool) -> bool:
        """Process one key event. Returns True if it triggered a hotkey
        (the caller should then not forward the key-down to the game)."""
        if not pressed:
            self._held.discard(code)
            return False
        repeat = code in self._held
        self._held.add(code)
        if repeat or not self.enabled or keycodes.is_modifier(code):
            return False
        with self._lock:
            combos = list(self._combos.items())
            callbacks = self._callbacks
        held_mods = frozenset(m for m in keycodes.MODIFIERS if self._modifier_held(m))
        for action, (mods, key) in combos:
            if key == code and mods == held_mods:
                cb = callbacks.get(action)
                if cb:
                    try:
                        cb()
                    except Exception:
                        log.exception("Hotkey action %s failed", action)
                return True
        return False

    def reset(self) -> None:
        self._held.clear()


def find_duplicate(combos: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """Return a pair of actions that share the same combo, if any."""
    seen: Dict[Tuple[frozenset, str], str] = {}
    for action, combo in combos.items():
        p = keycodes.parse_combo(combo) if combo else None
        if p is None:
            continue
        if p in seen:
            return seen[p], action
        seen[p] = action
    return None
