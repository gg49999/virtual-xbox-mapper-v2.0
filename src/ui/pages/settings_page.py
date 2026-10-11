"""
Settings page: application-wide preferences grouped into cards,
Windows Settings style. Every change applies immediately.
"""
from __future__ import annotations

import os
import shutil
from PyQt6.QtCore import Qt, QRectF, QUrl, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QDesktopServices, QStandardItemModel
from PyQt6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QWidget

import keycodes
from app_info import VIGEMBUS_URL
from controller_models import DEFAULT_MODEL_ID, MODELS, get_model
from engine import HOTKEY_ACTIONS, TICK_RATES
from hotkey_manager import find_duplicate
from logger import get_logger, set_level, log_file_path
from paths import controller_image_dir, log_dir, roaming_dir, resource_path
from ui import theme
from ui.binding_dialog import confirm
from ui.calibration_dialog import CalibrationDialog
from ui.pages.base import Page
from ui.widgets import (
    Card, SettingRow, LabeledToggle, HotkeyEdit, StatusPill, InfoBar, button, label, divider,
)
import startup

log = get_logger("SettingsPage")


class AccentPicker(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, value: str, parent=None):
        super().__init__(parent)
        self._value = value
        self._keys = list(theme.ACCENTS.keys())
        self.setFixedSize(len(self._keys) * 34, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Accent color")
        theme.signals.changed.connect(self.update)
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        self.setToolTip("Accent color: " + theme.ACCENTS[self._value][0])

    def set_value(self, v: str) -> None:
        self._value = v
        self._update_tooltip()
        self.update()

    def mousePressEvent(self, e):
        idx = int(e.position().x() // 34)
        if 0 <= idx < len(self._keys):
            self._select(self._keys[idx])

    def keyPressEvent(self, e):
        i = self._keys.index(self._value)
        if e.key() == Qt.Key.Key_Right:
            self._select(self._keys[(i + 1) % len(self._keys)])
        elif e.key() == Qt.Key.Key_Left:
            self._select(self._keys[(i - 1) % len(self._keys)])
        else:
            super().keyPressEvent(e)

    def _select(self, key: str) -> None:
        if key != self._value:
            self.set_value(key)
            self.changed.emit(key)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, key in enumerate(self._keys):
            _, light, dark = theme.ACCENTS[key]
            c = QRectF(i * 34 + 4, 4, 22, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(dark if theme.T.dark else light))
            p.drawEllipse(c)
            if key == self._value:
                p.setPen(QPen(theme.qcolor(theme.T.text), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c.adjusted(-3, -3, 3, 3))
        if self.hasFocus():
            p.setPen(QPen(theme.qcolor(theme.T.accent), 1, Qt.PenStyle.DotLine))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()


class SettingsPage(Page):
    def __init__(self, engine, window):
        super().__init__("Settings", "", scroll=True, max_width=980)
        self.engine = engine
        self.window = window
        self.s = engine.settings
        self.content.addWidget(self._general())
        self.content.addWidget(self._controller())
        self.content.addWidget(self._capture())
        self.content.addWidget(self._hotkeys())
        self.content.addWidget(self._appearance())
        self.content.addWidget(self._advanced())
        self.content.addStretch()
        engine.connection_changed.connect(lambda ok, msg: self._update_status())
        self._update_status()

    # ---- helpers ----------------------------------------------------------

    def _toggle(self, section: str, key: str, on_change=None) -> LabeledToggle:
        t = LabeledToggle(bool(self.s.get(section, key)))

        def changed(v, section=section, key=key):
            self.s.set(section, key, v)
            if on_change:
                on_change(v)
        t.toggled.connect(changed)
        return t

    def _combo(self, items: list[tuple], current, on_change) -> QComboBox:
        c = QComboBox()
        for value, text in items:
            c.addItem(text, value)
        idx = c.findData(current)
        c.setCurrentIndex(max(0, idx))
        c.currentIndexChanged.connect(lambda _i, c=c: on_change(c.currentData()))
        return c

    # ---- cards ----------------------------------------------------------------

    def _general(self) -> Card:
        card = Card("General", icon="home")
        startup_toggle = LabeledToggle(startup.is_enabled() if startup.supported() else False)
        startup_toggle.setEnabled(startup.supported())
        startup_toggle.toggled.connect(self._set_startup)
        card.add(SettingRow("Start with Windows", "Launch minimized to the tray when you sign in.", startup_toggle))
        card.add(divider())
        card.add(SettingRow("Start minimized", "Open in the notification area instead of showing this window.",
                            self._toggle("general", "start_minimized")))
        card.add(divider())
        card.add(SettingRow("Keep running when closed", "Closing the window keeps the controller active in the "
                            "notification area. Use Exit from the tray menu to quit.",
                            self._toggle("general", "minimize_to_tray")))
        card.add(divider())
        card.add(SettingRow("Turn on emulation at launch", "",
                            self._toggle("general", "emulation_on_launch")))
        card.add(divider())
        card.add(SettingRow("Remember last profile", "Otherwise the “Default” profile is loaded at launch.",
                            self._toggle("general", "auto_load_last_profile")))
        card.add(divider())
        card.add(SettingRow("On-screen notifications", "Briefly show a banner over your game when a hotkey "
                            "changes something (capture, emulation, profile).",
                            self._toggle("general", "show_osd")))
        card.add(divider())
        card.add(SettingRow("Tray notifications", "Also show Windows notifications for hotkey actions.",
                            self._toggle("general", "tray_notifications")))
        return card

    def _controller(self) -> Card:
        card = Card("Virtual controller", "The controller that Windows and your games see.", icon="gamepad")
        status_row = QHBoxLayout()
        self.status_pill = StatusPill()
        status_row.addWidget(self.status_pill)
        self.status_msg = label("", "caption", wrap=True)
        status_row.addWidget(self.status_msg, 1)
        self.reconnect_btn = button("Reconnect", icon="refresh", on_click=self._reconnect)
        status_row.addWidget(self.reconnect_btn)
        status_row.addWidget(button("Get driver", icon="link",
                                    on_click=lambda: QDesktopServices.openUrl(QUrl(VIGEMBUS_URL)),
                                    tooltip="Download the ViGEmBus driver"))
        card.body().addLayout(status_row)
        card.add(divider())
        # Controller type. Entries the installed driver can't present are
        # listed but disabled; the note below the row says why (_sync_model).
        self.model_combo = QComboBox()
        # Keep the box compact - its width would otherwise follow the longest
        # entry - and let the drop-down list be as wide as its entries need.
        self.model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model_combo.setMinimumContentsLength(26)
        self.model_combo.activated.connect(lambda index: self._set_model(self.model_combo.itemData(index)))
        self.model_row = SettingRow("Controller type", "How it identifies itself to Windows and games.",
                                    self.model_combo)
        card.add(self.model_row)
        # What is in effect and why; filled in by _sync_model.
        self.model_note = label("", "caption", wrap=True)
        card.add(self.model_note)
        card.add(divider())
        card.add(SettingRow("Connect automatically", "Create the virtual controller when the app starts.",
                            self._toggle("general", "auto_enable_controller")))
        card.add(divider())
        rate = self._combo([(hz, f"{hz} Hz" + ("  (recommended)" if hz == 125 else "")) for hz in TICK_RATES],
                           self.engine.tick_rate, self._set_rate)
        card.add(SettingRow("Update rate", "How often stick ramps and mouse aim are recalculated. Higher is "
                            "smoother but uses more CPU.", rate))
        card.add(divider())
        card.add(SettingRow("Round stick output", "Limit diagonal key presses (e.g. W+D) to the stick's circle, "
                            "like a real thumbstick.",
                            self._toggle("controller", "circular_sticks", lambda _v: self.engine.apply_profile_tuning())))
        return card

    def _capture(self) -> Card:
        card = Card("Mouse capture", "While captured, mouse movement drives a stick and the cursor is parked.",
                    icon="target")
        card.add(SettingRow("Hide the cursor while captured", "",
                            self._toggle("capture", "hide_cursor")))
        card.add(divider())
        card.add(SettingRow("Release when switching windows",
                            "Automatically release the mouse if you Alt+Tab away from the game.",
                            self._toggle("capture", "release_on_focus_change")))
        card.add(divider())
        card.add(SettingRow("Use Raw Input", "Read mouse movement directly from the device for the most precise "
                            "aim (recommended). Turn off only if aiming doesn't respond.",
                            self._toggle("capture", "use_raw_input")))
        return card

    def _hotkeys(self) -> Card:
        card = Card("Hotkeys", "Global shortcuts that work while a game is focused. Click a shortcut, then "
                    "press the new keys. Backspace clears it.", icon="keyboard")
        self.hotkey_warning = InfoBar("", "", "warning", closable=False)
        self.hotkey_warning.hide()
        card.add(self.hotkey_warning)
        self.hotkey_edits: dict[str, HotkeyEdit] = {}
        for i, (action, title) in enumerate(HOTKEY_ACTIONS.items()):
            edit = HotkeyEdit(self.s.get("hotkeys", action, ""))
            edit.comboChanged.connect(lambda combo, a=action: self._set_hotkey(a, combo))
            # Don't let the keys being recorded fire existing hotkeys or reach the game.
            edit.recording.connect(self.engine.set_suspended)
            self.hotkey_edits[action] = edit
            if i:
                card.add(divider())
            card.add(SettingRow(title, "", edit))
        restore = button("Restore default hotkeys", "subtle", icon="refresh", on_click=self._restore_hotkeys)
        card.header_actions.addWidget(restore)
        return card

    def _appearance(self) -> Card:
        card = Card("Appearance", icon="star")
        a = self.s.section("appearance")
        card.add(SettingRow("Theme", "", self._combo(
            [("dark", "Dark"), ("light", "Light"), ("system", "Use system setting")], a.get("theme", "dark"),
            lambda v: self._set_appearance("theme", v))))
        card.add(divider())
        self.accent = AccentPicker(a.get("accent", "green"))
        self.accent.changed.connect(lambda v: self._set_appearance("accent", v))
        card.add(SettingRow("Accent color", "", self.accent))
        card.add(divider())
        self.style_combo = self._combo(
            [("model3d", "3D model"), ("vector", "Illustration (2.5D)"), ("photo", "Photo"),
             ("custom", "Your own photo")],
            a.get("diagram_style", "vector"), self._set_diagram_style)
        card.add(SettingRow("Controller picture", "How the controller is drawn on the Mapping and Live test pages.",
                            self.style_combo))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Load your own photo…", icon="folder", on_click=self._choose_custom_image))
        self.recal_btn = button("Recalibrate", icon="target", on_click=self._recalibrate)
        row.addWidget(self.recal_btn)
        card.body().addLayout(row)
        card.add(divider())
        card.add(SettingRow("Live view refresh rate", "", self._combo(
            [(30, "30 fps (battery saver)"), (60, "60 fps"), (120, "120 fps")], a.get("ui_refresh_hz", 60),
            lambda v: self._set_appearance("ui_refresh_hz", v))))
        self._update_recal()
        return card

    def _advanced(self) -> Card:
        card = Card("Troubleshooting", icon="info")
        card.add(SettingRow("Log detail", "Use Debug when reporting a problem.", self._combo(
            [("ERROR", "Errors only"), ("WARNING", "Warnings"), ("INFO", "Normal"), ("DEBUG", "Debug")],
            self.s.get("advanced", "log_level", "INFO"), self._set_log_level)))
        card.add(divider())
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(button("Open log folder", icon="folder",
                             on_click=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir()))))
        row.addWidget(button("Open settings folder", icon="folder",
                             on_click=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(roaming_dir()))))
        row.addStretch()
        row.addWidget(button("Reset all settings", "danger", icon="refresh", on_click=self._reset_all))
        card.body().addLayout(row)
        path = log_file_path()
        if path:
            card.add(label(f"Log file: {path}", "caption", wrap=True))
        return card

    # ---- behaviours -------------------------------------------------------------

    def _update_status(self) -> None:
        if self.engine.connected:
            self.status_pill.set_status("Connected", "ok")
            self.status_msg.setText(f"Windows sees an {get_model(self.engine.controller.model).label}.")
        else:
            self.status_pill.set_status("Not connected", "error")
            self.status_msg.setText(self.engine.controller.last_error or "The virtual controller is not connected.")
        self._sync_model()

    # ---- controller type ---------------------------------------------------

    def _sync_model(self) -> None:
        """Bring the Controller type row in line with the saved choice and
        with what the installed driver supports. That can change while the
        app runs (install the driver, then Reconnect), so this runs on every
        connection change."""
        supported = self.engine.controller.supported_models
        requested = get_model(self.s.get("controller", "model", DEFAULT_MODEL_ID)).id
        combo = self.model_combo
        combo.blockSignals(True)
        combo.clear()
        item_model = combo.model()
        for model in MODELS:
            available = model.id in supported
            combo.addItem(model.label if available else f"{model.label} - not available", model.id)
            index = combo.count() - 1
            combo.setItemData(index, model.summary, Qt.ItemDataRole.ToolTipRole)
            if not available and isinstance(item_model, QStandardItemModel):
                item = item_model.item(index)
                if item is not None:
                    item.setEnabled(False)
        combo.setCurrentIndex(max(0, combo.findData(requested if requested in supported else DEFAULT_MODEL_ID)))
        popup = combo.view()
        if popup is not None:
            popup.setMinimumWidth(popup.sizeHintForColumn(0) + 32)
        combo.blockSignals(False)
        self.model_note.setText(self._model_description())
        combo.setAccessibleDescription(self.model_note.text())

    def _model_description(self) -> str:
        """What the virtual controller is presented as, and why that may not
        be what was selected."""
        controller = self.engine.controller
        supported = controller.supported_models
        requested = get_model(self.s.get("controller", "model", DEFAULT_MODEL_ID))
        effective = get_model(controller.model)

        if len(supported) <= 1:
            text = ("The installed ViGEmBus driver can only present an Xbox 360 controller. The other "
                    "types need the driver build that ships with this project (see driver/README.md).")
            if requested.id != DEFAULT_MODEL_ID:
                text += f" Your saved choice ({requested.label}) applies once it is installed."
            return text

        text = f"Windows and games see the virtual controller as an {effective.label}."
        if requested.id not in supported:
            text += f" Your saved choice ({requested.label}) is not supported by the installed driver."
        elif requested.id == DEFAULT_MODEL_ID and effective.id != DEFAULT_MODEL_ID:
            text += (" That is this PC's driver-wide default, which replaces Xbox 360 for every "
                     "application (driver\\ViGEmBus\\tools\\Set-XboxModel.ps1 changes it).")
        else:
            text += " Changing the type re-plugs the controller, so a running game sees a controller swap."
        return text

    def _set_model(self, model_id) -> None:
        engine = self.engine
        model = get_model(model_id)
        before = engine.controller.model
        if not engine.set_controller_model(model.id):
            self.window.toast("Couldn't switch controller type",
                              engine.controller.last_error or f"The installed driver can't present an {model.label}.",
                              "error")
        elif engine.connected and engine.controller.model != before:
            self.window.toast("Controller type changed",
                              f"Windows now sees an {get_model(engine.controller.model).label}.", "success")
        self._update_status()

    def _reconnect(self) -> None:
        if self.engine.reconnect_controller():
            self.window.toast("Virtual controller connected", "", "success")
        else:
            self.window.toast("Couldn't connect", self.engine.controller.last_error, "error")

    def _set_rate(self, hz) -> None:
        self.engine.set_tick_rate(int(hz))

    def _set_startup(self, on: bool) -> None:
        try:
            startup.set_enabled(on)
            self.s.set("general", "start_with_windows", on)
        except OSError as exc:
            self.window.toast("Couldn't change startup setting", str(exc), "error")

    def _set_hotkey(self, action: str, combo: str) -> None:
        combos = {a: self.s.get("hotkeys", a, "") for a in HOTKEY_ACTIONS}
        combos[action] = combo
        dup = find_duplicate(combos)
        if dup:
            other = dup[0] if dup[1] == action else dup[1]
            self.hotkey_warning.set_content(
                "Shortcut already in use",
                f"{keycodes.combo_display(combo)} is already used for “{HOTKEY_ACTIONS[other]}”.", "warning")
            self.hotkey_warning.show()
            self.hotkey_edits[action].set_combo(self.s.get("hotkeys", action, ""))
            return
        self.hotkey_warning.hide()
        self.s.set("hotkeys", action, combo)
        self.engine.reload_hotkeys()
        self.window.refresh_hotkey_hints()

    def _restore_hotkeys(self) -> None:
        self.s.reset_section("hotkeys")
        for action, edit in self.hotkey_edits.items():
            edit.set_combo(self.s.get("hotkeys", action, ""))
        self.hotkey_warning.hide()
        self.engine.reload_hotkeys()
        self.window.refresh_hotkey_hints()
        self.window.toast("Default hotkeys restored", "", "success")

    def _set_appearance(self, key: str, value) -> None:
        self.s.set("appearance", key, value)
        if key in ("theme", "accent"):
            self.window.apply_theme()
        elif key == "ui_refresh_hz":
            self.window.restart_refresh_timer()

    def _set_diagram_style(self, style: str) -> None:
        if style == "custom" and not self._custom_image_valid():
            self._choose_custom_image()
            return
        self.s.set("appearance", "diagram_style", style)
        self.window.apply_diagram_style()
        self._update_recal()

    def _custom_image_valid(self) -> bool:
        a = self.s.section("appearance")
        return bool(a.get("custom_image_path") and os.path.exists(a.get("custom_image_path"))
                    and a.get("custom_calibration_path") and os.path.exists(a.get("custom_calibration_path")))

    def _update_recal(self) -> None:
        self.recal_btn.setEnabled(self.s.get("appearance", "diagram_style", "vector") in ("photo", "custom"))

    def _choose_custom_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a controller photo", os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            self._sync_style_combo()
            return
        dlg = CalibrationDialog(path, self)
        if not dlg.exec() or not dlg.points:
            self._sync_style_combo()
            return
        img_dir = controller_image_dir()
        dest = os.path.join(img_dir, "custom" + (os.path.splitext(path)[1].lower() or ".png"))
        cal = os.path.join(img_dir, "calibration.json")
        try:
            if os.path.abspath(path) != os.path.abspath(dest):
                shutil.copyfile(path, dest)
            dlg.save_to(os.path.basename(dest), cal)
        except OSError as exc:
            self.window.toast("Couldn't save the photo", str(exc), "error")
            self._sync_style_combo()
            return
        self.s.section("appearance").update({"custom_image_path": dest, "custom_calibration_path": cal,
                                             "diagram_style": "custom"})
        self.s.save()
        self.window.apply_diagram_style()
        self._sync_style_combo()
        self._update_recal()
        self.window.toast("Your controller photo is now in use", "", "success")

    def _recalibrate(self) -> None:
        style = self.s.get("appearance", "diagram_style", "vector")
        if style == "custom" and self._custom_image_valid():
            image = self.s.get("appearance", "custom_image_path")
        else:
            image = resource_path("assets", "controller_reference.png")
        if not os.path.exists(image):
            self.window.toast("No photo to calibrate", "", "warning")
            return
        dlg = CalibrationDialog(image, self)
        if not dlg.exec() or not dlg.points:
            return
        img_dir = controller_image_dir()
        cal = os.path.join(img_dir, "calibration.json" if style == "custom" else "photo_calibration.json")
        try:
            dlg.save_to(os.path.basename(image), cal)
        except OSError as exc:
            self.window.toast("Couldn't save calibration", str(exc), "error")
            return
        key = "custom_calibration_path" if style == "custom" else "photo_calibration_path"
        self.s.set("appearance", key, cal)
        self.window.apply_diagram_style()
        self.window.toast("Calibration saved", "", "success")

    def _sync_style_combo(self) -> None:
        self.style_combo.blockSignals(True)
        self.style_combo.setCurrentIndex(max(0, self.style_combo.findData(
            self.s.get("appearance", "diagram_style", "vector"))))
        self.style_combo.blockSignals(False)

    def _set_log_level(self, level: str) -> None:
        self.s.set("advanced", "log_level", level)
        set_level(level)

    def _reset_all(self) -> None:
        if not confirm(self, "Reset all settings",
                       "Restore every setting (including hotkeys and appearance) to its default? "
                       "Your profiles are not affected.", "Reset", True):
            return
        self.s.reset_to_default()
        if startup.supported():
            try:
                startup.set_enabled(False)
            except OSError:
                pass
        self.engine.reload_hotkeys()
        self.engine.apply_controller_settings()
        self.window.settings_reset()

