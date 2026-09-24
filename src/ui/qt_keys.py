"""Translate Qt key events into canonical input codes (see keycodes.py).

On Windows the native virtual-key code is used, exactly like the global
pynput listener, so a key captured in the UI always matches the key the
engine sees at runtime."""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

import keycodes

_K = Qt.Key
_QT_NAMED = {
    _K.Key_Space: "space", _K.Key_Return: "enter", _K.Key_Enter: "enter",
    _K.Key_Backspace: "backspace", _K.Key_Tab: "tab", _K.Key_Backtab: "tab",
    _K.Key_Escape: "esc", _K.Key_Shift: "shift", _K.Key_Control: "ctrl",
    _K.Key_Alt: "alt", _K.Key_AltGr: "alt", _K.Key_Meta: "win", _K.Key_Super_L: "win",
    _K.Key_Super_R: "win", _K.Key_CapsLock: "caps_lock", _K.Key_Up: "up",
    _K.Key_Down: "down", _K.Key_Left: "left", _K.Key_Right: "right",
    _K.Key_Home: "home", _K.Key_End: "end", _K.Key_PageUp: "page_up",
    _K.Key_PageDown: "page_down", _K.Key_Insert: "insert", _K.Key_Delete: "delete",
    _K.Key_Print: "print_screen", _K.Key_ScrollLock: "scroll_lock",
    _K.Key_NumLock: "num_lock", _K.Key_Pause: "pause", _K.Key_Menu: "menu",
    _K.Key_Semicolon: ";", _K.Key_Colon: ";", _K.Key_Equal: "=", _K.Key_Plus: "=",
    _K.Key_Comma: ",", _K.Key_Less: ",", _K.Key_Minus: "-", _K.Key_Underscore: "-",
    _K.Key_Period: ".", _K.Key_Greater: ".", _K.Key_Slash: "/", _K.Key_Question: "/",
    _K.Key_QuoteLeft: "`", _K.Key_AsciiTilde: "`", _K.Key_BracketLeft: "[",
    _K.Key_BraceLeft: "[", _K.Key_BracketRight: "]", _K.Key_BraceRight: "]",
    _K.Key_Backslash: "\\", _K.Key_Bar: "\\", _K.Key_Apostrophe: "'", _K.Key_QuoteDbl: "'",
    _K.Key_Exclam: "1", _K.Key_At: "2", _K.Key_NumberSign: "3", _K.Key_Dollar: "4",
    _K.Key_Percent: "5", _K.Key_AsciiCircum: "6", _K.Key_Ampersand: "7",
    _K.Key_Asterisk: "8", _K.Key_ParenLeft: "9", _K.Key_ParenRight: "0",
}
_KEYPAD = {
    _K.Key_Asterisk: "num_multiply", _K.Key_Plus: "num_add", _K.Key_Minus: "num_subtract",
    _K.Key_Period: "num_decimal", _K.Key_Slash: "num_divide", _K.Key_Enter: "enter",
}


def code_from_key_event(e: QKeyEvent) -> str | None:
    if sys.platform.startswith("win"):
        code = keycodes.from_vk(e.nativeVirtualKey())
        if code:
            return code
    key = e.key()
    try:
        key = Qt.Key(key)
    except ValueError:
        return None
    keypad = bool(e.modifiers() & Qt.KeyboardModifier.KeypadModifier)
    if keypad:
        if Qt.Key.Key_0.value <= key.value <= Qt.Key.Key_9.value:
            return f"num{key.value - Qt.Key.Key_0.value}"
        if key in _KEYPAD:
            return _KEYPAD[key]
    if Qt.Key.Key_A.value <= key.value <= Qt.Key.Key_Z.value:
        return chr(ord("a") + key.value - Qt.Key.Key_A.value)
    if Qt.Key.Key_0.value <= key.value <= Qt.Key.Key_9.value:
        return str(key.value - Qt.Key.Key_0.value)
    if Qt.Key.Key_F1.value <= key.value <= Qt.Key.Key_F24.value:
        return f"f{key.value - Qt.Key.Key_F1.value + 1}"
    return _QT_NAMED.get(key)


def code_from_mouse_button(button: Qt.MouseButton) -> str | None:
    return {
        Qt.MouseButton.LeftButton: "mouse_left",
        Qt.MouseButton.RightButton: "mouse_right",
        Qt.MouseButton.MiddleButton: "mouse_middle",
        Qt.MouseButton.BackButton: "mouse_x1",
        Qt.MouseButton.ForwardButton: "mouse_x2",
    }.get(button)
