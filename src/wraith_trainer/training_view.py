"""Training setup, aiming viewport, and live score display."""

from dataclasses import replace
from math import radians, tan
from pathlib import Path
from random import Random
from statistics import mean

import pygame

from .dashboard import BLUE, CYAN, GREEN, GRID, MUTED, RED, TEXT, Dashboard
from .diagnostics import Diagnostics
from .flight import bearing, focal_length, project
from .joystick import SIMULATOR
from .profile_view import ProfileView
from .ship_profiles import ShipProfile
from .training import TICK, Isolation, Mode, Pattern, Session, Settings

FIELD = pygame.Rect(32, 132, 1216, 576)
DESCRIPTIONS = {
    Mode.MICRO: "Acquire small nearby targets and hold the reticle steady.",
    Mode.TRACKING: "Follow one moving target for the full round.",
    Mode.ISOLATION: "Lock camera rotation to one axis and measure unintended input on the other.",
    Mode.ACQUISITION: "Acquire a sequence of targets at wider angular offsets.",
}
OPTIONS = {
    "duration": ("Round length", 15, 15, 180, " s"),
    "radius": ("Target angular radius", 0.1, 0.3, 2.0, "°"),
    "offset": ("Target displacement", 1.0, 4.0, 22.0, "°"),
    "hold": ("Required hold", 0.05, 0.05, 2.0, " s"),
    "interval": ("Time between targets", 0.05, 0.05, 2.0, " s"),
    "targets": ("Target goal", 1, 1, 30, ""),
    "speed": ("Target speed limit", 1.0, 1.0, 20.0, "°/s"),
    "acceleration": ("Target speed ramp", 2.0, 2.0, 40.0, "°/s²"),
}


