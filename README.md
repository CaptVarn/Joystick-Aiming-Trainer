# Wraith Flight Trainer

Wraith Flight Trainer is a standalone desktop tool for Star Citizen joystick aiming practice. It includes joystick diagnostics, calibration, response tuning, local diagnostic recording, and four rotational aiming drills. The trainer operates independently of Star Citizen.

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

## Precision training

1. In **Diagnostics**, select your stick, then map and center **Pitch** and **Yaw**. On a stick you have already checked, set the response curve and deadzone you want to practice with. The simulator comes mapped and works with **A / D** (yaw left/right), **W / S** (pitch down/up), and **Shift** (fine input).
2. Click **Training**. Select a drill and adjust its settings. If a required mapping is missing, the setup screen tells you which one to add. Switch between training and diagnostics in the same run to keep your device's mappings and response settings.
3. Click **Start round**. The reticle stays at the center as the view turns. Keep the target inside the reticle tolerance until the hold completes, or stay with the moving target for the full tracking round. The red edge marker points toward a target outside the view.
4. Review the scores after time expires, the target goal is reached, or you end the round. Space starts or ends a round, and Escape returns to diagnostics. Losing focus or disconnecting the active stick ends the round and leaves its current scores visible.

| Drill | What to practice | Controls |
| --- | --- | --- |
| Micro-correction | Acquire and hold small, stationary targets near your current aim. | Round length, radius, displacement, hold, and interval. |
| Continuous tracking | Follow a moving target. | Horizontal, vertical, diagonal, circle, sinusoidal, figure eight, or smooth random path. Set angular radius, path displacement, speed limit, and speed ramp. |
| Axis isolation | Practice pitch alone, yaw alone, or both. Map both to measure input on the locked axis. | Same target settings as micro-correction, plus active axes. |
| Target acquisition | Acquire a fixed number of stationary targets at wider offsets. | Target count and optional joystick-button confirmation. Press the selected button after the HUD prompts you. In the simulator, buttons 0–3 are Z, X, C, and V. |

The camera uses a 120 Hz simulation step. The input loop feeds the same processed signals used by diagnostics, while the render loop displays the latest simulation state. For tracking, the speed setting bounds target angular speed, and the ramp changes how quickly the underlying path speed reaches that limit.

### Flight profiles

Open **Training → Flight profiles** before starting a round. Browse the presets or edit the model, rates, and vertical field of view. **Generic assisted** is the default. It accelerates toward the commanded rate and continues rotating briefly after you center the stick, while it brakes to zero. **Phase 2 direct** reproduces instant rate changes with the previous 45°/s pitch and yaw caps and 38° vertical field of view.

- Each axis has a rate cap in degrees per second and acceleration and braking limits in degrees per second squared. When you reverse, the model brakes to zero before accelerating in the new direction.
- The command exponent shapes the processed stick input before it sets the desired rate. An exponent of 1 preserves the Diagnostics response. The optional acceleration curve softens the acceleration available for partial deflections. A value of 1 uses the same acceleration limit across the axis.
- Enable **Roll** if you have mapped it in Diagnostics. Roll banks the view during drills with both pitch and yaw active. Pitch-only and yaw-only drills keep the other axes locked. Angular error measures the direction to the target and is independent of bank and FOV.
- **Save JSON** creates a separate file in the displayed profile folder. On Windows, the default is `%USERPROFILE%\.wraith-flight-trainer\profiles`. To import, place a JSON profile in that folder, select **Refresh**, browse to the file, and select **Load JSON**. Use `--profile-dir` to choose a different folder or `--profile` to start with a particular JSON file.
- For a custom profile, edit a preset and export it, then change the `name` and any source fields in the JSON. Schema 1 uses `rate`, `acceleration`, and `braking` under `pitch`, `yaw`, and `roll`. `acceleration_curve` and `command_exponent` are optional and default to 1.

#### Ship data

The four ship presets use the unboosted **Pitch / Yaw / Roll** values from the April 27, 2026 SPViewer snapshot. Each value also matches the corresponding Flight Controller entry in that snapshot. The snapshot does not identify a game patch. Acceleration, braking, field of view, and response shaping use trainer defaults. [Pinned SPViewer snapshot](https://github.com/TheRealWiseWolfHolo/StarCitizen-Info/blob/7bc6c0652cd0e8736c1b1494317a64610220ca6d/docs/ship-details.json)

| Ship | Pitch | Yaw | Roll | Source |
| --- | ---: | ---: | ---: | --- |
| Aegis Gladius | 68°/s | 52°/s | 200°/s | [SPViewer](https://www.spviewer.eu/performance?ship=aegs_gladius) |
| Anvil Arrow | 75°/s | 57°/s | 205°/s | [SPViewer](https://www.spviewer.eu/performance?ship=anvl_arrow) |
| Anvil F8C Lightning | 38°/s | 35°/s | 140°/s | [SPViewer](https://www.spviewer.eu/performance?ship=anvl_lightning_f8c) |
| Anvil F7C-M Super Hornet Mk I | 53°/s | 42°/s | 145°/s | [SPViewer](https://www.spviewer.eu/performance?ship=anvl_hornet_f7cm) |

### Training scoring

- **On target** is the fraction of scored ticks within the target's angular radius. Time on target is the number of those ticks divided by 120. Gaps between targets are excluded.
- **Angular error** is the angle between camera forward and the direction to the target. The HUD reports current, mean, root-mean-square, and maximum error in degrees.
- **Overshoots** count horizontal or vertical crossings of the target center that leave a band of one-quarter of the target radius, with a 0.12° minimum. **Corrections** count processed input direction reversals that cross the ±0.04 command thresholds on an active axis.
- **Acquisition** time starts at target appearance and ends after the continuous hold and any required confirmation. **Settling** time runs from the first entry into tolerance to the start of the successful hold.
- **Off-axis input RMS** measures the unused axis's processed input during single-axis practice. It is available when that axis is mapped. **Input change RMS** in tracking measures the RMS per-second change of the two-axis processed command vector on simulation ticks.

Training scores are displayed for the current round. Diagnostic CSV and JSON recording remains available in **Diagnostics**. Persistent training history is later-phase work.

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

Automated checks cover simulated desktop startup, recording and export, mocked hotplug and disconnect, calibration, response math, and diagnostic calculations. They also cover camera projection, fixed-step scoring, tracking path speed, isolation, hold timing, and button confirmation. To check Phase 2 on physical hardware, open **Training** with your VKB mappings, verify rotation direction in Axis isolation, then complete a Micro-correction hold and follow a moving target in Continuous tracking.

To check Phase 3 on the VKB, keep the drill and Diagnostics settings fixed. Run a yaw-only round with **Phase 2 direct**, then repeat with **Generic assisted** and compare stopping behavior. With assisted flight, the yaw rate shown in the HUD should taper to zero after centering.
