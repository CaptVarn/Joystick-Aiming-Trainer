"""Pygame drawing and pointer targets for the diagnostics dashboard."""

import pygame

from .diagnostics import CHART_NS, Diagnostics
from .joystick import SIMULATOR
from .recording import CHANNELS, TESTS

SIZE = (1280, 840)
BACKGROUND = "#0b1018"
PANEL = "#111a25"
BORDER = "#29394a"
GRID = "#213344"
TEXT = "#edf4fc"
MUTED = "#9bb0c5"
CYAN = "#60e4ec"
BLUE = "#a1b0ff"
RED = "#ff817d"
GREEN = "#92e5b7"

RESPONSE_CONTROLS = (
    ("inner", "Inner deadzone", 0.01, 0.00, 0.50, ".0%"),
    ("outer", "Outer deadzone", 0.01, 0.00, 0.40, ".0%"),
    ("exponent", "Curve exponent", 0.1, 0.2, 5.0, ".1f"),
    ("sensitivity", "Sensitivity", 0.1, 0.1, 3.0, ".1f"),
    ("maximum", "Output limit", 0.05, 0.1, 1.0, ".0%"),
    ("smoothing_seconds", "Smoothing", 0.01, 0.0, 0.30, "ms"),
)


class Dashboard:
    def __init__(self) -> None:
        self.canvas = pygame.Surface(SIZE)
        self.fonts = {
            "tiny": pygame.font.Font(None, 17),
            "body": pygame.font.Font(None, 21),
            "label": pygame.font.Font(None, 24),
            "title": pygame.font.Font(None, 40),
            "mono": pygame.font.SysFont("Consolas,DejaVu Sans Mono,monospace", 14),
        }
        self.hitboxes: dict[str, pygame.Rect] = {}
        self.mouse = (-1, -1)
        self.viewport = pygame.Rect((0, 0), SIZE)

    def text(self, text: str, x: int, y: int, color: str = TEXT, font: str = "body") -> None:
        self.canvas.blit(self.fonts[font].render(text, True, color), (x, y))

    def right(self, text: str, x: int, y: int, color: str = MUTED, font: str = "tiny") -> None:
        self.text(text, x - self.fonts[font].size(text)[0], y, color, font)

    def clip_text(self, text: str, x: int, y: int, width: int, color: str = TEXT) -> None:
        font = self.fonts["body"]
        if font.size(text)[0] > width:
            while font.size(text + "…")[0] > width:
                text = text[:-1]
            text += "…"
        self.text(text, x, y, color)

    def panel(self, rect: pygame.Rect | tuple[int, int, int, int], color: str = PANEL) -> None:
        pygame.draw.rect(self.canvas, color, rect, border_radius=12)
        pygame.draw.rect(self.canvas, BORDER, rect, width=1, border_radius=12)

    def line(self, start: tuple[int, int], end: tuple[int, int], color: str = BORDER) -> None:
        pygame.draw.line(self.canvas, color, start, end)

    def button(
        self,
        key: str,
        caption: str,
        rect: tuple[int, int, int, int],
        *,
        selected: bool = False,
        enabled: bool = True,
        accent: str = CYAN,
    ) -> None:
        box = pygame.Rect(rect)
        hover = enabled and box.collidepoint(self.mouse)
        bg = "#20384a" if enabled and (selected or hover) else "#151f2b"
        border = accent if enabled and (selected or hover) else BORDER
        pygame.draw.rect(self.canvas, bg, box, border_radius=6)
        pygame.draw.rect(self.canvas, border, box, width=1, border_radius=6)
        font = self.fonts["body"]
        label = font.render(caption, True, accent if selected else TEXT if enabled else "#667c92")
        self.canvas.blit(label, label.get_rect(center=box.center))
        if enabled:
            self.hitboxes[key] = box

    def position(self, pos: tuple[int, int]) -> tuple[int, int]:
        x, y = pos
        return (
            (x - self.viewport.x) * SIZE[0] // self.viewport.width,
            (y - self.viewport.y) * SIZE[1] // self.viewport.height,
        )

    def action_at(self, pos: tuple[int, int]) -> str | None:
        logical = self.position(pos)
        return next(
            (action for action, rect in self.hitboxes.items() if rect.collidepoint(logical)), None
        )

    def draw(
        self,
        screen: pygame.Surface,
        state: Diagnostics,
        *,
        selected: int,
        axes_page: int,
        buttons_page: int,
        more_devices: bool,
        demo: bool,
        exporting: bool,
    ) -> None:
        self.begin(screen)
        self.header(state, more_devices, demo)
        self.button(
            "training",
            "Training >",
            (560, 42, 145, 34),
            enabled=not (state.capture or state.learning or state.travel),
        )
        self.capture_bar(state, exporting)
        self.axes_panel(state, selected, axes_page)
        self.buttons_panel(state, buttons_page)
        self.graph(state, selected)
        self.analysis_panel(state, selected)
        self.settings_panel(state, selected)
        self.line((32, 784), (1248, 784))
        self.clip_text(state.notice, 32, 800, 900, MUTED)
        self.right("SPACE  Record / stop     F11  Fullscreen", 1248, 803)
        self.present(screen)

    def begin(self, screen: pygame.Surface) -> None:
        width, height = screen.get_size()
        scale = min(width / SIZE[0], height / SIZE[1])
        size = (max(1, int(SIZE[0] * scale)), max(1, int(SIZE[1] * scale)))
        self.viewport = pygame.Rect((0, 0), size)
        self.viewport.center = screen.get_rect().center
        self.mouse = self.position(pygame.mouse.get_pos())
        self.hitboxes.clear()
        self.canvas.fill(BACKGROUND)

    def present(self, screen: pygame.Surface) -> None:
        size = self.viewport.size
        screen.fill(BACKGROUND)
        screen.blit(
            self.canvas if size == SIZE else pygame.transform.smoothscale(self.canvas, size),
            self.viewport,
        )

    def header(self, state: Diagnostics, more_devices: bool, demo: bool) -> None:
        mark = [(33, 64), (45, 36), (54, 54), (63, 36), (75, 64)]
        pygame.draw.lines(self.canvas, CYAN, False, mark, 3)
        self.text("WRAITH FLIGHT TRAINER", 92, 27, TEXT, "title")
        self.text("Joystick diagnostics", 94, 68, MUTED)
        self.panel((719, 23, 529, 70))
        self.text("INPUT DEVICE", 737, 34, MUTED, "tiny")
        self.clip_text(state.device.name, 737, 55, 267)
        self.button(
            "device_previous", "<", (1014, 41, 37, 34), enabled=more_devices and not state.capture
        )
        self.button(
            "device_next", ">", (1057, 41, 37, 34), enabled=more_devices and not state.capture
        )
        self.button(
            "demo",
            "Demo on" if demo else "Demo off",
            (1110, 41, 120, 34),
            selected=demo,
            enabled=state.device.instance_id == SIMULATOR and not state.capture,
        )

    def capture_bar(self, state: Diagnostics, exporting: bool) -> None:
        self.panel((32, 107, 1216, 58))
        self.button("protocol_previous", "<", (47, 119, 30, 34), enabled=not state.capture)
        self.button("protocol_next", ">", (235, 119, 30, 34), enabled=not state.capture)
        self.text(state.protocol, 88, 128)
        self.clip_text(TESTS[state.protocol], 279, 127, 430, MUTED)
        self.button(
            "rate_down", "-", (718, 119, 28, 34), enabled=not state.capture and state.rate > 30
        )
        self.text(f"{state.rate} Hz", 756, 128)
        self.button(
            "rate_up", "+", (822, 119, 28, 34), enabled=not state.capture and state.rate < 240
        )
        self.button(
            "record",
            "Stop recording" if state.capture else "Record test",
            (866, 119, 166, 34),
            selected=True,
            accent=RED if state.capture else CYAN,
            enabled=bool(
                state.capture or (state.latest and not state.learning and not state.travel)
            ),
        )
        self.button(
            "export",
            "Exporting..." if exporting else "Export CSV + JSON",
            (1044, 119, 186, 34),
            enabled=bool(state.completed and not exporting and not state.capture),
        )

    def axes_panel(self, state: Diagnostics, selected: int, page: int) -> None:
        self.panel((32, 180, 304, 332))
        self.text("Physical inputs", 49, 197, TEXT, "label")
        self.text(
            f"{state.device.axes} axes   /   {state.device.buttons} buttons"
            f"   /   {state.device.hats} hats",
            49,
            224,
            MUTED,
            "tiny",
        )
        self.text(state.device.guid, 49, 242, MUTED, "mono")
        self.line((49, 262), (319, 262))
        frame = state.frame
        if frame and not frame.axes:
            self.text("This device reports no axes.", 49, 273, MUTED)
        elif frame:
            for row, axis in enumerate(range(page * 6, min((page + 1) * 6, len(frame.axes)))):
                y = 276 + row * 29
                value = frame.axes[axis]
                mapped = next(
                    (CHANNELS[i] for i, ch in enumerate(state.channels) if ch.index == axis), ""
                )
                self.text(f"AX {axis:02d}", 49, y, TEXT, "mono")
                self.right(
                    f"{value:+.3f}", 317, y, CYAN if mapped == CHANNELS[selected] else TEXT, "mono"
                )
                pygame.draw.rect(self.canvas, GRID, (115, y + 7, 108, 3), border_radius=1)
                self.line((169, y + 3), (169, y + 14), BORDER)
                self.line((169, y + 8), (169 + round(value * 54), y + 8), CYAN)
                self.text(mapped, 231, y + 1, MUTED, "tiny")
        if state.device.axes > 6:
            self.button("axes_previous", "<", (49, 463, 34, 32), enabled=page > 0)
            self.text(f"Page {page + 1} / {(state.device.axes + 5) // 6}", 97, 472, MUTED, "tiny")
            self.button(
                "axes_next", ">", (285, 463, 34, 32), enabled=(page + 1) * 6 < state.device.axes
            )
        else:
            if state.device.instance_id == SIMULATOR:
                self.text("W S  Pitch    A D  Yaw    Q E  Roll", 49, 453, MUTED, "tiny")
            self.text("SDL axis values   ·   −1.0 to +1.0", 49, 476, MUTED, "tiny")

    def buttons_panel(self, state: Diagnostics, page: int) -> None:
        self.panel((32, 528, 304, 240))
        self.text("Buttons & hats", 49, 545, TEXT, "label")
        if state.frame:
            buttons, hats = state.frame.buttons, state.frame.hats
            for row, axis in enumerate(range(page * 12, min((page + 1) * 12, len(buttons)))):
                x, y = 49 + row % 6 * 45, 580 + row // 6 * 32
                color = CYAN if buttons[axis] else MUTED
                rect = pygame.Rect(x, y, 39, 26)
                pygame.draw.rect(
                    self.canvas, "#193842" if buttons[axis] else GRID, rect, border_radius=5
                )
                label = self.fonts["tiny"].render(f"B{axis}", True, color)
                self.canvas.blit(label, label.get_rect(center=rect.center))
            if not buttons:
                self.text("No buttons reported", 49, 586, MUTED, "tiny")
            for row, index in enumerate(range(page * 2, min((page + 1) * 2, len(hats)))):
                x, y = hats[index]
                self.text(f"HAT {index}    X {x:+d}   Y {y:+d}", 49, 651 + row * 21, TEXT, "mono")
            if not hats:
                self.text("No hats reported", 49, 651, MUTED, "tiny")
            num_pages = max((len(buttons) + 11) // 12, (len(hats) + 1) // 2)
            if num_pages > 1:
                self.button("buttons_previous", "<", (49, 719, 34, 32), enabled=page > 0)
                self.text(f"Page {page + 1} / {num_pages}", 97, 728, MUTED, "tiny")
                self.button("buttons_next", ">", (285, 719, 34, 32), enabled=page + 1 < num_pages)
            elif state.device.instance_id == SIMULATOR:
                self.text("Z X C V  Buttons     Arrow keys  Hat", 49, 730, MUTED, "tiny")

    def graph(self, state: Diagnostics, selected: int) -> None:
        self.panel((352, 180, 540, 332))
        self.text("Live signal", 370, 197, TEXT, "label")
        self.text(CHANNELS[selected], 370, 225, MUTED, "tiny")
        self.right(
            f"{state.effective_hz:.1f} Hz effective" if state.effective_hz else "— Hz effective",
            873,
            201,
        )
        axis = state.channels[selected].index
        traces = [("Raw", CYAN), ("Normalized", BLUE), ("Processed", RED)]
        values = (None, None, None)
        if axis is not None and state.latest and state.history:
            values = (
                state.latest.raw[axis],
                state.latest.normalized[selected],
                state.latest.processed[selected],
            )
        for index, ((label, color), value) in enumerate(zip(traces, values, strict=True)):
            x = 507 + index * 124
            self.line((x, 231), (x + 12, 231), color)
            self.text(
                f"{label}  {value:+.3f}" if value is not None else label, x + 17, 225, color, "tiny"
            )

        rect = pygame.Rect(420, 260, 453, 208)
        self.grid(rect)
        for label, y in (("+1.0", rect.top), (" 0.0", rect.centery), ("−1.0", rect.bottom)):
            self.right(label, 410, y - 7, MUTED, "mono")
        for x, label in (
            (rect.left, "−5 s"),
            (rect.centerx - 12, "−2.5 s"),
            (rect.right - 27, "Now"),
        ):
            self.text(label, x, 480, MUTED, "tiny")
        if axis is None:
            self.text("Map this channel to display a signal.", 517, 354, MUTED)
        elif len(state.history) > 1:
            end = state.history[-1][0]
            series = [[], [], []]
            for now, sample in state.history:
                x = rect.right - (end - now) * rect.width / CHART_NS
                for points, value in zip(
                    series,
                    (sample.raw[axis], sample.normalized[selected], sample.processed[selected]),
                    strict=True,
                ):
                    points.append((x, rect.centery - value * rect.height / 2))
            for points, (_, color) in zip(series, traces, strict=True):
                pygame.draw.aalines(self.canvas, color, False, points)

    def grid(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.canvas, "#0c141e", rect)
        for fraction in range(5):
            x = rect.x + rect.width * fraction // 4
            y = rect.y + rect.height * fraction // 4
            self.line((x, rect.top), (x, rect.bottom), BORDER if fraction == 2 else GRID)
            self.line((rect.left, y), (rect.right, y), BORDER if fraction == 2 else GRID)

    def analysis_panel(self, state: Diagnostics, selected: int) -> None:
        self.panel((352, 528, 540, 240))
        self.text("Response curve", 370, 545, TEXT, "label")
        self.text("Last recording", 646, 545, TEXT, "label")
        self.line((625, 548), (625, 747))
        self.text("Raw in / processed out", 370, 572, MUTED, "tiny")
        self.right("Identity", 605, 572, BLUE)
        rect = pygame.Rect(378, 599, 225, 121)
        self.grid(rect)
        self.line(rect.bottomleft, rect.topright, BLUE)

        def curve_point(raw: float, value: float) -> tuple[int, int]:
            return (
                round(rect.centerx + raw * rect.width / 2),
                round(rect.centery - value * rect.height / 2),
            )

        values = [i / 60 for i in range(-60, 61)]
        pygame.draw.aalines(
            self.canvas,
            RED,
            False,
            [curve_point(raw, state.static_value(selected, raw)) for raw in values],
        )
        axis = state.channels[selected].index
        if state.latest and axis is not None:
            raw = state.latest.raw[axis]
            pygame.draw.circle(
                self.canvas, CYAN, curve_point(raw, state.static_value(selected, raw)), 4
            )
        self.text("−1", 374, 732, MUTED, "tiny")
        self.right("+1", 608, 732)

        if state.capture:
            elapsed = max(0, state.last_ns - state.start_ns) / 1e9
            self.text(f"Recording  {elapsed:05.1f} s", 646, 590, RED)
            self.text(f"{len(state.capture.samples):,} samples", 646, 619, MUTED)
        elif state.completed:
            capture, summary = state.completed
            self.clip_text(
                f"{capture.protocol}  ·  {summary['samples']:,} samples", 646, 573, 220, MUTED
            )
            axis_metrics = summary["axes"].get(CHANNELS[selected], {})
            for index, (label, key) in enumerate(
                (
                    ("Center spread", "center_std"),
                    ("Center drift", "center_drift"),
                    ("Initial jump", "initial_jump"),
                    ("Onset deflection", "onset_deflection"),
                )
            ):
                y = 602 + index * 27
                self.text(label, 646, y, MUTED)
                value = axis_metrics.get(key)
                self.right(f"{value:+.5f}" if value is not None else "—", 873, y, TEXT, "mono")
            rate = summary["effective_hz"]
            if rate:
                self.text(
                    f"{rate:.1f} Hz effective  ·  {summary['duration_seconds']:.2f} s",
                    646,
                    723,
                    GREEN,
                    "tiny",
                )
        else:
            self.text("Record a test to see metrics.", 646, 590, MUTED)

    def settings_panel(self, state: Diagnostics, selected: int) -> None:
        self.panel((908, 180, 340, 588))
        self.text("Axis configuration", 926, 197, TEXT, "label")
        for index, label in enumerate(CHANNELS):
            self.button(
                f"channel_{index}",
                label,
                (926 + index * 102, 230, 94, 33),
                selected=index == selected,
                enabled=not state.travel and not state.learning,
            )
        channel = state.channels[selected]
        axis = channel.index
        unlocked = not state.capture and not state.travel and not state.learning
        mapped = axis is not None
        self.text(f"Physical axis {axis}" if mapped else "No physical axis mapped", 926, 278, MUTED)
        self.button(
            "map_previous", "<", (1139, 271, 33, 29), enabled=bool(unlocked and state.device.axes)
        )
        self.button(
            "map_next", ">", (1180, 271, 33, 29), enabled=bool(unlocked and state.device.axes)
        )
        self.button(
            "learn",
            "Cancel detection" if state.learning else "Detect movement",
            (926, 312, 177, 33),
            selected=bool(state.learning),
            enabled=bool(
                state.frame and state.frame.axes and not state.capture and not state.travel
            ),
        )
        self.button("clear", "Clear", (1112, 312, 101, 33), enabled=bool(unlocked and mapped))
        self.button("center", "Set center", (926, 356, 132, 33), enabled=bool(unlocked and mapped))
        self.button(
            "travel",
            "Save travel" if state.travel else "Capture travel",
            (1067, 356, 146, 33),
            selected=bool(state.travel),
            enabled=bool(mapped and not state.capture and not state.learning),
        )
        calibration = channel.processor.calibration
        self.text(
            f"{calibration.minimum:+.3f}  {calibration.center:+.3f}  {calibration.maximum:+.3f}",
            926,
            400,
            MUTED,
            "mono",
        )
        self.right("Min / center / max", 1213, 401)
        self.line((926, 426), (1213, 426))
        response = channel.processor.response
        for index, (key, label, _, minimum, maximum, number_format) in enumerate(RESPONSE_CONTROLS):
            y = 444 + index * 42
            amount = getattr(response, key)
            value = (
                f"{amount * 1000:.0f} ms"
                if number_format == "ms"
                else format(amount, number_format)
            )
            self.text(label, 926, y + 7, TEXT)
            self.button(
                f"{key}_down", "-", (1059, y, 32, 30), enabled=bool(unlocked and amount > minimum)
            )
            self.right(value, 1164, y + 7, TEXT, "mono")
            self.button(
                f"{key}_up", "+", (1180, y, 33, 30), enabled=bool(unlocked and amount < maximum)
            )
        self.button(
            "invert",
            "Inverted" if response.inverted else "Invert axis",
            (926, 704, 132, 33),
            selected=response.inverted,
            enabled=bool(unlocked),
        )
        self.button("reset", "Reset response", (1067, 704, 146, 33), enabled=bool(unlocked))
