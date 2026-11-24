"""Trainer rotational settings and local JSON interchange."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from importlib.resources import files
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable


class FlightMode(StrEnum):
    ASSISTED = "Assisted"
    DIRECT = "Direct"


def bounded(value: float, low: float, high: float, label: str) -> None:
    if type(value) not in (int, float) or not low <= value <= high or not isfinite(value):
        raise ValueError(f"{label} must be a number from {low:g} to {high:g}.")


@dataclass(frozen=True)
class AxisFlight:
    rate: float = 45.0
    acceleration: float = 120.0
    braking: float = 150.0
    acceleration_curve: float = 1.0
    command_exponent: float = 1.0

    def __post_init__(self) -> None:
        bounded(self.rate, 1, 360, "Rate")
        bounded(self.acceleration, 1, 3600, "Acceleration")
        bounded(self.braking, 1, 3600, "Braking")
        bounded(self.acceleration_curve, 1, 4, "Acceleration curve")
        bounded(self.command_exponent, 0.25, 4, "Command exponent")


@dataclass(frozen=True)
class ShipProfile:
    name: str = "Generic assisted"
    mode: FlightMode = FlightMode.ASSISTED
    fov: float = 38.0
    pitch: AxisFlight = field(default_factory=AxisFlight)
    yaw: AxisFlight = field(default_factory=AxisFlight)
    roll: AxisFlight = field(default_factory=lambda: AxisFlight(75, 180, 220))
    source: str = ""
    source_date: str = ""
    game_version: str = ""
    notes: str = "Trainer defaults for practice. No ship measurements."
    edited: bool = False

    def __post_init__(self) -> None:
        for value, limit, label in (
            (self.name, 80, "Name"),
            (self.source, 500, "Source"),
            (self.source_date, 80, "Source date"),
            (self.game_version, 80, "Game version"),
            (self.notes, 1500, "Notes"),
        ):
            if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
                raise ValueError(f"{label} must be single-line text of at most {limit} characters.")
        if not self.name.strip():
            raise ValueError("Profile name must not be blank.")
        if type(self.edited) is not bool:
            raise ValueError("Edited must be a boolean.")
        object.__setattr__(self, "mode", FlightMode(self.mode))
        bounded(self.fov, 20, 100, "Vertical field of view")


GENERIC_PROFILE = ShipProfile()
DIRECT_PROFILE = ShipProfile(
    name="Phase 2 direct",
    mode=FlightMode.DIRECT,
    notes="Instant rate changes for comparison with Phase 2 training.",
)


def load_profile(path: Path | Traversable) -> ShipProfile:
    with path.open(encoding="utf-8-sig") as file:
        content = file.read(32769)
    if len(content) > 32768:
        raise ValueError("Profile is larger than 32 KiB.")
    data = json.loads(content)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
        raise ValueError("Profile must be a JSON object with schema_version 1.")
    if data.pop("schema_version") != 1:
        raise ValueError("Unsupported ship profile schema version.")

    try:
        for axis in ("pitch", "yaw", "roll"):
            config = data[axis]
            if not isinstance(config, dict):
                raise ValueError(f"{axis.capitalize()} settings must be a JSON object.")
            for field_name in ("rate", "acceleration", "braking"):
                if field_name not in config:
                    raise ValueError(f"{axis.capitalize()} requires {field_name}.")
            data[axis] = AxisFlight(**config)
        return ShipProfile(**data)
    except (KeyError, TypeError) as error:
        raise ValueError(f"Invalid ship profile fields: {error}") from error


def export_profile(profile: ShipProfile, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"ship-{uuid4().hex[:12]}.json"
    with TemporaryDirectory(prefix=".wraith-", dir=directory) as temporary:
        staged = Path(temporary) / path.name
        document = {"schema_version": 1, **asdict(profile)}
        staged.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        staged.replace(path)
    return path


PRESETS = (
    GENERIC_PROFILE,
    DIRECT_PROFILE,
    *(
        load_profile(files("wraith_trainer").joinpath("profiles", f"{name}.json"))
        for name in ("gladius", "arrow", "lightning", "super-hornet-mk1")
    ),
)