class TrainingView:
    def __init__(self, ui: Dashboard, profile_dir: Path, profile: ShipProfile | None) -> None:
        self.ui = ui
        self.profiles = ProfileView(ui, profile_dir, profile)
        self.profiles_open = False
        self.mode = Mode.MICRO
        self.settings = {mode: Settings.defaults(mode) for mode in Mode}
        sky = Random(52)
        self.stars = [
            (bearing(sky.uniform(-180, 180), sky.uniform(-80, 80)), sky.randint(25, 110))
            for _ in range(420)
        ]

    @property
    def config(self) -> Settings:
        return self.settings[self.mode]

    def adjust(self, action: str, buttons: int) -> None:
        option, direction = action.rsplit("_", 1)
        change = 1 if direction == "next" else -1
        cfg = self.config
        if option == "mode":
            modes = list(Mode)
            self.mode = modes[(modes.index(self.mode) + change) % len(modes)]
            return
        if option in OPTIONS:
            _, step, minimum, maximum, _ = OPTIONS[option]
            value = min(maximum, max(minimum, round(getattr(cfg, option) + step * change, 2)))
        elif option == "pattern":
            patterns = list(Pattern)
            value = patterns[(patterns.index(cfg.pattern) + change) % len(patterns)]
        elif option == "isolation":
            axes = list(Isolation)
            value = axes[(axes.index(cfg.isolation) + change) % len(axes)]
        elif option == "trigger":
            current = -1 if cfg.trigger is None or cfg.trigger >= buttons else cfg.trigger
            index = ((current + 1 + change) % (buttons + 1)) - 1
            value = None if index == -1 else index
        else:
            return
        self.settings[self.mode] = replace(cfg, **{option: value})

    def draw(
        self,
        screen: pygame.Surface,
        state: Diagnostics,
        session: Session | None,
        unavailable: str,
    ) -> None:
        ui = self.ui
        ui.begin(screen)
        ui.text("WRAITH FLIGHT TRAINER", 32, 28, TEXT, "title")
        ui.text("Precision training", 34, 70, MUTED)
        ui.clip_text(state.device.name, 747, 45, 267, MUTED)
        ui.button("diagnostics", "< Diagnostics", (1055, 35, 193, 38))
        if self.profiles_open:
            ui.button("profile_back", "< Training setup", (1055, 82, 193, 34))
            self.profiles.draw()
        elif session is None:
            ui.button("profile_open", "Flight profiles", (1055, 82, 193, 34))
            profile = self.profiles.profile
            ui.clip_text(f"{profile.name}  /  {profile.fov:g}° vertical FOV", 34, 98, 500, CYAN)
            self.setup(state, unavailable)
        else:
            self.flight(session)
            self.score(session)
            if session.finish_reason is None:
                ui.button("stop_training", "End round", (1055, 82, 193, 34))
            else:
                ui.button("training_setup", "Training setup", (1055, 82, 193, 34), selected=True)
        ui.line((32, 785), (1248, 785))
        if state.device.instance_id == SIMULATOR:
            ui.text("W/S  Pitch     A/D  Yaw     Q/E  Roll     Shift  Fine input", 32, 804, MUTED)
        footer = (
            "ESC  Training setup"
            if self.profiles_open
            else "ESC  Diagnostics    SPACE  Start / end"
        )
        ui.right(f"{footer}    F11  Fullscreen", 1248, 807)
        ui.present(screen)

    def setup(self, state: Diagnostics, unavailable: str) -> None:
        ui = self.ui
        ui.panel((274, 126, 732, 610))
        ui.text("Training mode", 304, 153, TEXT, "label")
        self.selector("mode", "", self.mode, 190)
        ui.clip_text(DESCRIPTIONS[self.mode], 304, 243, 672, MUTED)
        ui.line((304, 273), (976, 273))
        cfg = self.config
        rows = ["duration", "radius", "offset"]
        if self.mode == Mode.TRACKING:
            rows += ["pattern", "speed", "acceleration"]
        else:
            rows += ["hold", "interval"]
            if self.mode == Mode.ISOLATION:
                rows += ["isolation"]
            if self.mode == Mode.ACQUISITION:
                rows += ["targets", "trigger"]
        for index, option in enumerate(rows):
            y = 288 + index * 47
            if option in OPTIONS:
                label, _, low, high, unit = OPTIONS[option]
                value = getattr(cfg, option)
                self.selector(option, label, f"{value:g}{unit}", y, value > low, value < high)
            elif option == "pattern":
                self.selector(option, "Target path", cfg.pattern, y)
            elif option == "isolation":
                self.selector(option, "Active axes", cfg.isolation, y)
            else:
                valid = cfg.trigger is not None and cfg.trigger < state.device.buttons
                caption = f"Button {cfg.trigger}" if valid else "Automatic"
                if state.device.instance_id == SIMULATOR and valid:
                    caption += f" ({'ZXCV'[cfg.trigger]})"
                self.selector(
                    option,
                    "Confirm acquisition",
                    caption,
                    y,
                    state.device.buttons > 0,
                    state.device.buttons > 0,
                )
        ui.line((304, 631), (976, 631))
        ui.clip_text(
            unavailable or "Uses the mappings and response settings from Diagnostics.",
            304,
            655,
            452,
            RED if unavailable else MUTED,
        )
        ui.button(
            "start_training",
            "Start round",
            (772, 645, 204, 48),
            selected=True,
            enabled=not unavailable,
        )

    def selector(
        self, option: str, label: str, value: str, y: int, left: bool = True, right: bool = True
    ) -> None:
        ui = self.ui
        ui.text(label, 304, y + 11, MUTED)
        ui.button(f"{option}_previous", "<", (706, y, 39, 35), enabled=left)
        ui.clip_text(value, 759, y + 10, 161)
        ui.button(f"{option}_next", ">", (937, y, 39, 35), enabled=right)

    def flight(self, session: Session) -> None:
        ui = self.ui
        ui.text(session.mode, 32, 103, CYAN, "label")
        ui.right(f"{session.remaining:05.1f} s", 1013, 100, TEXT, "label")
        ui.panel(FIELD, "#0b121d")
        canvas = ui.canvas
        old_clip = canvas.get_clip()
        canvas.set_clip(FIELD.inflate(-4, -4))
        cx, cy = FIELD.center
        camera = session.camera
        basis = camera.basis()
        focal = focal_length(FIELD.height, camera.profile.fov)
        for direction, brightness in self.stars:
            pos = project(direction, basis, focal)
            if pos is not None:
                x, y = round(cx + pos[0]), round(cy + pos[1])
                if FIELD.collidepoint(x, y):
                    canvas.set_at((x, y), (brightness, brightness + 18, brightness + 36))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            pygame.draw.line(
                canvas, CYAN, (cx + 10 * dx, cy + 10 * dy), (cx + 25 * dx, cy + 25 * dy)
            )
        pygame.draw.circle(canvas, TEXT, (cx, cy), 2)
        if session.target is not None:
            self.target_marker(session, focal)
        canvas.set_clip(old_clip)
        ui.text(
            f"HDG {camera.yaw % 360:05.1f}°    PITCH {camera.pitch:+05.1f}°"
            + (f"    ROLL {camera.roll:+05.1f}°" if 2 in session.axes else ""),
            51,
            150,
            MUTED,
            "mono",
        )
        ui.clip_text(
            f"{camera.profile.name}  /  {camera.profile.fov:g}° V-FOV", 51, 173, 280, MUTED
        )
        ui.text(
            f"RATE   P {camera.pitch_rate:+.1f}   Y {camera.yaw_rate:+.1f}"
            + (f"   R {camera.roll_rate:+.1f}" if 2 in session.axes else "")
            + "  °/s",
            51,
            196,
            MUTED,
            "mono",
        )
        if session.finish_reason:
            ui.panel((350, 151, 580, 68))
            ui.text(session.finish_reason, 375, 174, TEXT, "label")
        elif session.target is None:
            ui.text("Next target", 51, 674, BLUE)
        elif session.mode != Mode.TRACKING:
            if session.ready and session.settings.trigger is not None:
                ui.text(f"Press button {session.settings.trigger} to confirm", 51, 674, GREEN)
            elif session.inside:
                hold = min(1.0, session.target.held * TICK / session.settings.hold)
                pygame.draw.rect(canvas, GRID, (51, 679, 152, 5))
                pygame.draw.rect(canvas, GREEN, (51, 679, round(152 * hold), 5))
                ui.text("Hold", 214, 672, GREEN)

    def target_marker(self, session: Session, focal: float) -> None:
        target = session.target
        assert target is not None
        ui = self.ui
        cx, cy = FIELD.center
        projected = session.camera.projection(target.direction, focal)
        visible = FIELD.inflate(-46, -46)
        if projected and visible.collidepoint(cx + projected[0], cy + projected[1]):
            px, py = round(cx + projected[0]), round(cy + projected[1])
            radius = max(2, round(focal * tan(radians(session.settings.radius))))
            color = GREEN if session.inside else RED
            pygame.draw.circle(ui.canvas, color, (px, py), radius, 2)
            if abs(px - cx) > 3 or abs(py - cy) > 3:
                pygame.draw.circle(ui.canvas, color, (px, py), 2)
            return
        x, y, z = session.camera.coordinates(target.direction)
        if abs(x) + abs(y) < 1e-6 and z < 0:
            x = 1.0
        scale = max(abs(x) / (visible.width / 2), abs(y) / (visible.height / 2), 1e-6)
        anchor = round(cx + x / scale), round(cy - y / scale)
        pygame.draw.circle(ui.canvas, RED, anchor, 7, 2)
        pygame.draw.circle(ui.canvas, RED, anchor, 2)

    def score(self, session: Session) -> None:
        ui = self.ui
        score = session.score
        current = f"{session.error:.2f}°" if session.error is not None else "—"
        hits = str(len(score.acquisition))
        if session.mode == Mode.ACQUISITION:
            hits += f" / {session.settings.targets}"
        values = [
            ("On target", f"{score.accuracy:.0%} / {score.on_target * TICK:.1f} s"),
            ("Angular error", current),
            (
                "Mean / RMS / max error",
                f"{score.mean_error:.1f}° / {score.rms_error:.1f}° / {score.max_error:.1f}°",
            ),
            ("Overshoots / corrections", f"{score.overshoots} / {score.corrections}"),
        ]
        if session.mode != Mode.TRACKING:
            values.append(("Targets acquired", hits))
        if session.mode != Mode.TRACKING and session.mode != Mode.ISOLATION:
            times = (
                "—"
                if not score.acquisition
                else f"{mean(score.acquisition):.2f} / {mean(score.settling):.2f} s"
            )
            values.append(("Mean acquire / settle", times))
        if session.mode == Mode.ISOLATION:
            off_axis = score.interference_rms
            values.append(
                (
                    "Off-axis input RMS",
                    f"{off_axis:.1%}" if off_axis is not None else "—",
                )
            )
        if session.mode == Mode.TRACKING:
            values.append(("Input change RMS", f"{score.input_change_rms:.2f} /s"))
        width = 1216 // len(values)
        for index, (label, value) in enumerate(values):
            x = 32 + index * width
            ui.text(label, x, 724, MUTED, "tiny")
            ui.text(value, x, 746, TEXT, "label")
