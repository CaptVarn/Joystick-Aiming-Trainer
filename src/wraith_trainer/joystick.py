"""Pygame device lifecycle plus keyboard-driven simulated input."""

import logging
from dataclasses import dataclass
from math import expm1, sin

import pygame

SIMULATOR = -1
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Device:
    instance_id: int
    name: str
    guid: str
    axes: int
    buttons: int
    hats: int


@dataclass(frozen=True)
class InputFrame:
    axes: tuple[float, ...]
    buttons: tuple[bool, ...]
    hats: tuple[tuple[int, int], ...]


class JoystickManager:
    def __init__(self) -> None:
        self.hardware: dict[int, pygame.joystick.JoystickType] = {}
        self.devices = {SIMULATOR: Device(SIMULATOR, "Simulated joystick", "simulation", 3, 4, 1)}
        self.simulated = [0.0, 0.0, 0.0]
        for index in range(pygame.joystick.get_count()):
            try:
                self.add(index)
            except pygame.error:
                LOG.warning("event=joystick_open_failed index=%s", index, exc_info=True)

    def add(self, index: int) -> None:
        stick = pygame.joystick.Joystick(index)
        instance = stick.get_instance_id()
        if instance in self.hardware:
            return
        self.devices[instance] = Device(
            instance,
            stick.get_name(),
            stick.get_guid(),
            stick.get_numaxes(),
            stick.get_numbuttons(),
            stick.get_numhats(),
        )
        self.hardware[instance] = stick

    def remove(self, instance: int) -> None:
        if instance in self.hardware:
            self.hardware.pop(instance).quit()
            del self.devices[instance]

    def read(self, instance: int, elapsed: float, now: float, demo: bool = False) -> InputFrame:
        if instance == SIMULATOR:
            return self._simulate(elapsed, now, demo)
        device, stick = self.devices[instance], self.hardware[instance]
        return InputFrame(
            tuple(stick.get_axis(index) for index in range(device.axes)),
            tuple(bool(stick.get_button(index)) for index in range(device.buttons)),
            tuple(stick.get_hat(index) for index in range(device.hats)),
        )

    def _simulate(self, elapsed: float, now: float, demo: bool) -> InputFrame:
        keys = pygame.key.get_pressed()
        scale = 0.2 if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] else 0.75
        for axis, (positive, negative) in enumerate(
            ((pygame.K_s, pygame.K_w), (pygame.K_d, pygame.K_a), (pygame.K_e, pygame.K_q))
        ):
            direction = int(keys[positive]) - int(keys[negative])
            target = scale * direction
            if demo and not direction:
                target = (0.20, 0.33, 0.10)[axis] * sin(now * (1.7 + 0.4 * axis) + axis)
            if axis == 1 and direction and abs(self.simulated[axis]) < 0.025:
                # An illustrative reported onset step for exercising the analysis.
                self.simulated[axis] = 0.032 * direction
            self.simulated[axis] += -expm1(-elapsed / 0.10) * (target - self.simulated[axis])
        return InputFrame(
            tuple(
                value + 0.001 * sin(now * (25 + index))
                for index, value in enumerate(self.simulated)
            ),
            tuple(bool(keys[key]) for key in (pygame.K_z, pygame.K_x, pygame.K_c, pygame.K_v)),
            (
                (
                    int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT]),
                    int(keys[pygame.K_UP]) - int(keys[pygame.K_DOWN]),
                ),
            ),
        )
