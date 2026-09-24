"""
Tuning page: how mouse movement and keyboard presses are shaped into
analog stick output. All values belong to the active profile (so an FPS
profile can have different sensitivity than a racing profile) and save
automatically.
"""
from __future__ import annotations

import math

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout

from mouse_controller import MouseProfile, response_curve_point
from ui.pages.base import Page
from ui.widgets import (
    Card, SettingRow, SliderRow, LabeledToggle, CurvePreview, ResponsiveColumns, button, label, divider,
    format_multiplier, format_percent, format_ms,
)

CURVES = [
    ("linear", "Linear", "Output grows evenly with mouse speed."),
    ("aggressive", "Aggressive", "Boosts small movements; snappier turning."),
    ("quadratic", "Smooth", "Finer control at low speed, fast at high speed."),
    ("cubic", "Precise", "Very fine control for small corrections."),
]
MOUSE_TARGETS = [("right_stick", "Right stick (look / aim)"), ("left_stick", "Left stick (movement)"),
                 ("none", "Nothing")]
RAMP_CURVES = [("ease_out", "Ease out (responsive)"), ("linear", "Linear"), ("ease_in", "Ease in (gradual)")]


class TuningPage(Page):
    def __init__(self, engine, window):
        super().__init__("Tuning", "", scroll=True)
        self.engine = engine
        self.window = window
        self._loading = False

        self.actions.addWidget(button("Reset to defaults", icon="refresh", on_click=self._reset))

        cols = ResponsiveColumns(980)
        self.content.addWidget(cols)
        cols.add(self._build_mouse_card())
        cols.add(self._build_keyboard_card())
        cols.add(self._build_trigger_card())
        self.content.addStretch()

        engine.profile_changed.connect(lambda _n: self.load_values())
        engine.tuning_changed.connect(self._on_external_tuning)
        self.load_values()

    # ---- Cards ------------------------------------------------------------

    def _build_mouse_card(self) -> Card:
        card = Card("Mouse aim", "How mouse movement becomes stick movement while the mouse is captured.",
                    icon="mouse")
        body = card.body()

        self.mouse_target = QComboBox()
        for key, text in MOUSE_TARGETS:
            self.mouse_target.addItem(text, key)
        self.mouse_target.currentIndexChanged.connect(self._mouse_target_changed)
        body.addWidget(SettingRow("Mouse drives", "Which stick follows the mouse.", self.mouse_target))
        body.addWidget(divider())

        self.link_xy = LabeledToggle(True, "Linked", "Separate")
        self.link_xy.toggled.connect(self._link_changed)
        body.addWidget(SettingRow("Same sensitivity for both axes", "", self.link_xy))
        self.sens_x = SliderRow("Horizontal sensitivity", 0.05, 5.0, 1.0, 0.05, format_multiplier)
        self.sens_y = SliderRow("Vertical sensitivity", 0.05, 5.0, 1.0, 0.05, format_multiplier)
        self.sens_x.valueChanged.connect(self._sens_x_changed)
        self.sens_y.valueChanged.connect(self._mouse_changed)
        body.addWidget(self.sens_x)
        body.addWidget(self.sens_y)

        curve_row = QHBoxLayout()
        curve_row.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(label("Response curve"))
        self.curve = QComboBox()
        for key, text, _ in CURVES:
            self.curve.addItem(text, key)
        self.curve.setAccessibleName("Response curve")
        self.curve.currentIndexChanged.connect(self._mouse_changed)
        left.addWidget(self.curve)
        self.curve_help = label("", "caption", wrap=True)
        left.addWidget(self.curve_help)
        left.addStretch()
        curve_row.addLayout(left, 1)
        self.preview = CurvePreview()
        curve_row.addWidget(self.preview, 1)
        body.addLayout(curve_row)
        body.addWidget(divider())

        self.smoothing = SliderRow("Smoothing", 0.0, 0.95, 0.35, 0.05, format_percent,
                                   "Evens out jitter at the cost of a little latency.")
        self.accel = SliderRow("Acceleration", 0.0, 3.0, 0.0, 0.1, lambda v: "Off" if v == 0 else f"{v:.1f}",
                               "Fast flicks turn disproportionately further.")
        self.deadzone = SliderRow("Deadzone", 0.0, 0.3, 0.02, 0.01, format_percent,
                                  "Ignore tiny movements below this output.")
        self.anti_deadzone = SliderRow("Anti-deadzone", 0.0, 0.5, 0.0, 0.01, format_percent,
                                       "Skip past the game's own stick deadzone so small movements register. "
                                       "Increase until slow mouse movement starts turning the camera.")
        self.max_output = SliderRow("Maximum output", 0.2, 1.0, 1.0, 0.05, format_percent)
        self.precision = SliderRow("Precision aim scale", 0.1, 1.0, 0.5, 0.05, format_percent,
                                   "Sensitivity while the Precision Aim input is held.")
        for w in (self.smoothing, self.accel, self.deadzone, self.anti_deadzone, self.max_output, self.precision):
            w.valueChanged.connect(self._mouse_changed)
            body.addWidget(w)
        body.addWidget(divider())

        self.invert_x = LabeledToggle(False)
        self.invert_y = LabeledToggle(False)
        self.raw = LabeledToggle(False)
        for w in (self.invert_x, self.invert_y, self.raw):
            w.toggled.connect(self._mouse_changed)
        body.addWidget(SettingRow("Invert horizontal", "", self.invert_x))
        body.addWidget(SettingRow("Invert vertical", "", self.invert_y))
        body.addWidget(SettingRow("Direct mode", "Bypass curve, smoothing and acceleration for a 1:1 feel.", self.raw))
        return card

    def _build_keyboard_card(self) -> Card:
        card = Card("Keyboard movement", "How keys bound to stick directions (e.g. WASD) drive the stick.",
                    icon="keyboard")
        body = card.body()
        self.analog = LabeledToggle(True)
        self.analog.toggled.connect(self._keyboard_changed)
        body.addWidget(SettingRow("Analog ramping", "Ease the stick in and out instead of snapping to full.",
                                  self.analog))
        self.ramp_up = SliderRow("Ramp up", 0, 1000, 120, 10, format_ms, "Time to reach full deflection.")
        self.ramp_down = SliderRow("Ramp down", 0, 1000, 90, 10, format_ms, "Time to return to centre.")
        self.ramp_curve = QComboBox()
        for key, text in RAMP_CURVES:
            self.ramp_curve.addItem(text, key)
        self.ramp_curve.currentIndexChanged.connect(self._keyboard_changed)
        self.strength = SliderRow("Stick strength", 0.1, 1.0, 1.0, 0.05, format_percent,
                                  "Maximum deflection from keys.")
        self.walk = SliderRow("Walk modifier", 0.1, 1.0, 0.5, 0.05, format_percent,
                              "Deflection while the Walk Modifier input is held.")
        for w in (self.ramp_up, self.ramp_down):
            w.valueChanged.connect(self._keyboard_changed)
            body.addWidget(w)
        body.addWidget(SettingRow("Ramp shape", "", self.ramp_curve))
        for w in (self.strength, self.walk):
            w.valueChanged.connect(self._keyboard_changed)
            body.addWidget(w)
        return card

    def _build_trigger_card(self) -> Card:
        card = Card("Triggers", "How far LT and RT are pulled when their input is held.", icon="gamepad")
        self.lt = SliderRow("Left trigger (LT)", 0.1, 1.0, 1.0, 0.05, format_percent)
        self.rt = SliderRow("Right trigger (RT)", 0.1, 1.0, 1.0, 0.05, format_percent)
        for w in (self.lt, self.rt):
            w.valueChanged.connect(self._trigger_changed)
            card.add(w)
        card.add(label("Tip: a lighter pull on LT is useful for games where a partial pull aims "
                       "and a full pull does something else.", "caption", wrap=True))
        return card

    # ---- Load / save -------------------------------------------------------

    def on_show(self) -> None:
        self.load_values()

    def _on_external_tuning(self) -> None:
        if not self._loading and not self.isVisible():
            self.load_values()

    def load_values(self) -> None:
        profile = self.engine.profile
        if not profile:
            return
        self._loading = True
        try:
            self.set_subtitle(f"Settings for profile “{profile.name}”. Changes apply instantly and save "
                              "automatically.")
            m = self.engine.effective_mouse()
            idx = self.mouse_target.findData(profile.mouse_target)
            self.mouse_target.setCurrentIndex(max(0, idx))
            linked = math.isclose(m.sensitivity_x, m.sensitivity_y)
            self.link_xy.setChecked(linked)
            self.sens_x.set_value(m.sensitivity_x)
            self.sens_y.set_value(m.sensitivity_y)
            self.sens_y.setEnabled(not linked)
            self.curve.setCurrentIndex(max(0, self.curve.findData(m.response_curve)))
            self.smoothing.set_value(m.smoothing)
            self.accel.set_value(m.acceleration)
            self.deadzone.set_value(m.deadzone)
            self.anti_deadzone.set_value(m.anti_deadzone)
            self.max_output.set_value(m.max_output)
            self.precision.set_value(m.precision_scale)
            self.invert_x.setChecked(m.invert_x)
            self.invert_y.setChecked(m.invert_y)
            self.raw.setChecked(m.raw_input)
            k = self.engine.effective_keyboard()
            self.analog.setChecked(bool(k.get("analog_simulation", True)))
            self.ramp_up.set_value(float(k.get("ramp_up_ms", 120)))
            self.ramp_down.set_value(float(k.get("ramp_down_ms", 90)))
            self.ramp_curve.setCurrentIndex(max(0, self.ramp_curve.findData(k.get("acceleration_curve", "ease_out"))))
            self.strength.set_value(float(k.get("digital_stick_strength", 1.0)))
            self.walk.set_value(float(k.get("walk_scale", 0.5)))
            self.lt.set_value(float(profile.triggers.get("left_strength", 1.0)))
            self.rt.set_value(float(profile.triggers.get("right_strength", 1.0)))
            self._update_ramp_enabled()
            self._update_preview()
        finally:
            self._loading = False

    def _current_mouse(self) -> MouseProfile:
        return MouseProfile(
            sensitivity_x=self.sens_x.value(),
            sensitivity_y=self.sens_x.value() if self.link_xy.isChecked() else self.sens_y.value(),
            deadzone=self.deadzone.value(),
            anti_deadzone=self.anti_deadzone.value(),
            response_curve=self.curve.currentData() or "linear",
            smoothing=self.smoothing.value(),
            acceleration=self.accel.value(),
            max_output=self.max_output.value(),
            invert_x=self.invert_x.isChecked(),
            invert_y=self.invert_y.isChecked(),
            raw_input=self.raw.isChecked(),
            precision_scale=self.precision.value(),
        )

    def _update_preview(self) -> None:
        mp = self._current_mouse()
        self.preview.set_function(lambda x, mp=mp: response_curve_point(x, mp))
        key = self.curve.currentData()
        self.curve_help.setText(next((h for k, _, h in CURVES if k == key), ""))
        for w in (self.curve, self.smoothing, self.accel):
            w.setEnabled(not mp.raw_input)

    def _link_changed(self, linked: bool) -> None:
        self.sens_y.setEnabled(not linked)
        if linked:
            self.sens_y.set_value(self.sens_x.value())
        self._mouse_changed()

    def _sens_x_changed(self, v: float) -> None:
        if self.link_xy.isChecked():
            self.sens_y.set_value(v)
        self._mouse_changed()

    def _mouse_changed(self, *_):
        self._update_preview()
        if self._loading or not self.engine.profile:
            return
        self.engine.profile.mouse = self._current_mouse().to_dict()
        self.engine.tuning_edited()

    def _mouse_target_changed(self, *_):
        if self._loading or not self.engine.profile:
            return
        self.engine.profile.mouse_target = self.mouse_target.currentData()
        self.engine.bindings_edited()

    def _update_ramp_enabled(self) -> None:
        on = self.analog.isChecked()
        for w in (self.ramp_up, self.ramp_down, self.ramp_curve):
            w.setEnabled(on)

    def _keyboard_changed(self, *_):
        self._update_ramp_enabled()
        if self._loading or not self.engine.profile:
            return
        self.engine.profile.keyboard = {
            "analog_simulation": self.analog.isChecked(),
            "ramp_up_ms": int(self.ramp_up.value()),
            "ramp_down_ms": int(self.ramp_down.value()),
            "acceleration_curve": self.ramp_curve.currentData() or "ease_out",
            "digital_stick_strength": self.strength.value(),
            "walk_scale": self.walk.value(),
        }
        self.engine.tuning_edited()

    def _trigger_changed(self, *_):
        if self._loading or not self.engine.profile:
            return
        self.engine.profile.triggers = {"left_strength": self.lt.value(), "right_strength": self.rt.value()}
        self.engine.tuning_edited()

    def _reset(self) -> None:
        profile = self.engine.profile
        if not profile:
            return
        saved = (dict(profile.mouse), dict(profile.keyboard), dict(profile.triggers), profile.mouse_target)
        profile.mouse, profile.keyboard, profile.triggers = {}, {}, {}
        profile.mouse_target = "right_stick"
        self.engine.bindings_edited()
        self.engine.tuning_edited()
        self.load_values()
        self.window.toast("Tuning reset to defaults", "", "info", action=("Undo", lambda: self._undo_reset(saved)))

    def _undo_reset(self, saved) -> None:
        profile = self.engine.profile
        if not profile:
            return
        profile.mouse, profile.keyboard, profile.triggers, profile.mouse_target = saved
        self.engine.bindings_edited()
        self.engine.tuning_edited()
        self.load_values()

    def refresh_live(self) -> None:
        x, y = self.engine.mapping.mouse.last_output
        mag = math.hypot(x, y)
        mp = self._current_mouse()
        # invert response_curve_point to place the dot on the curve
        lo, hi = 0.0, 1.0
        for _ in range(18):
            mid = (lo + hi) / 2
            if response_curve_point(mid, mp) < mag:
                lo = mid
            else:
                hi = mid
        self.preview.set_live(hi if mag > 0.001 else 0.0)

