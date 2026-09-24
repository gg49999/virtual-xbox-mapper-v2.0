"""
MainWindow
Application shell, laid out like a modern Windows app:

  ┌──────────┬───────────────────────────────────────────────────────┐
  │ App name │ command bar: status · emulation · capture · release   │
  │          ├───────────────────────────────────────────────────────┤
  │ Nav pane │ banner (driver missing, input unavailable, …)         │
  │          │ page (Mapping · Tuning · Live test · Profiles · …)    │
  │ Settings │                                             [toasts]  │
  │ About    │                                                       │
  ├──────────┴───────────────────────────────────────────────────────┤
  │ status bar                                                       │
  └──────────────────────────────────────────────────────────────────┘

The navigation pane collapses to icons on narrow windows. All engine
signals arrive here on the GUI thread; this class never touches the
engine's background threads directly.
"""
from __future__ import annotations

import os
import sys
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer, QRectF, QSize, QUrl, pyqtSignal, QPoint
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence, QPainter, QShortcut, QDesktopServices, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QSystemTrayIcon, QMenu, QLabel,
    QAbstractButton, QApplication,
)

import keycodes
from app_info import APP_NAME, VIGEMBUS_URL
from engine import Engine
from logger import get_logger
from paths import resource_path
from ui import theme, icons
from ui.osd import OSD
from ui.widgets import StatusPill, LabeledToggle, InfoBar, ToastHost, button, label, divider, repolish
from ui.pages.mapping_page import MappingPage
from ui.pages.tuning_page import TuningPage
from ui.pages.test_page import TestPage
from ui.pages.profiles_page import ProfilesPage
from ui.pages.settings_page import SettingsPage
from ui.pages.about_page import AboutPage

log = get_logger("UI")

NAV_TOP = [("mapping", "Mapping", "gamepad"), ("tuning", "Tuning", "sliders"),
           ("test", "Live test", "pulse"), ("profiles", "Profiles", "layers")]
NAV_BOTTOM = [("settings", "Settings", "gear"), ("about", "About", "info")]
COMPACT_BREAKPOINT = 1100


