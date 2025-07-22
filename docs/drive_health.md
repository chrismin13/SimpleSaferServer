# Drive Health

The Drive Health page allows you to check the health of your storage drive using SMART data and a machine learning model.

## Features
- **Error/Warning Alerts**: Shown if SMART data is missing or the model is not loaded.
- **Missing Attributes**: Lists any SMART attributes not available for the drive, with a warning that accuracy may be affected.
- **Prediction Result**: Shows if a failure is predicted, with probability percentage.
- **Run Health Check**: Button to run a new health check (submits the form).
- **SMART Data Table**: Lists all SMART attributes, descriptions, raw values, and status (available/default).
- **Tooltips**: Hover over info icons for detailed attribute descriptions.
- **Download Telemetry**: Button to download SMART telemetry data.
- **Send Telemetry**: Button to email telemetry data.

## UI Details
- Inline feedback for errors and missing data.
- Table with attribute, description, value, and status.
- Spinners and tooltips for user feedback.

---

This page helps monitor drive health and predict failures using SMART data. 