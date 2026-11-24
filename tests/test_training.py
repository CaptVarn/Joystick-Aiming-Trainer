from dataclasses import replace
from math import acos, degrees

import pytest

from wraith_trainer.training import (
    RATE,
    TICK,
    Camera,
    Isolation,
    Mode,
    Pattern,
    Session,
    Settings,
    bearing,
    dot,
    focal_length,
)


def test_rotation_projects_a_stationary_target_relative_to_fixed_center():
    camera = Camera()
    target = bearing(5, 0)
    focal = focal_length(576)
    before = camera.projection(target, focal)
    assert before[0] > 0
    for _ in range(24):
        camera.rotate(0, 0.5)
    assert camera.yaw == pytest.approx(4.5)
    after = camera.projection(target, focal)
    assert 0 < after[0] < before[0]
    camera.rotate(0, 0)
    assert camera.projection(target, focal) == after
    assert camera.projection(bearing(180, 0), focal) is None
    assert camera.projection(bearing(camera.yaw, camera.pitch), focal) == pytest.approx((0, 0))


def test_time_progression_and_scoring_are_independent_of_update_cadence():
    cfg = Settings.defaults(Mode.TRACKING)
    coarse = Session(Mode.TRACKING, cfg, 0, seed=1)
    fine = Session(Mode.TRACKING, cfg, 0, seed=1)
    for session in (coarse, fine):
        session.input(0, 0.25, False)
    coarse.advance(1_000_000_000)
    for index in range(1, 101):
        fine.advance(index * 10_000_000)
    assert coarse.ticks == fine.ticks == 120
    assert coarse.camera.yaw == fine.camera.yaw == pytest.approx(RATE * 0.25)
    assert coarse.target.direction == fine.target.direction
    assert coarse.score == fine.score
    assert coarse.score.mean_error > 0
    assert coarse.score.input_change_rms == 0


@pytest.mark.parametrize("pattern", list(Pattern))
def test_tracking_patterns_move_continuously_within_configured_speed(pattern):
    cfg = replace(Settings.defaults(Mode.TRACKING), pattern=pattern)
    session = Session(Mode.TRACKING, cfg, 0, seed=2)
    target = session.target
    initial = previous = target.direction
    for _ in range(360):
        session.step()
        step = degrees(acos(max(-1, min(1, dot(previous, target.direction)))))
        assert step <= cfg.speed * TICK + 1e-6
        assert target.speed <= cfg.speed
        previous = target.direction
    assert previous != initial


def test_micro_correction_requires_an_unbroken_hold_and_schedules_a_new_target():
    session = Session(Mode.MICRO, replace(Settings(), hold=0.05, interval=0.1), 0, seed=3)
    target = session.target
    target.direction = bearing(0, 0)
    for _ in range(3):
        session.step()
    target.direction = bearing(6, 0)
    session.step()
    target.direction = bearing(0, 0)
    for _ in range(6):
        session.step()
    assert session.score.acquisition == pytest.approx([10 * TICK])
    assert session.score.settling == pytest.approx([4 * TICK])
    assert session.score.accuracy == pytest.approx(0.9)
    assert session.target is None
    for _ in range(11):
        session.step()
    assert session.score.valid == 10
    session.step()
    assert session.target is not None


def test_trigger_confirmation_requires_a_new_press_after_hold():
    cfg = replace(Settings.defaults(Mode.ACQUISITION), trigger=2, hold=0.05, targets=1)
    session = Session(Mode.ACQUISITION, cfg, 0, seed=7)
    session.target.direction = bearing(0, 0)
    session.input(0, 0, True)
    for _ in range(10):
        session.step()
    assert session.ready and not session.score.acquisition
    session.input(0, 0, False)
    session.step()
    session.input(0, 0, True)
    session.step()
    assert session.finish_reason == "Target goal complete"
    assert len(session.score.acquisition) == 1


def test_yaw_isolation_tracks_off_axis_input_without_using_it_for_rotation():
    cfg = replace(Settings.defaults(Mode.ISOLATION), isolation=Isolation.YAW)
    session = Session(Mode.ISOLATION, cfg, 0, seed=0)
    session.input(None, 0.25, False)
    session.step()
    assert session.score.interference_rms is None
    session.input(0.4, 0.25, False)
    session.advance(500_000_000)
    assert session.camera.pitch == 0
    assert session.camera.yaw == pytest.approx(0.5 * RATE * 0.25)
    assert session.score.interference_rms == pytest.approx(0.4)


def test_round_timeout_and_overshoot_hysteresis():
    cfg = replace(Settings.defaults(Mode.ACQUISITION), duration=1)
    session = Session(Mode.ACQUISITION, cfg, 0, seed=11)
    target = session.target
    for angle in (-0.7, -0.05, 0.05, 0.7, 0.05, -0.05):
        target.direction = bearing(angle, 0)
        session.step()
    assert session.score.overshoots == 1
    session.advance(2_000_000_000)
    assert session.ticks == 120
    assert session.finish_reason == "Time complete"
