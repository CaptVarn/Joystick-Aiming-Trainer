"""World-space rotational aiming and fixed-step practice scoring."""

from dataclasses import dataclass, field
from enum import StrEnum
from math import acos, cos, degrees, radians, sin, sqrt, tau
from random import Random

from .flight import PITCH_LIMIT, Camera, Vector, bearing
from .ship_profiles import GENERIC_PROFILE, ShipProfile

TICK_HZ = 120
TICK = 1 / TICK_HZ


class Mode(StrEnum):
    MICRO = "Micro-correction"
    TRACKING = "Continuous tracking"
    ISOLATION = "Axis isolation"
    ACQUISITION = "Target acquisition"


class Pattern(StrEnum):
    HORIZONTAL = "Horizontal"
    VERTICAL = "Vertical"
    DIAGONAL = "Diagonal"
    CIRCLE = "Circle"
    SINE = "Sinusoidal"
    FIGURE_EIGHT = "Figure eight"
    RANDOM = "Smooth random"


class Isolation(StrEnum):
    PITCH = "Pitch only"
    YAW = "Yaw only"
    BOTH = "Pitch + yaw"


# Bounds on the length of each normalized path derivative with respect to phase.
PATH_RATE = {
    Pattern.HORIZONTAL: 1.0,
    Pattern.VERTICAL: 1.0,
    Pattern.DIAGONAL: sqrt(2) * 0.7,
    Pattern.CIRCLE: 1.0,
    Pattern.SINE: sqrt(1 + 1.1**2),
    Pattern.FIGURE_EIGHT: sqrt(1 + 1.2**2),
    Pattern.RANDOM: sqrt((0.6 + 0.3 * 0.57) ** 2 + (0.56 * 1.37 + 0.35 * 0.71) ** 2),
}


@dataclass(frozen=True)
class Settings:
    duration: int = 30
    radius: float = 0.7
    offset: float = 5.0
    hold: float = 0.25
    interval: float = 0.35
    targets: int = 10
    pattern: Pattern = Pattern.FIGURE_EIGHT
    speed: float = 7.0
    acceleration: float = 14.0
    isolation: Isolation = Isolation.BOTH
    trigger: int | None = None
    roll_enabled: bool = False

    @classmethod
    def defaults(cls, mode: Mode) -> "Settings":
        if mode == Mode.ACQUISITION:
            return cls(radius=1.2, offset=13.0, duration=45, hold=0.15)
        if mode == Mode.TRACKING:
            return cls(radius=1.5, offset=8.0)
        if mode == Mode.ISOLATION:
            return cls(radius=0.9, offset=6.0, isolation=Isolation.YAW)
        return cls()


def required_axes(mode: Mode, isolation: Isolation, roll_enabled: bool = False) -> tuple[int, ...]:
    if mode == Mode.ISOLATION and isolation != Isolation.BOTH:
        return (0,) if isolation == Isolation.PITCH else (1,)
    return (0, 1, 2) if roll_enabled else (0, 1)


@dataclass
class Target:
    origin_yaw: float
    origin_pitch: float
    direction: Vector
    born: int
    phase: float = 0.0
    speed: float = 0.0
    held: int = 0
    entered: int | None = None
    streak_start: int | None = None
    sides: list[int] = field(default_factory=lambda: [0, 0])


@dataclass
class Score:
    valid: int = 0
    on_target: int = 0
    total_error: float = 0
    squared_error: float = 0
    max_error: float = 0
    overshoots: int = 0
    corrections: int = 0
    acquisition: list[float] = field(default_factory=list)
    settling: list[float] = field(default_factory=list)
    interference: float = 0.0
    interference_samples: int = 0
    input_change: float = 0.0

    @property
    def accuracy(self) -> float:
        return self.on_target / self.valid if self.valid else 0.0

    @property
    def mean_error(self) -> float:
        return self.total_error / self.valid if self.valid else 0.0

    @property
    def rms_error(self) -> float:
        return sqrt(self.squared_error / self.valid) if self.valid else 0.0

    @property
    def interference_rms(self) -> float | None:
        if not self.interference_samples:
            return None
        return sqrt(self.interference / self.interference_samples)

    @property
    def input_change_rms(self) -> float:
        return sqrt(self.input_change / (self.valid - 1)) / TICK if self.valid > 1 else 0.0


