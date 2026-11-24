"""Calibration and response processing for SDL's signed axis values."""

from dataclasses import dataclass, field
from math import copysign, expm1, isfinite


@dataclass(frozen=True)
class Calibration:
    minimum: float = -1.0
    center: float = 0.0
    maximum: float = 1.0

    def __post_init__(self) -> None:
        if not -1 <= self.minimum < self.center < self.maximum <= 1:
            raise ValueError("Calibration requires minimum < center < maximum within [-1, 1].")


@dataclass(frozen=True)
class Response:
    inner: float = 0.03
    outer: float = 0.0
    exponent: float = 1.7
    sensitivity: float = 1.0
    maximum: float = 1.0
    smoothing_seconds: float = 0.0
    inverted: bool = False

    def __post_init__(self) -> None:
        if not (
            0 <= self.inner < 1
            and 0 <= self.outer < 1 - self.inner
            and isfinite(self.exponent)
            and self.exponent > 0
            and isfinite(self.sensitivity)
            and self.sensitivity > 0
            and 0 < self.maximum <= 1
            and isfinite(self.smoothing_seconds)
            and self.smoothing_seconds >= 0
        ):
            raise ValueError("Invalid response settings.")


def normalize(raw: float, calibration: Calibration) -> float:
    """Map each side of the measured center independently into [-1, 1]."""
    offset = raw - calibration.center
    limit = calibration.maximum - calibration.center
    if offset < 0:
        limit = calibration.center - calibration.minimum
    return max(-1.0, min(1.0, offset / limit))


def shape(normalized: float, response: Response) -> float:
    """Apply inversion, rescaled deadzones, a signed power curve and a gain limit."""
    magnitude = (abs(normalized) - response.inner) / (1 - response.inner - response.outer)
    magnitude = max(0.0, min(1.0, magnitude))
    output = min(response.maximum, magnitude**response.exponent * response.sensitivity)
    return copysign(output, -normalized if response.inverted else normalized)


@dataclass
class AxisProcessor:
    calibration: Calibration = field(default_factory=Calibration)
    response: Response = field(default_factory=Response)
    output: float | None = None

    def update(self, raw: float, elapsed: float) -> tuple[float, float]:
        normalized = normalize(raw, self.calibration)
        target = shape(normalized, self.response)
        if self.output is None or self.response.smoothing_seconds == 0:
            self.output = target
        else:
            weight = -expm1(-max(0.0, elapsed) / self.response.smoothing_seconds)
            self.output += weight * (target - self.output)
        return normalized, self.output


@dataclass
class TravelCapture:
    """Collect physical extrema while the user sweeps the controls."""

    minimum: list[float]
    maximum: list[float]

    @classmethod
    def start(cls, raw: tuple[float, ...]) -> "TravelCapture":
        return cls(list(raw), list(raw))

    def update(self, raw: tuple[float, ...]) -> None:
        for index, value in enumerate(raw):
            self.minimum[index] = min(value, self.minimum[index])
            self.maximum[index] = max(value, self.maximum[index])

    def calibration_for(self, axis: int, center: float) -> Calibration | None:
        if center - self.minimum[axis] < 0.05 or self.maximum[axis] - center < 0.05:
            return None
        return Calibration(self.minimum[axis], center, self.maximum[axis])


def moved_axis(
    baseline: tuple[float, ...], raw: tuple[float, ...], threshold: float = 0.22
) -> int | None:
    """Identify the largest deliberate change from the current resting snapshot."""
    differences = [abs(after - before) for before, after in zip(baseline, raw, strict=True)]
    index = max(range(len(differences)), key=differences.__getitem__, default=None)
    if index is not None and differences[index] >= threshold:
        return index
    return None
