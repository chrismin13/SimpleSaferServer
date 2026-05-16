import contextlib
import csv
import json
import logging
import re
import shutil
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

from simple_safer_server.adapters.drive_health_commands import (
    DriveHealthCommandAdapter,
    TimeoutExpired,
)
from simple_safer_server.services.alert_notifications import AlertNotifier
from simple_safer_server.services.file_persistence import atomic_write_json
from simple_safer_server.services.runtime import get_runtime

LOGGER = logging.getLogger(__name__)
NUMPY_X86_V2_PREDICTION_UNAVAILABLE_MESSAGE = (
    "SMART prediction is unavailable because this machine's CPU cannot run "
    "the installed NumPy package. SMART and HDSentinel checks can still run."
)
GENERAL_PREDICTION_UNAVAILABLE_MESSAGE = (
    "SMART prediction is unavailable because the prediction dependencies could not be loaded. "
    "SMART and HDSentinel checks can still run."
)

try:
    import joblib
    import pandas as pd
    from xgboost import XGBClassifier

    PREDICTION_DEPENDENCIES_AVAILABLE = True
    PREDICTION_UNAVAILABLE_MESSAGE = None
except Exception as exc:
    # Native extension loaders can raise RuntimeError or OSError before Python
    # gets an ImportError. Keep SMART/HDSentinel usable when prediction is the
    # only unavailable part of Drive Health.
    pd = None
    XGBClassifier = None
    joblib = None
    PREDICTION_DEPENDENCIES_AVAILABLE = False
    if "X86_V2" in str(exc):
        PREDICTION_UNAVAILABLE_MESSAGE = NUMPY_X86_V2_PREDICTION_UNAVAILABLE_MESSAGE
    else:
        PREDICTION_UNAVAILABLE_MESSAGE = GENERAL_PREDICTION_UNAVAILABLE_MESSAGE
    LOGGER.warning("SMART prediction dependencies could not be loaded: %s", exc)


DRIVE_HEALTH_TIMEOUT_MESSAGE = (
    "The drive health check timed out before the device responded. "
    "A sleeping USB drive, adapter, or dock may need another check after it spins up."
)
drive_health_command_adapter = DriveHealthCommandAdapter()
SMARTCTL_JSON_UPGRADE_MESSAGE = (
    "The installed smartctl version does not support JSON output required for SMART-based health prediction. "
    "Upgrade smartmontools on this machine to enable SMART prediction."
)

SMART_FIELDS = {
    "smart_1_raw": {
        "default": 0.0,
        "name": "Read Error Rate",
        "description": "The rate of hardware read errors that occurred when reading data from the disk surface. A non-zero value may indicate problems with the disk surface or read/write heads.",
        "short_desc": "Rate of hardware read errors",
    },
    "smart_3_raw": {
        "default": 0.0,
        "name": "Spin-Up Time",
        "description": "Average time (in milliseconds) for the disk to spin up from a stopped state to full speed. Higher values may indicate mechanical problems.",
        "short_desc": "Time to reach full speed",
    },
    "smart_4_raw": {
        "default": 0.0,
        "name": "Start/Stop Count",
        "description": "The number of times the disk has been powered on and off. This is a lifetime counter that increases with each power cycle.",
        "short_desc": "Number of power cycles",
    },
    "smart_5_raw": {
        "default": 0.0,
        "name": "Reallocated Sectors Count",
        "description": "The number of bad sectors that have been found and remapped. A non-zero value indicates the disk has had some problems, and the value should not increase over time.",
        "short_desc": "Number of remapped sectors",
    },
    "smart_7_raw": {
        "default": 0.0,
        "name": "Seek Error Rate",
        "description": "The rate of seek errors that occur when the drive's heads try to position themselves over a track. Higher values may indicate mechanical problems.",
        "short_desc": "Rate of positioning errors",
    },
    "smart_10_raw": {
        "default": 0.0,
        "name": "Spin Retry Count",
        "description": "The number of times the drive had to retry spinning up. A non-zero value indicates problems with the drive's motor or power supply.",
        "short_desc": "Number of spin-up retries",
    },
    "smart_192_raw": {
        "default": 0.0,
        "name": "Emergency Retract Count",
        "description": "The number of times the drive's heads were retracted due to power loss or other emergency conditions. High values may indicate power problems.",
        "short_desc": "Number of emergency head retractions",
    },
    "smart_193_raw": {
        "default": 0.0,
        "name": "Load Cycle Count",
        "description": "The number of times the drive's heads have been loaded and unloaded. This is a lifetime counter that increases with each load/unload cycle.",
        "short_desc": "Number of head load/unload cycles",
    },
    "smart_194_raw": {
        "default": 25.0,
        "name": "Temperature",
        "description": "The current temperature of the drive in Celsius. Normal operating temperature is typically between 30-50°C. Higher temperatures may indicate cooling problems.",
        "short_desc": "Current drive temperature",
    },
    "smart_197_raw": {
        "default": 0.0,
        "name": "Current Pending Sectors",
        "description": "The number of sectors that are waiting to be remapped. A non-zero value indicates the drive has found bad sectors that it hasn't been able to remap yet.",
        "short_desc": "Number of sectors waiting to be remapped",
    },
    "smart_198_raw": {
        "default": 0.0,
        "name": "Offline Uncorrectable",
        "description": "The number of sectors that could not be corrected during offline testing. A non-zero value indicates the drive has sectors that are permanently damaged.",
        "short_desc": "Number of uncorrectable sectors",
    },
}