class Session:
    def __init__(
        self,
        mode: Mode,
        settings: Settings,
        start_ns: int,
        *,
        profile: ShipProfile = GENERIC_PROFILE,
        seed: int | None = None,
    ):
        self.mode = mode
        self.settings = settings
        self.start_ns = start_ns
        self.rng = Random(seed)
        self.random_phases = tuple(self.rng.uniform(0, tau) for _ in range(4))
        self.camera = Camera(profile)
        self.score = Score()
        self.axes = required_axes(mode, settings.isolation, settings.roll_enabled)
        self.ticks = 0
        self.error: float | None = None
        self.inside = False
        self.finish_reason: str | None = None
        self.target = self.spawn_target()
        self.next_spawn = 0
        self.stick: tuple[float | None, float | None] = (None, None)
        self.roll = 0.0
        self.previous_stick: tuple[float, float] | None = None
        self.last_command = [0, 0]
        self.trigger_down = False
        self.trigger_pending = False
        self.prime_trigger = True

    @property
    def remaining(self) -> float:
        return max(0.0, self.settings.duration - self.ticks * TICK)

    @property
    def ready(self) -> bool:
        return bool(self.target and self.inside and self.target.held * TICK >= self.settings.hold)

    def finish(self, reason: str) -> None:
        if self.finish_reason is None:
            self.finish_reason = reason

    def input(
        self, pitch: float | None, yaw: float | None, trigger: bool, *, roll: float = 0.0
    ) -> None:
        self.stick = pitch, yaw
        self.roll = roll
        if self.ready and not self.prime_trigger and trigger and not self.trigger_down:
            self.trigger_pending = True
        self.trigger_down = trigger
        self.prime_trigger = False

    def advance(self, now_ns: int) -> None:
        """Step simulation and scoring from monotonic time, independently of drawing."""
        due = (now_ns - self.start_ns) * TICK_HZ // 1_000_000_000
        while self.ticks < due and self.finish_reason is None:
            self.step()

    def spawn_target(self) -> Target:
        yaw, pitch = self.camera.yaw, self.camera.pitch
        if self.mode == Mode.TRACKING:
            target = Target(yaw, pitch, bearing(yaw, pitch), self.ticks)
            target.direction = self.tracking_direction(target)
            return target
        radius = self.settings.offset * self.rng.uniform(0.65, 1.0)
        sign = self.rng.choice((-1, 1))
        if self.axes == (0,):
            pitch += sign * radius if abs(pitch + sign * radius) <= PITCH_LIMIT else -sign * radius
        elif self.axes == (1,):
            yaw += sign * radius / cos(radians(pitch))
        else:
            angle = self.rng.uniform(0, tau)
            pitch += radius * sin(angle)
            yaw += radius * cos(angle) / cos(radians(self.camera.pitch))
            if abs(pitch) > PITCH_LIMIT:
                pitch = 2 * self.camera.pitch - pitch
        return Target(yaw, pitch, bearing(yaw, pitch), self.ticks)

    def move_target(self, target: Target) -> None:
        settings = self.settings
        target.speed = min(settings.speed, target.speed + settings.acceleration * TICK)
        target.phase += target.speed * TICK / (settings.offset * PATH_RATE[settings.pattern])
        target.direction = self.tracking_direction(target)

    def tracking_direction(self, target: Target) -> Vector:
        settings = self.settings
        t = target.phase
        a, b, c, d = self.random_phases
        match settings.pattern:
            case Pattern.HORIZONTAL:
                x, y = sin(t), 0
            case Pattern.VERTICAL:
                x, y = 0, sin(t)
            case Pattern.DIAGONAL:
                x, y = 0.7 * sin(t), 0.7 * sin(t)
            case Pattern.CIRCLE:
                x, y = cos(t), sin(t)
            case Pattern.SINE:
                x, y = sin(t), 0.55 * sin(2 * t + 0.6)
            case Pattern.FIGURE_EIGHT:
                x, y = sin(t), 0.6 * sin(2 * t)
            case Pattern.RANDOM:
                x = 0.6 * sin(t + a) + 0.3 * sin(0.57 * t + b)
                y = 0.56 * sin(1.37 * t + c) + 0.35 * sin(0.71 * t + d)
        return bearing(
            target.origin_yaw + x * settings.offset, target.origin_pitch + y * settings.offset
        )

    def step(self) -> None:
        self.ticks += 1
        pitch, yaw = self.stick
        self.camera.rotate(
            (pitch or 0.0) if 0 in self.axes else 0,
            (yaw or 0.0) if 1 in self.axes else 0,
            self.roll if 2 in self.axes else 0,
            TICK,
        )
        if self.target is None and self.ticks >= self.next_spawn:
            self.target = self.spawn_target()
            self.last_command = [0, 0]
        if self.target is not None:
            if self.mode == Mode.TRACKING:
                self.move_target(self.target)
            self.measure(self.target)
        self.trigger_pending = False
        if self.remaining <= 0:
            self.finish("Time complete")

    def measure(self, target: Target) -> None:
        x, y, z = self.camera.coordinates(target.direction, banked=False)
        self.error = degrees(acos(max(-1.0, min(1.0, z))))
        self.inside = self.error <= self.settings.radius
        score = self.score
        score.valid += 1
        score.on_target += self.inside
        score.total_error += self.error
        score.squared_error += self.error**2
        score.max_error = max(score.max_error, self.error)
        if len(self.axes) == 1:
            off_axis = self.stick[1 - self.axes[0]]
            if off_axis is not None:
                score.interference += off_axis**2
                score.interference_samples += 1
        if self.mode == Mode.TRACKING:
            pitch, yaw = self.stick
            command_pair = (pitch or 0.0, yaw or 0.0)
            if self.previous_stick is not None:
                dp = command_pair[0] - self.previous_stick[0]
                dy = command_pair[1] - self.previous_stick[1]
                score.input_change += dp**2 + dy**2
            self.previous_stick = command_pair

        band = sin(radians(max(0.12, self.settings.radius * 0.25)))
        for axis, distance in enumerate((y, x)):
            if axis not in self.axes:
                continue
            if z > 0 and abs(distance) >= band:
                side = 1 if distance > 0 else -1
                score.overshoots += bool(target.sides[axis] and target.sides[axis] != side)
                target.sides[axis] = side
            elif z <= 0:
                target.sides[axis] = 0
            command = self.stick[axis] or 0.0
            if abs(command) >= 0.04:
                sign = 1 if command > 0 else -1
                score.corrections += bool(
                    self.last_command[axis] and self.last_command[axis] != sign
                )
                self.last_command[axis] = sign

        if self.mode == Mode.TRACKING:
            return
        if self.inside:
            if target.entered is None:
                target.entered = self.ticks
            if target.held == 0:
                target.streak_start = self.ticks
            target.held += 1
        else:
            target.held = 0
        if self.ready and (self.settings.trigger is None or self.trigger_pending):
            assert target.entered is not None and target.streak_start is not None
            score.acquisition.append((self.ticks - target.born) * TICK)
            score.settling.append((target.streak_start - target.entered) * TICK)
            self.target = None
            self.inside = False
            self.error = None
            self.next_spawn = self.ticks + round(self.settings.interval * TICK_HZ)
            if self.mode == Mode.ACQUISITION and len(score.acquisition) >= self.settings.targets:
                self.finish("Target goal complete")
