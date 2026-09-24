"""
Virtual Xbox Mapper - entry point.

* Only one instance runs at a time (a second launch just brings the
  existing window to the front), so two virtual controllers are never
  created by accident.
* Unhandled exceptions - on any thread - are logged and shown in a
  dialog instead of silently killing the process.
* The system cursor is always restored on exit, even after a crash
  while the mouse was captured.
"""
from __future__ import annotations

import argparse
import atexit
import os
import sys
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

from app_info import APP_NAME, APP_ID, APP_VERSION, APP_PUBLISHER
from logger import setup_logging, get_logger, set_level

setup_logging()
log = get_logger("Main")


def _instance_key() -> str:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    return f"{APP_ID}-{user}"


class SingleInstance(QObject):
    activated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.server = None

    def try_become_primary(self) -> bool:
        key = _instance_key()
        sock = QLocalSocket()
        sock.connectToServer(key)
        if sock.waitForConnected(300):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return False
        QLocalServer.removeServer(key)   # clean up after a crashed instance
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_connection)
        if not self.server.listen(key):
            log.warning("Single-instance server could not listen: %s", self.server.errorString())
        return True

    def _on_connection(self) -> None:
        conn = self.server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(lambda c=conn: (c.readAll(), self.activated.emit()))
            conn.disconnected.connect(conn.deleteLater)


class _ErrorRelay(QObject):
    show = pyqtSignal(str)


def _install_exception_hooks(app: QApplication) -> None:
    relay = _ErrorRelay(app)
    shown = {"count": 0}

    def show_dialog(text: str) -> None:
        if shown["count"] >= 3:      # avoid a cascade of dialogs
            return
        shown["count"] += 1
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(f"{APP_NAME} - Unexpected error")
        box.setText("Something went wrong. The app will keep running, but you may want to restart it.\n\n"
                    "Details were written to the log file (Settings › Troubleshooting).")
        box.setDetailedText(text)
        box.exec()
        shown["count"] -= 1

    relay.show.connect(show_dialog)

    def handle(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        relay.show.emit("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    sys.excepthook = handle
    threading.excepthook = lambda args: handle(args.exc_type, args.exc_value, args.exc_traceback)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_ID, description=APP_NAME)
    parser.add_argument("--minimized", action="store_true", help="start hidden in the notification area")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    args, _unknown = parser.parse_known_args(argv[1:])
    return args


def main() -> int:
    args = _parse_args(sys.argv)
    if not sys.platform.startswith("win"):
        log.warning("This application targets Windows (ViGEmBus / XInput). On other platforms the "
                    "virtual controller and cursor capture are unavailable; the UI runs for development.")

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_PUBLISHER)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    _install_exception_hooks(app)

    instance = SingleInstance()
    if not instance.try_become_primary():
        log.info("Another instance is running; asked it to show its window.")
        return 0

    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.{APP_VERSION}")
        except Exception:
            pass

    from win_input import restore_system_cursors
    restore_system_cursors()                  # undo a hidden cursor left by a crash
    atexit.register(restore_system_cursors)

    from paths import resource_path
    from settings_manager import SettingsManager
    from profile_manager import ProfileManager
    from engine import Engine
    from ui import icons
    from ui.main_window import MainWindow
    import startup

    settings = SettingsManager(seed_path=resource_path("config", "default_settings.json"))
    set_level("DEBUG" if args.debug else settings.get("advanced", "log_level", "INFO"))
    log.info("%s %s starting", APP_NAME, APP_VERSION)
    profiles = ProfileManager(seed_dir=resource_path("profiles"))
    engine = Engine(settings, profiles)

    app.setWindowIcon(icons.app_icon())
    window = MainWindow(engine)
    instance.activated.connect(window.show_and_raise)
    engine.start()
    window.sync_from_engine()
    startup.refresh()

    hidden = args.minimized or settings.get("general", "start_minimized", False)
    if not hidden or window.tray is None:
        window.show_initial()

    app.aboutToQuit.connect(lambda: window.quit_app() if not window._quitting else None)
    code = app.exec()
    log.info("Exited with code %s", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
