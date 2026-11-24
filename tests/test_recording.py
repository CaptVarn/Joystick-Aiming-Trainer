import csv
import json

import numpy as np
import pytest

from wraith_trainer import recording
from wraith_trainer.diagnostics import Diagnostics
from wraith_trainer.joystick import Device, InputFrame
from wraith_trainer.recording import axis_metrics, export_capture


def test_center_stability_uses_full_center_hold_and_excludes_movement_metrics():
    times = np.arange(8) * 100_000_000
    values = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.001, 0.002, 0.004])
    result = axis_metrics(times, values, center_hold=True)
    assert result["baseline"] == 0
    assert result["center_std"] == pytest.approx(np.std(values))
    assert result["center_drift"] == pytest.approx(0.0015)
    assert result["center_jitter_rms"] == pytest.approx(np.sqrt(6e-6 / 7))
    assert "initial_jump" not in result


def test_initial_jump_and_reversal_use_hysteresis_and_timestamp():
    values = np.array([0.0, 0.001, 0.0, -0.001, 0.0, 0.004, 0.034, 0.025, 0.005, -0.021])
    times = np.arange(len(values)) * 100_000_000
    result = axis_metrics(times, values)
    assert result["initial_jump"] == pytest.approx(0.030)
    assert result["onset_deflection"] == pytest.approx(0.034)
    assert result["minimum_observed_step"] == pytest.approx(0.009)
    assert result["reversal_count"] == 1
    assert result["mean_reversal_seconds"] == pytest.approx(0.1)
    assert result["return_rms"] == pytest.approx(0.005)
    assert result["velocity_rms_per_second"] == pytest.approx(
        np.sqrt(np.mean(np.diff(values) ** 2)) / 0.1
    )


def test_insufficient_baseline_and_subthreshold_movement():
    short = axis_metrics(np.array([0, 10_000_000]), np.array([0.0, 0.004]))
    assert "center_std" not in short
    quiet = axis_metrics(np.arange(8) * 100_000_000, np.array([0, 0, 0, 0, 0, 0.011, 0.018, 0.001]))
    assert "initial_jump" not in quiet
    assert quiet["reversal_count"] == 0


def test_recording_exports_raw_signals_controls_settings_and_effective_rate(tmp_path):
    device = Device(4, "Example USB joystick", "guid", 2, 1, 1)
    state = Diagnostics(120, device, 0)
    state.set_mapping(0, 0)
    state.set_mapping(1, 1)
    state.protocol = "Yaw isolation"
    state.start_recording(100_000_000, simulated_demo=False)
    for index in range(8):
        active = index >= 5
        frame = InputFrame((0.004 if active else 0, 0.05 if active else 0), (active,), ((1, -1),))
        state.sample(frame, 100_000_000 * (index + 1))
    state.stop_recording()
    capture, summary = state.completed
    assert summary["effective_hz"] == pytest.approx(10)
    assert summary["axes"]["Pitch"]["interference_rms"] == pytest.approx(0.004)
    assert summary["axes"]["Yaw"]["initial_jump"] == pytest.approx(0.05)

    csv_path, json_path = export_capture(capture, summary, tmp_path)
    assert export_capture(capture, summary, tmp_path) == (csv_path, json_path)
    document = json.loads(json_path.read_text())
    assert document["metadata"]["device"]["guid"] == "guid"
    assert document["metadata"]["axes"]["Yaw"]["response"]["inner"] == 0.03
    assert document["requested_hz"] == 120
    sample = document["samples"][-1]
    assert sample["elapsed_ns"] == 700_000_000
    assert sample["raw"] == [0.004, 0.05]
    assert sample["normalized"] == [0.004, 0.05, None]
    assert sample["processed"][0] == 0
    assert 0 < sample["processed"][1] < sample["normalized"][1]
    assert sample["buttons"] == [True]
    assert sample["hats"] == [[1, -1]]

    with csv_path.open(newline="") as file:
        rows = list(csv.DictReader(file))
        assert len(rows) == 8
        assert rows[-1]["raw_axis_1"] == "0.05"
        assert rows[-1]["button_0"] == "1"
        assert rows[-1]["hat_0_y"] == "-1"
        assert json.loads(rows[0]["capture_metadata_json"])["capture_id"] == capture.capture_id
        assert rows[-1]["capture_metadata_json"] == ""


def test_failed_export_keeps_no_partial_files(tmp_path, monkeypatch):
    state = Diagnostics(120, Device(1, "Example stick", "guid", 1, 0, 0), 0)
    state.start_recording(0, simulated_demo=False)
    state.sample(InputFrame((0.0,), (), ()), 10_000_000)
    state.stop_recording()
    capture, summary = state.completed

    def fail_during_write(capture, summary, csv_path, json_path):
        json_path.write_text("{}")
        raise OSError("CSV write failed")

    with monkeypatch.context() as patch:
        patch.setattr(recording, "_write_capture", fail_during_write)
        with pytest.raises(OSError, match="CSV write failed"):
            export_capture(capture, summary, tmp_path)
        assert not list(tmp_path.iterdir())
    assert all(path.is_file() for path in export_capture(capture, summary, tmp_path))
