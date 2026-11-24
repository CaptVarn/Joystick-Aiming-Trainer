"""Timestamped diagnostic captures, numerical summaries, and portable exports."""

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy as np

TESTS = {
    "Center hold": "Release the stick and let it rest throughout the recording.",
    "Micro yaw": "Rest for 0.5 s, then make several tiny twist corrections.",
    "Slow twist": "Rest for 0.5 s, then slowly increase twist in one direction.",
    "Yaw reversal": "Rest for 0.5 s, then switch repeatedly between left and right twist.",
    "Deflection hold": "Rest for 0.5 s, then hold a small, steady twist.",
    "Return to center": "Rest for 0.5 s, then twist and release the stick several times.",
    "Pitch isolation": "Rest for 0.5 s, then move pitch while keeping twist relaxed.",
    "Yaw isolation": "Rest for 0.5 s, then twist without deliberately moving pitch.",
}
CHANNELS = ("Pitch", "Yaw", "Roll")
BASELINE_NS = 500_000_000
MOVEMENT_THRESHOLD = 0.02
REST_THRESHOLD = 0.01


@dataclass(frozen=True)
class Sample:
    elapsed_ns: int
    raw: tuple[float, ...]
    normalized: tuple[float | None, ...]
    processed: tuple[float | None, ...]
    buttons: tuple[bool, ...]
    hats: tuple[tuple[int, int], ...]


@dataclass
class Capture:
    protocol: str
    requested_hz: int
    metadata: dict
    samples: list[Sample]
    started_utc: str
    capture_id: str
    result: str = "complete"

    @classmethod
    def start(cls, protocol: str, hz: int, metadata: dict) -> "Capture":
        return cls(protocol, hz, metadata, [], datetime.now(UTC).isoformat(), uuid4().hex[:12])

    def summary(self) -> dict:
        samples = self.samples
        timestamps = np.array([sample.elapsed_ns for sample in samples], dtype=np.int64)
        window = (int(timestamps[-1]) - int(timestamps[0])) / 1e9 if len(timestamps) > 1 else 0
        axes = self.metadata["axes"]
        mapped = {
            name: index
            for name, settings in axes.items()
            if (index := settings["index"]) is not None
        }
        raw = np.asarray([sample.raw for sample in samples])
        metrics = {
            name: axis_metrics(timestamps, raw[:, axis], center_hold=self.protocol == "Center hold")
            for name, axis in mapped.items()
            if len(samples) > 1
        }
        if self.protocol in {"Pitch isolation", "Yaw isolation"} and len(samples) > 1:
            primary = self.protocol.split()[0]
            if primary in mapped and "baseline" in metrics[primary]:
                active = (timestamps - timestamps[0] >= BASELINE_NS) & (
                    np.abs(raw[:, mapped[primary]] - metrics[primary]["baseline"])
                    >= MOVEMENT_THRESHOLD
                )
                for name, axis in mapped.items():
                    if name != primary and np.any(active) and "baseline" in metrics[name]:
                        deviation = raw[active, axis] - metrics[name]["baseline"]
                        metrics[name]["interference_rms"] = float(np.sqrt(np.mean(deviation**2)))
        return {
            "samples": len(samples),
            "effective_hz": (len(samples) - 1) / window if window > 0 else None,
            "duration_seconds": window,
            "axes": metrics,
        }


