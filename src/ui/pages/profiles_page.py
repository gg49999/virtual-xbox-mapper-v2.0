"""
Profiles page: create, activate, duplicate, rename, import/export,
reset and delete profiles, and edit each profile's description.
"""
from __future__ import annotations

import datetime
import os

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QFileDialog, QInputDialog,
    QLineEdit, QSplitter, QWidget, QFrame,
)

from profile_manager import validate_profile_name, TARGET_NAMES
from ui.binding_dialog import confirm
from ui.pages.base import Page
from ui.widgets import Card, button, label, divider, KeyChip, FlowLayoutWidget


def _ask_name(parent, title: str, prompt: str, text: str = "") -> str | None:
    while True:
        name, ok = QInputDialog.getText(parent, title, prompt, QLineEdit.EchoMode.Normal, text)
        if not ok:
            return None
        err = validate_profile_name(name)
        if not err:
            return name.strip()
        parent.window().toast("Invalid name", err, "warning")
        text = name


class ProfilesPage(Page):
    def __init__(self, engine, window):
        super().__init__("Profiles", "A profile is a complete layout: bindings, behaviors and tuning. "
                                     "Switch profiles with Ctrl+Alt+←/→ while playing.")
        self.engine = engine
        self.window = window
        self.actions.addWidget(button("Import…", icon="download", on_click=self._import))
        self.actions.addWidget(button("New profile", "primary", icon="plus", on_click=self._new))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        list_card = QFrame()
        list_card.setProperty("card", True)
        lv = QVBoxLayout(list_card)
        lv.setContentsMargins(8, 8, 8, 8)
        self.list = QListWidget()
        self.list.setAccessibleName("Profiles")
        self.list.currentItemChanged.connect(lambda *_: self._show_details())
        self.list.itemDoubleClicked.connect(lambda *_: self._activate())
        lv.addWidget(self.list, 1)
        folder_btn = button("Open profiles folder", "link", on_click=self._open_folder)
        lv.addWidget(folder_btn)
        list_card.setMinimumWidth(260)
        list_card.setMaximumWidth(380)
        splitter.addWidget(list_card)

        self.details = Card(padding=20)
        d = self.details.body()
        head = QHBoxLayout()
        self.d_name = label("", "title")
        head.addWidget(self.d_name, 1)
        self.d_badge = label("Active", "caption")
        head.addWidget(self.d_badge)
        d.addLayout(head)
        self.d_meta = label("", "caption")
        d.addWidget(self.d_meta)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.activate_btn = button("Use this profile", "primary", icon="check", on_click=self._activate)
        row.addWidget(self.activate_btn)
        row.addWidget(button("Duplicate", icon="copy", on_click=self._duplicate))
        row.addWidget(button("Rename", icon="edit", on_click=self._rename))
        row.addWidget(button("Export…", icon="upload", on_click=self._export))
        row.addStretch()
        d.addLayout(row)
        d.addWidget(divider())
        d.addWidget(label("Description", "section"))
        self.d_desc = QPlainTextEdit()
        self.d_desc.setPlaceholderText("What is this profile for? (e.g. “Halo Infinite — low sensitivity”)")
        self.d_desc.setFixedHeight(72)
        self.d_desc.textChanged.connect(lambda: self._desc_timer.start())
        d.addWidget(self.d_desc)
        self._desc_timer = QTimer(self)
        self._desc_timer.setSingleShot(True)
        self._desc_timer.setInterval(600)
        self._desc_timer.timeout.connect(self._save_description)
        d.addWidget(label("Bindings", "section"))
        self.d_bindings = QWidget()
        self.d_bindings_layout = QVBoxLayout(self.d_bindings)
        self.d_bindings_layout.setContentsMargins(0, 0, 0, 0)
        self.d_bindings_layout.setSpacing(4)
        d.addWidget(self.d_bindings)
        d.addStretch()
        d.addWidget(divider())
        danger = QHBoxLayout()
        danger.addWidget(button("Reset to default bindings", icon="refresh", on_click=self._reset))
        danger.addStretch()
        danger.addWidget(button("Delete profile", "danger", icon="trash", on_click=self._delete))
        d.addLayout(danger)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 700])
        self.content.addWidget(splitter, 1)

        engine.profiles_changed.connect(self.refresh)
        engine.profile_changed.connect(lambda _n: self.refresh())
        self.refresh()

    # ---- List ---------------------------------------------------------------

    def on_show(self) -> None:
        self.refresh()

    def _selected_name(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self, select: str | None = None) -> None:
        select = select or self._selected_name() or (self.engine.profile.name if self.engine.profile else None)
        active = self.engine.profile.name if self.engine.profile else None
        self.list.blockSignals(True)
        self.list.clear()
        for name in self.engine.profiles.list_profiles():
            item = QListWidgetItem(("●  " if name == active else "     ") + name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip("Active profile" if name == active else "Double-click to use")
            self.list.addItem(item)
            if name == select:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._show_details()

    def _show_details(self) -> None:
        name = self._selected_name()
        if not name:
            return
        active = self.engine.profile
        try:
            profile = active if active and active.name == name else self.engine.profiles.load(name)
        except (OSError, ValueError) as exc:
            self.d_name.setText(name)
            self.d_meta.setText(f"Couldn't read this profile: {exc}")
            return
        is_active = active is not None and active.name == name
        self.d_name.setText(profile.name)
        self.d_badge.setVisible(is_active)
        self.activate_btn.setEnabled(not is_active)
        modified = datetime.datetime.fromtimestamp(profile.modified).strftime("%b %d, %Y %I:%M %p") \
            if profile.modified else "unknown"
        n_controls = sum(1 for c in profile.bindings.values() if c)
        self.d_meta.setText(f"{n_controls} controls bound • {profile.binding_count()} inputs • "
                            f"last modified {modified}")
        self.d_desc.blockSignals(True)
        self.d_desc.setPlainText(profile.description)
        self.d_desc.blockSignals(False)
        while self.d_bindings_layout.count():
            item = self.d_bindings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for target, codes in list(profile.bindings.items())[:10]:
            if not codes:
                continue
            row = QHBoxLayout()
            w = QWidget()
            w.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            name_lbl = label(TARGET_NAMES.get(target, target), "body2")
            name_lbl.setMinimumWidth(150)
            row.addWidget(name_lbl)
            chips = FlowLayoutWidget(4)
            for c in codes:
                chips.add(KeyChip(c, small=True))
            row.addWidget(chips, 1)
            self.d_bindings_layout.addWidget(w)
        extra = n_controls - min(10, n_controls)
        if extra > 0:
            self.d_bindings_layout.addWidget(label(f"+ {extra} more — open the Mapping page to see all.", "caption"))

    def _save_description(self) -> None:
        name = self._selected_name()
        if not name:
            return
        text = self.d_desc.toPlainText().strip()
        try:
            if self.engine.profile and self.engine.profile.name == name:
                self.engine.profile.description = text
                self.engine.save_active_profile()
            else:
                p = self.engine.profiles.load(name)
                p.description = text
                self.engine.profiles.save(p)
        except (OSError, ValueError) as exc:
            self.window.toast("Couldn't save description", str(exc), "error")

    # ---- Actions ---------------------------------------------------------------

    def _run(self, fn, success: str | None = None) -> bool:
        try:
            fn()
        except (OSError, ValueError) as exc:
            self.window.toast("Something went wrong", str(exc), "error")
            return False
        if success:
            self.window.toast(success, "", "success")
        return True

    def _new(self) -> None:
        name = _ask_name(self, "New profile", "Profile name:", self.engine.profiles.unique_name("New Profile"))
        if not name:
            return
        if self._run(lambda: self.engine.profiles.create(name)):
            self.engine.profiles_changed.emit()
            self.engine.load_profile(name, announce=False)
            self.refresh(name)
            self.window.toast(f"Created “{name}”", "It starts with the default WASD + mouse layout.",
                              "success")

    def _activate(self) -> None:
        name = self._selected_name()
        if name and (not self.engine.profile or self.engine.profile.name != name):
            self.engine.load_profile(name, announce=False)
            self.window.toast(f"Now using “{name}”", "", "success")

    def _duplicate(self) -> None:
        name = self._selected_name()
        if not name:
            return
        self.engine.flush_pending_save()
        new = _ask_name(self, "Duplicate profile", "Name for the copy:", self.engine.profiles.unique_name(f"{name} copy"))
        if new and self._run(lambda: self.engine.profiles.duplicate(name, new), f"Duplicated as “{new}”"):
            self.engine.profiles_changed.emit()
            self.refresh(new)

    def _rename(self) -> None:
        name = self._selected_name()
        if not name:
            return
        new = _ask_name(self, "Rename profile", "New name:", name)
        if not new or new == name:
            return
        self.engine.flush_pending_save()
        was_active = self.engine.profile and self.engine.profile.name == name
        if self._run(lambda: self.engine.profiles.rename(name, new), f"Renamed to “{new}”"):
            if was_active:
                self.engine.load_profile(new, announce=False)
            self.engine.profiles_changed.emit()
            self.refresh(new)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import profile", os.path.expanduser("~"), "Profiles (*.json)")
        if not path:
            return
        try:
            profile = self.engine.profiles.import_profile(path)
        except (OSError, ValueError) as exc:
            self.window.toast("Import failed", f"That file isn't a valid profile ({exc}).", "error")
            return
        except Exception as exc:  # json.JSONDecodeError is a ValueError, but be safe with odd files
            self.window.toast("Import failed", str(exc), "error")
            return
        self.engine.profiles_changed.emit()
        self.refresh(profile.name)
        self.window.toast(f"Imported “{profile.name}”", "", "success")

    def _export(self) -> None:
        name = self._selected_name()
        if not name:
            return
        self.engine.flush_pending_save()
        path, _ = QFileDialog.getSaveFileName(self, "Export profile",
                                              os.path.join(os.path.expanduser("~"), f"{name}.json"),
                                              "Profiles (*.json)")
        if path:
            self._run(lambda: self.engine.profiles.export_profile(name, path), "Profile exported")

    def _reset(self) -> None:
        name = self._selected_name()
        if not name or not confirm(self, "Reset profile",
                                   f"Reset “{name}” to the default bindings and tuning?", "Reset", True):
            return
        if self._run(lambda: self.engine.profiles.reset_to_default(name), f"“{name}” was reset"):
            if self.engine.profile and self.engine.profile.name == name:
                self.engine.load_profile(name, announce=False)
            self.refresh(name)

    def _delete(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if len(self.engine.profiles.list_profiles()) <= 1:
            self.window.toast("Can't delete", "You need at least one profile.", "warning")
            return
        if not confirm(self, "Delete profile", f"Delete “{name}”? This can't be undone.", "Delete", True):
            return
        was_active = self.engine.profile and self.engine.profile.name == name
        if self._run(lambda: self.engine.profiles.delete(name), f"Deleted “{name}”"):
            if was_active:
                self.engine.load_profile(self.engine.profiles.list_profiles()[0], announce=False)
            self.engine.profiles_changed.emit()
            self.refresh()

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.engine.profiles.dir))

