"""Desktop entry point and independently scheduled input and rendering."""

import argparse
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter_ns

import pygame

from .axis import Response
from .dashboard import RESPONSE_CONTROLS, SIZE, Dashboard
from .diagnostics import Diagnostics
from .joystick import SIMULATOR, JoystickManager
from .recording import CHANNELS, TESTS, Sample, export_capture
from .training import Session, required_axes
from .training_view import TrainingView

LOG = logging.getLogger(__name__)
RENDER_HZ = 60


def advance_deadline(deadline: int, now: int, interval: int) -> int:
    """Skip missed polls without synthesizing timestamped input samples."""
    return deadline + ((now - deadline) // interval + 1) * interval


class Application:
    def __init__(
        self,
        rate: int,
        output: Path,
        *,
        simulate: bool = False,
        fullscreen: bool = False,
    ) -> None:
        self.window_size = SIZE
        self.fullscreen = fullscreen
        self.screen = self.open_window()
        pygame.display.set_caption("Wraith Flight Trainer")
        self.manager = JoystickManager()
        device = SIMULATOR if simulate else next(iter(self.manager.hardware), SIMULATOR)
        self.state = Diagnostics(rate, self.manager.devices[device], perf_counter_ns())
        self.dashboard = Dashboard()
        self.training = TrainingView(self.dashboard)
        self.in_training = False
        self.session: Session | None = None
        self.selected = 1
        self.axes_page = self.buttons_page = 0
        self.output = output
        self.demo = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wraith-export")
        self.export: Future[tuple[Path, Path]] | None = None

    def open_window(self) -> pygame.Surface:
        if self.fullscreen:
            return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        return pygame.display.set_mode(self.window_size, pygame.RESIZABLE)

    def change_device(self, instance: int, now_ns: int) -> None:
        self.state.select_device(self.manager.devices[instance], now_ns)
        self.axes_page = self.buttons_page = 0

    def disconnect(self, instance: int, now_ns: int) -> None:
        device = self.manager.devices.get(instance)
        self.manager.remove(instance)
        self.state.profiles.pop(instance, None)
        if self.state.device.instance_id == instance and device is not None:
            self.finish_training(now_ns, f"{device.name} disconnected")
            was_recording = self.state.capture is not None
            self.state.stop_recording("device disconnected")
            result = self.state.notice if was_recording else ""
            self.change_device(SIMULATOR, now_ns)
            self.state.notice = (
                f"{device.name} disconnected. {result or 'Switched to simulated input.'}"
            )

    def record(self, now_ns: int) -> None:
        if self.state.capture:
            self.state.stop_recording()
        elif self.state.latest and not self.state.travel and not self.state.learning:
            self.state.start_recording(now_ns, simulated_demo=self.demo)

    def poll_input(self, now_ns: int) -> None:
        if self.session:
            self.session.advance(now_ns)
        instance = self.state.device.instance_id
        try:
            frame = self.manager.read(
                instance, (now_ns - self.state.last_ns) / 1e9, now_ns / 1e9, self.demo
            )
        except pygame.error:
            if instance == SIMULATOR:
                raise
            LOG.exception("event=joystick_read_failed instance_id=%s", instance)
            self.disconnect(instance, now_ns)
        else:
            self.state.sample(frame, now_ns)
            self.update_training_input(self.state.latest)

    def training_unavailable(self) -> str:
        axes = required_axes(self.training.mode, self.training.config.isolation)
        missing = [CHANNELS[axis] for axis in axes if self.state.channels[axis].index is None]
        if missing:
            return f"Map {' and '.join(missing)} in Diagnostics."
        return "" if self.state.latest else "Waiting for input from the selected device."

    def update_training_input(self, sample: Sample | None) -> None:
        if self.session is None or self.session.finish_reason or sample is None:
            return
        pitch, yaw, _ = sample.processed
        trigger = self.session.settings.trigger
        pressed = trigger is not None and trigger < len(sample.buttons) and sample.buttons[trigger]
        self.session.input(pitch, yaw, pressed)

    def finish_training(self, now_ns: int, reason: str) -> None:
        if self.session:
            self.session.advance(now_ns)
            self.session.finish(reason)

    def training_action(self, action: str, now_ns: int) -> None:
        if action == "diagnostics":
            self.in_training = False
            self.session = None
        elif action == "start_training" and self.session is None:
            if self.training_unavailable():
                return
            settings = self.training.config
            if settings.trigger is not None and settings.trigger >= self.state.device.buttons:
                settings = replace(settings, trigger=None)
            self.session = Session(self.training.mode, settings, now_ns)
            self.update_training_input(self.state.latest)
        elif action == "stop_training":
            self.finish_training(now_ns, "Round ended")
        elif action == "training_setup" and self.session and self.session.finish_reason:
            self.session = None
        elif self.session is None and action.endswith(("_next", "_previous")):
            self.training.adjust(action, self.state.device.buttons)

    def handle_action(self, action: str, now_ns: int) -> None:
        state = self.state
        if self.in_training:
            self.training_action(action, now_ns)
        elif action == "training":
            if not (state.capture or state.learning or state.travel):
                self.in_training = True
                self.demo = False
        elif action == "record":
            self.record(now_ns)
        elif action == "export" and state.completed and self.export is None and not state.capture:
            capture, summary = state.completed
            self.export = self.executor.submit(export_capture, capture, summary, self.output)
            state.notice = "Writing CSV and JSON…"
        elif action.startswith(("axes_", "buttons_")):
            field, direction = action.split("_")
            page = f"{field}_page"
            device = state.device
            limit = (
                (device.axes + 5) // 6
                if field == "axes"
                else max((device.buttons + 11) // 12, (device.hats + 1) // 2)
            )
            next_page = getattr(self, page) + (1 if direction == "next" else -1)
            setattr(self, page, max(0, min(limit - 1, next_page)))
        elif action.startswith("channel_"):
            if not state.learning and not state.travel:
                self.selected = int(action[-1])
        elif not state.capture:
            self.configure(action, now_ns)

    def configure(self, action: str, now_ns: int) -> None:
        state = self.state
        increment = 1 if action.endswith(("next", "_up")) else -1
        channel = state.channels[self.selected]
        if action.startswith("device_"):
            ids = list(self.manager.devices)
            current = ids.index(state.device.instance_id)
            self.change_device(ids[(current + increment) % len(ids)], now_ns)
        elif action == "demo" and state.device.instance_id == SIMULATOR:
            self.demo = not self.demo
        elif action.startswith("protocol_"):
            tests = tuple(TESTS)
            state.protocol = tests[(tests.index(state.protocol) + increment) % len(tests)]
        elif action.startswith("rate_"):
            state.rate = min(240, max(30, state.rate + 30 * increment))
        elif action == "learn":
            state.learn(self.selected)
        elif action == "travel":
            state.capture_travel(self.selected)
        elif not state.learning and not state.travel:
            if action.startswith("map_"):
                used = {other.index for other in state.channels if other is not channel}
                choices = [axis for axis in range(state.device.axes) if axis not in used]
                if choices:
                    index = (
                        choices.index(channel.index)
                        if channel.index is not None
                        else (-1 if increment == 1 else 0)
                    )
                    state.set_mapping(self.selected, choices[(index + increment) % len(choices)])
            elif action == "clear":
                state.set_mapping(self.selected, None)
            elif action == "center":
                state.set_center(self.selected)
            elif action == "reset":
                state.adjust(self.selected, **asdict(Response()))
            elif action == "invert":
                state.adjust(self.selected, inverted=not channel.processor.response.inverted)
            else:
                self.adjust_response(action, increment)

    def adjust_response(self, action: str, increment: int) -> None:
        response = self.state.channels[self.selected].processor.response
        for key, _, step, minimum, maximum, _ in RESPONSE_CONTROLS:
            if action in (f"{key}_up", f"{key}_down"):
                value = round(getattr(response, key) + step * increment, 4)
                self.state.adjust(self.selected, **{key: min(maximum, max(minimum, value))})
                return

    def finish_export(self) -> None:
        if self.export is None or not self.export.done():
            return
        try:
            csv_path, _ = self.export.result()
        except (OSError, ValueError) as exc:
            LOG.exception("event=diagnostic_export_failed")
            self.state.notice = f"Export failed: {exc}"
        else:
            self.state.notice = f"Exported CSV and JSON to {csv_path.parent}"
        finally:
            self.export = None

    def event(self, event: pygame.event.Event, now_ns: int) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.JOYDEVICEADDED:
            try:
                self.manager.add(event.device_index)
            except pygame.error:
                LOG.warning(
                    "event=joystick_open_failed index=%s", event.device_index, exc_info=True
                )
                self.state.notice = "Could not open the new joystick. Reconnect it and try again."
        elif event.type == pygame.JOYDEVICEREMOVED:
            self.disconnect(event.instance_id, now_ns)
        elif event.type == pygame.WINDOWFOCUSLOST:
            self.finish_training(now_ns, "Window lost focus")
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                if not self.fullscreen:
                    self.window_size = self.screen.get_size()
                self.fullscreen = not self.fullscreen
                self.screen = self.open_window()
            elif event.key == pygame.K_SPACE:
                if not self.in_training:
                    self.record(now_ns)
                elif self.session is None:
                    self.training_action("start_training", now_ns)
                elif self.session.finish_reason:
                    self.training_action("training_setup", now_ns)
                else:
                    self.training_action("stop_training", now_ns)
            elif event.key == pygame.K_ESCAPE:
                if self.in_training:
                    self.training_action("diagnostics", now_ns)
                elif self.state.learning:
                    self.state.learn(self.selected)
                elif self.state.travel:
                    self.state.travel = None
                    self.state.notice = "Travel capture cancelled."
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if action := self.dashboard.action_at(event.pos):
                self.handle_action(action, now_ns)
        return True

    def draw(self) -> None:
        if self.in_training:
            self.training.draw(self.screen, self.state, self.session, self.training_unavailable())
        else:
            self.dashboard.draw(
                self.screen,
                self.state,
                selected=self.selected,
                axes_page=self.axes_page,
                buttons_page=self.buttons_page,
                more_devices=len(self.manager.devices) > 1,
                demo=self.demo and self.state.device.instance_id == SIMULATOR,
                exporting=self.export is not None,
            )
        pygame.display.flip()

    def run(self) -> None:
        clock = pygame.time.Clock()
        sample_due = render_due = perf_counter_ns()
        rate = self.state.rate
        render_interval = 1_000_000_000 // RENDER_HZ
        try:
            while True:
                for event in pygame.event.get():
                    if not self.event(event, perf_counter_ns()):
                        return

                now_ns = perf_counter_ns()
                if self.state.rate != rate:
                    rate = self.state.rate
                    sample_due = now_ns
                    self.state.history.clear()
                if now_ns >= sample_due:
                    self.poll_input(now_ns)
                    sample_due = advance_deadline(sample_due, now_ns, 1_000_000_000 // rate)
                elif self.session:
                    self.session.advance(now_ns)
                if now_ns >= render_due:
                    self.finish_export()
                    self.draw()
                    render_due = advance_deadline(render_due, now_ns, render_interval)
                clock.tick(500)
        finally:
            self.executor.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wraith Flight Trainer diagnostics and training")
    parser.add_argument("--simulate", action="store_true", help="start with the simulated joystick")
    parser.add_argument("--fullscreen", action="store_true", help="launch fullscreen")
    parser.add_argument(
        "--sample-rate", default=120, type=int, metavar="HZ", help="requested rate (30–240 Hz)"
    )
    parser.add_argument("--export-dir", default=Path("diagnostic_exports"), type=Path)
    args = parser.parse_args(argv)
    if not 30 <= args.sample_rate <= 240:
        parser.error("--sample-rate must be between 30 and 240 Hz")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    pygame.display.init()
    pygame.font.init()
    pygame.joystick.init()
    try:
        Application(
            args.sample_rate,
            args.export_dir.expanduser().resolve(),
            simulate=args.simulate,
            fullscreen=args.fullscreen,
        ).run()
    finally:
        pygame.quit()
    return 0
