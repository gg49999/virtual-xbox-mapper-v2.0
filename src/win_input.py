"""
Windows-only helpers for mouse capture:

* CursorLock   - parks the cursor in the middle of the game window with
                 ClipCursor, optionally hides it system-wide, and notices
                 when the user switches to another window.
* RawMouse     - reads true relative mouse motion through the Raw Input
                 API (WM_INPUT), independent of cursor position, Windows
                 pointer acceleration, and screen edges.

Every call is wrapped so that a failure degrades to "capture without
that feature" instead of an exception. On other platforms everything
here is a harmless no-op, which keeps the UI usable for development.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional

from logger import get_logger

log = get_logger("WinInput")

IS_WINDOWS = sys.platform.startswith("win")

user32 = None
if IS_WINDOWS:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.ClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
        user32.ClipCursor.restype = wintypes.BOOL
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.CreateCursor.argtypes = [wintypes.HINSTANCE, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
        user32.CreateCursor.restype = wintypes.HANDLE
        user32.SetSystemCursor.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        user32.SetSystemCursor.restype = wintypes.BOOL
        user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
        user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                           ctypes.POINTER(wintypes.UINT), wintypes.UINT]
        user32.GetRawInputData.restype = wintypes.UINT
    except Exception as exc:  # pragma: no cover - Windows only
        log.warning("user32 unavailable: %s", exc)
        user32 = None

_SPI_SETCURSORS = 0x0057
_OCR_IDS = (32512, 32513, 32514, 32515, 32516, 32642, 32643, 32644, 32645, 32646, 32648, 32649, 32650)
_VK_MODIFIERS = {"ctrl": (0x11,), "alt": (0x12,), "shift": (0x10,), "win": (0x5B, 0x5C)}


def modifier_down(name: str) -> Optional[bool]:
    """Real-time modifier state from the OS, or None if unavailable."""
    if not user32:
        return None
    try:
        return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _VK_MODIFIERS[name])
    except Exception:
        return None


def restore_system_cursors() -> None:
    """Reload the user's cursor scheme (undoes any hidden-cursor state,
    including one left behind by a crash)."""
    if user32:
        try:
            user32.SystemParametersInfoW(_SPI_SETCURSORS, 0, None, 0)
        except Exception:
            pass


class CursorLock:
    def __init__(self):
        self.active = False
        self.center = (0, 0)
        self._hwnd = None
        self._cursor_hidden = False

    def start(self, hide_cursor: bool, clip: bool) -> None:
        if self.active:
            return
        self.active = True
        self._clip = clip
        if not user32:
            return
        try:
            self._hwnd = user32.GetForegroundWindow()
            rect = wintypes.RECT()
            if self._hwnd and user32.GetWindowRect(self._hwnd, ctypes.byref(rect)):
                cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
            else:
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                cx, cy = pt.x, pt.y
            self.center = (cx, cy)
            user32.SetCursorPos(cx, cy)
            self._apply_clip()
            if hide_cursor:
                self._hide_cursor()
        except Exception as exc:
            log.warning("Cursor lock could not be fully applied: %s", exc)

    def _apply_clip(self) -> None:
        if user32 and self._clip:
            cx, cy = self.center
            rect = wintypes.RECT(cx, cy, cx + 1, cy + 1)
            user32.ClipCursor(ctypes.byref(rect))

    def _hide_cursor(self) -> None:
        and_mask = (ctypes.c_ubyte * 128)(*([0xFF] * 128))
        xor_mask = (ctypes.c_ubyte * 128)()
        for ocr in _OCR_IDS:
            handle = user32.CreateCursor(None, 0, 0, 32, 32, and_mask, xor_mask)
            if handle:
                user32.SetSystemCursor(handle, ocr)  # the system takes ownership
        self._cursor_hidden = True

    def recenter(self) -> None:
        if self.active and user32:
            try:
                user32.SetCursorPos(*self.center)
            except Exception:
                pass

    def maintain(self, release_on_focus_change: bool) -> bool:
        """Re-assert the clip (other apps may reset it). Returns False when
        the user switched away from the captured window."""
        if not self.active or not user32:
            return True
        try:
            if release_on_focus_change and self._hwnd:
                if user32.GetForegroundWindow() != self._hwnd:
                    return False
            self._apply_clip()
        except Exception:
            pass
        return True

    def stop(self) -> None:
        if not self.active:
            return
        self.active = False
        if not user32:
            return
        try:
            user32.ClipCursor(None)
        except Exception:
            pass
        if self._cursor_hidden:
            restore_system_cursors()
            self._cursor_hidden = False


# ---- Raw Input ---------------------------------------------------------------

if IS_WINDOWS and user32:
    from PyQt6.QtCore import QAbstractNativeEventFilter

    _WM_INPUT = 0x00FF
    _RID_INPUT = 0x10000003
    _RIM_TYPEMOUSE = 0
    _RIDEV_INPUTSINK = 0x00000100
    _RIDEV_REMOVE = 0x00000001
    _MOUSE_MOVE_ABSOLUTE = 0x0001

    class _RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                    ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]

    class _RAWINPUTHEADER(ctypes.Structure):
        _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                    ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]

    class _BUTTONS(ctypes.Structure):
        _fields_ = [("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.USHORT)]

    class _BUTTONS_UNION(ctypes.Union):
        _fields_ = [("ulButtons", wintypes.ULONG), ("s", _BUTTONS)]

    class _RAWMOUSE(ctypes.Structure):
        _fields_ = [("usFlags", wintypes.USHORT), ("u", _BUTTONS_UNION),
                    ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG),
                    ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]

    class _RAWINPUT(ctypes.Structure):
        _fields_ = [("header", _RAWINPUTHEADER), ("mouse", _RAWMOUSE)]

    user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(_RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
    user32.RegisterRawInputDevices.restype = wintypes.BOOL

    class RawMouse(QAbstractNativeEventFilter):
        """Delivers relative mouse motion from WM_INPUT to `on_delta`."""

        def __init__(self, on_delta: Callable[[float, float], None]):
            super().__init__()
            self.on_delta = on_delta
            self._window = None
            self._registered = False
            self._last_abs = None
            self._header_size = ctypes.sizeof(_RAWINPUTHEADER)
            self._buf = _RAWINPUT()
            self._buf_size = wintypes.UINT(ctypes.sizeof(_RAWINPUT))

        def start(self) -> bool:
            if self._registered:
                return True
            try:
                from PyQt6.QtWidgets import QApplication, QWidget
                from PyQt6.QtCore import Qt
                if self._window is None:
                    self._window = QWidget()
                    self._window.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
                    self._window.setWindowTitle("VirtualXboxMapper raw input sink")
                    QApplication.instance().installNativeEventFilter(self)
                hwnd = int(self._window.winId())
                dev = _RAWINPUTDEVICE(0x01, 0x02, _RIDEV_INPUTSINK, hwnd)
                if not user32.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev)):
                    log.warning("RegisterRawInputDevices failed (error %d).", ctypes.get_last_error())
                    return False
                self._registered = True
                self._last_abs = None
                return True
            except Exception as exc:
                log.warning("Raw Input unavailable: %s", exc)
                return False

        def stop(self) -> None:
            if not self._registered:
                return
            try:
                dev = _RAWINPUTDEVICE(0x01, 0x02, _RIDEV_REMOVE, None)
                user32.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev))
            except Exception:
                pass
            self._registered = False

        def nativeEventFilter(self, eventType, message):
            try:
                if not self._registered:
                    return False, 0
                kind = eventType.data() if hasattr(eventType, "data") else bytes(eventType)
                if kind != b"windows_generic_MSG":
                    return False, 0
                msg = wintypes.MSG.from_address(int(message))
                if msg.message != _WM_INPUT:
                    return False, 0
                size = wintypes.UINT(ctypes.sizeof(_RAWINPUT))
                got = user32.GetRawInputData(msg.lParam, _RID_INPUT, ctypes.byref(self._buf),
                                             ctypes.byref(size), self._header_size)
                if got == 0xFFFFFFFF or got == 0 or self._buf.header.dwType != _RIM_TYPEMOUSE:
                    return False, 0
                m = self._buf.mouse
                if m.usFlags & _MOUSE_MOVE_ABSOLUTE:
                    # Tablets / remote desktop report absolute positions.
                    if self._last_abs is not None:
                        dx = (m.lLastX - self._last_abs[0]) / 65535.0 * 1920
                        dy = (m.lLastY - self._last_abs[1]) / 65535.0 * 1080
                        self._last_abs = (m.lLastX, m.lLastY)
                        if dx or dy:
                            self.on_delta(dx, dy)
                    else:
                        self._last_abs = (m.lLastX, m.lLastY)
                elif m.lLastX or m.lLastY:
                    self.on_delta(float(m.lLastX), float(m.lLastY))
            except Exception:
                pass
            return False, 0
else:
    class RawMouse:  # type: ignore[no-redef]
        def __init__(self, on_delta):
            self.on_delta = on_delta

        def start(self) -> bool:
            return False

        def stop(self) -> None:
            pass
