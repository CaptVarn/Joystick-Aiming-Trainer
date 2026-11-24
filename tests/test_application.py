import json
from collections import defaultdict
from time import perf_counter_ns

import pygame
import pytest

from wraith_trainer.application import Application, advance_deadline, main
from wraith_trainer.joystick import SIMULATOR


@pytest.fixture
def sdl(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(pygame.font, "SysFont", lambda *_: pygame.font.Font(None, 16))
    pygame.display.init()
    pygame.font.init()
    pygame.joystick.init()
    yield
    pygame.quit()


def click(app, action, now):
    point = app.dashboard.hitboxes[action].center
    app.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point), now)
    app.draw()


def test_simulated_dashboard_can_record_and_export(sdl, tmp_path, monkeypatch):
    keys = defaultdict(int)
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: keys)
    app = Application(120, tmp_path, simulate=True)
    try:
        now = perf_counter_ns()
        app.poll_input(now)
        app.draw()
        click(app, "protocol_next", now)
        click(app, "inner_up", now)
        click(app, "record", now)
        assert "inner_up" not in app.dashboard.hitboxes
        for index in range(1, 96):
            keys[pygame.K_d] = index > 65
            app.poll_input(now + index * 8_333_333)
        click(app, "record", now + 800_000_000)
        click(app, "export", now + 800_000_000)
        app.export.result(timeout=5)
        app.finish_export()

        document = json.loads(next(tmp_path.rglob("*.json")).read_text())
        assert document["protocol"] == "Micro yaw"
        assert document["metadata"]["axes"]["Yaw"]["response"]["inner"] == 0.04
        assert document["summary"]["samples"] == 95
        assert document["summary"]["effective_hz"] == pytest.approx(120)
        assert document["summary"]["axes"]["Yaw"]["initial_jump"] > 0.02
        assert len(list(tmp_path.rglob("*.csv"))) == 1
        assert app.state.notice.startswith("Exported")
    finally:
        app.executor.shutdown()


def test_hotplug_and_disconnect_preserve_in_progress_capture(sdl, tmp_path, monkeypatch):
    class PluggedStick:
        def __init__(self):
            self.axis_value = 0.0
            self.closed = False

        def get_instance_id(self):
            return 42

        def get_name(self):
            return "Example stick"

        def get_guid(self):
            return "example-guid"

        def get_numaxes(self):
            return 1

        def get_numbuttons(self):
            return 1

        def get_numhats(self):
            return 1

        def get_axis(self, index):
            assert index == 0
            return self.axis_value

        def get_button(self, index):
            return True

        def get_hat(self, index):
            return (1, 0)

        def quit(self):
            self.closed = True

    stick = PluggedStick()
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda _: stick)
    monkeypatch.setattr(pygame.joystick, "get_count", lambda: 0)
    app = Application(120, tmp_path, simulate=True)
    try:
        now = perf_counter_ns()
        app.event(pygame.event.Event(pygame.JOYDEVICEADDED, device_index=0), now)
        app.draw()
        click(app, "device_next", now)
        assert app.state.device.instance_id == 42
        assert app.state.channels[1].index is None
        app.poll_input(now + 1_000_000)
        app.draw()
        click(app, "learn", now + 1_000_000)
        stick.axis_value = 0.5
        app.poll_input(now + 2_000_000)
        assert app.state.channels[1].index == 0
        app.draw()
        click(app, "record", now + 3_000_000)
        app.poll_input(now + 4_000_000)
        app.event(pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=42), now + 5_000_000)

        assert stick.closed
        assert app.state.device.instance_id == SIMULATOR
        assert app.state.capture is None
        capture, summary = app.state.completed
        assert capture.result == "device disconnected"
        assert summary["samples"] == 1
        assert capture.samples[0].raw == (0.5,)
        assert capture.samples[0].buttons == (True,)
        assert capture.samples[0].hats == ((1, 0),)
    finally:
        app.executor.shutdown()


def test_entry_point_draws_and_exits(sdl, monkeypatch, tmp_path):
    draw = Application.draw
    frames = []

    def draw_then_quit(app):
        frames.append(app.state.latest)
        draw(app)
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    monkeypatch.setattr(Application, "draw", draw_then_quit)
    assert main(["--simulate", "--sample-rate", "90", "--export-dir", str(tmp_path)]) == 0
    assert len(frames) == 1
    assert len(frames[0].raw) == 3


def test_scheduler_skips_missed_poll_slots():
    assert advance_deadline(10, 10, 10) == 20
    assert advance_deadline(10, 35, 10) == 40
