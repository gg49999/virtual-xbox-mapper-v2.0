"""
KeyboardController
Turns key-down/key-up state into an analog value that ramps up and down
over time, so held movement keys (W/A/S/D etc.) feel closer to pushing
an analog stick than snapping instantly to 100%.

Each logical axis endpoint (e.g. "left stick +Y") gets its own
AnalogAxis instance so ramping is independent per direction.
"""
from __future__ import annotations

from dataclasses import dataclass

RAMP_CURVES = ("linear", "ease_out", "ease_in")


@dataclass
class RampProfile:
    enabled: bool = True
    ramp_up_ms: int = 120
    ramp_down_ms: int = 90
    strength: float = 1.0     # max value reached when fully ramped (0..1)
    deadzone: float = 0.0
    curve: str = "ease_out"   # linear | ease_out | ease_in

    @classmethod
    def from_settings(cls, k: dict) -> "RampProfile":
        def num(key, default, cast):
            v = k.get(key, default)
            return cast(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default

        curve = k.get("acceleration_curve", "ease_out")
        return cls(
            enabled=bool(k.get("analog_simulation", True)),
            ramp_up_ms=num("ramp_up_ms", 120, int),
            ramp_down_ms=num("ramp_down_ms", 90, int),
            strength=max(0.05, min(1.0, num("digital_stick_strength", 1.0, float))),
            deadzone=max(0.0, min(0.9, num("deadzone", 0.0, float))),
            curve=curve if curve in RAMP_CURVES else "ease_out",
        )


class AnalogAxis:
    """A single directional input (e.g. 'W held') that ramps 0 -> strength
    while held, and strength -> 0 when released."""

    def __init__(self, profile: RampProfile):
        self.profile = profile
        self._value = 0.0          # linear ramp progress, 0..1
        self._held = False

    def set_held(self, held: bool) -> None:
        self._held = held

    @property
    def held(self) -> bool:
        return self._held

    def set_profile(self, profile: RampProfile) -> None:
        self.profile = profile

    def reset(self) -> None:
        self._value = 0.0
        self._held = False

    def update(self, dt: float) -> float:
        p = self.profile
        if not p.enabled:
            self._value = 1.0 if self._held else 0.0
            return self._value * p.strength

        target = 1.0 if self._held else 0.0
        duration_ms = max(1, p.ramp_up_ms if self._held else p.ramp_down_ms)
        step = max(0.0, dt) * 1000.0 / duration_ms
        if self._value < target:
            self._value = min(target, self._value + step)
        elif self._value > target:
            self._value = max(target, self._value - step)
        return _apply_curve(self._value, p.curve) * p.strength

    @property
    def value(self) -> float:
        return self._value


def _apply_curve(v: float, curve: str) -> float:
    v = max(0.0, min(1.0, v))
    if curve == "ease_out":
        return 1 - (1 - v) ** 2
    if curve == "ease_in":
        return v ** 2
    return v


class DigitalStickAxis:
    """Combines two opposing AnalogAxis instances (e.g. A / D) into a single
    -1..1 stick axis value."""

    def __init__(self, profile: RampProfile):
        self.negative = AnalogAxis(profile)
        self.positive = AnalogAxis(profile)

    @property
    def profile(self) -> RampProfile:
        return self.negative.profile

    def set_profile(self, profile: RampProfile) -> None:
        self.negative.set_profile(profile)
        self.positive.set_profile(profile)

    def set_negative_held(self, held: bool) -> None:
        self.negative.set_held(held)

    def set_positive_held(self, held: bool) -> None:
        self.positive.set_held(held)

    def reset(self) -> None:
        self.negative.reset()
        self.positive.reset()

    def update(self, dt: float) -> float:
        value = self.positive.update(dt) - self.negative.update(dt)
        if abs(value) < self.profile.deadzone:
            return 0.0
        return max(-1.0, min(1.0, value))