class NavButton(QAbstractButton):
    def __init__(self, key: str, text: str, icon: str, parent=None):
        super().__init__(parent)
        self.key, self._text, self._icon = key, text, icon
        self.compact = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(text)
        self.setFixedHeight(40)
        self._kb_focus = False
        theme.signals.changed.connect(self.update)

    def focusInEvent(self, e):
        self._kb_focus = e.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self._kb_focus = False
        super().focusOutEvent(e)

    def set_compact(self, compact: bool) -> None:
        self.compact = compact
        self.setToolTip(self._text if compact else "")
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(48 if self.compact else 200, 40)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, _):
        t = theme.T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(4, 2, self.width() - 8, self.height() - 4)
        if self.isChecked() or self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(t.control_hover if self.isChecked() else t.control))
            p.drawRoundedRect(r, 6, 6)
        if self.isChecked():
            p.setBrush(theme.qcolor(t.accent))
            p.drawRoundedRect(QRectF(r.left(), r.center().y() - 8, 3, 16), 1.5, 1.5)
        if self.hasFocus() and self._kb_focus:
            p.setPen(theme.qcolor(t.text))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 6, 6)
        icon_rect = QRectF(r.left() + 12, r.center().y() - 10, 20, 20)
        icons.paint(p, self._icon, icon_rect, theme.qcolor(t.accent if self.isChecked() else t.text))
        if not self.compact:
            f = QFont(self.font())
            f.setPixelSize(13)
            if self.isChecked():
                f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            p.setPen(theme.qcolor(t.text))
            p.drawText(r.adjusted(44, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        p.end()


class NavPane(QWidget):
    selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navPane")
        self.buttons: dict[str, NavButton] = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 10, 4, 10)
        v.setSpacing(2)
        head = QHBoxLayout()
        head.setContentsMargins(12, 2, 8, 14)
        head.setSpacing(10)
        self.logo = QLabel()
        self.logo.setFixedSize(22, 22)
        head.addWidget(self.logo)
        self.title = label(APP_NAME, "appTitle")
        head.addWidget(self.title, 1)
        v.addLayout(head)
        for key, text, ic in NAV_TOP:
            v.addWidget(self._make(key, text, ic))
        v.addStretch()
        for key, text, ic in NAV_BOTTOM:
            v.addWidget(self._make(key, text, ic))
        self._render_logo()
        theme.signals.changed.connect(self._render_logo)
        self.set_compact(False)

    def _render_logo(self) -> None:
        self.logo.setPixmap(icons.app_icon("#107c10").pixmap(22, 22))

    def _make(self, key: str, text: str, ic: str) -> NavButton:
        b = NavButton(key, text, ic)
        b.clicked.connect(lambda _=False, k=key: self.selected.emit(k))
        self.buttons[key] = b
        return b

    def set_current(self, key: str) -> None:
        for k, b in self.buttons.items():
            b.setChecked(k == key)

    def set_compact(self, compact: bool) -> None:
        self.title.setVisible(not compact)
        for b in self.buttons.values():
            b.set_compact(compact)
        self.setFixedWidth(56 if compact else 232)


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine):
        super().__init__()
        self.engine = engine
        self.settings = engine.settings
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(880, 600)
        self._quitting = False
        self._pages: dict[str, QWidget] = {}
        self._page_keys: list[str] = []
        self.tray: Optional[QSystemTrayIcon] = None
        self.osd = OSD()

        self._build()
        self._build_tray()
        self._wire_engine()
        self._shortcuts()
        self.apply_theme()
        self.apply_diagram_style()
        self._restore_geometry()
        self.restart_refresh_timer()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_bar)
        self._status_timer.start(1000)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.nav = NavPane()
        self.nav.selected.connect(self.go_to)
        h.addWidget(self.nav)

        self.content_area = QWidget()
        self.content_area.setObjectName("contentArea")
        cv = QVBoxLayout(self.content_area)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self._build_command_bar())
        cv.addWidget(divider())

        self.banners: dict[str, InfoBar] = {}
        self._banner_box = QVBoxLayout()
        self._banner_box.setContentsMargins(32, 12, 32, 0)
        self._banner_box.setSpacing(8)
        banner_holder = QWidget()
        banner_holder.setLayout(self._banner_box)
        self._banner_holder = banner_holder
        banner_holder.hide()
        cv.addWidget(banner_holder)

        self.stack = QStackedWidget()
        cv.addWidget(self.stack, 1)
        h.addWidget(self.content_area, 1)
        self.setCentralWidget(root)

        for key, cls in (("mapping", MappingPage), ("tuning", TuningPage), ("test", TestPage),
                         ("profiles", ProfilesPage), ("settings", SettingsPage), ("about", AboutPage)):
            self._add_page(key, cls(self.engine, self))

        self.toasts = ToastHost(self.content_area)

        sb = self.statusBar()
        sb.setSizeGripEnabled(True)
        self.sb_profile = QLabel()
        self.sb_emulation = QLabel()
        self.sb_capture = QLabel()
        self.sb_rate = QLabel()
        self.sb_hints = QLabel()
        for w in (self.sb_profile, self.sb_emulation, self.sb_capture, self.sb_rate):
            sb.addWidget(w)
        sb.addPermanentWidget(self.sb_hints)
        self.refresh_hotkey_hints()

    def _add_page(self, key: str, page: QWidget) -> None:
        self._pages[key] = page
        self._page_keys.append(key)
        self.stack.addWidget(page)

    def _build_command_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        h = QHBoxLayout(bar)
        h.setContentsMargins(24, 8, 16, 8)
        h.setSpacing(10)
        self.status_pill = StatusPill("Starting…", "off")
        self.status_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_pill.setToolTip("Virtual controller status — click for details")
        self.status_pill.clicked.connect(lambda: self.go_to("settings"))
        h.addWidget(self.status_pill)
        self.profile_chip = button("", "subtle", icon="layers", on_click=lambda: self.go_to("profiles"),
                                   tooltip="Active profile — click to manage profiles")
        h.addWidget(self.profile_chip)
        h.addStretch()
        h.addWidget(label("Emulation", "body2"))
        self.emulation_toggle = LabeledToggle(True, "On", "Off")
        self.emulation_toggle.setAccessibleName("Emulation")
        self.emulation_toggle.toggled.connect(self.engine.set_emulation)
        h.addWidget(self.emulation_toggle)
        h.addSpacing(6)
        self.capture_btn = button("Capture mouse", icon="target", on_click=self.engine.toggle_capture)
        self.capture_btn.setMinimumWidth(170)
        h.addWidget(self.capture_btn)
        self.release_btn = button("Release all", "danger", icon="stop", on_click=self.engine.emergency_release)
        h.addWidget(self.release_btn)
        return bar

    def _shortcuts(self) -> None:
        for i, key in enumerate(self._page_keys, start=1):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, activated=lambda k=key: self.go_to(k))
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.quit_app)
        QShortcut(QKeySequence("F1"), self, activated=lambda: self.go_to("about"))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self.go_to("settings"))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def go_to(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.nav.set_current(key)
        page.on_show()
        self.settings.set("window", "last_page", self._page_keys.index(key), autosave=False)

    def current_page(self):
        return self.stack.currentWidget()

    # ------------------------------------------------------------------
    # Engine wiring
    # ------------------------------------------------------------------

    def _wire_engine(self) -> None:
        e = self.engine
        e.connection_changed.connect(self._on_connection)
        e.emulation_changed.connect(self._on_emulation)
        e.capture_changed.connect(self._on_capture)
        e.profile_changed.connect(self._on_profile)
        e.profiles_changed.connect(self._rebuild_tray_profiles)
        e.notify.connect(lambda title, msg, level: self.toast(title, msg, level))
        e.osd.connect(self._on_osd)
        e.show_window_requested.connect(self.show_and_raise)

    def sync_from_engine(self) -> None:
        """Pull the full current state (used once after engine.start())."""
        e = self.engine
        self._on_connection(e.connected, e.controller.last_error or "")
        self._on_emulation(e.emulation_enabled)
        self._on_capture(e.captured)
        if e.profile:
            self._on_profile(e.profile.name)
        if e.input_error:
            self.show_banner("Keyboard and mouse capture is unavailable", e.input_error, "error", reason="input")
        last = self.settings.get("window", "last_page", 0)
        self.go_to(self._page_keys[last] if isinstance(last, int) and 0 <= last < len(self._page_keys) else "mapping")

    def _on_connection(self, connected: bool, message: str) -> None:
        if connected:
            self.status_pill.set_status("Controller connected", "ok")
            self.hide_banner("driver")
        else:
            self.status_pill.set_status("Controller not connected", "error")
            self.show_banner(
                "Virtual controller not connected",
                "Install the ViGEmBus driver (free, one-time), then press Reconnect. "
                + (f"Details: {message}" if message else ""),
                "error", reason="driver",
                actions=[("Get ViGEmBus", lambda: QDesktopServices.openUrl(QUrl(VIGEMBUS_URL)), None),
                         ("Reconnect", self._reconnect, "primary")])
        self._update_tray()

    def _reconnect(self) -> None:
        if self.engine.reconnect_controller():
            self.toast("Virtual controller connected", "", "success")

    def _on_emulation(self, enabled: bool) -> None:
        self.emulation_toggle.setChecked(enabled)
        self.capture_btn.setEnabled(enabled or self.engine.captured)
        self._update_status_bar()
        self._update_tray()

    def _on_capture(self, captured: bool) -> None:
        hk = keycodes.combo_display(self.settings.get("hotkeys", "toggle_mouse_capture", "f8"))
        self.capture_btn.setText(f"Release mouse ({hk})" if captured else f"Capture mouse ({hk})")
        self.capture_btn.setProperty("kind", "toggleOn" if captured else None)
        repolish(self.capture_btn)
        self._update_status_bar()
        self._update_tray()

    def _on_profile(self, name: str) -> None:
        self.profile_chip.setText(name)
        self._rebuild_tray_profiles()
        self._update_status_bar()

    def _on_osd(self, text: str, kind: str) -> None:
        if self.settings.get("general", "show_osd", True) and not self.isActiveWindow():
            self.osd.show_message(text, kind)
        if self.tray and self.settings.get("general", "tray_notifications", False) and not self.isActiveWindow():
            self.tray.showMessage(APP_NAME, text, QSystemTrayIcon.MessageIcon.Information, 2000)

    def refresh_hotkey_hints(self) -> None:
        h = self.settings.section("hotkeys")
        cap = keycodes.combo_display(h.get("toggle_mouse_capture", ""))
        rel = keycodes.combo_display(h.get("emergency_release", ""))
        emu = keycodes.combo_display(h.get("toggle_emulation", ""))
        self.capture_btn.setToolTip(f"Turn mouse movement into stick movement ({cap})")
        self.release_btn.setToolTip(f"Instantly release every input and the mouse ({rel})")
        self.emulation_toggle.setToolTip(f"Turn keyboard/mouse → controller translation on or off ({emu})")
        self.sb_hints.setText(f"{cap} capture  •  {emu} emulation  •  {rel} release all")
        self._on_capture(self.engine.captured)

    def _update_status_bar(self) -> None:
        e = self.engine
        self.sb_profile.setText(f"Profile: {e.profile.name if e.profile else '-'}")
        self.sb_emulation.setText("Emulation: " + ("On" if e.emulation_enabled else "Off"))
        self.sb_capture.setText("Mouse: " + ("Captured" + (" (Raw Input)" if e.input.using_raw_input else "")
                                             if e.captured else "Free"))
        hz = e.measured_tick_hz
        self.sb_rate.setText(f"Engine: {hz:.0f} Hz" if hz else "")

    # ------------------------------------------------------------------
    # Banner & toasts
    # ------------------------------------------------------------------

    def show_banner(self, title: str, message: str, level: str = "warning", reason: str = "general",
                    actions: list[tuple[str, Callable, Optional[str]]] | None = None) -> None:
        bar = self.banners.get(reason)
        if bar is None:
            bar = InfoBar(title, message, level, closable=True)
            bar.closed.connect(self._update_banner_holder)
            self.banners[reason] = bar
            self._banner_box.addWidget(bar)
        bar.set_content(title, message, level)
        bar.clear_actions()
        for text, cb, kind in actions or []:
            bar.add_action(text, cb, kind)
        bar.show()
        self._update_banner_holder()

    def hide_banner(self, reason: str) -> None:
        bar = self.banners.get(reason)
        if bar:
            bar.hide()
        self._update_banner_holder()

    def _update_banner_holder(self) -> None:
        self._banner_holder.setVisible(any(not b.isHidden() for b in self.banners.values()))

    def toast(self, title: str, message: str = "", level: str = "info",
              action: tuple[str, Callable] | None = None) -> None:
        self.toasts.show_toast(title, message, level, action=action)

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------

    def apply_theme(self) -> None:
        a = self.settings.section("appearance")
        theme.apply(QApplication.instance(), a.get("theme", "dark"), a.get("accent", "green"))
        self._apply_title_bar()
        self._update_tray()

    def _apply_title_bar(self) -> None:
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            value = ctypes.c_int(1 if theme.T.dark else 0)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, then pre-20H1)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                              ctypes.sizeof(value)) == 0:
                    break
        except Exception:
            pass

    def apply_diagram_style(self) -> None:
        a = self.settings.section("appearance")
        style = a.get("diagram_style", "vector")
        image = cal = None
        if style == "photo":
            image = resource_path("assets", "controller_reference.png")
            custom_cal = a.get("photo_calibration_path")
            cal = custom_cal if custom_cal and os.path.exists(custom_cal) else \
                resource_path("assets", "controller_calibration.json")
        elif style == "custom":
            image, cal = a.get("custom_image_path"), a.get("custom_calibration_path")
        for page in (self._pages["mapping"], self._pages["test"]):
            if image and cal and os.path.exists(image) and os.path.exists(cal):
                if not page.diagram.use_image(image, cal):
                    page.diagram.use_vector()
                    self.toast("Couldn't load the controller photo", "Showing the illustration instead.", "warning")
            elif style == "model3d":
                if not page.diagram.use_vector("3d") and page is self._pages["mapping"]:
                    self.toast("3D model assets not found", "Showing the 2.5D illustration instead.", "warning")
            else:
                page.diagram.use_vector("2.5d")

    def restart_refresh_timer(self) -> None:
        hz = self.settings.get("appearance", "ui_refresh_hz", 60)
        try:
            hz = max(10, min(240, int(hz)))
        except (TypeError, ValueError):
            hz = 60
        if not hasattr(self, "_refresh_timer"):
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._refresh_timer.timeout.connect(self._refresh_live)
        self._refresh_timer.start(int(1000 / hz))

    def _refresh_live(self) -> None:
        if not self.isVisible() or self.isMinimized():
            return
        page = self.current_page()
        if page is not None:
            page.refresh_live()

    def settings_reset(self) -> None:
        self.apply_theme()
        self.apply_diagram_style()
        self.restart_refresh_timer()
        self.refresh_hotkey_hints()
        old = self._pages["settings"]
        new = SettingsPage(self.engine, self)
        idx = self.stack.indexOf(old)
        self.stack.insertWidget(idx, new)
        self.stack.removeWidget(old)
        old.deleteLater()
        self._pages["settings"] = new
        self.go_to("settings")
        self.toast("Settings restored to defaults", "", "success")

    # ------------------------------------------------------------------
    # Tray
    # ------------------------------------------------------------------

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("System tray not available; closing the window will exit.")
            return
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        menu = QMenu()
        self.tray_show = QAction("Open " + APP_NAME, menu)
        self.tray_show.triggered.connect(self.show_and_raise)
        f = self.tray_show.font()
        f.setBold(True)
        self.tray_show.setFont(f)
        menu.addAction(self.tray_show)
        menu.addSeparator()
        self.tray_emulation = QAction("Emulation", menu, checkable=True)
        self.tray_emulation.triggered.connect(self.engine.set_emulation)
        menu.addAction(self.tray_emulation)
        self.tray_capture = QAction("Capture mouse", menu, checkable=True)
        self.tray_capture.triggered.connect(self.engine.set_capture)
        menu.addAction(self.tray_capture)
        release = QAction("Release all inputs", menu)
        release.triggered.connect(self.engine.emergency_release)
        menu.addAction(release)
        menu.addSeparator()
        self.tray_profiles = QMenu("Profile", menu)
        menu.addMenu(self.tray_profiles)
        menu.addSeparator()
        quit_action = QAction("Exit", menu)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
                self.hide()
            else:
                self.show_and_raise()

    def _rebuild_tray_profiles(self) -> None:
        if not self.tray:
            return
        self.tray_profiles.clear()
        group = QActionGroup(self.tray_profiles)
        group.setExclusive(True)
        active = self.engine.profile.name if self.engine.profile else None
        for name in self.engine.profiles.list_profiles():
            act = QAction(name, self.tray_profiles, checkable=True)
            act.setChecked(name == active)
            act.triggered.connect(lambda _=False, n=name: self.engine.load_profile(n))
            group.addAction(act)
            self.tray_profiles.addAction(act)

    def _update_tray(self) -> None:
        if not self.tray:
            return
        e = self.engine
        self.tray.setIcon(icons.status_icon(e.emulation_enabled and e.connected, e.captured))
        state = "not connected" if not e.connected else ("mouse captured" if e.captured else
                                                          ("on" if e.emulation_enabled else "off"))
        self.tray.setToolTip(f"{APP_NAME} — {state}")
        self.tray_emulation.setChecked(e.emulation_enabled)
        self.tray_capture.setChecked(e.captured)

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def resizeEvent(self, e) -> None:
        self.nav.set_compact(self.width() < COMPACT_BREAKPOINT)
        super().resizeEvent(e)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._apply_title_bar()

    def _restore_geometry(self) -> None:
        w = self.settings.section("window")
        width, height = int(w.get("width") or 1280), int(w.get("height") or 800)
        self.resize(max(width, self.minimumWidth()), max(height, self.minimumHeight()))
        x, y = w.get("x"), w.get("y")
        if isinstance(x, int) and isinstance(y, int) and QGuiApplication.screenAt(QPoint(x + 60, y + 20)):
            self.move(x, y)
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.resize(min(self.width(), geo.width() - 40), min(self.height(), geo.height() - 60))
                self.move(geo.center() - self.rect().center())
        self._start_maximized = bool(w.get("maximized"))

    def show_initial(self) -> None:
        if self._start_maximized:
            self.showMaximized()
        else:
            self.show()

    def _save_geometry(self) -> None:
        w = self.settings.section("window")
        w["maximized"] = self.isMaximized()
        if not self.isMaximized() and not self.isMinimized():
            g = self.geometry()
            w.update({"width": g.width(), "height": g.height(), "x": self.x(), "y": self.y()})
        self.settings.save()

    def closeEvent(self, event) -> None:
        if not self._quitting and self.tray and self.settings.get("general", "minimize_to_tray", True):
            event.ignore()
            self._save_geometry()
            self.hide()
            if not self.settings.get("general", "tray_hint_shown", False):
                self.tray.showMessage(APP_NAME, "Still running in the notification area. Right-click the icon "
                                      "to exit.", QSystemTrayIcon.MessageIcon.Information, 4000)
                self.settings.set("general", "tray_hint_shown", True)
            return
        event.accept()
        self.quit_app()

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._save_geometry()
        self.engine.shutdown()
        if self.tray:
            self.tray.hide()
        self.osd.close()
        QApplication.instance().quit()

