"""
Live Test page: shows exactly what the virtual controller is reporting
to Windows (sticks, triggers, buttons, rumble from the game) plus a log
of raw keyboard/mouse input and what each input drove. Use it to verify
the whole pipeline before launching a game.
"""
from __future__ import annotations

import subprocess
import sys
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QSplitter, QWidget, QFrame, QScrollArea

import keycodes
from profile_manager import TARGET_NAMES
from ui.controller_diagram import ControllerDiagram
from ui.pages.base import Page
from ui.widgets import Card, StickPad, MeterBar, button, label, LabeledToggle

MAX_LOG = 250


class TestPage(Page):
    def __init__(self, engine, window):
        super().__init__("Live test", "Everything the virtual controller is sending to Windows, in real time.")
        self.engine = engine
        self.window = window
        self._paused = False
        self._last_state = None

        self.rate_label = label("", "caption")
        self.actions.addWidget(self.rate_label)
        if sys.platform.startswith("win"):
            self.actions.addWidget(button("Game Controllers panel", icon="link", on_click=self._open_joycpl,
                                          tooltip="Open Windows' built-in controller test (joy.cpl)"))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        left = QFrame()
        left.setProperty("card", True)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 12, 12, 8)
        bar = QHBoxLayout()
        bar.addStretch()
        bar.addWidget(label("Labels", "caption"))
        self.labels_toggle = LabeledToggle(False, "", "")
        self.labels_toggle.setAccessibleName("Show binding labels")
        bar.addWidget(self.labels_toggle)
        lv.addLayout(bar)
        self.diagram = ControllerDiagram(interactive=False)
        self.diagram.set_show_callouts(False)
        self.labels_toggle.toggled.connect(self.diagram.set_show_callouts)
        lv.addWidget(self.diagram, 1)
        self.buttons_label = label("No buttons pressed", "caption")
        self.buttons_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lv.addWidget(self.buttons_label)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(12)
        sticks = Card("Sticks", icon="target", padding=14)
        row = QHBoxLayout()
        self.left_pad = StickPad("Left")
        self.right_pad = StickPad("Right")
        row.addWidget(self.left_pad)
        row.addWidget(self.right_pad)
        sticks.body().addLayout(row)
        rv.addWidget(sticks)

        meters = Card("Triggers & rumble", icon="pulse", padding=14)
        self.lt_bar = MeterBar("Left trigger (LT)")
        self.rt_bar = MeterBar("Right trigger (RT)")
        self.rumble_l = MeterBar("Rumble — large motor", color_token="warning")
        self.rumble_s = MeterBar("Rumble — small motor", color_token="warning")
        for w in (self.lt_bar, self.rt_bar, self.rumble_l, self.rumble_s):
            meters.add(w)
        meters.add(label("Rumble shows vibration requested by the game.", "caption", wrap=True))
        rv.addWidget(meters)

        log_card = Card("Input log", icon="keyboard", padding=14)
        self.pause_toggle = LabeledToggle(False, "Paused", "Live")
        self.pause_toggle.toggled.connect(lambda on: setattr(self, "_paused", on))
        log_card.header_actions.addWidget(self.pause_toggle)
        log_card.header_actions.addWidget(button("Clear", "subtle", on_click=lambda: self.log.clear()))
        self.log = QListWidget()
        self.log.setMinimumHeight(180)
        self.log.setUniformItemSizes(True)
        self.log.setAccessibleName("Input log")
        log_card.add(self.log, 1)
        rv.addWidget(log_card, 1)
        right.setObjectName("pageScrollBody")
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setWidget(right)
        scroller.setMinimumWidth(340)
        scroller.setMaximumWidth(480)
        splitter.addWidget(scroller)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([760, 400])
        self.content.addWidget(splitter, 1)

        engine.input_event.connect(self._on_input)
        engine.profile_changed.connect(lambda _n: self._sync_profile())
        self._sync_profile()

    def _sync_profile(self) -> None:
        p = self.engine.profile
        if p:
            self.diagram.set_profile(p.bindings, p.modes, p.mouse_target)

    def on_show(self) -> None:
        self._sync_profile()

    def _open_joycpl(self) -> None:
        try:
            subprocess.Popen(["control", "joy.cpl"])
        except OSError as exc:
            self.window.toast("Couldn't open Game Controllers", str(exc), "error")

    def _on_input(self, code: str, pressed: bool) -> None:
        if self._paused or not self.isVisible():
            return
        profile = self.engine.profile
        targets = profile.find_conflicts(code) if profile else []
        arrow = "↓" if pressed else "↑"
        mapped = ", ".join(TARGET_NAMES.get(t, t) for t in targets) if targets else "not mapped"
        if self.engine.suspended:
            mapped = "(binding)"
        elif not self.engine.emulation_enabled:
            mapped = "(emulation off)"
        stamp = time.strftime("%H:%M:%S")
        item = QListWidgetItem(f"{stamp}   {arrow} {keycodes.display_name(code):<14}  →  {mapped}")
        self.log.insertItem(0, item)
        while self.log.count() > MAX_LOG:
            self.log.takeItem(self.log.count() - 1)

    def refresh_live(self) -> None:
        s = self.engine.controller.snapshot()
        self.diagram.set_state(s)
        self.left_pad.set_value(*s.left_stick)
        self.right_pad.set_value(*s.right_stick)
        self.lt_bar.set_value(s.left_trigger)
        self.rt_bar.set_value(s.right_trigger)
        large, small = s.rumble
        self.rumble_l.set_value(large / 255.0)
        self.rumble_s.set_value(small / 255.0)
        pressed = [b.name.replace("_", " ").title().replace("Dpad", "D-Pad") for b, on in s.buttons.items() if on]
        self.buttons_label.setText("Pressed: " + ", ".join(pressed) if pressed else "No buttons pressed")
        hz = self.engine.measured_tick_hz
        self.rate_label.setText(f"Engine {hz:.0f} Hz" if hz else "")