HDSENTINEL_SECTION = "hdsentinel"
HDSENTINEL_DEFAULTS = {
    "enabled": True,
    "health_change_alert": True,
}


class DriveHealthSummaryService:
    """Keep the dashboard health summary in process memory only."""

    def __init__(self):
        self._lock = threading.Lock()
        self._summary = self._empty_summary()
        self._publish_seq = 0

    def _empty_summary(self):
        return {
            "status": "unknown",
            "source": "memory",
            "checked_at": None,
            "probability": None,
            "temperature": None,
            "hdsentinel_health": None,
            "hdsentinel_performance": None,
            "detail": "No check yet",
            "error": None,
        }

    def get_summary(self):
        # Return a copy so callers cannot mutate the last-known state in place.
        with self._lock:
            return self._public_summary(self._summary)

    def _public_summary(self, summary):
        return {key: value for key, value in summary.items() if not key.startswith("_")}

    def publish(self, summary):
        latest = self._empty_summary()
        for key in latest:
            if key in summary:
                latest[key] = summary[key]
        with self._lock:
            existing_checked_at = _summary_timestamp(self._summary)
            incoming_checked_at = _summary_timestamp(latest)
            incoming_seq = self._publish_seq + 1
            existing_seq = self._summary.get("_publish_seq", 0)
            if (
                existing_checked_at is not None
                and incoming_checked_at is not None
                and (incoming_checked_at, incoming_seq) <= (existing_checked_at, existing_seq)
            ):
                return self._public_summary(self._summary)
            self._publish_seq = incoming_seq
            latest["_publish_seq"] = self._publish_seq
            self._summary = latest
        return self._public_summary(latest)


def _summary_timestamp(summary):
    checked_at = summary.get("checked_at")
    if not checked_at:
        return None
    try:
        return datetime.fromisoformat(checked_at)
    except (TypeError, ValueError):
        return None


