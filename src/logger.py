"""
Central logging setup. All modules pull their logger from here so log
output is consistent and ends up in both the console and a rotating
file under %LOCALAPPDATA%\\VirtualXboxMapper\\logs.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from app_info import APP_ID

_configured = False
_file_path: str | None = None


def setup_logging(level: int = logging.INFO) -> None:
    global _configured, _file_path
    if _configured:
        return
    _configured = True

    root = logging.getLogger(APP_ID)
    root.setLevel(level)
    root.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # pythonw / windowed PyInstaller builds have no stdout.
    if sys.stdout is not None:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        root.addHandler(console)

    try:
        from paths import log_dir
        _file_path = os.path.join(log_dir(), "app.log")
        file_handler = logging.handlers.RotatingFileHandler(
            _file_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        _file_path = None
        root.warning("Could not open log file; continuing with console logging only.")


def set_level(level_name: str) -> None:
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logging.getLogger(APP_ID).setLevel(level)


def log_file_path() -> str | None:
    return _file_path


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"{APP_ID}.{name}")
