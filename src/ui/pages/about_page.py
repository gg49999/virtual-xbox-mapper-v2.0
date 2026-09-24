"""About page: version, links, shortcuts, credits and diagnostics."""
from __future__ import annotations

import platform
import sys

from PyQt6.QtCore import Qt, QUrl, QT_VERSION_STR, PYQT_VERSION_STR
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel

import keycodes
from app_info import APP_NAME, APP_VERSION, APP_DESCRIPTION, PROJECT_URL, ISSUES_URL, VIGEMBUS_URL
from engine import HOTKEY_ACTIONS
from ui import icons, theme
from ui.pages.base import Page
from ui.widgets import Card, button, label, divider, SettingRow


class AboutPage(Page):
    def __init__(self, engine, window):
        super().__init__("About", "", scroll=True, max_width=980)
        self.engine = engine
        self.window = window

        hero = Card(padding=24)
        row = QHBoxLayout()
        row.setSpacing(20)
        self.logo = QLabel()
        self.logo.setFixedSize(72, 72)
        row.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(label(APP_NAME, "title"))
        text.addWidget(label(f"Version {APP_VERSION}", "caption"))
        text.addWidget(label(APP_DESCRIPTION, "body2", wrap=True))
        links = QHBoxLayout()
        links.setSpacing(8)
        links.addWidget(button("Project page", icon="link", on_click=lambda: QDesktopServices.openUrl(QUrl(PROJECT_URL))))
        links.addWidget(button("Report a problem", icon="alert", on_click=lambda: QDesktopServices.openUrl(QUrl(ISSUES_URL))))
        links.addWidget(button("Copy diagnostics", icon="copy", on_click=self._copy_diag))
        links.addStretch()
        text.addSpacing(6)
        text.addLayout(links)
        row.addLayout(text, 1)
        hero.body().addLayout(row)
        self.content.addWidget(hero)

        self.shortcuts = Card("Keyboard shortcuts", icon="keyboard")
        self.content.addWidget(self.shortcuts)
        self._shortcut_rows: list = []

        start = Card("Getting started", icon="info")
        steps = [
            ("1", "Make sure the status in the top bar says Controller connected. If not, install the "
                  "ViGEmBus driver and press Reconnect."),
            ("2", "Open Live test and press your keys: the on-screen controller should react."),
            ("3", "Start your game or xbox.com/play, then press the capture hotkey to turn mouse movement "
                  "into right-stick aiming."),
            ("4", "Press the emergency-release hotkey at any time to let go of every input and the mouse."),
        ]
        for i, (n, s) in enumerate(steps):
            if i:
                start.add(divider())
            start.add(SettingRow(f"Step {n}", s))
        start.add(button("Download ViGEmBus driver", "link",
                         on_click=lambda: QDesktopServices.openUrl(QUrl(VIGEMBUS_URL))))
        self.content.addWidget(start)

        credits = Card("Open-source components", icon="star")
        for name, desc in (
            ("ViGEmBus", "Virtual gamepad bus driver by Nefarius Software Solutions (BSD-3-Clause)."),
            ("vgamepad", "Python bindings for ViGEm (MIT)."),
            ("pynput", "Global keyboard and mouse monitoring (LGPL-3.0)."),
            ("Qt / PyQt6", "User-interface framework (LGPL / GPL)."),
        ):
            credits.add(SettingRow(name, desc))
        credits.add(label("Xbox is a trademark of Microsoft Corporation. This project is not affiliated with "
                          "or endorsed by Microsoft.", "caption", wrap=True))
        self.content.addWidget(credits)

        self.diag = Card("System information", icon="gear")
        self.diag_label = label("", "mono", wrap=True)
        self.diag_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.diag.add(self.diag_label)
        self.content.addWidget(self.diag)
        self.content.addStretch()
        theme.signals.changed.connect(self._render_logo)
        self._render_logo()

    def _render_logo(self) -> None:
        self.logo.setPixmap(icons.app_icon(theme.T.accent if not theme.T.dark else "#107c10").pixmap(72, 72))

    def on_show(self) -> None:
        for w in self._shortcut_rows:
            w.setParent(None)
            w.deleteLater()
        self._shortcut_rows = []
        for i, (action, title) in enumerate(HOTKEY_ACTIONS.items()):
            if i:
                d = divider()
                self.shortcuts.add(d)
                self._shortcut_rows.append(d)
            combo = self.engine.settings.get("hotkeys", action, "")
            row = SettingRow(title, "", label(keycodes.combo_display(combo), "body2"))
            self.shortcuts.add(row)
            self._shortcut_rows.append(row)
        self.diag_label.setText(self.diagnostics())

    def diagnostics(self) -> str:
        e = self.engine
        return "\n".join([
            f"{APP_NAME} {APP_VERSION}",
            f"OS: {platform.platform()}",
            f"Python: {sys.version.split()[0]}  Qt: {QT_VERSION_STR}  PyQt: {PYQT_VERSION_STR}",
            f"Virtual controller: {'connected' if e.connected else 'not connected'}"
            + (f" ({e.controller.last_error})" if e.controller.last_error else ""),
            f"vgamepad available: {e.controller.is_available}",
            f"Input capture: {'running' if e.input.running else 'unavailable'}"
            + (f" ({e.input_error})" if e.input_error else ""),
            f"Raw Input in use: {e.input.using_raw_input}",
            f"Engine rate: {e.tick_rate} Hz (measured {e.measured_tick_hz:.0f} Hz)",
            f"Active profile: {e.profile.name if e.profile else '-'}",
        ])

    def _copy_diag(self) -> None:
        QGuiApplication.clipboard().setText(self.diagnostics())
        self.window.toast("Diagnostics copied", "Paste them into your bug report.", "success")
