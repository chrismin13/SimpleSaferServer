# Drive Health

The Drive Health page combines two views of the configured backup drive:

- SMART data plus the local machine-learning failure prediction
- HDSentinel health and performance reporting

## Features
- **Run Health Check**: Runs a manual SMART and HDSentinel refresh from the page.
- **Prediction Result**: Shows whether the SMART model predicts failure, with probability percentage.
- **Missing Attributes**: Lists SMART attributes that fell back to defaults.
- **HDSentinel Status**: Shows install state, device, model, serial, health, performance, temperature, size, and last checked time.
- **HDSentinel Settings**: Lets users enable or disable HDSentinel monitoring and toggle health-change alerts.
- **SMART Data Table**: Lists SMART attributes, descriptions, raw values, and status.
- **Download Telemetry**: Downloads the SMART telemetry CSV.

## Alerting
- HDSentinel alerts only trigger on health changes between scheduled checks.
- Temperature is displayed but does not currently trigger alerts.

---

This page is the main place to inspect the backup drive's current SMART and HDSentinel health data.