def build_drive_health_summary(
    config_manager,
    system_utils,
    runtime=None,
    *,
    collect_hdsentinel=True,
):
    """Run a live probe and convert it into the compact dashboard contract."""
    runtime = runtime or get_runtime()
    checked_at = datetime.now().isoformat()
    summary = {
        "status": "unknown",
        "source": "live",
        "checked_at": checked_at,
        "probability": None,
        "temperature": None,
        "hdsentinel_health": None,
        "hdsentinel_performance": None,
        "detail": "Drive health data is not available.",
        "error": None,
    }

    smart, _missing_attrs, smart_error = get_smart_attributes(
        config_manager,
        system_utils,
        runtime=runtime,
    )
    if smart is not None:
        probability = predict_failure_probability(smart, runtime=runtime)
        if probability is not None:
            summary["probability"] = probability
            summary["temperature"] = smart.get("smart_194_raw")
            summary["status"] = (
                "good" if probability < get_optimal_threshold(runtime) else "warning"
            )
            summary["detail"] = "SMART prediction completed."
        else:
            summary["detail"] = get_prediction_unavailable_message()
            summary["error"] = summary["detail"]
    else:
        # Timeouts and missing data are operationally common with sleeping USB
        # drives, so the dashboard keeps them neutral instead of alarming users.
        summary["detail"] = smart_error or "Could not retrieve SMART data."
        summary["error"] = smart_error

    if collect_hdsentinel and get_hdsentinel_settings(config_manager)["enabled"]:
        hdsentinel_snapshot = collect_hdsentinel_snapshot(
            config_manager,
            system_utils,
            runtime=runtime,
        )
        if hdsentinel_snapshot and hdsentinel_snapshot.get("available"):
            summary["hdsentinel_health"] = hdsentinel_snapshot.get("health_pct")
            summary["hdsentinel_performance"] = hdsentinel_snapshot.get("performance_pct")
            if summary["temperature"] is None:
                summary["temperature"] = hdsentinel_snapshot.get("temperature_c")

    return summary


def get_fake_smart_attributes():
    attrs = {field: info["default"] for field, info in SMART_FIELDS.items()}
    attrs.update(
        {
            "smart_1_raw": 0.0,
            "smart_3_raw": 1420.0,
            "smart_4_raw": 321.0,
            "smart_5_raw": 0.0,
            "smart_7_raw": 0.0,
            "smart_10_raw": 0.0,
            "smart_192_raw": 2.0,
            "smart_193_raw": 145.0,
            "smart_194_raw": 31.0,
            "smart_197_raw": 0.0,
            "smart_198_raw": 0.0,
        }
    )
    return attrs, []


def get_smartctl_json_support():
    # Do not cache this result across the whole process. Operators can install
    # or upgrade smartmontools while the web service keeps running, and a stale
    # negative result would keep blocking SMART reads until restart.
    if not shutil.which("smartctl"):
        return False, "smartctl is not installed on this machine."

    result = drive_health_command_adapter.smartctl_help()
    help_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    if "-j" in help_output or "--json" in help_output:
        return True, None
    return False, SMARTCTL_JSON_UPGRADE_MESSAGE


@lru_cache(maxsize=1)
def _load_model_and_threshold(model_path: str, threshold_path: str):
    if not PREDICTION_DEPENDENCIES_AVAILABLE:
        return None, 0.5

    model = XGBClassifier()
    try:
        model.load_model(model_path)
        threshold = float(joblib.load(threshold_path))
        return model, threshold
    except Exception as exc:
        LOGGER.warning("Failed to load drive health model: %s", exc)
        return None, 0.5


def get_prediction_unavailable_message():
    return PREDICTION_UNAVAILABLE_MESSAGE or GENERAL_PREDICTION_UNAVAILABLE_MESSAGE


def get_optimal_threshold(runtime=None):
    if not PREDICTION_DEPENDENCIES_AVAILABLE:
        return 0.5

    runtime = runtime or get_runtime()
    _, threshold = _load_model_and_threshold(
        str(runtime.model_dir / "xgb_model.json"),
        str(runtime.model_dir / "optimal_threshold_xgb.pkl"),
    )
    return threshold


def predict_failure_probability(smart, runtime=None):
    if not PREDICTION_DEPENDENCIES_AVAILABLE:
        return None

    runtime = runtime or get_runtime()
    model, _ = _load_model_and_threshold(
        str(runtime.model_dir / "xgb_model.json"),
        str(runtime.model_dir / "optimal_threshold_xgb.pkl"),
    )

    if model is not None and pd is not None:
        df = pd.DataFrame([smart])
        probabilities = model.predict_proba(df)
        return float(probabilities[0, 1])

    if runtime.is_fake:
        temperature = float(smart.get("smart_194_raw", 30.0) or 30.0)
        reallocated = float(smart.get("smart_5_raw", 0.0) or 0.0)
        pending = float(smart.get("smart_197_raw", 0.0) or 0.0)
        probability = 0.03 + min(0.25, reallocated * 0.02) + min(0.25, pending * 0.05)
        if temperature > 40:
            probability += min(0.15, (temperature - 40) * 0.01)
        return min(0.95, probability)

    return None


