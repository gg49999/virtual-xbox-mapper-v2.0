"""
Filesystem locations. Everything the app writes lives under the user's
profile (%APPDATA% for settings/profiles, %LOCALAPPDATA% for logs), and
everything it reads from the install (bundled profiles, images) is found
through `resource_path()` so it works both from source and when frozen
by PyInstaller.
"""
from __future__ import annotations

import os
import sys

from app_info import APP_ID


def project_root() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    return os.path.join(project_root(), *parts)


def _ensure(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def roaming_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return _ensure(os.path.join(base, APP_ID))


def local_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return _ensure(os.path.join(base, APP_ID))


def profiles_dir() -> str:
    return _ensure(os.path.join(roaming_dir(), "profiles"))


def controller_image_dir() -> str:
    return _ensure(os.path.join(roaming_dir(), "controller_image"))


def log_dir() -> str:
    return _ensure(os.path.join(local_dir(), "logs"))


def launch_command() -> str:
    """Command line that starts this app, used for the Windows "Run" key."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{exe}" "{script}" --minimized'
