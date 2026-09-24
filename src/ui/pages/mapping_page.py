"""
Mapping page: the interactive controller diagram plus an inspector.

Inspector has two views:
  * Overview - every control grouped by area, searchable by control or key.
  * Detail   - one control: its inputs, behaviour (hold/toggle/turbo),
               and control-specific options (trigger pull strength).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLineEdit, QScrollArea, QFrame, QStackedWidget,
    QComboBox, QSizePolicy,
)

import keycodes
from profile_manager import TARGET_GROUPS, TARGET_NAMES, TARGET_DESCRIPTIONS, TRIGGER_TARGETS
from ui import theme, icons
from ui.controller_diagram import ControllerDiagram
from ui.binding_dialog import BindingDialog
from ui.pages.base import Page
from ui.widgets import (
    KeyChip, FlowLayoutWidget, SegmentedControl, SliderRow, button, icon_button, label, divider,
    LabeledToggle,
)
from engine import HOTKEY_ACTIONS


class _ControlRow(QWidget):
    """Clickable row in the overview list: control name + key chips."""
    clicked = pyqtSignal(str)

    def __init__(self, target: str, parent=None):
        super().__init__(parent)
        self.target = target
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(TARGET_NAMES.get(target, target))
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 6, 8, 6)
        h.setSpacing(8)
        self.name = label(TARGET_NAMES.get(target, target))
        self.name.setMinimumWidth(110)
        h.addWidget(self.name, 1)
        self.mode_label = label("", "caption")
        h.addWidget(self.mode_label)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(4)
        h.addLayout(self.chips)
        self.unbound = label("Not bound", "caption")
        h.addWidget(self.unbound)
        chevron = QWidget()
        chevron.setFixedSize(16, 16)
        chevron.paintEvent = lambda _e, w=chevron: self._paint_chevron(w)
        h.addWidget(chevron)
        theme.signals.changed.connect(self.update)

    def _paint_chevron(self, w: QWidget) -> None:
        p = QPainter(w)
        from PyQt6.QtCore import QRectF
        icons.paint(p, "chevron_right", QRectF(0, 0, 16, 16), theme.qcolor(theme.T.text_3))
        p.end()

    def set_data(self, codes: list[str], mode: str) -> None:
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for code in codes[:3]:
            self.chips.addWidget(KeyChip(code, small=True))
        if len(codes) > 3:
            self.chips.addWidget(label(f"+{len(codes) - 3}", "caption"))
        self.unbound.setVisible(not codes)
        self.mode_label.setText({"toggle": "Toggle", "turbo": "Turbo"}.get(mode, ""))
        self.setToolTip(", ".join(keycodes.display_name(c) for c in codes) or "Not bound")

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.target)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.target)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        if not (self._hover or self.hasFocus()):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(theme.qcolor(theme.T.accent) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(theme.T.control_hover))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        p.end()


class Inspector(QFrame):
    target_selected = pyqtSignal(object)   # str or None

    def __init__(self, page: "MappingPage"):
        super().__init__()
        self.page = page
        self.engine = page.engine
        self.setProperty("card", True)
        self.setMinimumWidth(300)
        self.setMaximumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        v.addWidget(self.stack)
        self._build_overview()
        self._build_detail()
        self.target: Optional[str] = None

    # ---- Overview ----------------------------------------------------------

    def _build_overview(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 8, 8)
        v.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label("All controls", "subtitle"), 1)
        self.count_label = label("", "caption")
        head.addWidget(self.count_label)
        head.addSpacing(8)
        v.addLayout(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search controls or keys")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search", theme.T.text_3, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._filter)
        self.search.setAccessibleName("Search controls")
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 8, 0)
        search_row.addWidget(self.search)
        v.addLayout(search_row)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("pageScrollBody")
        self.rows_layout = QVBoxLayout(body)
        self.rows_layout.setContentsMargins(0, 0, 8, 0)
        self.rows_layout.setSpacing(0)
        self.rows: dict[str, _ControlRow] = {}
        self.sections: list[tuple[QWidget, list[str]]] = []
        for group, targets in TARGET_GROUPS:
            header = label(group.upper(), "section")
            header.setContentsMargins(10, 12, 0, 4)
            self.rows_layout.addWidget(header)
            for t in targets:
                row = _ControlRow(t)
                row.clicked.connect(self.page.select_target)
                self.rows[t] = row
                self.rows_layout.addWidget(row)
            self.sections.append((header, targets))
        self.empty_label = label("No controls match your search.", "caption")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()
        self.rows_layout.addWidget(self.empty_label)
        self.rows_layout.addStretch()
        area.setWidget(body)
        v.addWidget(area, 1)
        self.stack.addWidget(w)

    def _filter(self, text: str) -> None:
        q = text.strip().lower()
        profile = self.engine.profile
        any_visible = False
        for header, targets in self.sections:
            visible = 0
            for t in targets:
                codes = profile.inputs_for(t) if profile else []
                hay = " ".join([TARGET_NAMES.get(t, t), t] + codes + [keycodes.display_name(c) for c in codes]).lower()
                show = not q or q in hay
                self.rows[t].setVisible(show)
                visible += show
            header.setVisible(visible > 0)
            any_visible = any_visible or visible > 0
        self.empty_label.setVisible(not any_visible)

    def refresh_overview(self) -> None:
        profile = self.engine.profile
        if not profile:
            return
        for t, row in self.rows.items():
            row.set_data(profile.inputs_for(t), profile.mode_for(t))
        bound = sum(1 for t in self.rows if profile.inputs_for(t))
        self.count_label.setText(f"{bound} of {len(self.rows)} bound")
        self._filter(self.search.text())

    # ---- Detail ----------------------------------------------------------------

    def _build_detail(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 16, 16)
        v.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(4)
        back = button("All controls", "subtle", icon="chevron_left", on_click=lambda: self.page.select_target(None))
        top.addWidget(back)
        top.addStretch()
        v.addLayout(top)

        self.d_title = label("", "title")
        self.d_group = label("", "caption")
        title_box = QVBoxLayout()
        title_box.setContentsMargins(4, 0, 0, 0)
        title_box.setSpacing(0)
        title_box.addWidget(self.d_title)
        title_box.addWidget(self.d_group)
        v.addLayout(title_box)
        self.d_desc = label("", "body2", wrap=True)
        v.addWidget(self.d_desc)
        v.addWidget(divider())

        v.addWidget(label("Assigned inputs", "section"))
        self.chips = FlowLayoutWidget(6)
        v.addWidget(self.chips)
        self.none_label = label("Nothing is assigned yet.", "caption")
        v.addWidget(self.none_label)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.add_btn = button("Add input", "primary", icon="plus", on_click=lambda: self.page.begin_binding(self.target))
        self.add_btn.setToolTip("Press a key or mouse button to assign it to this control")
        btns.addWidget(self.add_btn)
        self.clear_btn = button("Clear", icon="trash", on_click=lambda: self.page.clear_target(self.target))
        btns.addWidget(self.clear_btn)
        btns.addStretch()
        v.addLayout(btns)
        v.addWidget(divider())

        v.addWidget(label("Behavior", "section"))
        self.mode = SegmentedControl([("hold", "Hold"), ("toggle", "Toggle"), ("turbo", "Turbo")], "hold")
        self.mode.changed.connect(self._mode_changed)
        v.addWidget(self.mode)
        self.mode_help = label("", "caption", wrap=True)
        v.addWidget(self.mode_help)
        self.turbo = SliderRow("Turbo rate", 2, 30, 10, 1, "{:.0f} presses/s")
        self.turbo.valueChanged.connect(self._turbo_changed)
        v.addWidget(self.turbo)

        self.trigger_strength = SliderRow("Pull strength", 0.1, 1.0, 1.0, 0.05, lambda x: f"{x * 100:.0f}%",
                                          "How far the trigger is pulled while the input is held.")
        self.trigger_strength.valueChanged.connect(self._trigger_changed)
        v.addWidget(self.trigger_strength)
        self.tuning_link = button("Adjust stick feel on the Tuning page", "link",
                                  on_click=lambda: self.page.navigate("tuning"))
        v.addWidget(self.tuning_link)
        v.addStretch()
        w.setObjectName("pageScrollBody")
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(w)
        self.stack.addWidget(area)

    def show_target(self, target: Optional[str]) -> None:
        self.target = target
        if target is None:
            self.refresh_overview()
            self.stack.setCurrentIndex(0)
            return
        self.refresh_detail()
        self.stack.setCurrentIndex(1)

    def refresh_detail(self) -> None:
        t = self.target
        profile = self.engine.profile
        if t is None or profile is None:
            return
        self.d_title.setText(TARGET_NAMES.get(t, t))
        group = next((g for g, ts in TARGET_GROUPS if t in ts), "")
        self.d_group.setText(group)
        desc = TARGET_DESCRIPTIONS.get(t, "")
        self.d_desc.setText(desc)
        self.d_desc.setVisible(bool(desc))
        self.chips.clear()
        codes = profile.inputs_for(t)
        for code in codes:
            chip = KeyChip(code, removable=True)
            chip.removeRequested.connect(lambda c, t=t: self.page.remove_input(t, c))
            self.chips.add(chip)
        self.chips.setVisible(bool(codes))
        self.none_label.setVisible(not codes)
        self.clear_btn.setEnabled(bool(codes))
        mode = profile.mode_for(t)
        self.mode.set_value(mode)
        self._update_mode_help(mode)
        self.turbo.set_value(profile.turbo_rate(t))
        self.turbo.setVisible(mode == "turbo")
        is_trigger = t in TRIGGER_TARGETS
        self.trigger_strength.setVisible(is_trigger)
        if is_trigger:
            key = "left_strength" if t == "LEFT_TRIGGER" else "right_strength"
            self.trigger_strength.set_value(float(profile.triggers.get(key, 1.0)))
        self.tuning_link.setVisible("STICK" in t or t in ("WALK_MODIFIER", "PRECISION_AIM"))
        self.chips.updateGeometry()

    def _update_mode_help(self, mode: str) -> None:
        self.mode_help.setText({
            "hold": "The control is held for as long as the input is held.",
            "toggle": "Press once to hold the control, press again to release it.",
            "turbo": "While the input is held, the control is pressed and released rapidly.",
        }[mode])

    def _mode_changed(self, mode: str) -> None:
        profile = self.engine.profile
        if not profile or not self.target:
            return
        profile.set_mode(self.target, mode, self.turbo.value())
        self.turbo.setVisible(mode == "turbo")
        self._update_mode_help(mode)
        self.engine.bindings_edited()

    def _turbo_changed(self, rate: float) -> None:
        profile = self.engine.profile
        if profile and self.target and profile.mode_for(self.target) == "turbo":
            profile.set_mode(self.target, "turbo", rate)
            self.engine.tuning_edited()   # debounced save, no full rebuild

    def _trigger_changed(self, value: float) -> None:
        profile = self.engine.profile
        if not profile or self.target not in TRIGGER_TARGETS:
            return
        key = "left_strength" if self.target == "LEFT_TRIGGER" else "right_strength"
        profile.triggers[key] = round(value, 3)
        self.engine.tuning_edited()


class MappingPage(Page):
    def __init__(self, engine, window):
        super().__init__("Mapping", "Click any control to change what it's bound to. Changes save automatically.")
        self.engine = engine
        self.window = window
        self.selected: Optional[str] = None

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.setToolTip("Active profile")
        self.profile_combo.setAccessibleName("Active profile")
        self.profile_combo.activated.connect(self._combo_activated)
        self.actions.addWidget(label("Profile", "body2"))
        self.actions.addWidget(self.profile_combo)
        self.actions.addWidget(icon_button("layers", "Manage profiles", lambda: self.navigate("profiles")))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.splitter = splitter

        diagram_card = QFrame()
        diagram_card.setProperty("card", True)
        dv = QVBoxLayout(diagram_card)
        dv.setContentsMargins(12, 10, 12, 8)
        dv.setSpacing(4)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.status_hint = label("", "caption")
        bar.addWidget(self.status_hint, 1)
        bar.addWidget(label("Labels", "caption"))
        self.labels_toggle = LabeledToggle(bool(engine.settings.get("appearance", "show_callouts", True)), "", "")
        self.labels_toggle.setAccessibleName("Show binding labels")
        self.labels_toggle.toggled.connect(self._toggle_labels)
        bar.addWidget(self.labels_toggle)
        dv.addLayout(bar)
        self.diagram = ControllerDiagram(interactive=True)
        self.diagram.set_show_callouts(self.labels_toggle.isChecked())
        self.diagram.target_clicked.connect(self.select_target)
        self.diagram.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dv.addWidget(self.diagram, 1)
        splitter.addWidget(diagram_card)

        self.inspector = Inspector(self)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([920, 310])
        self.content.addWidget(splitter, 1)

        engine.profile_changed.connect(self._on_profile_changed)
        engine.profiles_changed.connect(self.refresh_profiles)
        engine.tuning_changed.connect(self._on_tuning_changed)
        self.refresh_profiles()

    # ---- Navigation helpers -----------------------------------------------

    def navigate(self, page_key: str) -> None:
        self.window.go_to(page_key)

    def on_show(self) -> None:
        self.refresh_profiles()
        self._sync_diagram()
        self.inspector.show_target(self.selected)

    def refresh_live(self) -> None:
        self.diagram.set_state(self.engine.controller.snapshot())

    # ---- Profile combo -------------------------------------------------------

    def refresh_profiles(self) -> None:
        names = self.engine.profiles.list_profiles()
        active = self.engine.profile.name if self.engine.profile else ""
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(names)
        if active in names:
            self.profile_combo.setCurrentText(active)
        self.profile_combo.blockSignals(False)

    def _combo_activated(self, _idx: int) -> None:
        name = self.profile_combo.currentText()
        if self.engine.profile and name != self.engine.profile.name:
            self.engine.load_profile(name, announce=False)

    # ---- Engine events ------------------------------------------------------

    def _on_profile_changed(self, _name: str) -> None:
        self.refresh_profiles()
        self._sync_diagram()
        self.inspector.show_target(self.selected)

    def _on_tuning_changed(self) -> None:
        pass

    def _sync_diagram(self) -> None:
        p = self.engine.profile
        if not p:
            return
        self.diagram.set_profile(p.bindings, p.modes, p.mouse_target)
        self.diagram.set_selected(self.selected)
        bound = sum(1 for c in p.bindings.values() if c)
        self.status_hint.setText(f"{p.name} • {bound} controls bound")

    def _toggle_labels(self, on: bool) -> None:
        self.diagram.set_show_callouts(on)
        self.engine.settings.set("appearance", "show_callouts", on)

    # ---- Selection & editing -------------------------------------------------

    def select_target(self, target) -> None:
        self.selected = target or None
        self.diagram.set_selected(self.selected)
        self.inspector.show_target(self.selected)

    def begin_binding(self, target: Optional[str]) -> None:
        profile = self.engine.profile
        if not profile or not target:
            return
        reserved = {}
        for action, title in HOTKEY_ACTIONS.items():
            parsed = keycodes.parse_combo(self.engine.settings.get("hotkeys", action, ""))
            if parsed and not parsed[0]:
                reserved[parsed[1]] = title
        self.diagram.set_highlight(target)
        self.engine.set_suspended(True)
        try:
            dlg = BindingDialog(target, lambda code: profile.find_conflicts(code, target), reserved, self.window)
            accepted = dlg.exec()
        finally:
            self.engine.set_suspended(False)
            self.diagram.set_highlight(None)
        if not accepted or not dlg.result_code:
            return
        code = dlg.result_code
        if dlg.replace_conflicts:
            for other in profile.find_conflicts(code, target):
                profile.unbind(other, code)
        profile.bind(target, code)
        self.engine.bindings_edited()
        self.window.toast(f"{keycodes.display_name(code)} → {TARGET_NAMES.get(target, target)}", "", "success")

    def remove_input(self, target: str, code: str) -> None:
        profile = self.engine.profile
        if not profile:
            return
        profile.unbind(target, code)
        self.engine.bindings_edited()
        self.window.toast(f"Removed {keycodes.display_name(code)} from {TARGET_NAMES.get(target, target)}",
                          "", "info", action=("Undo", lambda: self._undo_remove(target, code)))

    def _undo_remove(self, target: str, code: str) -> None:
        profile = self.engine.profile
        if profile:
            profile.bind(target, code)
            self.engine.bindings_edited()

    def clear_target(self, target: Optional[str]) -> None:
        profile = self.engine.profile
        if not profile or not target:
            return
        previous = profile.inputs_for(target)
        if not previous:
            return
        profile.clear(target)
        self.engine.bindings_edited()
        self.window.toast(f"Cleared {TARGET_NAMES.get(target, target)}", "", "info",
                          action=("Undo", lambda: self._restore(target, previous)))

    def _restore(self, target: str, codes: list[str]) -> None:
        profile = self.engine.profile
        if profile:
            for c in codes:
                profile.bind(target, c)
            self.engine.bindings_edited()