def resolve_backup_partition_device(config_manager, runtime=None):
    runtime = runtime or get_runtime()
    if runtime.is_fake:
        return "/dev/fakebackup1", None

    uuid = config_manager.get_value("backup", "uuid", None)
    if not uuid:
        return None, "No backup drive UUID configured."

    try:
        blkid_out = drive_health_command_adapter.find_device_by_uuid(uuid)
    except TimeoutExpired:
        return None, (
            "The backup drive lookup timed out before the device responded. "
            "A sleeping USB drive, adapter, or dock may need another check after it spins up."
        )
    partition_device = blkid_out.stdout.strip()
    if not partition_device:
        return None, f"Backup drive with UUID {uuid} was not found."

    return partition_device, None


def resolve_backup_parent_device(config_manager, system_utils, runtime=None):
    runtime = runtime or get_runtime()
    if runtime.is_fake:
        return "/dev/fakebackup", "/dev/fakebackup1", None

    partition_device, error = resolve_backup_partition_device(config_manager, runtime=runtime)
    if error:
        return None, None, error

    parent_device = system_utils.get_parent_device(partition_device)
    if not parent_device:
        return None, partition_device, f"Could not determine parent device for {partition_device}."

    return parent_device, partition_device, None


def get_smart_attributes(config_manager, system_utils, device=None, runtime=None):
    runtime = runtime or get_runtime()
    if runtime.is_fake:
        attrs, missing = get_fake_smart_attributes()
        return attrs, missing, None

    try:
        smartctl_json_supported, smartctl_json_error = get_smartctl_json_support()
        if not smartctl_json_supported:
            LOGGER.warning(smartctl_json_error)
            return None, None, smartctl_json_error

        if device is None:
            device, _, error = resolve_backup_parent_device(
                config_manager, system_utils, runtime=runtime
            )
            if error:
                LOGGER.warning(error)
                return None, None, error

        command = ["smartctl", "-A", "-j", device]

        result = drive_health_command_adapter.smartctl_attributes(command)
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        if not stdout:
            error_message = stderr or "smartctl returned no JSON output"
            LOGGER.warning("Failed to retrieve SMART JSON: %s", error_message)
            return None, None, error_message

        data = json.loads(stdout)

        smart_table = data.get("ata_smart_attributes", {}).get("table")
        if not smart_table:
            # Some smartctl failures still emit valid JSON, but without the ATA
            # SMART table we need for prediction. Treat that as a read failure
            # instead of silently falling back to model defaults.
            messages = data.get("smartctl", {}).get("messages") or []
            first_message = messages[0].get("string") if messages else None
            error_message = (
                stderr or first_message or "smartctl could not retrieve SMART attributes"
            )
            LOGGER.warning("Failed to retrieve SMART JSON: %s", error_message)
            return None, None, error_message

        attrs = {field: info["default"] for field, info in SMART_FIELDS.items()}
        missing_attrs = set(SMART_FIELDS.keys())

        for item in smart_table or []:
            field_name = f"smart_{item['id']}_raw"
            if field_name not in SMART_FIELDS:
                continue
            try:
                if field_name == "smart_194_raw":
                    attrs[field_name] = float(int(item["raw"]["value"]) & 0xFF)
                else:
                    attrs[field_name] = float(item["raw"]["value"])
                missing_attrs.remove(field_name)
            except (ValueError, KeyError, TypeError):
                LOGGER.warning("Could not parse SMART value for %s", field_name)

        return attrs, list(missing_attrs), None
    except TimeoutExpired:
        error_message = DRIVE_HEALTH_TIMEOUT_MESSAGE
        LOGGER.warning(error_message)
        return None, None, error_message
    except json.JSONDecodeError as exc:
        LOGGER.warning("Failed to parse smartctl JSON output: %s", exc)
        # We only surface the upgrade warning from the explicit capability
        # check above. If `-j` is advertised but this invocation still emits
        # malformed or plain-text output, that usually points to a device,
        # bridge, or transport problem rather than an outdated binary.
        error_message = (
            locals().get("stderr")
            or locals().get("stdout")
            or f"Failed to parse smartctl JSON output: {exc}"
        )
        return None, None, error_message
    except Exception as exc:
        LOGGER.warning("Unexpected SMART read error: %s", exc)
        return None, None, str(exc)


