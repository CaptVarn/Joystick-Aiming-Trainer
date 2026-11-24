# Changelog

## 0.3.0

- Added assisted rotational dynamics with independent pitch, yaw, and roll rate limits, acceleration, braking, and response settings.
- Added adjustable vertical field of view, optional roll, and a direct-response preset for Phase 2 comparisons.
- Added a flight profile editor with JSON import and export, and four Star Citizen presets with unboosted rate limits from a dated SPViewer snapshot.

## 0.2.0

- Added rotational aiming with a fixed reticle and four training drills.
- Added configurable targets, seven tracking paths, optional button confirmation, and live round scoring.
- Reused diagnostics mapping, calibration, response curves, and simulated input during training.
- Fixed `main.py` to find trainer sources in a fresh checkout and show setup instructions when dependencies are missing.

## 0.1.0

- Added the Wraith Flight Trainer desktop diagnostics dashboard.
- Added SDL joystick discovery and selection, axis mapping and calibration, live raw and processed plots, and simulated input.
- Added timed diagnostic protocols, center and motion metrics, and CSV and JSON exports.
- Added automated tests and Windows setup and hardware testing instructions.
