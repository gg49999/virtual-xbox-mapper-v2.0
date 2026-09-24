"""Start-with-Windows registration via the per-user Run key."""
from __future__ import annotations

import sys

from app_info import APP_ID
from paths import launch_command

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def supported() -> bool:
    return sys.platform.startswith("win")


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_ID)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    """Raises OSError if the registry can't be written."""
    if not supported():
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_ID)
            except FileNotFoundError:
                pass


def refresh() -> None:
    """If startup is enabled, rewrite the entry so it points at the current
    executable (e.g. after the app was moved or updated)."""
    if supported() and is_enabled():
        try:
            set_enabled(True)
        except OSError:
            pass
