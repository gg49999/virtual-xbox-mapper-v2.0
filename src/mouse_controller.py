"""
MouseController
Converts raw mouse motion into an analog stick vector.

Motion deltas are accumulated as they arrive (from Raw Input or the
pynput hook, at whatever rate the mouse polls) and turned into a
*velocity* once per engine tick. Stick deflection is proportional to
mouse speed, which is what makes mouse-look feel consistent regardless
of the mouse's polling rate or the engine's tick rate:

    velocity (px/s) -> sensitivity -> acceleration -> response curve
      -> smoothing -> radial deadzone -> anti-deadzone -> max output

All shaping is radial (applied to the vector's magnitude), so diagonal
movement keeps its direction instead of being bent toward the axes.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, fields

# Mouse speed (pixels / second) that produces full stick deflection at
# sensitivity 1.0.
REFERENCE_SPEED = 1000.0

RESPONSE_CURVES = {
    "linear": 1.0,
    "aggressive": 0.6,   # boosts small movements
    "quadratic": 2.0,    # finer control at low speed
    "cubic": 3.0,
}


@dataclass
class MouseProfile:
    sensitivity_x: float = 1.0
    sensitivity_y: float = 1.0
    deadzone: float = 0.02         # ignore stick outputs smaller than this
    anti_deadzone: float = 0.0     # jump past the game's own deadzone
    response_curve: str = "linear"
    smoothing: float = 0.35        # 0 = off .. 0.95 = very smooth
    acceleration: float = 0.0      # 0 = off .. 3
    max_output: float = 1.0
    invert_x: bool = False
    invert_y: bool = False
    raw_input: bool = False        # bypass accel/curve/smoothing
    precision_scale: float = 0.5   # sensitivity multiplier while Precision Aim is held

    @classmethod
    def from_dict(cls, d: dict) -> "MouseProfile":
        known = {f.name: f for f in fields(cls)}
        kwargs = {}
        for k, v in (d or {}).items():
            if k not in known:
                continue
            default = known[k].default
            if isinstance(default, bool):
                if isinstance(v, bool):
                    kwargs[k] = v
            elif isinstance(default, float):
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    kwargs[k] = float(v)
            elif isinstance(default, str) and isinstance(v, str):
                kwargs[k] = v
        profile = cls(**kwargs)
        if profile.response_curve not in RESPONSE_CURVES:
            profile.response_curve = "linear"
        return profile

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class MouseController:
    def __init__(self, profile: MouseProfile | None = None):
        self.profile = profile or MouseProfile()
        self._lock = threading.Lock()
        self._acc_x = 0.0
        self._acc_y = 0.0
        self._sx = 0.0
        self._sy = 0.0
        self.precision = False
        self.last_output = (0.0, 0.0)

    def set_profile(self, profile: MouseProfile) -> None:
        self.profile = profile

    def add_delta(self, dx: float, dy: float) -> None:
        """Thread-safe: called from the input thread for every motion event."""
        with self._lock:
            self._acc_x += dx
            self._acc_y += dy

    def compute(self, dt: float) -> tuple[float, float]:
        """Consume accumulated motion and return the stick vector (x, y) in
        [-1, 1], with +y meaning stick *up* (mouse moved away from you)."""
        with self._lock:
            dx, dy = self._acc_x, self._acc_y
            self._acc_x = self._acc_y = 0.0

        p = self.profile
        dt = max(dt, 1e-4)
        scale = p.precision_scale if self.precision else 1.0
        vx = dx / dt / REFERENCE_SPEED * p.sensitivity_x * scale
        vy = -dy / dt / REFERENCE_SPEED * p.sensitivity_y * scale  # screen y grows downward

        if p.raw_input:
            x, y = _clamp_radial(vx, vy, 1.0)
            self._sx, self._sy = x, y
        else:
            mag = math.hypot(vx, vy)
            if mag > 0:
                if p.acceleration > 0:
                    mult = 1.0 + p.acceleration * min(mag, 3.0)
                    vx, vy, mag = vx * mult, vy * mult, mag * mult
                shaped = min(mag, 1.0) ** RESPONSE_CURVES.get(p.response_curve, 1.0)
                vx, vy = vx / mag * shaped, vy / mag * shaped

            tau = _clamp(p.smoothing, 0.0, 0.95) * 0.12   # seconds
            alpha = 1.0 if tau <= 0 else 1.0 - math.exp(-dt / tau)
            self._sx += (vx - self._sx) * alpha
            self._sy += (vy - self._sy) * alpha
            if abs(self._sx) < 1e-4:
                self._sx = 0.0
            if abs(self._sy) < 1e-4:
                self._sy = 0.0
            x, y = self._sx, self._sy

        x, y = shape_output(x, y, p.deadzone, p.anti_deadzone, p.max_output)
        if p.invert_x:
            x = -x
        if p.invert_y:
            y = -y
        self.last_output = (x, y)
        return x, y

    def reset(self) -> None:
        with self._lock:
            self._acc_x = self._acc_y = 0.0
        self._sx = self._sy = 0.0
        self.last_output = (0.0, 0.0)


def shape_output(x: float, y: float, deadzone: float, anti_deadzone: float,
                 max_output: float) -> tuple[float, float]:
    """Radial deadzone -> anti-deadzone -> max-output clamp."""
    mag = math.hypot(x, y)
    if mag <= 0.0:
        return 0.0, 0.0
    mag_in = min(mag, 1.0)
    deadzone = _clamp(deadzone, 0.0, 0.9)
    if mag_in <= deadzone:
        return 0.0, 0.0
    out = (mag_in - deadzone) / (1.0 - deadzone)
    anti = _clamp(anti_deadzone, 0.0, 0.9)
    out = anti + (1.0 - anti) * out
    out = min(out, _clamp(max_output, 0.05, 1.0))
    return x / mag * out, y / mag * out


def response_curve_point(t: float, profile: MouseProfile) -> float:
    """Stick output for a normalised input speed t in [0, 1] - used by the
    UI to draw the response-curve preview."""
    t = _clamp(t, 0.0, 1.0)
    if not profile.raw_input:
        if profile.acceleration > 0:
            t = min(1.0, t * (1.0 + profile.acceleration * t))
        t = t ** RESPONSE_CURVES.get(profile.response_curve, 1.0)
    x, _ = shape_output(t, 0.0, profile.deadzone, profile.anti_deadzone, profile.max_output)
    return x


def _clamp_radial(x: float, y: float, limit: float) -> tuple[float, float]:
    mag = math.hypot(x, y)
    if mag > limit > 0:
        return x / mag * limit, y / mag * limit
    return x, y


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
