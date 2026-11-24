"""Rotation dynamics and projection for the fixed-step aiming camera."""

from dataclasses import dataclass
from math import copysign, cos, radians, sin, tan

from .ship_profiles import GENERIC_PROFILE, AxisFlight, FlightMode, ShipProfile

PITCH_LIMIT = 85.0
Vector = tuple[float, float, float]


def bearing(yaw: float, pitch: float) -> Vector:
    y, p = radians(yaw), radians(pitch)
    return sin(y) * cos(p), sin(p), cos(y) * cos(p)


def dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def focal_length(height: int, vertical_fov: float = GENERIC_PROFILE.fov) -> float:
    return height / (2 * tan(radians(vertical_fov / 2)))


def wrap(degrees: float) -> float:
    return (degrees + 180) % 360 - 180


def ramp(speed: float, target: float, limit: float, seconds: float) -> tuple[float, float]:
    """Return the speed and angle after a linear ramp followed by a steady rate."""
    delta = target - speed
    arrival = abs(delta) / limit
    ramp_time = min(seconds, arrival)
    end = target if arrival <= seconds else speed + copysign(limit * seconds, delta)
    angle = (speed + end) * ramp_time / 2 + end * (seconds - ramp_time)
    return end, angle


def axis_step(
    speed: float, command: float, config: AxisFlight, mode: FlightMode, seconds: float
) -> tuple[float, float]:
    command = max(-1.0, min(1.0, command))
    target = copysign(abs(command) ** config.command_exponent * config.rate, command)
    if mode == FlightMode.DIRECT:
        return target, target * seconds

    acceleration = config.acceleration * (
        0.25 + 0.75 * abs(command) ** (config.acceleration_curve - 1)
    )
    if speed * target < 0:
        stop_time = abs(speed) / config.braking
        if stop_time >= seconds:
            return ramp(speed, 0, config.braking, seconds)
        end, angle = ramp(0, target, acceleration, seconds - stop_time)
        return end, angle + speed * stop_time / 2
    limit = config.braking if abs(target) < abs(speed) else acceleration
    return ramp(speed, target, limit, seconds)


@dataclass
class Camera:
    profile: ShipProfile = GENERIC_PROFILE
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    pitch_rate: float = 0.0
    yaw_rate: float = 0.0
    roll_rate: float = 0.0

    def rotate(self, pitch: float, yaw: float, roll: float, seconds: float) -> None:
        profile = self.profile
        self.pitch_rate, dp = axis_step(
            self.pitch_rate, pitch, profile.pitch, profile.mode, seconds
        )
        self.yaw_rate, dy = axis_step(self.yaw_rate, yaw, profile.yaw, profile.mode, seconds)
        self.roll_rate, dr = axis_step(self.roll_rate, roll, profile.roll, profile.mode, seconds)
        bank = radians(self.roll + dr / 2)
        position = self.pitch + dp * cos(bank) + dy * sin(bank)
        heading = dy * cos(bank) - dp * sin(bank)
        if profile.mode == FlightMode.ASSISTED:
            # A degree of heading covers less angle as the view approaches the pole.
            middle_pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, (self.pitch + position) / 2))
            heading /= cos(radians(middle_pitch))
        self.yaw = wrap(self.yaw + heading)
        self.roll = wrap(self.roll + dr)
        self.pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, position))
        if position != self.pitch and self.roll == 0 and self.pitch * self.pitch_rate > 0:
            self.pitch_rate = 0.0

    def basis(self, *, banked: bool = True) -> tuple[Vector, Vector, Vector]:
        y, p = radians(self.yaw), radians(self.pitch)
        sy, cy, sp, cp = sin(y), cos(y), sin(p), cos(p)
        forward = (sy * cp, sp, cy * cp)
        right = (cy, 0.0, -sy)
        up = (-sy * sp, cp, -cy * sp)
        if not banked or self.roll == 0:
            return right, up, forward
        r = radians(self.roll)
        cr, sr = cos(r), sin(r)
        return (
            tuple(x * cr + u * sr for x, u in zip(right, up, strict=True)),
            tuple(u * cr - x * sr for x, u in zip(right, up, strict=True)),
            forward,
        )

    def coordinates(self, direction: Vector, *, banked: bool = True) -> Vector:
        right, up, forward = self.basis(banked=banked)
        return dot(direction, right), dot(direction, up), dot(direction, forward)

    def projection(self, direction: Vector, focal: float) -> tuple[float, float] | None:
        return project(direction, self.basis(), focal)


def project(
    direction: Vector, basis: tuple[Vector, Vector, Vector], focal: float
) -> tuple[float, float] | None:
    right, up, forward = basis
    depth = dot(direction, forward)
    if depth <= 0.01:
        return None
    return focal * dot(direction, right) / depth, -focal * dot(direction, up) / depth