def axis_metrics(
    timestamps_ns: np.ndarray, values: np.ndarray, *, center_hold: bool = False
) -> dict[str, float | int]:
    """Summarize one raw axis with a timed center reference and movement hysteresis."""
    seconds = (timestamps_ns - timestamps_ns[0]) / 1e9
    result: dict[str, float | int] = {}
    elapsed = np.diff(seconds)
    if np.all(elapsed > 0):
        velocity = np.diff(values) / elapsed
        result["velocity_rms_per_second"] = float(np.sqrt(np.mean(velocity**2)))
        if len(velocity) > 1:
            acceleration = np.diff(velocity) / ((elapsed[:-1] + elapsed[1:]) / 2)
            result["acceleration_rms_per_second2"] = float(np.sqrt(np.mean(acceleration**2)))

    baseline_end = int(np.searchsorted(timestamps_ns, timestamps_ns[0] + BASELINE_NS))
    if baseline_end < 2 or baseline_end == len(values):
        return result
    resting = values[:baseline_end]
    baseline = float(np.median(resting))
    result["baseline"] = baseline
    center = values if center_hold else resting
    result["center_std"] = float(np.std(center))
    result["center_drift"] = float(
        np.median(center[len(center) // 2 :]) - np.median(center[: len(center) // 2])
    )
    result["center_jitter_rms"] = float(np.sqrt(np.mean(np.diff(center) ** 2)))
    if center_hold:
        return result

    noise = max(0.001, float(np.max(np.abs(np.diff(resting)))))
    steps = np.abs(np.diff(values, prepend=values[0]))
    movement = (steps > noise) & (np.abs(values - baseline) > REST_THRESHOLD)
    observed = steps[baseline_end:][movement[baseline_end:]]
    if observed.size:
        result["minimum_observed_step"] = float(np.min(observed))

    direction = 0
    armed = abs(values[baseline_end - 1] - baseline) <= REST_THRESHOLD
    returns = []
    reversals = []
    reversal_start = None
    for index in range(baseline_end, len(values)):
        delta = values[index] - baseline
        distance = abs(delta)
        sign = 1 if delta > 0 else -1
        if distance <= REST_THRESHOLD:
            if not armed and direction:
                returns.append(delta)
            armed = True
        if direction and reversal_start is None and distance < MOVEMENT_THRESHOLD:
            reversal_start = seconds[index]
        if distance < MOVEMENT_THRESHOLD:
            continue
        if armed and "initial_jump" not in result:
            result["initial_jump"] = float(abs(values[index] - values[index - 1]))
            result["onset_deflection"] = float(distance)
        if direction and sign != direction:
            start = seconds[index - 1] if reversal_start is None else reversal_start
            reversals.append(seconds[index] - start)
        reversal_start = None
        direction = sign
        armed = False

    result["reversal_count"] = len(reversals)
    result["return_count"] = len(returns)
    if reversals:
        result["mean_reversal_seconds"] = float(np.mean(reversals))
    if returns:
        result["return_rms"] = float(np.sqrt(np.mean(np.square(returns))))
    return result


def export_capture(capture: Capture, summary: dict, directory: Path) -> tuple[Path, Path]:
    """Publish both files together after writing them on the same filesystem."""
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"wraith-{capture.capture_id}"
    published = directory / stem
    csv_path, json_path = published / f"{stem}.csv", published / f"{stem}.json"
    if csv_path.is_file() and json_path.is_file():
        return csv_path, json_path
    with TemporaryDirectory(prefix=".wraith-", dir=directory) as staging:
        staged = Path(staging) / stem
        staged.mkdir()
        _write_capture(capture, summary, staged / csv_path.name, staged / json_path.name)
        staged.rename(published)
    return csv_path, json_path


def _write_capture(capture: Capture, summary: dict, csv_path: Path, json_path: Path) -> None:
    data = {
        "schema_version": 1,
        "capture_id": capture.capture_id,
        "protocol": capture.protocol,
        "started_utc": capture.started_utc,
        "requested_hz": capture.requested_hz,
        "result": capture.result,
        "metadata": capture.metadata,
        "summary": summary,
    }
    with json_path.open("w", encoding="utf-8") as file:
        file.write(json.dumps(data, allow_nan=False)[:-1])
        file.write(', "samples": [')
        for index, sample in enumerate(capture.samples):
            if index:
                file.write(",")
            file.write(json.dumps(asdict(sample), allow_nan=False))
        file.write("]}")

    inputs = capture.metadata["device"]
    headings = ["elapsed_ns"]
    headings += [f"raw_axis_{index}" for index in range(inputs["axes"])]
    headings += [
        f"{stage}_{name.lower()}" for stage in ("normalized", "processed") for name in CHANNELS
    ]
    headings += [f"button_{index}" for index in range(inputs["buttons"])]
    headings += [f"hat_{index}_{axis}" for index in range(inputs["hats"]) for axis in ("x", "y")]
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([*headings, "capture_metadata_json"])
        for index, sample in enumerate(capture.samples):
            writer.writerow(
                [
                    sample.elapsed_ns,
                    *sample.raw,
                    *sample.normalized,
                    *sample.processed,
                    *(int(pressed) for pressed in sample.buttons),
                    *(coordinate for hat in sample.hats for coordinate in hat),
                    json.dumps(data, allow_nan=False) if index == 0 else "",
                ]
            )
