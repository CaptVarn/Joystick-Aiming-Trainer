import json
from dataclasses import replace

import pytest

from wraith_trainer.flight import PITCH_LIMIT, Camera, axis_step, bearing, focal_length
from wraith_trainer.ship_profiles import (
    DIRECT_PROFILE,
    GENERIC_PROFILE,
    PRESETS,
    AxisFlight,
    FlightMode,
    export_profile,
    load_profile,
)
from wraith_trainer.training import TICK, Isolation, Mode, Session, Settings


def test_assisted_axis_accelerates_caps_and_brakes_with_continuous_displacement():
    profile = replace(GENERIC_PROFILE, yaw=AxisFlight(30, 60, 90))
    camera = Camera(profile)
    camera.rotate(0, 1, 0, 0.25)
    assert (camera.yaw_rate, camera.yaw) == pytest.approx((15, 1.875))
    camera.rotate(0, 1, 0, 0.5)
    assert (camera.yaw_rate, camera.yaw) == pytest.approx((30, 15))
    camera.rotate(0, 0, 0, 1)
    assert (camera.yaw_rate, camera.yaw) == pytest.approx((0, 20))
    camera.rotate(0, 0, 0, 1)
    assert camera.yaw == pytest.approx(20)


def test_reversal_brakes_through_zero_before_accelerating_in_new_direction():
    config = AxisFlight(45, 100, 200)
    assert axis_step(20, -1, config, FlightMode.ASSISTED, 0.2) == pytest.approx((-10, 0.5))
    assert axis_step(-20, 1, config, FlightMode.ASSISTED, 0.05) == pytest.approx((-10, -0.75))


def test_rate_exponent_and_acceleration_curve_shape_independent_quantities():
    config = AxisFlight(100, 200, 200, acceleration_curve=2, command_exponent=2)
    assert axis_step(0, 0.5, config, FlightMode.DIRECT, 1) == pytest.approx((25, 25))
    assert axis_step(0, 0.5, config, FlightMode.ASSISTED, 0.1) == pytest.approx((12.5, 0.625))


def test_axes_have_independent_rate_caps_and_pitch_recovers_from_limit():
    camera = Camera(replace(GENERIC_PROFILE, pitch=AxisFlight(20), yaw=AxisFlight(30)))
    for _ in range(600):
        camera.rotate(1, 1, 0, TICK)
    assert (camera.pitch, camera.yaw_rate) == pytest.approx((PITCH_LIMIT, 30))
    assert camera.pitch_rate == 0
    camera.rotate(-1, 0, 0, TICK)
    assert camera.pitch < PITCH_LIMIT


def test_wider_fov_projects_target_closer_to_center_without_changing_angular_error():
    direction = bearing(10, 0)
    camera = Camera()
    narrow = camera.projection(direction, focal_length(576, 30))
    wide = camera.projection(direction, focal_length(576, 70))
    assert 0 < wide[0] < narrow[0]
    for fov in (30, 70):
        profile = replace(GENERIC_PROFILE, fov=fov)
        session = Session(Mode.MICRO, Settings(), 0, profile=profile, seed=0)
        session.target.direction = direction
        session.step()
        assert session.error == pytest.approx(10)


def test_roll_banks_the_view_without_changing_the_aim_point_or_counting_a_crossing():
    session = Session(
        Mode.MICRO, replace(Settings(), roll_enabled=True), 0, profile=DIRECT_PROFILE, seed=0
    )
    session.target.direction = bearing(8, 1)
    session.input(0, 0, False, roll=1)
    session.advance(1_000_000_000)
    assert session.camera.roll == pytest.approx(75)
    assert (session.camera.pitch, session.camera.yaw) == (0, 0)
    assert session.score.max_error == pytest.approx(session.score.mean_error)
    assert session.score.overshoots == 0
    assert session.camera.coordinates(session.target.direction) != pytest.approx(
        session.camera.coordinates(session.target.direction, banked=False)
    )
    assert session.camera.projection(bearing(0, 0), 400) == pytest.approx((0, 0))


def test_single_axis_drill_locks_roll_even_when_enabled():
    cfg = replace(Settings(), isolation=Isolation.YAW, roll_enabled=True)
    session = Session(Mode.ISOLATION, cfg, 0, seed=0)
    session.input(0.5, 1, False, roll=1)
    session.advance(1_000_000_000)
    assert session.camera.yaw > 0
    assert (session.camera.pitch, session.camera.roll) == (0, 0)


def test_profile_json_round_trip_preserves_dynamics_and_provenance(tmp_path):
    profile = replace(PRESETS[2], fov=61, edited=True, yaw=AxisFlight(52, 100, 200, 2, 0.75))
    path = export_profile(profile, tmp_path)
    assert load_profile(path) == profile
    assert export_profile(profile, tmp_path) != path
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert json.loads(path.read_text())["schema_version"] == 1


@pytest.mark.parametrize(
    "invalid",
    [{"schema_version": 9}, {"fov": float("nan")}, {"pitch": {"rate": 0}}, {"yaw": True}],
)
def test_profile_json_rejects_invalid_values(tmp_path, invalid):
    path = export_profile(GENERIC_PROFILE, tmp_path)
    document = json.loads(path.read_text())
    document.update(invalid)
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        load_profile(path)


def test_spviewer_presets_match_the_pinned_unboosted_snapshot():
    expected = [
        ("Aegis Gladius", 68, 52, 200),
        ("Anvil Arrow", 75, 57, 205),
        ("Anvil F8C Lightning", 38, 35, 140),
        ("Anvil F7C-M Super Hornet Mk I", 53, 42, 145),
    ]
    sourced = [profile for profile in PRESETS if profile.source]
    assert [(p.name, p.pitch.rate, p.yaw.rate, p.roll.rate) for p in sourced] == expected
    for profile in sourced:
        assert profile.source.startswith("https://www.spviewer.eu/performance?ship=")
        assert profile.source_date == "2026-04-27"
        assert profile.game_version == ""
        assert profile.yaw.braking == GENERIC_PROFILE.yaw.braking
