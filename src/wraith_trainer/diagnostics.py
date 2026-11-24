"""UI-independent diagnostics state and capture lifecycle."""

from collections import deque
from dataclasses import asdict, dataclass, field, replace

from .axis import AxisProcessor, Calibration, TravelCapture, moved_axis, normalize, shape
from .joystick import SIMULATOR, Device, InputFrame
from .recording import CHANNELS, TESTS, Capture, Sample

MAX_CAPTURE_NS = 300_000_000_000
CHART_NS = 5_000_000_000


@dataclass
class Channel:
    index: int | None = None
    processor: AxisProcessor = field(default_factory=AxisProcessor)


class Diagnostics:
    def __init__(self, rate: int, device: Device, now_ns: int) -> None:
        self.rate = rate
        self.profiles: dict[int, list[Channel]] = {}
        self.capture: Capture | None = None
        self.completed: tuple[Capture, dict] | None = None
        self.start_ns = 0
        self.protocol = next(iter(TESTS))
        self.select_device(device, now_ns)

    def select_device(self, device: Device, now_ns: int) -> None:
        self.device = device
        if device.instance_id not in self.profiles:
            indices = range(3) if device.instance_id == SIMULATOR else (None,) * 3
            self.profiles[device.instance_id] = [Channel(index) for index in indices]
        self.channels = self.profiles[device.instance_id]
        for channel in self.channels:
            channel.processor.output = None
        self.frame: InputFrame | None = None
        self.latest: Sample | None = None
        self.history: deque[tuple[int, Sample]] = deque()
        self.last_ns = now_ns
        self.effective_hz: float | None = None
        self.learning: tuple[int, tuple[float, ...]] | None = None
        self.travel: TravelCapture | None = None
        self.notice = f"Selected {device.name}."

    def sample(self, frame: InputFrame, now_ns: int) -> None:
        elapsed = (now_ns - self.last_ns) / 1e9
        self.last_ns = now_ns
        self.frame = frame
        if self.learning is not None:
            channel, baseline = self.learning
            if (axis := moved_axis(baseline, frame.axes)) is not None:
                self.set_mapping(channel, axis)
                self.learning = None
        if self.travel:
            self.travel.update(frame.axes)

        normalized, processed = [], []
        for channel in self.channels:
            if channel.index is None:
                normalized.append(None)
                processed.append(None)
            else:
                before, after = channel.processor.update(frame.axes[channel.index], elapsed)
                normalized.append(before)
                processed.append(after)
        sample = Sample(
            now_ns - self.start_ns if self.capture else 0,
            frame.axes,
            tuple(normalized),
            tuple(processed),
            frame.buttons,
            frame.hats,
        )
        self.latest = sample
        self.history.append((now_ns, sample))
        while self.history and now_ns - self.history[0][0] > CHART_NS:
            self.history.popleft()
        span = now_ns - self.history[0][0]
        self.effective_hz = (len(self.history) - 1) * 1e9 / span if span else None

        if self.capture:
            self.capture.samples.append(sample)
            if sample.elapsed_ns >= MAX_CAPTURE_NS:
                self.stop_recording("duration limit")

    def set_mapping(self, channel_index: int, physical_index: int | None) -> None:
        if physical_index is not None and any(
            channel.index == physical_index
            for index, channel in enumerate(self.channels)
            if index != channel_index
        ):
            self.notice = (
                f"Axis {physical_index} is already mapped. Clear its current mapping first."
            )
            return
        channel = self.channels[channel_index]
        if physical_index != channel.index:
            channel.index = physical_index
            channel.processor.calibration = Calibration()
            channel.processor.output = None
            self.history.clear()
        label = CHANNELS[channel_index]
        self.notice = (
            f"{label} cleared."
            if physical_index is None
            else f"{label} mapped to axis {physical_index}."
        )

    def learn(self, channel_index: int) -> None:
        if self.learning is not None:
            self.learning = None
            self.notice = "Axis detection cancelled."
        elif self.frame is not None and self.frame.axes:
            self.learning = (channel_index, self.frame.axes)
            self.notice = f"Move only the desired {CHANNELS[channel_index].lower()} axis now."

    def set_center(self, channel_index: int) -> None:
        channel = self.channels[channel_index]
        if channel.index is None or self.frame is None:
            return
        center = self.frame.axes[channel.index]
        old = channel.processor.calibration
        if center - old.minimum < 0.05 or old.maximum - center < 0.05:
            self.notice = "Center is too close to a travel limit. Release the stick and try again."
            return
        channel.processor.calibration = replace(old, center=center)
        channel.processor.output = None
        self.history.clear()
        self.notice = f"{CHANNELS[channel_index]} center captured at {center:+.4f}."

    def capture_travel(self, channel_index: int) -> None:
        channel = self.channels[channel_index]
        if channel.index is None or self.frame is None:
            return
        if self.travel is None:
            self.travel = TravelCapture.start(self.frame.axes)
            self.notice = "Sweep this axis fully in both directions, then click Save travel."
            return
        calibration = self.travel.calibration_for(
            channel.index, channel.processor.calibration.center
        )
        self.travel = None
        if calibration is None:
            self.notice = "Travel needs at least 0.05 raw units on both sides of center. Try again."
            return
        channel.processor.calibration = calibration
        channel.processor.output = None
        self.history.clear()
        self.notice = f"{CHANNELS[channel_index]} travel saved."

    def adjust(self, channel_index: int, **changes: float | bool) -> None:
        processor = self.channels[channel_index].processor
        processor.response = replace(processor.response, **changes)
        processor.output = None
        self.history.clear()

    def static_value(self, channel_index: int, raw: float) -> float:
        processor = self.channels[channel_index].processor
        return shape(normalize(raw, processor.calibration), processor.response)

    def start_recording(self, now_ns: int, *, simulated_demo: bool) -> None:
        self.start_ns = now_ns
        self.capture = Capture.start(
            self.protocol,
            self.rate,
            {
                "device": asdict(self.device),
                "simulated_demo": simulated_demo and self.device.instance_id == SIMULATOR,
                "axes": {
                    name: {
                        "index": channel.index,
                        "calibration": asdict(channel.processor.calibration),
                        "response": asdict(channel.processor.response),
                    }
                    for name, channel in zip(CHANNELS, self.channels, strict=True)
                },
            },
        )
        self.notice = "Recording. Follow the selected test instructions."

    def stop_recording(self, reason: str = "complete") -> None:
        if self.capture is None:
            return
        capture, self.capture = self.capture, None
        capture.result = reason
        if not capture.samples:
            self.notice = f"No samples captured ({reason})."
            return
        self.completed = (capture, capture.summary())
        self.notice = f"Recording stopped ({reason}). CSV and JSON export ready."
