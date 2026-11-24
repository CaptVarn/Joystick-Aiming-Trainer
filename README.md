# Wraith Flight Trainer

Wraith Flight Trainer is a standalone desktop tool for examining joystick input used in Star Citizen aiming practice. Phase 1 provides joystick diagnostics, calibration, response tuning, and local recording. The trainer operates independently of Star Citizen.

## Install and run

Clone or download the full repository and extract it before running `main.py`. Use Python 3.12 or newer. Python 3.12 is the version used for the Phase 1 verification.

On Windows, open PowerShell in the repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe main.py
```

On Linux or macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python main.py
```

Use the same interpreter for installation and launch. If you see a missing-module error when running from an IDE, select the repository's `.venv` interpreter. With the virtual environment active, `wraith-trainer` also launches the app. Add `--simulate` to start with the virtual stick, `--sample-rate 120` to set the requested poll rate (30–240 Hz), or `--export-dir recordings` to select a local export folder. Use F11 or `--fullscreen` for fullscreen.

### Fix a `pkgutil.ImpImporter` startup error on Windows

If the traceback goes through Pygame and `pkg_resources`, an older version of setuptools in your virtual environment is trying to use an API that Python 3.12 removed. From PowerShell in the repository folder, upgrade setuptools in that environment and rerun the app:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "setuptools>=70"
.\.venv\Scripts\python.exe main.py --simulate
```

If you installed from a GitHub ZIP, get source updates by downloading and extracting a new ZIP to a separate folder. Create a new virtual environment there using the Windows install steps above.

## Run a diagnostic

1. Connect a joystick before launching or while the dashboard is open. Use the arrows in **Input Device** to switch between devices. The physical input panel shows the SDL GUID, input counts, and the axis values reported by SDL.
2. Select **Pitch**, **Yaw**, or **Roll** in **Axis configuration**. Choose **Detect movement**, then move only the intended axis. Detection picks the largest deviation when an axis crosses 0.22 raw units. With a VKB Gladiator NXT, push or pull for pitch and twist for yaw. Use the mapping arrows to select an unused physical axis directly. Clear an existing assignment before moving it to another channel.
3. Release the joystick and click **Set center**. Click **Capture travel**, sweep that axis fully in both directions, and click **Save travel**. Repeat for each mapped axis. Use Escape to cancel detection or travel capture. Axis settings are kept for each connected device during the current run.
4. Set the inner and outer deadzones, response exponent, sensitivity, output limit, smoothing, and inversion as needed. An exponent of 1 gives a linear response before the other settings. The live graph shows the raw, normalized, and processed signals for the selected channel. The curve shows the steady-state output for each raw input, with the current raw position marked.
5. Use the test selector to choose **Center hold**, **Micro yaw**, **Slow twist**, **Yaw reversal**, **Deflection hold**, **Return to center**, **Pitch isolation**, or **Yaw isolation**. Click **Record test** or press Space. For movement tests, keep the stick at rest for at least half a second before beginning. Stop with the same control. Captures are limited to five minutes.
6. Read the completed recording's sample count, observed sample rate, and selected channel metrics. Click **Export CSV + JSON** to write both files in a capture folder under `diagnostic_exports/` by default. Export before starting another recording if you want to retain the current one. A device disconnect ends the capture, keeps captured samples available for export, and switches the app to simulated input.

### Simulated joystick

| Key | Input |
| --- | --- |
| W / S | Negative / positive pitch |
| A / D | Negative / positive yaw |
| Q / E | Negative / positive roll |
| Shift with an axis key | Lower commanded deflection |
| Z / X / C / V | Buttons 0–3 |
| Arrow keys | Hat |

Use **Demo on** to generate continuous movement for the live graphs. Turn the demo off before trying to measure a stationary baseline. The simulator includes a small illustrative yaw-onset step and center variation.

### Physical VKB verification

With the Gladiator NXT centered, record 10 seconds of **Center hold** and export it. Next, record several gentle twists in **Micro yaw**, beginning from a released stick. Compare the raw onset deflection and initial jump with the processed graph at different deadzones and response exponents. Run **Pitch isolation** and **Yaw isolation** to see whether either motion produces an unintended signal on the other axis. Press several joystick buttons, move the hat, and unplug the joystick during a short recording to check the device status and interrupted export.

Record the spring and mounting details separately when comparing exports. Use similar movement speed, requested sample rate, and test length across captures. The reported jumps and drift are properties of the sampled SDL signal. Mechanical force and friction require separate measurements.

## Diagnostic definitions

The app timestamps each poll using Python's monotonic performance counter. `elapsed_ns` is nanoseconds since the recording started. Effective rate is `(sample count − 1) / (last sample time − first sample time)`, in hertz. Polling and 60 Hz drawing use separate deadlines on the desktop event loop. Missed poll slots are skipped. An effective poll rate measures the application and can differ from the joystick's hardware report rate.

Raw values are the signed SDL axis samples, normally in `[-1, 1]`. Normalization subtracts the captured center and divides by the calibrated travel on the corresponding side, then clips to `[-1, 1]`. For normalized input `x`, inner deadzone `i`, and outer deadzone `o`, the curve magnitude is `clamp((abs(x) − i) / (1 − i − o), 0, 1)`. The app raises this magnitude to the response exponent, applies sensitivity, and caps the result at the output limit. It then restores the sign with optional inversion. Smoothing uses a first-order filter with weight `1 − exp(−elapsed / time_constant)` per poll. The plotted response curve omits smoothing because it describes the steady-state mapping.

| Metric | Calculation |
| --- | --- |
| Baseline | Median raw value in the first 0.5 seconds of sampled input. |
| Center spread | Population standard deviation. Uses the entire center-hold recording or the initial baseline window for a movement test. |
| Center drift | Median of the second half minus the median of the first half of that same window. |
| Center jitter | RMS of differences between successive samples in that window. |
| Initial jump | Absolute raw change from the preceding sample at the first armed crossing of 0.02 raw units from baseline. An axis is armed within 0.01 units of baseline. |
| Onset deflection | Absolute deviation from baseline at that crossing. |
| Minimum observed step | Smallest post-baseline sample change larger than both 0.001 and the largest baseline step, with the resulting sample outside the 0.01 rest band. This is a recorded step, and depends on polling and test motion. |
| Velocity and acceleration | RMS of successive raw differences divided by sample intervals. Acceleration uses successive velocities divided by the separation of their interval midpoints. Units are raw axis units per second and per second squared. |
| Reversal | Opposite-sign movement after reaching the 0.02 threshold. Timing starts at entry below the movement threshold, or the preceding sample for a direct crossing. |
| Return to center | First sample back within the 0.01 rest band after a movement. The reported RMS is the residual from baseline across those events. |
| Axis interference | During isolation tests, RMS deviation from baseline on each secondary mapped axis while the primary axis is at least 0.02 raw units from baseline after the baseline window. |

A missing metric means there were too few samples or no qualifying event. JSON includes UTC start time, device and axis configuration, the summary, and all samples. CSV contains the same sample columns, with the capture metadata and summary as JSON in its first data row. Raw channels are indexed by the device's reported order. Normalized and processed channels are ordered pitch, yaw, and roll. An unmapped channel is null in JSON and blank in CSV.

## Development checks

Run these commands with the virtual environment active:

```sh
python -m pip install -e '.[dev]'
python -m pytest
ruff check .
ruff format --check .
```

The Phase 1 checkpoint covers simulated desktop startup, recording and export, mocked hotplug and disconnect, calibration, response math, and diagnostic calculations. Physical hardware verification is pending. Flight training, ship physics, persistent session history, and Windows executable packaging are later phases.
