"""Local profile selection and a desktop editor for rotational settings."""

from dataclasses import replace
from pathlib import Path

from .dashboard import CYAN, MUTED, RED, Dashboard
from .ship_profiles import PRESETS, FlightMode, ShipProfile, export_profile, load_profile

FIELDS = (
    ("rate", "Rate limit  °/s", 5, 1, 360),
    ("acceleration", "Acceleration  °/s²", 10, 1, 3600),
    ("braking", "Braking  °/s²", 10, 1, 3600),
    ("acceleration_curve", "Acceleration curve", 0.1, 1, 4),
    ("command_exponent", "Command exponent", 0.1, 0.25, 4),
)
AXES = ("pitch", "yaw", "roll")


class ProfileView:
    def __init__(self, ui: Dashboard, directory: Path, profile: ShipProfile | None) -> None:
        self.ui = ui
        self.directory = directory
        self.profile = profile or PRESETS[0]
        self.preset_index = -1 if profile is not None else 0
        self.files: list[Path] = []
        self.file_index = 0
        self.roll_enabled = False
        self.notice = ""
        self.error = False

    def refresh(self) -> None:
        try:
            self.files = sorted(
                (path for path in self.directory.glob("*.json") if path.is_file()),
                key=lambda path: path.name.lower(),
            )
        except OSError as error:
            self.report(str(error), error=True)
        else:
            self.file_index = min(self.file_index, max(0, len(self.files) - 1))

    def report(self, message: str, *, error: bool = False) -> None:
        self.notice = message
        self.error = error

    def action(self, action: str) -> None:
        if action == "ship_save":
            try:
                path = export_profile(self.profile, self.directory)
            except OSError as error:
                self.report(f"Could not save profile. {error}", error=True)
            else:
                self.report(f"Saved {path.name}.")
                self.refresh()
                if path in self.files:
                    self.file_index = self.files.index(path)
        elif action == "ship_load" and self.files:
            try:
                profile = load_profile(self.files[self.file_index])
            except (OSError, ValueError) as error:
                self.report(f"Could not load profile. {error}", error=True)
            else:
                self.profile = profile
                self.preset_index = -1
                self.report(f"Loaded {profile.name}.")
        elif action == "ship_refresh":
            self.report("")
            self.refresh()
        elif action == "ship_roll":
            self.roll_enabled = not self.roll_enabled
        elif action == "ship_mode":
            mode = (
                FlightMode.DIRECT
                if self.profile.mode == FlightMode.ASSISTED
                else FlightMode.ASSISTED
            )
            self.profile = replace(self.profile, mode=mode, edited=True)
        elif action.startswith("ship_") and action.endswith(("_up", "_down")):
            field, direction = action.removeprefix("ship_").rsplit("_", 1)
            self.adjust(field, 1 if direction == "up" else -1)

    def adjust(self, field: str, step: int) -> None:
        if field == "preset":
            index = self.preset_index
            if index < 0 and step < 0:
                index = 0
            self.preset_index = (index + step) % len(PRESETS)
            self.profile = PRESETS[self.preset_index]
            self.report("")
        elif field == "file" and self.files:
            self.file_index = (self.file_index + step) % len(self.files)
        elif field == "fov":
            value = min(100, max(20, self.profile.fov + step * 2))
            self.profile = replace(self.profile, fov=value, edited=True)
        elif "." in field:
            axis, name = field.split(".")
            config = getattr(self.profile, axis)
            _, _, amount, low, high = next(item for item in FIELDS if item[0] == name)
            value = min(high, max(low, round(getattr(config, name) + step * amount, 2)))
            self.profile = replace(
                self.profile, **{axis: replace(config, **{name: value}), "edited": True}
            )

    def draw(self) -> None:
        ui = self.ui
        profile = self.profile
        ui.panel((32, 132, 398, 633))
        ui.panel((446, 132, 802, 633))
        ui.text("Flight profile", 53, 156, font="label")
        ui.clip_text(profile.name, 53, 202, 349, CYAN)
        qualifier = "Imported profile" if self.preset_index < 0 else "Trainer preset"
        if profile.edited:
            qualifier += " · edited"
        ui.text(qualifier, 53, 230, MUTED, "tiny")
        provenance = profile.game_version
        if profile.source_date:
            provenance = f"Snapshot {profile.source_date} · {provenance or 'patch unlisted'}"
        ui.clip_text(provenance, 53, 257, 349, MUTED)
        ui.clip_text(profile.source or "Local trainer settings", 53, 280, 349, MUTED)
        ui.clip_text(profile.notes, 53, 303, 349, MUTED)
        ui.button("ship_preset_down", "<", (53, 337, 42, 34))
        ui.text("Browse presets", 110, 347, MUTED)
        ui.button("ship_preset_up", ">", (360, 337, 42, 34))
        ui.line((53, 394), (402, 394))
        ui.text("Profile files", 53, 420, font="label")
        filename = self.files[self.file_index].name if self.files else "No JSON profiles found"
        ui.clip_text(filename, 53, 455, 349, MUTED)
        ui.button("ship_file_down", "<", (53, 486, 42, 34), enabled=len(self.files) > 1)
        ui.button("ship_file_up", ">", (103, 486, 42, 34), enabled=len(self.files) > 1)
        ui.button("ship_refresh", "Refresh", (310, 486, 92, 34))
        ui.button("ship_load", "Load JSON", (53, 542, 166, 38), enabled=bool(self.files))
        ui.button("ship_save", "Save JSON", (234, 542, 168, 38), selected=True)
        ui.text("Profile folder", 53, 608, MUTED, "tiny")
        if ui.fonts["body"].size(str(self.directory))[0] > 349:
            ui.clip_text(
                self.directory.parent.name + " / " + self.directory.name, 53, 630, 349, MUTED
            )
        else:
            ui.text(str(self.directory), 53, 630, MUTED)
        ui.clip_text(self.notice, 53, 684, 349, RED if self.error else CYAN)
        self.controls()

    def controls(self) -> None:
        ui = self.ui
        profile = self.profile
        ui.text("Rotation & view", 469, 156, font="label")
        ui.text("Flight mode", 469, 211, MUTED)
        ui.button("ship_mode", profile.mode, (577, 199, 143, 34), selected=True)
        ui.text("Vertical field of view", 790, 211, MUTED)
        self.numeric("fov", profile.fov, 997, 199, 20, 100, "°")
        ui.line((469, 257), (1223, 257))
        for index, axis in enumerate(AXES):
            ui.text(axis.capitalize(), 684 + 179 * index, 278, CYAN)
        for index, (key, caption, _, low, high) in enumerate(FIELDS):
            y = 314 + index * 55
            ui.text(caption, 469, y + 11, MUTED)
            for column, axis in enumerate(AXES):
                value = getattr(getattr(profile, axis), key)
                self.numeric(
                    f"{axis}.{key}",
                    value,
                    655 + 179 * column,
                    y,
                    low,
                    high,
                    enabled=profile.mode == FlightMode.ASSISTED
                    or key not in {"acceleration", "braking", "acceleration_curve"},
                )
        ui.line((469, 600), (1223, 600))
        ui.button(
            "ship_roll",
            "Roll enabled" if self.roll_enabled else "Roll disabled",
            (469, 628, 186, 38),
            selected=self.roll_enabled,
        )
        ui.text("Optional roll requires a mapped axis and a two-axis drill.", 675, 640, MUTED)
        ui.text("Command shaping applies after the Diagnostics response curve.", 469, 704, MUTED)

    def numeric(
        self,
        key: str,
        value: float,
        x: int,
        y: int,
        low: float,
        high: float,
        suffix: str = "",
        *,
        enabled: bool = True,
    ) -> None:
        ui = self.ui
        ui.button(f"ship_{key}_down", "-", (x, y, 32, 34), enabled=enabled and value > low)
        ui.right(f"{value:g}{suffix}", x + 90, y + 11, MUTED if enabled else "#667c92", "mono")
        ui.button(f"ship_{key}_up", "+", (x + 107, y, 32, 34), enabled=enabled and value < high)