def append_telemetry(data_dict, prediction, runtime=None):
    if not data_dict:
        return

    runtime = runtime or get_runtime()
    telemetry_path = runtime.telemetry_path
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = telemetry_path.exists()

    with open(telemetry_path, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow([*list(SMART_FIELDS.keys()), "failure"])
        row = [data_dict.get(field, "") for field in SMART_FIELDS]
        row.append(prediction)
        writer.writerow(row)


def _parse_bool(value, default):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_hdsentinel_settings(config_manager):
    return {
        "enabled": _parse_bool(
            config_manager.get_value(HDSENTINEL_SECTION, "enabled", None),
            HDSENTINEL_DEFAULTS["enabled"],
        ),
        "health_change_alert": _parse_bool(
            config_manager.get_value(HDSENTINEL_SECTION, "health_change_alert", None),
            HDSENTINEL_DEFAULTS["health_change_alert"],
        ),
    }


def save_hdsentinel_settings(config_manager, *, enabled, health_change_alert):
    config_manager.set_value(HDSENTINEL_SECTION, "enabled", str(bool(enabled)).lower())
    config_manager.set_value(
        HDSENTINEL_SECTION,
        "health_change_alert",
        str(bool(health_change_alert)).lower(),
    )


def get_hdsentinel_binary_path(runtime=None):
    runtime = runtime or get_runtime()
    return runtime.bin_dir / "hdsentinel"


def get_hdsentinel_state_path(runtime=None):
    runtime = runtime or get_runtime()
    return runtime.data_dir / "hdsentinel_state.json"


def _write_json_atomically(path: Path, payload):
    atomic_write_json(path, payload, mode=0o644)


def load_hdsentinel_state(runtime=None):
    runtime = runtime or get_runtime()
    path = get_hdsentinel_state_path(runtime)
    if not path.exists():
        return None

    try:
        state = json.loads(path.read_text())
        return state.get("last_snapshot")
    except Exception as exc:
        LOGGER.warning("Failed to load HDSentinel state: %s", exc)
        return None


def save_hdsentinel_state(snapshot, runtime=None):
    runtime = runtime or get_runtime()
    path = get_hdsentinel_state_path(runtime)
    _write_json_atomically(path, {"last_snapshot": snapshot})


def _format_size_mb(size_mb):
    if size_mb is None:
        return None
    if size_mb >= 1024 * 1024:
        return f"{size_mb / (1024 * 1024):.2f} TB"
    if size_mb >= 1024:
        return f"{size_mb / 1024:.1f} GB"
    return f"{size_mb} MB"


def _parse_optional_int(value):
    if value in {None, "", "?", "-"}:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _format_power_on_time_from_hours(hours):
    if hours is None:
        return None
    days, remainder = divmod(hours, 24)
    if days:
        return f"{days} days, {remainder} hours"
    return f"{hours} hours"


def _extract_first_match(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _parse_power_on_hours_from_text(text):
    if not text:
        return None
    days_match = re.search(r"(\d+)\s+days?", text, flags=re.IGNORECASE)
    hours_match = re.search(r"(\d+)\s+hours?", text, flags=re.IGNORECASE)
    minutes_match = re.search(r"(\d+)\s+minutes?", text, flags=re.IGNORECASE)

    if days_match or hours_match or minutes_match:
        total_hours = 0
        if days_match:
            total_hours += int(days_match.group(1)) * 24
        if hours_match:
            total_hours += int(hours_match.group(1))
        if minutes_match and int(minutes_match.group(1)) >= 30:
            total_hours += 1
        return total_hours

    compact_match = re.search(r"(\d+)\s*hours?", text, flags=re.IGNORECASE)
    if compact_match:
        return int(compact_match.group(1))

    return None


def get_fake_hdsentinel_snapshot(config_manager=None, runtime=None):
    runtime = runtime or get_runtime()
    settings = (
        get_hdsentinel_settings(config_manager)
        if config_manager is not None
        else HDSENTINEL_DEFAULTS
    )
    return {
        "installed": True,
        "enabled": settings["enabled"],
        "health_change_alert": settings["health_change_alert"],
        "available": settings["enabled"],
        "device": "/dev/fakebackup",
        "model": "Fake Developer Backup Drive",
        "serial": "FAKE-BACKUP-0001",
        "size_mb": 953869,
        "size_text": "931.5 GB",
        "temperature_c": 31,
        "health_pct": 100,
        "performance_pct": 100,
        "power_on_hours": 612,
        "power_on_time_text": "25 days, 12 hours",
        "last_checked": datetime.now().isoformat(timespec="seconds"),
        "error": None if settings["enabled"] else "HDSentinel monitoring is disabled.",
        "binary_path": str(get_hdsentinel_binary_path(runtime)),
    }


def parse_hdsentinel_solid_output(output, device=None):
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line.startswith("/dev/"):
            continue

        parts = line.split()
        if len(parts) < 7:
            continue

        if device and parts[0] != device:
            continue

        size_mb = _parse_optional_int(parts[6])
        power_on_hours = _parse_optional_int(parts[3])
        return {
            "device": parts[0],
            "temperature_c": _parse_optional_int(parts[1]),
            "health_pct": _parse_optional_int(parts[2]),
            "power_on_hours": power_on_hours,
            "power_on_time_text": _format_power_on_time_from_hours(power_on_hours),
            "model": parts[4].replace("_", " "),
            "serial": parts[5].replace("_", " "),
            "size_mb": size_mb,
            "size_text": _format_size_mb(size_mb),
        }

    return None


def parse_hdsentinel_report(report_text):
    health_pct = _parse_optional_int(_extract_first_match([r"Health\s*:\s*(\d+)%"], report_text))
    performance_pct = _parse_optional_int(
        _extract_first_match([r"Performance\s*:\s*(\d+)%"], report_text)
    )
    temperature_c = _parse_optional_int(
        _extract_first_match([r"Temperature\s*:\s*(-?\d+)\s*(?:°|deg)?\s*C"], report_text)
    )
    power_on_time_text = _extract_first_match(
        [r"Power on time\s*:\s*(.+)$", r"Power-on time\s*:\s*(.+)$"],
        report_text,
    )
    power_on_hours = _parse_power_on_hours_from_text(power_on_time_text)

    return {
        "health_pct": health_pct,
        "performance_pct": performance_pct,
        "temperature_c": temperature_c,
        "power_on_hours": power_on_hours,
        "power_on_time_text": power_on_time_text,
        "model": _extract_first_match([r"Model ID\s*:\s*(.+)$", r"Model\s*:\s*(.+)$"], report_text),
        "serial": _extract_first_match(
            [r"Serial Number\s*:\s*(.+)$", r"Serial No\.?\s*:\s*(.+)$"],
            report_text,
        ),
        "size_text": _extract_first_match(
            [r"Size\s*:\s*(.+)$", r"Capacity\s*:\s*(.+)$"], report_text
        ),
        "interface": _extract_first_match([r"Interface\s*:\s*(.+)$"], report_text),
        "firmware": _extract_first_match(
            [r"Revision\s*:\s*(.+)$", r"Firmware Revision\s*:\s*(.+)$"], report_text
        ),
    }


def _run_hdsentinel_command(binary_path: Path, args):
    command = [str(binary_path), *args]
    return drive_health_command_adapter.hdsentinel(command)


def collect_hdsentinel_snapshot(config_manager, system_utils, runtime=None, device=None):
    runtime = runtime or get_runtime()
    settings = get_hdsentinel_settings(config_manager)
    binary_path = get_hdsentinel_binary_path(runtime)
    snapshot = {
        "installed": binary_path.exists() or runtime.is_fake,
        "enabled": settings["enabled"],
        "health_change_alert": settings["health_change_alert"],
        "available": False,
        "device": None,
        "model": None,
        "serial": None,
        "size_mb": None,
        "size_text": None,
        "temperature_c": None,
        "health_pct": None,
        "performance_pct": None,
        "power_on_hours": None,
        "power_on_time_text": None,
        "interface": None,
        "firmware": None,
        "last_checked": datetime.now().isoformat(timespec="seconds"),
        "error": None,
        "binary_path": str(binary_path),
    }

    if runtime.is_fake:
        return get_fake_hdsentinel_snapshot(config_manager=config_manager, runtime=runtime)

    if not settings["enabled"]:
        snapshot["error"] = "HDSentinel monitoring is disabled."
        return snapshot

    if not binary_path.exists():
        snapshot["error"] = f"HDSentinel binary is not installed at {binary_path}."
        return snapshot

    if device is None:
        device, _, error = resolve_backup_parent_device(
            config_manager, system_utils, runtime=runtime
        )
        if error:
            snapshot["error"] = error
            return snapshot

    try:
        solid_result = _run_hdsentinel_command(binary_path, ["-solid", "-dev", device])
    except TimeoutExpired:
        snapshot["device"] = device
        snapshot["error"] = DRIVE_HEALTH_TIMEOUT_MESSAGE
        return snapshot
    if solid_result.returncode != 0:
        stderr = (solid_result.stderr or solid_result.stdout or "").strip()
        snapshot["device"] = device
        snapshot["error"] = stderr or "HDSentinel did not return drive data."
        return snapshot

    solid_data = parse_hdsentinel_solid_output(solid_result.stdout, device=device)
    if not solid_data:
        snapshot["device"] = device
        snapshot["error"] = "HDSentinel returned output that could not be parsed."
        return snapshot

    report_text = None
    report_data = {}
    with NamedTemporaryFile(suffix=".txt", delete=False) as tmp_file:
        report_path = Path(tmp_file.name)

    try:
        try:
            report_result = _run_hdsentinel_command(
                binary_path, ["-dev", device, "-r", str(report_path)]
            )
        except TimeoutExpired:
            report_result = None
            snapshot["error"] = DRIVE_HEALTH_TIMEOUT_MESSAGE
        if report_result is not None and report_result.returncode == 0 and report_path.exists():
            report_text = report_path.read_text(errors="replace")
            report_data = parse_hdsentinel_report(report_text)
    finally:
        with contextlib.suppress(FileNotFoundError):
            report_path.unlink()

    snapshot.update(solid_data)
    for key, value in report_data.items():
        if value not in {None, ""}:
            snapshot[key] = value

    if snapshot["power_on_time_text"] is None and snapshot["power_on_hours"] is not None:
        snapshot["power_on_time_text"] = _format_power_on_time_from_hours(
            snapshot["power_on_hours"]
        )

    # HDSentinel can time out while writing the report after the quick SOLID
    # probe succeeded. Preserve that partial data as available so the dashboard
    # can show usable health fields alongside the timeout warning.
    snapshot["available"] = True
    return snapshot


def get_hdsentinel_display_snapshot(config_manager, system_utils, runtime=None):
    runtime = runtime or get_runtime()
    snapshot = load_hdsentinel_state(runtime)
    if snapshot is not None:
        return snapshot
    if runtime.is_fake:
        return get_fake_hdsentinel_snapshot(config_manager=config_manager, runtime=runtime)
    return None


def _log_and_email_alert(config_manager, runtime, title, message, *, alert_type, source):
    AlertNotifier(
        config_manager,
        runtime,
        command_adapter=drive_health_command_adapter,
        logger=LOGGER,
    ).notify(title, message, alert_type=alert_type, source=source)


def run_hdsentinel_health_monitor(config_manager, system_utils, runtime=None):
    runtime = runtime or get_runtime()
    previous_snapshot = load_hdsentinel_state(runtime)
    current_snapshot = collect_hdsentinel_snapshot(config_manager, system_utils, runtime=runtime)
    settings = get_hdsentinel_settings(config_manager)
    alert_sent = False

    previous_health = None if not previous_snapshot else previous_snapshot.get("health_pct")
    current_health = current_snapshot.get("health_pct")

    if (
        settings["enabled"]
        and settings["health_change_alert"]
        and current_snapshot.get("available")
        and previous_snapshot
        and previous_snapshot.get("available")
        and previous_health is not None
        and current_health is not None
        and current_health != previous_health
    ):
        drive_label = (
            current_snapshot.get("model") or current_snapshot.get("device") or "backup drive"
        )
        title = "HDSentinel Drive Health Changed"
        message = (
            f"HDSentinel reported a health change for {drive_label}. "
            f"Previous health: {previous_health}%. Current health: {current_health}%."
        )
        if current_snapshot.get("performance_pct") is not None:
            message += f" Current performance: {current_snapshot['performance_pct']}%."
        if current_snapshot.get("serial"):
            message += f" Serial: {current_snapshot['serial']}."
        _log_and_email_alert(
            config_manager,
            runtime,
            title,
            message,
            alert_type="warning",
            source="hdsentinel",
        )
        alert_sent = True

    save_hdsentinel_state(current_snapshot, runtime=runtime)
    return {
        "previous_snapshot": previous_snapshot,
        "snapshot": current_snapshot,
        "alert_sent": alert_sent,
    }


def run_scheduled_drive_health_check(config_manager, system_utils, runtime=None):
    runtime = runtime or get_runtime()
    mount_point = config_manager.get_value("backup", "mount_point", runtime.default_mount_point)

    if not system_utils.is_mounted(mount_point):
        title = "Drive Health Check Failed - Drive Not Mounted"
        message = f"The backup drive is not mounted at {mount_point}."
        _log_and_email_alert(
            config_manager,
            runtime,
            title,
            message,
            alert_type="error",
            source="check_health",
        )
        raise RuntimeError(message)

    device, _, error = resolve_backup_parent_device(config_manager, system_utils, runtime=runtime)
    if error:
        title = "Drive Health Check Failed - Drive Not Found"
        _log_and_email_alert(
            config_manager,
            runtime,
            title,
            error,
            alert_type="error",
            source="check_health",
        )
        raise RuntimeError(error)

    smart, missing_attrs, smart_error = get_smart_attributes(
        config_manager,
        system_utils,
        device=device,
        runtime=runtime,
    )
    if smart is None:
        hdsentinel_result = run_hdsentinel_health_monitor(
            config_manager, system_utils, runtime=runtime
        )
        if smart_error == SMARTCTL_JSON_UPGRADE_MESSAGE and hdsentinel_result.get(
            "snapshot", {}
        ).get("available"):
            LOGGER.warning(smart_error)
            return {
                "device": device,
                "smart": None,
                "missing_attrs": None,
                "probability": None,
                "prediction": None,
                "threshold": get_optimal_threshold(runtime),
                "hdsentinel": hdsentinel_result,
                "smart_warning": smart_error,
            }

        message = smart_error or f"Could not retrieve SMART data from {device}."
        LOGGER.warning("Drive health check could not retrieve SMART data: %s", message)
        _log_and_email_alert(
            config_manager,
            runtime,
            "Drive Health Check Failed - SMART Read Error",
            message,
            alert_type="error",
            source="check_health",
        )
        raise RuntimeError(message)

    probability = predict_failure_probability(smart, runtime=runtime)
    if probability is None:
        message = get_prediction_unavailable_message()
        LOGGER.warning("Scheduled Drive Health completed without prediction: %s", message)
        hdsentinel_result = run_hdsentinel_health_monitor(
            config_manager, system_utils, runtime=runtime
        )
        return {
            "device": device,
            "smart": smart,
            "missing_attrs": missing_attrs,
            "probability": None,
            "prediction": None,
            # No threshold is returned here because a threshold only has
            # operational meaning when the model produced a probability.
            "prediction_warning": message,
            "hdsentinel": hdsentinel_result,
        }

    threshold = get_optimal_threshold(runtime)
    prediction = int(probability >= threshold)
    if prediction == 1:
        _log_and_email_alert(
            config_manager,
            runtime,
            "Drive Health Warning",
            f"Drive health check predicted failure with probability {probability:.4f}. Drive: {device}.",
            alert_type="warning",
            source="check_health",
        )

    hdsentinel_result = run_hdsentinel_health_monitor(config_manager, system_utils, runtime=runtime)
    return {
        "device": device,
        "smart": smart,
        "missing_attrs": missing_attrs,
        "probability": probability,
        "prediction": prediction,
        "threshold": threshold,
        "hdsentinel": hdsentinel_result,
    }
