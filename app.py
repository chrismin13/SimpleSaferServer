# sudo apt install python3-flask python3-psutil python3-xgboost python3-joblib python3-pandas smartmontools python3-sklearn python3-flask-socketio
from flask import Flask, render_template, jsonify, request, abort, url_for, redirect, send_file, session, flash, current_app, make_response, send_from_directory
import subprocess
import psutil
from datetime import datetime, timedelta
import json
import os
import csv
import threading
from config_manager import ConfigManager
from setup_wizard import setup, install_systemd_tasks
import logging
from user_manager import UserManager, login_required, admin_required
from flask_socketio import SocketIO
from logging.handlers import RotatingFileHandler
import sys
import time
from system_utils import SystemUtils
from smb_manager import SMBManager
from tempfile import NamedTemporaryFile
from runtime import get_runtime, get_fake_state

try:
    import pandas as pd
    from xgboost import XGBClassifier
    import joblib
except ModuleNotFoundError:
    pd = None
    XGBClassifier = None
    joblib = None

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for session management
socketio = SocketIO(app) 
runtime = get_runtime()
fake_state = get_fake_state() if runtime.is_fake else None
user_manager = UserManager(runtime=runtime)

system_utils = SystemUtils(runtime=runtime)
smb_manager = SMBManager(runtime=runtime)

# Configure logging
log_dir = str(runtime.logs_dir)
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'app.log')

handler = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)
app.logger.info('SimpleSaferServer startup')

# Initialize configuration
config_manager = ConfigManager(runtime=runtime)

# Register setup blueprint
app.register_blueprint(setup)

# Paths for the XGBoost model and threshold
MODEL_PATH = str(runtime.model_dir / "xgb_model.json")
THRESHOLD_PATH = str(runtime.model_dir / "optimal_threshold_xgb.pkl")

# Load model and threshold once on startup
model = None
optimal_threshold = 0.5
if XGBClassifier is not None and joblib is not None:
    model = XGBClassifier()
    try:
        model.load_model(MODEL_PATH)
        optimal_threshold = joblib.load(THRESHOLD_PATH)
    except Exception as exc:
        print(f"Failed to load model: {exc}")
        model = None
        optimal_threshold = 0.5


def predict_failure_probability(smart):
    if model is not None and pd is not None:
        df = pd.DataFrame([smart])
        probabilities = model.predict_proba(df)
        return float(probabilities[0, 1])

    if runtime.is_fake:
        temperature = float(smart.get('smart_194_raw', 30.0) or 30.0)
        reallocated = float(smart.get('smart_5_raw', 0.0) or 0.0)
        pending = float(smart.get('smart_197_raw', 0.0) or 0.0)
        probability = 0.03 + min(0.25, reallocated * 0.02) + min(0.25, pending * 0.05)
        if temperature > 40:
            probability += min(0.15, (temperature - 40) * 0.01)
        return min(0.95, probability)

    return None

# SMART attributes used for telemetry/model with their default values and descriptions
SMART_FIELDS = {
    "smart_1_raw": {
        "default": 0.0,
        "name": "Read Error Rate",
        "description": "The rate of hardware read errors that occurred when reading data from the disk surface. A non-zero value may indicate problems with the disk surface or read/write heads.",
        "short_desc": "Rate of hardware read errors"
    },
    "smart_3_raw": {
        "default": 0.0,
        "name": "Spin-Up Time",
        "description": "Average time (in milliseconds) for the disk to spin up from a stopped state to full speed. Higher values may indicate mechanical problems.",
        "short_desc": "Time to reach full speed"
    },
    "smart_4_raw": {
        "default": 0.0,
        "name": "Start/Stop Count",
        "description": "The number of times the disk has been powered on and off. This is a lifetime counter that increases with each power cycle.",
        "short_desc": "Number of power cycles"
    },
    "smart_5_raw": {
        "default": 0.0,
        "name": "Reallocated Sectors Count",
        "description": "The number of bad sectors that have been found and remapped. A non-zero value indicates the disk has had some problems, and the value should not increase over time.",
        "short_desc": "Number of remapped sectors"
    },
    "smart_7_raw": {
        "default": 0.0,
        "name": "Seek Error Rate",
        "description": "The rate of seek errors that occur when the drive's heads try to position themselves over a track. Higher values may indicate mechanical problems.",
        "short_desc": "Rate of positioning errors"
    },
    "smart_10_raw": {
        "default": 0.0,
        "name": "Spin Retry Count",
        "description": "The number of times the drive had to retry spinning up. A non-zero value indicates problems with the drive's motor or power supply.",
        "short_desc": "Number of spin-up retries"
    },
    "smart_192_raw": {
        "default": 0.0,
        "name": "Emergency Retract Count",
        "description": "The number of times the drive's heads were retracted due to power loss or other emergency conditions. High values may indicate power problems.",
        "short_desc": "Number of emergency head retractions"
    },
    "smart_193_raw": {
        "default": 0.0,
        "name": "Load Cycle Count",
        "description": "The number of times the drive's heads have been loaded and unloaded. This is a lifetime counter that increases with each load/unload cycle.",
        "short_desc": "Number of head load/unload cycles"
    },
    "smart_194_raw": {
        "default": 25.0,
        "name": "Temperature",
        "description": "The current temperature of the drive in Celsius. Normal operating temperature is typically between 30-50°C. Higher temperatures may indicate cooling problems.",
        "short_desc": "Current drive temperature"
    },
    "smart_197_raw": {
        "default": 0.0,
        "name": "Current Pending Sectors",
        "description": "The number of sectors that are waiting to be remapped. A non-zero value indicates the drive has found bad sectors that it hasn't been able to remap yet.",
        "short_desc": "Number of sectors waiting to be remapped"
    },
    "smart_198_raw": {
        "default": 0.0,
        "name": "Offline Uncorrectable",
        "description": "The number of sectors that could not be corrected during offline testing. A non-zero value indicates the drive has sectors that are permanently damaged.",
        "short_desc": "Number of uncorrectable sectors"
    }
}


def get_fake_smart_attributes():
    attrs = {field: info["default"] for field, info in SMART_FIELDS.items()}
    attrs.update({
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
    })
    return attrs, []


def get_smart_attributes(device=None):
    """Return SMART attributes as a dictionary using smartctl JSON output."""
    if runtime.is_fake:
        return get_fake_smart_attributes()
    try:
        # If device is not specified, get UUID from config and resolve to device
        if device is None:
            uuid = config_manager.get_value('backup', 'uuid', None)
            if not uuid:
                print("No UUID found in config for backup partition.")
                return None, None
            # Find the partition device with this UUID
            blkid_out = subprocess.run(['blkid', '-t', f'UUID={uuid}', '-o', 'device'], capture_output=True, text=True)
            partition_device = blkid_out.stdout.strip()
            if not partition_device:
                print(f"No partition found with UUID {uuid}")
                return None, None
            # Get the parent drive (e.g. /dev/sda)
            device = system_utils.get_parent_device(partition_device)
            if not device:
                print(f"Could not determine parent device for partition {partition_device}")
                return None, None
        result = subprocess.run(
            ["sudo", "smartctl", "-A", "-j", device], capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        
        # Initialize dictionary with default values for all required SMART fields
        attrs = {field: info["default"] for field, info in SMART_FIELDS.items()}
        missing_attrs = set(SMART_FIELDS.keys())
        
        # Update with actual values from smartctl output
        for item in data.get("ata_smart_attributes", {}).get("table", []):
            field_name = f"smart_{item['id']}_raw"
            if field_name in SMART_FIELDS:
                try:
                    # Temperature is a special case, it is a 16 bit value, but we only want the lowest byte
                    # Extract the lowest byte for smart_194_raw (Temperature)
                    if field_name == "smart_194_raw":
                        attrs[field_name] = float(int(item["raw"]["value"]) & 0xFF)
                    else:
                        attrs[field_name] = float(item["raw"]["value"])
                    missing_attrs.remove(field_name)
                except (ValueError, KeyError, TypeError):
                    print(f"Warning: Could not parse value for {field_name}")
                    continue
        
        return attrs, list(missing_attrs)
    except subprocess.CalledProcessError as e:
        print(f"Failed to execute smartctl: {e}")
        return None, None
    except json.JSONDecodeError as e:
        print(f"Failed to parse smartctl JSON output: {e}")
        return None, None
    except Exception as e:
        print(f"Unexpected error reading SMART data: {e}")
        return None, None


def append_telemetry(data_dict, prediction):
    """Append SMART data and prediction to telemetry.csv."""
    if not data_dict:
        return
    telemetry_path = runtime.telemetry_path
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = telemetry_path.exists()
    with open(telemetry_path, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(list(SMART_FIELDS.keys()) + ["failure"])
        row = [data_dict.get(field, "") for field in SMART_FIELDS.keys()]
        row.append(prediction)
        writer.writerow(row)

# a service can either be running right now, or could have succeeded or failed last time it ran
class Status:
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILURE = "Failure"
    MISSING = "Missing"
    NOT_RUN_YET = "Not Run Yet"
    ERROR = "Error"
    

# use actual dates for next run and last run
class Task:
    def __init__(self, name, service_name, timer_name):
        self.name = name
        self.service_name = service_name
        self.timer_name = timer_name

    def get_logs(self, lines: int = 50) -> str:
        """Return the latest systemd journal logs for this service."""
        if runtime.is_fake:
            return fake_state.get_task_log(self.name)
        try:
            result = subprocess.run(
                [
                    "journalctl",
                    "-u",
                    self.service_name,
                    "-n",
                    str(lines),
                    "--no-pager",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return "Retrieval Error"

    def start(self):
        """Start the associated service asynchronously."""
        if runtime.is_fake:
            start_fake_task(self.name)
            return
        try:
            subprocess.Popen(
                ["systemctl", "start", self.service_name, "--no-block"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to start {self.service_name}: {exc}")

    def stop(self):
        """Stop the associated service asynchronously."""
        if runtime.is_fake:
            fake_state.append_task_log(self.name, f"Stopped {self.name} in fake mode.")
            fake_state.set_task_state(self.name, status=Status.SUCCESS)
            return
        try:
            subprocess.Popen(
                ["systemctl", "stop", self.service_name, "--no-block"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to stop {self.service_name}: {exc}")
    
    @property
    def next_run(self):
        """
        Returns the next run time of the systemd timer by executing
        a system command.
        """
        if runtime.is_fake:
            return fake_state.get_next_run(self.name, config_manager.get_value('schedule', 'backup_cloud_time', '03:00'))
        try:
            # Example: using 'systemctl list-timers' or 'systemctl show'
            result = subprocess.run(
                ["systemctl", "show", self.timer_name, "--property=NextElapseUSecRealtime"],
                capture_output=True,
                text=True,
                check=True
            )
            # Parse the output (this will depend on your exact command and output format)
            output = result.stdout.strip()
            print(f"Next run output: {output}")  # Debugging line
            if "=" in output:
                return output.split("=")[-1].strip()
            return "Unknown"
        except subprocess.CalledProcessError as e:
            # Handle error gracefully
            return f"Retrieval Error"

    @property
    def last_run(self):
        """
        Returns the last run time of the systemd service.
        """
        if runtime.is_fake:
            task_state = fake_state.get_task_state(self.name)
            return task_state.get("last_run") or "Not Run Yet"
        try:
            result = subprocess.run(
                ["systemctl", "show", self.service_name, "--property=ExecMainStartTimestamp"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.strip()
            if "=" in output:
                return output.split("=")[-1].strip()
            return "Unknown"
        except subprocess.CalledProcessError as e:
            return f"Retrieval Error"

    @property
    def last_run_duration(self):
        """Return the duration of the last run in a human friendly format."""
        if runtime.is_fake:
            task_state = fake_state.get_task_state(self.name)
            return task_state.get("last_run_duration", "-")
        try:
            result = subprocess.run(
                [
                    "systemctl",
                    "show",
                    self.service_name,
                    "--property=ExecMainStartTimestampMonotonic",
                    "--property=ExecMainExitTimestampMonotonic",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            start = exit_ts = None
            for line in result.stdout.splitlines():
                if line.startswith("ExecMainStartTimestampMonotonic="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        start = int(value)
                elif line.startswith("ExecMainExitTimestampMonotonic="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        exit_ts = int(value)

            if start is not None and exit_ts is not None and exit_ts >= start:
                delta = timedelta(microseconds=exit_ts - start)
                total_seconds = int(delta.total_seconds())
                months, days = divmod(delta.days, 30)
                hours, rem = divmod(total_seconds % 86400, 3600)
                minutes, seconds = divmod(rem, 60)
                parts = []
                if months:
                    parts.append(f"{months}mo")
                if days:
                    parts.append(f"{days}d")
                if hours:
                    parts.append(f"{hours}h")
                if minutes:
                    parts.append(f"{minutes}m")
                parts.append(f"{seconds}s")
                return " ".join(parts)
            return "Unknown"
        except subprocess.CalledProcessError:
            return "Retrieval Error"

    @property
    def status(self):
        """
        Returns the status of the service: Running, Success, or Failure.
        """
        if runtime.is_fake:
            task_state = fake_state.get_task_state(self.name)
            return task_state.get("status", Status.NOT_RUN_YET)
        try:
            # Check if the service exists
            result = subprocess.run(
                ["systemctl", "show", self.service_name, "--property=LoadState"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.strip()
            if "not-found" in output:
                return Status.MISSING

            # Check if the service is active
            result = subprocess.run(
                ["systemctl", "is-active", self.service_name],
                capture_output=True,
                text=True,
                check=False  # Allow non-zero exit codes (inactive)
            )
            output = result.stdout.strip()
            if output == "activating":
                return Status.RUNNING

            # If not running, check the last exit code/status
            result = subprocess.run(
                ["systemctl", "show", self.service_name, "--property=Result"],
                capture_output=True,
                text=True,
                check=True
            )
            result_output = result.stdout.strip()
            if "=" in result_output:
                result_value = result_output.split("=")[-1].strip()
                if result_value == "success":
                    # Check if the service has not run yet
                    result = subprocess.run(
                        ["systemctl", "show", self.service_name, "--property=ExecMainStartTimestamp"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    output = result.stdout.strip()
                    if output.endswith('=') or output == '':
                        return Status.NOT_RUN_YET
                    else:
                        return Status.SUCCESS
                else:
                    return Status.FAILURE
                
            

            return Status.ERROR  # Default to Error if parsing fails

        except subprocess.CalledProcessError:
            return Status.ERROR

@app.route('/')
def index():
    """Main entry point - redirects to appropriate page based on setup status"""
    if not config_manager.is_setup_complete():
        return redirect(url_for('setup.setup_page'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - only accessible after setup is complete"""
    if not config_manager.is_setup_complete():
        return redirect(url_for('setup.setup_page'))
    if 'username' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        # Reload user data to ensure we have the latest
        user_manager.users = user_manager._load_users()
        
        username = request.form['username']
        password = request.form['password']
        
        if user_manager.verify_user(username, password):
            # Check if user is admin before allowing login
            if user_manager.is_admin(username):
                session['username'] = username
                session.pop('skip_login_disabled', None)
                return redirect(url_for('dashboard'))
            else:
                flash('This account does not have administrator privileges. Only administrators can access the SimpleSaferServer management interface. Please contact your system administrator for access or view the accompanying documentation for information on how to mount any network file shares that you have been given access to.', 'error')
                return render_template('login.html')
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')


def get_auto_login_username():
    configured_username = config_manager.get_value('system', 'username', '')
    user_manager.users = user_manager._load_users()
    return user_manager.get_preferred_admin_username(configured_username)


@app.before_request
def auto_login_fake_mode_user():
    if not runtime.is_fake or not runtime.skip_login:
        return None
    if request.endpoint in {'static'}:
        return None
    if session.get('skip_login_disabled'):
        return None
    if 'username' in session:
        return None
    if not config_manager.is_setup_complete():
        return None

    username = get_auto_login_username()
    if username and user_manager.is_admin(username):
        session['username'] = username
        session['auto_logged_in'] = True
    return None

@app.route('/network_file_sharing')
@login_required
def network_file_sharing():
    backup_mount_point = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
    return render_template('network_file_sharing.html', username=session.get('username'), backup_mount_point=backup_mount_point)

@app.route('/users')
@login_required
def users():
    return render_template('users.html', username=session.get('username'))

@app.route('/logout')
def logout():
    session.clear()
    if runtime.is_fake and runtime.skip_login:
        session['skip_login_disabled'] = True
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if not config_manager.is_setup_complete():
        return redirect(url_for('setup.setup_page'))
    # Get tasks from config
    config = config_manager.get_all_config()
    # Get task information
    tasks = []
    for task in TASKS:
        try:
            # Get next run time
            next_run = task.next_run
            # Get last run time
            last_run = task.last_run
            # Get status using Task.status property
            status = task.status
            # Get last run duration if implemented
            last_run_duration = getattr(task, 'last_run_duration', 'N/A')
            tasks.append({
                'name': task.name,
                'next_run': next_run,
                'last_run': last_run,
                'status': status,
                'last_run_duration': last_run_duration
            })
        except Exception as e:
            print(f"Error getting task info for {task.name}: {e}")
            tasks.append({
                'name': task.name,
                'next_run': 'Error',
                'last_run': 'Error',
                'status': 'Error',
                'last_run_duration': 'Error'
            })
    # Get system metrics
    mount_point = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
    mounted = system_utils.is_mounted(mount_point)
    try:
        disk = psutil.disk_usage(mount_point)
    except Exception:
        disk = psutil.disk_usage(runtime.repo_root)
    cpu_percent = psutil.cpu_percent()
    ram_percent = psutil.virtual_memory().percent
    return render_template('dashboard.html',
        used_storage=f"{disk.used / (1024**3):.1f}",
        total_storage=f"{disk.total / (1024**3):.1f}",
        storage_usage=f"{disk.percent}%",
        cloud_backup_status='Active' if config.get('cloud_backup_enabled') else 'Inactive',
        health_status='Good',
        hdd_temp='35',  # Just the number, template will add °C
        cpu_usage=f"{cpu_percent}%",
        ram_usage=f"{ram_percent}%",
        mount_info={'is_mounted': mounted, 'mount_point': mount_point},
        tasks=tasks
    )


@app.route("/task/<task_name>")
@login_required
def task_detail(task_name):
    task = get_task(task_name)
    if not task:
        abort(404)
    logs = task.get_logs()
    return render_template("task_detail.html", task=task, logs=logs)


@app.route("/task/<task_name>/logs")
@login_required
def task_logs(task_name):
    """Return latest logs for the given task."""
    task = get_task(task_name)
    if not task:
        abort(404)
    lines = int(request.args.get("lines", 50))
    logs = task.get_logs(lines)
    return logs, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/task/<task_name>/start", methods=["POST"])
@login_required
def start_task(task_name):
    task = get_task(task_name)
    if not task:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({"success": False, "message": "Task not found"}), 404
        abort(404)
    try:
        task.start()
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({"success": True, "message": f"Started {task_name}."})
        return redirect(url_for("task_detail", task_name=task_name))
    except Exception as e:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({"success": False, "message": str(e)}), 500
        abort(500)


@app.route("/task/<task_name>/stop", methods=["POST"])
@login_required
def stop_task(task_name):
    task = get_task(task_name)
    if not task:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({"success": False, "message": "Task not found"}), 404
        abort(404)
    try:
        task.stop()
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({"success": True, "message": f"Stopped {task_name}."})
        return redirect(url_for("task_detail", task_name=task_name))
    except Exception as e:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({"success": False, "message": str(e)}), 500
        abort(500)


# API route for running a task
@app.route("/run_task/<task_name>", methods=["POST"])
@login_required
def run_task(task_name):

    task = get_task(task_name)
    if not task:
        return jsonify({"success": False, "message": "Task not found"}), 404
    try:
        task.start()
        # Do not return a json response here, just redirect to the task detail page
        return redirect(url_for("task_detail", task_name=task_name))
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# API route for unmounting storage
@app.route("/unmount", methods=["POST"])
@login_required
def unmount():
    mount_point = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
    try:
        if runtime.is_fake:
            fake_state.set_mount(False)
            fake_state.append_task_log('Check Mount', f'Backup source disconnected from {mount_point}.')
            return jsonify({"success": True, "message": "Local backup source disconnected."})

        # 1. Disconnect all SMB users (if possible)
        try:
            subprocess.run(["sudo", "smbcontrol", "all", "close-share", mount_point], check=False)
        except Exception:
            pass  # Ignore errors, just try to close sessions
        # 2. Stop all systemd tasks
        for service in ["check_mount.service", "check_health.service", "backup_cloud.service"]:
            subprocess.run(["sudo", "systemctl", "stop", service], check=False)
        # 3. Stop smbd and nmbd
        subprocess.run(["sudo", "systemctl", "stop", "smbd"], check=False)
        subprocess.run(["sudo", "systemctl", "stop", "nmbd"], check=False)
        # 4. Unmount the drive
        subprocess.run(["sudo", "umount", mount_point], check=True)
        # 5. Power down the drive (try hdparm, ignore errors if not supported)
        try:
            uuid = config_manager.get_value('backup', 'uuid', None)
            if uuid:
                blkid_out = subprocess.run(['blkid', '-t', f'UUID={uuid}', '-o', 'device'], capture_output=True, text=True)
                partition_device = blkid_out.stdout.strip()
                if partition_device:
                    parent_device = system_utils.get_parent_device(partition_device)
                    if parent_device:
                        subprocess.run(["sudo", "hdparm", "-y", parent_device], check=False)
        except Exception:
            pass
        # 6. Start smbd and nmbd again so network file sharing is available
        try:
            subprocess.run(["sudo", "systemctl", "start", "smbd"], check=False)
            subprocess.run(["sudo", "systemctl", "start", "nmbd"], check=False)
        except Exception:
            pass
        return jsonify({"success": True, "message": "Drive unmounted and powered down. It is now safe to remove the drive."})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "message": f"Failed to unmount drive: {e}"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Unexpected error: {e}"}), 500


# API route for restarting the system
@app.route("/restart", methods=["POST"])
@admin_required
def restart():
    try:
        if runtime.is_fake:
            return jsonify({"success": True, "message": "Fake mode: restart simulated."})
        subprocess.run(["sudo", "systemctl", "reboot"], check=True)
        return jsonify({"success": True, "message": "System is restarting..."})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "message": f"Failed to restart system: {e}"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Unexpected error: {e}"}), 500


# API route for shutting down the system
@app.route("/shutdown", methods=["POST"])
@admin_required
def shutdown():
    try:
        if runtime.is_fake:
            return jsonify({"success": True, "message": "Fake mode: shutdown simulated."})
        subprocess.run(["sudo", "systemctl", "poweroff"], check=True)
        return jsonify({"success": True, "message": "System is shutting down..."})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "message": f"Failed to shut down system: {e}"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Unexpected error: {e}"}), 500


# Drive health page
@app.route("/drives", methods=["GET", "POST"])
@login_required
def drives():
    prediction = None
    probability = None
    error = None
    smart = None
    missing_attrs = None
    if request.method == "POST":
        result = get_smart_attributes()
        if result is None:
            error = "Could not retrieve SMART data"
        else:
            smart, missing_attrs = result
            prob = predict_failure_probability(smart)
            if prob is not None:
                prediction = int(prob >= optimal_threshold)
                probability = prob
                append_telemetry(smart, prediction)
            else:
                error = "Model not loaded"
    return render_template(
        "drive_health.html",
        smart=smart,
        prediction=prediction,
        probability=probability,
        error=error,
        missing_attrs=missing_attrs,
        smart_fields=SMART_FIELDS,
    )


@app.route("/download_telemetry")
@login_required
def download_telemetry():
    if runtime.telemetry_path.exists():
        return send_file(runtime.telemetry_path, as_attachment=True)
    abort(404)


def run_fake_cloud_backup():
    source = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
    destination = config_manager.get_value('backup', 'rclone_dir', '').strip()
    rclone_config_path = runtime.rclone_config_dir / 'rclone.conf'
    if not source:
        raise RuntimeError('No source folder configured.')
    if not os.path.isdir(source):
        raise RuntimeError(f'Source folder does not exist: {source}')
    if not destination:
        raise RuntimeError('No cloud destination configured.')
    if ':' in destination and not rclone_config_path.exists():
        raise RuntimeError(f'Rclone config not found at {rclone_config_path}')

    fake_state.append_task_log('Cloud Backup', f'Starting backup from {source} to {destination}')
    bandwidth_limit = config_manager.get_value('backup', 'bandwidth_limit', '').strip()
    command = ['rclone', 'sync', source, destination, '--create-empty-src-dirs', '-v']
    if rclone_config_path.exists():
        command.extend(['--config', str(rclone_config_path)])
    if bandwidth_limit:
        command.extend(['--bwlimit', bandwidth_limit])

    result = subprocess.run(command, capture_output=True, text=True)
    output = (result.stdout or '') + (result.stderr or '')
    if output.strip():
        fake_state.append_task_log('Cloud Backup', output.strip())
    if result.returncode != 0:
        raise RuntimeError(output.strip() or 'Cloud backup failed.')


fake_task_threads: dict[str, threading.Thread] = {}
fake_task_lock = threading.Lock()


def start_fake_task(task_name: str):
    with fake_task_lock:
        existing_thread = fake_task_threads.get(task_name)
        if existing_thread and existing_thread.is_alive():
            raise RuntimeError(f'{task_name} is already running.')

        fake_state.set_task_state(task_name, status=Status.RUNNING)
        fake_state.append_task_log(task_name, f'Starting {task_name} in fake mode.')

        thread = threading.Thread(
            target=run_fake_task,
            args=(task_name,),
            name=f'fake-task-{task_name.lower().replace(" ", "-")}',
            daemon=True,
        )
        fake_task_threads[task_name] = thread
        thread.start()


def run_fake_task(task_name: str):
    start_time = datetime.now()
    try:
        if task_name == 'Check Mount':
            mount_point = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
            if not os.path.isdir(mount_point):
                raise RuntimeError(f'Backup source folder not found: {mount_point}')
            if not fake_state.is_mounted(mount_point):
                fake_state.set_mount(True, mount_point=mount_point)
                fake_state.append_task_log(task_name, f'Found local backup source at {mount_point}; marking it as connected.')
            fake_state.append_task_log(task_name, f'Backup source available at {mount_point}.')
        elif task_name == 'Drive Health Check':
            smart, _ = get_smart_attributes()
            probability = predict_failure_probability(smart)
            if probability is not None:
                fake_state.append_task_log(task_name, f'Drive health probability: {probability:.4f}')
            else:
                fake_state.append_task_log(task_name, 'Model unavailable; using sample SMART data only.')
        elif task_name == 'Cloud Backup':
            run_fake_cloud_backup()

        duration = max(0, int((datetime.now() - start_time).total_seconds()))
        fake_state.set_task_state(
            task_name,
            status=Status.SUCCESS,
            last_run=start_time.strftime('%Y-%m-%d %H:%M:%S'),
            last_run_duration=f'{duration}s',
        )
        fake_state.append_task_log(task_name, f'{task_name} finished successfully.')
    except Exception as exc:
        duration = max(0, int((datetime.now() - start_time).total_seconds()))
        fake_state.set_task_state(
            task_name,
            status=Status.FAILURE,
            last_run=start_time.strftime('%Y-%m-%d %H:%M:%S'),
            last_run_duration=f'{duration}s',
        )
        fake_state.append_task_log(task_name, f'{task_name} failed: {exc}')
        app.logger.warning('Fake task %s failed: %s', task_name, exc)
    finally:
        with fake_task_lock:
            active_thread = fake_task_threads.get(task_name)
            if active_thread is threading.current_thread():
                fake_task_threads.pop(task_name, None)


# Define tasks globally so they can be reused across routes
TASKS = [
    Task("Check Mount", "check_mount.service", "check_mount.timer"),
    Task("Drive Health Check", "check_health.service", "check_health.timer"),
    Task("Cloud Backup", "backup_cloud.service", "backup_cloud.timer")
]

def get_task(name: str):
    for task in TASKS:
        if task.name == name:
            return task
    return None

@app.route('/cloud_backup')
@login_required
def cloud_backup():
    return render_template('cloud_backup.html', username=session.get('username'))

@app.route('/alerts')
@login_required
def alerts():
    return render_template('alerts.html', username=session.get('username'))

# Alerts API endpoints
@app.route('/api/alerts', methods=['GET'])
@login_required
def api_get_alerts():
    """Get all alerts"""
    try:
        alerts = config_manager.get_alerts()
        return jsonify({'success': True, 'alerts': alerts})
    except Exception as e:
        current_app.logger.error(f"Error getting alerts: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/alerts/<int:alert_id>', methods=['GET'])
@login_required
def api_get_alert(alert_id):
    """Get a specific alert by ID"""
    try:
        alerts = config_manager.get_alerts()
        alert = next((a for a in alerts if a['id'] == alert_id), None)
        
        if alert:
            return jsonify({'success': True, 'alert': alert})
        else:
            return jsonify({'success': False, 'error': 'Alert not found'}), 404
    except Exception as e:
        current_app.logger.error(f"Error getting alert {alert_id}: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/alerts/<int:alert_id>/mark-read', methods=['POST'])
@login_required
def api_mark_alert_read(alert_id):
    """Mark an alert as read"""
    try:
        success = config_manager.mark_alert_read(alert_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to mark alert as read'})
    except Exception as e:
        current_app.logger.error(f"Error marking alert {alert_id} as read: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/alerts/clear', methods=['POST'])
@admin_required
def api_clear_alerts():
    """Clear all alerts"""
    try:
        success = config_manager.clear_alerts()
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to clear alerts'})
    except Exception as e:
        current_app.logger.error(f"Error clearing alerts: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/alerts/mark-all-read', methods=['POST'])
@login_required
def api_mark_all_alerts_read():
    """Mark all alerts as read"""
    try:
        success = config_manager.mark_all_alerts_read()
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to mark all alerts as read'})
    except Exception as e:
        current_app.logger.error(f"Error marking all alerts as read: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/alerts/email-config', methods=['GET'])
@login_required
def api_get_email_config():
    """Get current email configuration"""
    try:
        # Read msmtp config file to get current settings
        msmtp_config = {}
        try:
            with open(runtime.msmtp_config_path, 'r') as f:
                content = f.read()
            # Parse the msmtp config to extract settings
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('host '):
                    msmtp_config['smtp_server'] = line.split(' ', 1)[1]
                elif line.startswith('port '):
                    msmtp_config['smtp_port'] = line.split(' ', 1)[1]
                elif line.startswith('from '):
                    msmtp_config['from_address'] = line.split(' ', 1)[1]
                elif line.startswith('user '):
                    msmtp_config['smtp_username'] = line.split(' ', 1)[1]
                elif line.startswith('password '):
                    msmtp_config['smtp_password'] = line.split(' ', 1)[1]
        except FileNotFoundError:
            pass  # msmtp config doesn't exist yet
        # Get email address and from address from config manager as well
        email_address = config_manager.get_value('backup', 'email_address', '')
        from_address = config_manager.get_value('backup', 'from_address', '')
        if email_address and 'email_address' not in msmtp_config:
            msmtp_config['email_address'] = email_address
        if from_address and 'from_address' not in msmtp_config:
            msmtp_config['from_address'] = from_address
        
        return jsonify({'success': True, 'config': msmtp_config})
    except Exception as e:
        current_app.logger.error(f"Error getting email config: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/alerts/email-config', methods=['POST'])
@admin_required
def api_set_email_config():
    """Set email configuration"""
    try:
        data = request.get_json()
        email = data.get('email_address')
        from_address = data.get('from_address')
        smtp_server = data.get('smtp_server')
        smtp_port = data.get('smtp_port')
        smtp_username = data.get('smtp_username')
        smtp_password = data.get('smtp_password')
        if not all([email, from_address, smtp_server, smtp_port, smtp_username, smtp_password]):
            return jsonify({'success': False, 'error': 'All email fields are required'})
        # Save email and from address to config
        config_manager.set_value('backup', 'email_address', email)
        config_manager.set_value('backup', 'from_address', from_address)
        # Write msmtp configuration
        if not system_utils.write_msmtp_config(from_address, smtp_server, smtp_port, smtp_username, smtp_password):
            return jsonify({'success': False, 'error': 'Failed to write msmtp configuration'})
        
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error setting email config: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.context_processor
def inject_username():
    return dict(
        username=session.get('username'),
        runtime_mode=runtime.mode,
        default_mount_point=runtime.default_mount_point,
    )

@app.route('/api/users', methods=['GET'])
@admin_required
def api_list_users():
    # Reload user data to ensure we have the latest
    user_manager.users = user_manager._load_users()
    users = []
    for username, data in user_manager.users.items():
        users.append({
            'username': username,
            'is_admin': data.get('is_admin', False),
            'created_at': data.get('created_at'),
            'last_login': data.get('last_login')
        })
    return jsonify({'success': True, 'users': users})

@app.route('/api/users', methods=['POST'])
@admin_required
def api_add_user():
    # Reload user data to ensure we have the latest
    user_manager.users = user_manager._load_users()
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    is_admin = data.get('is_admin', False)
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password are required'})
    
    success, message = user_manager.create_user(username, password)
    if success:
        # Set admin status after creation
        user_manager.users[username]['is_admin'] = is_admin
        user_manager._save_users()
        return jsonify({'success': True, 'error': None})
    return jsonify({'success': False, 'error': message})

@app.route('/api/users/<username>', methods=['PUT'])
@admin_required
def api_edit_user(username):
    # Reload user data to ensure we have the latest
    user_manager.users = user_manager._load_users()
    data = request.get_json()
    new_password = data.get('password')
    is_admin = data.get('is_admin')

    if username not in user_manager.users:
        return jsonify({'success': False, 'error': 'User not found'})

    # Prevent self-demotion from admin
    if (
        username == session.get('username') and
        is_admin is not None and
        not bool(is_admin) and
        user_manager.users[username].get('is_admin', False)
    ):
        return jsonify({'success': False, 'error': 'You cannot remove your own admin privileges while logged in.'}), 400

    if new_password:
        from werkzeug.security import generate_password_hash
        user_manager.users[username]['password_hash'] = generate_password_hash(new_password)

    if is_admin is not None:
        user_manager.users[username]['is_admin'] = bool(is_admin)

    user_manager._save_users()
    return jsonify({'success': True})

@app.route('/api/users/<username>', methods=['DELETE'])
@admin_required
def api_delete_user(username):
    # Reload user data to ensure we have the latest
    user_manager.users = user_manager._load_users()
    
    if username == session.get('username'):
        return jsonify({'error': 'Cannot delete the currently logged-in user'}), 400
    
    success, message = user_manager.delete_user(username)
    if success:
        return jsonify({'message': f'User {username} deleted successfully'})
    else:
        return jsonify({'error': f'Failed to delete user {username}: {message}'}), 400

# SMB Share Management API endpoints
@app.route('/api/smb/shares', methods=['GET'])
@admin_required
def api_list_smb_shares():
    """Get list of all SMB shares from smb.conf"""
    try:
        shares = smb_manager.get_shares()
        return jsonify({'shares': shares})
    except Exception as e:
        current_app.logger.error(f"Error reading SMB shares: {e}")
        return jsonify({'error': 'Failed to read SMB shares'}), 500

@app.route('/api/smb/shares', methods=['POST'])
@admin_required
def api_add_smb_share():
    """Add a new SMB share"""
    try:
        data = request.get_json()
        share_name = data.get('name', '').strip()
        path = data.get('path', '').strip()
        writable = data.get('writable', False)
        comment = data.get('comment', '').strip()
        valid_users = data.get('valid_users', [])
        
        # Validation
        if not share_name or not path:
            return jsonify({'error': 'Share name and path are required'}), 400
        
        # Check if share name is valid (no spaces, special chars)
        if ' ' in share_name or any(char in share_name for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']):
            return jsonify({'error': 'Share name contains invalid characters'}), 400
        
        # Add share using SMB manager
        smb_manager.add_share(share_name, path, writable, comment, valid_users)
        
        return jsonify({'message': f'Share {share_name} added successfully'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error adding SMB share: {e}")
        return jsonify({'error': 'Failed to add SMB share'}), 500

@app.route('/api/smb/shares/<share_name>', methods=['PUT'])
@admin_required
def api_edit_smb_share(share_name):
    """Edit an existing SMB share"""
    try:
        data = request.get_json()
        new_name = data.get('name', '').strip()
        path = data.get('path', '').strip()
        writable = data.get('writable', False)
        comment = data.get('comment', '').strip()
        valid_users = data.get('valid_users', [])
        
        # Validation
        if not new_name or not path:
            return jsonify({'error': 'Share name and path are required'}), 400
        
        # Check if new share name is valid
        if ' ' in new_name or any(char in new_name for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']):
            return jsonify({'error': 'Share name contains invalid characters'}), 400
        
        # Update share using SMB manager
        smb_manager.update_share(share_name, new_name, path, writable, comment, valid_users)
        
        return jsonify({'message': f'Share {share_name} updated successfully'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error editing SMB share: {e}")
        return jsonify({'error': 'Failed to edit SMB share'}), 500

@app.route('/api/smb/shares/<share_name>', methods=['DELETE'])
@admin_required
def api_delete_smb_share(share_name):
    """Delete an SMB share"""
    try:
        smb_manager.delete_share(share_name)
        return jsonify({'message': f'Share {share_name} deleted successfully'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error deleting SMB share: {e}")
        return jsonify({'error': 'Failed to delete SMB share'}), 500

@app.route('/api/smb/status')
@login_required
def api_smb_status():
    """Get SMB service status"""
    try:
        status = smb_manager.get_service_status()
        return jsonify(status)
    except Exception as e:
        current_app.logger.error(f"Error getting SMB status: {e}")
        return jsonify({'error': 'Failed to get SMB status'}), 500

@app.route('/api/smb/restart', methods=['POST'])
@admin_required
def api_restart_smb():
    """Restart SMB services"""
    try:
        if smb_manager._restart_services():
            return jsonify({'message': 'SMB services restarted successfully'})
        else:
            return jsonify({'error': 'Failed to restart SMB services'}), 500
    except Exception as e:
        current_app.logger.error(f"Error restarting SMB services: {e}")
        return jsonify({'error': 'Failed to restart SMB services'}), 500

@app.route('/api/smb/shares/<share_name>/users', methods=['GET'])
@admin_required
def api_get_share_users(share_name):
    """Get users who have access to a specific share"""
    try:
        users = smb_manager.get_share_users(share_name)
        return jsonify({'users': users})
    except Exception as e:
        current_app.logger.error(f"Error getting share users: {e}")
        return jsonify({'error': 'Failed to get share users'}), 500

@app.route('/api/smb/shares/<share_name>/users', methods=['PUT'])
@admin_required
def api_update_share_users(share_name):
    """Update users who have access to a specific share"""
    try:
        data = request.get_json()
        users = data.get('users', [])
        
        # Validate that all users exist in the system
        for username in users:
            if not user_manager.get_user(username):
                return jsonify({'error': f'User {username} does not exist'}), 400
        
        smb_manager.update_share_users(share_name, users)
        return jsonify({'message': f'Share {share_name} users updated successfully'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error updating share users: {e}")
        return jsonify({'error': 'Failed to update share users'}), 500

@app.route('/api/list_dirs', methods=['GET'])
@admin_required
def api_list_dirs():
    """List subdirectories of a given path for folder picker UI."""
    path = request.args.get('path', '/')
    # Normalize and secure the path
    path = os.path.abspath(path)
    try:
        if not os.path.isdir(path):
            return jsonify({'error': 'Not a directory'}), 400
        # List only directories, ignore files
        entries = []
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                entries.append(entry)
        # Sort for UX
        entries.sort()
        # For root, parent is None; otherwise, parent is os.path.dirname(path)
        parent = os.path.dirname(path) if path != '/' else None
        return jsonify({'path': path, 'parent': parent, 'dirs': entries})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/storage/status')
@login_required
def api_storage_status():
    mount_point = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
    mounted = system_utils.is_mounted(mount_point)
    if mounted:
        try:
            disk = psutil.disk_usage(mount_point)
            used_storage = f"{disk.used / (1024**3):.1f}"
            total_storage = f"{disk.total / (1024**3):.1f}"
            storage_usage = f"{disk.percent}%"
        except Exception as e:
            used_storage = total_storage = storage_usage = None
    else:
        used_storage = total_storage = storage_usage = None
    return jsonify({
        'mounted': mounted,
        'used_storage': used_storage,
        'total_storage': total_storage,
        'storage_usage': storage_usage,
        'mount_point': mount_point
    })

@app.route('/api/drive_health/summary')
@login_required
def api_drive_health_summary():
    try:
        smart, missing_attrs = get_smart_attributes()
        if smart is None:
            return jsonify({'status': 'unknown', 'probability': None, 'temperature': None})
        prob = predict_failure_probability(smart)
        if prob is not None:
            temperature = smart.get('smart_194_raw', None)
            status = 'good' if prob < optimal_threshold else 'warning'
            return jsonify({
                'status': status,
                'probability': prob,
                'temperature': temperature
            })
        else:
            return jsonify({'status': 'unknown', 'probability': None, 'temperature': None})
    except Exception as e:
        return jsonify({'status': 'unknown', 'probability': None, 'temperature': None})

@app.route("/mount", methods=["POST"])
@login_required
def mount_drive():
    mount_point = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
    uuid = config_manager.get_value('backup', 'uuid', None)
    try:
        if runtime.is_fake:
            if not os.path.isdir(mount_point):
                return jsonify({"success": False, "message": f"Source folder not found: {mount_point}"}), 400
            fake_state.set_mount(True, mount_point=mount_point)
            fake_state.append_task_log('Check Mount', f'Backup source connected at {mount_point}.')
            return jsonify({"success": True, "message": "Local backup source connected."})

        if not uuid:
            return jsonify({"success": False, "message": "No drive UUID configured."}), 400
        # Find the device by UUID
        blkid_out = subprocess.run(['blkid', '-t', f'UUID={uuid}', '-o', 'device'], capture_output=True, text=True)
        partition_device = blkid_out.stdout.strip()
        if not partition_device:
            return jsonify({"success": False, "message": "Drive not found. Please check the connection."}), 400
        # Create mount point if it doesn't exist
        os.makedirs(mount_point, exist_ok=True)
        # Mount the device
        subprocess.run(["sudo", "mount", partition_device, mount_point], check=True)
        # Start systemd tasks
        for service in ["check_mount.service", "check_health.service", "backup_cloud.service"]:
            subprocess.run(["sudo", "systemctl", "start", service], check=False)
        # Start smbd and nmbd
        subprocess.run(["sudo", "systemctl", "start", "smbd"], check=False)
        subprocess.run(["sudo", "systemctl", "start", "nmbd"], check=False)
        return jsonify({"success": True, "message": "Drive mounted and available for use."})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "message": f"Failed to mount drive: {e}"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Unexpected error: {e}"}), 500

@app.route('/api/system/resources')
@login_required
def api_system_resources():
    try:
        cpu_percent = psutil.cpu_percent(interval=0.2)
        ram_percent = psutil.virtual_memory().percent
        net = psutil.net_io_counters()
        return jsonify({
            'cpu_usage': cpu_percent,
            'ram_usage': ram_percent,
            'bytes_sent': net.bytes_sent,
            'bytes_recv': net.bytes_recv
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/schedule')
@login_required
def api_tasks_schedule():
    try:
        tasks = []
        for task in TASKS:
            try:
                next_run = task.next_run
                last_run = task.last_run
                status = task.status
                last_run_duration = getattr(task, 'last_run_duration', 'N/A')
                tasks.append({
                    'name': task.name,
                    'next_run': next_run,
                    'last_run': last_run,
                    'status': status,
                    'last_run_duration': last_run_duration
                })
            except Exception as e:
                tasks.append({
                    'name': task.name,
                    'next_run': 'Error',
                    'last_run': 'Error',
                    'status': 'Error',
                    'last_run_duration': 'Error'
                })
        return jsonify({'tasks': tasks})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cloud_backup/config', methods=['GET'])
@login_required
def api_cloud_backup_get_config():
    """Get current cloud backup configuration (MEGA/rclone, schedule, bandwidth)"""
    try:
        config = config_manager.get_all_config()
        backup = config.get('backup', {})
        schedule = config.get('schedule', {})
        # Only expose non-sensitive info
        resp = {
            'cloud_mode': backup.get('cloud_mode', ''),
            'mega_email': backup.get('mega_email', ''),
            'mega_folder': backup.get('mega_folder', ''),
            'rclone_dir': backup.get('rclone_dir', ''),
            'bandwidth_limit': backup.get('bandwidth_limit', ''),
            'backup_cloud_time': schedule.get('backup_cloud_time', ''),
        }
        # For advanced mode, also return the current rclone.conf (if exists)
        import os
        rclone_conf_path = runtime.rclone_config_dir / 'rclone.conf'
        if os.path.exists(rclone_conf_path):
            with open(rclone_conf_path) as f:
                resp['rclone_config'] = f.read()
        else:
            resp['rclone_config'] = ''
        return jsonify({'success': True, 'config': resp})
    except Exception as e:
        current_app.logger.error(f"Error getting cloud backup config: {e}")
        return jsonify({'success': False, 'error': 'Could not load backup settings.'})

@app.route('/api/cloud_backup/config', methods=['POST'])
@login_required
def api_cloud_backup_set_config():
    """Set cloud backup configuration (MEGA/rclone, schedule, bandwidth)"""
    try:
        data = request.get_json()
        mode = data.get('cloud_mode')
        if mode == 'mega':
            email = data.get('mega_email')
            password = data.get('mega_password')
            folder = data.get('mega_folder')
            if not email or not folder:
                return jsonify({'success': False, 'error': 'Email and folder are required.'})
            
            # If password is provided, validate and update credentials
            if password:
                # Obscure password
                result = subprocess.run(["rclone", "obscure", password], stdout=subprocess.PIPE, check=True, text=True)
                obscured_pw = result.stdout.strip()
                config_manager.set_value('backup', 'mega_email', email)
                config_manager.set_value('backup', 'mega_pass', obscured_pw)
                # Write rclone config for MEGA
                mega_rclone_config = f"""[mega]\ntype = mega\nuser = {email}\npass = {obscured_pw}\n"""
                if not system_utils.setup_rclone(mega_rclone_config):
                    return jsonify({'success': False, 'error': 'Failed to write rclone config for MEGA.'})
            else:
                # No password provided, use existing stored credentials
                stored_email = config_manager.get_value('backup', 'mega_email', '')
                stored_pass = config_manager.get_value('backup', 'mega_pass', '')
                if not stored_email or not stored_pass:
                    return jsonify({'success': False, 'error': 'No MEGA credentials stored. Please provide password.'})
                # Update email if it changed
                if stored_email != email:
                    config_manager.set_value('backup', 'mega_email', email)
                    # Write rclone config with updated email
                    mega_rclone_config = f"""[mega]\ntype = mega\nuser = {email}\npass = {stored_pass}\n"""
                    if not system_utils.setup_rclone(mega_rclone_config):
                        return jsonify({'success': False, 'error': 'Failed to write rclone config for MEGA.'})
            
            config_manager.set_value('backup', 'cloud_mode', 'mega')
            config_manager.set_value('backup', 'mega_folder', folder)
            config_manager.set_value('backup', 'rclone_dir', f"mega:{folder}")
        elif mode == 'advanced':
            rclone_config = data.get('rclone_config')
            remote_name = data.get('remote_name')
            if not rclone_config or not remote_name:
                return jsonify({'success': False, 'error': 'Rclone config and remote name are required.'})
            if not system_utils.setup_rclone(rclone_config):
                return jsonify({'success': False, 'error': 'Failed to write rclone config.'})
            config_manager.set_value('backup', 'cloud_mode', 'advanced')
            config_manager.set_value('backup', 'rclone_dir', remote_name)
        # Schedule and bandwidth
        backup_time = data.get('backup_cloud_time')
        bandwidth_limit = data.get('bandwidth_limit')
        if backup_time:
            config_manager.set_value('schedule', 'backup_cloud_time', backup_time)
        if bandwidth_limit is not None:
            config_manager.set_value('backup', 'bandwidth_limit', bandwidth_limit)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error saving cloud backup config: {e}")
        return jsonify({'success': False, 'error': 'Could not save backup settings.'})

@app.route('/api/cloud_backup/status', methods=['GET'])
@login_required
def api_cloud_backup_status():
    """Get status, last run, next run, and run duration for the cloud backup task."""
    try:
        task = get_task('Cloud Backup')
        if not task:
            return jsonify({'success': False, 'error': 'Cloud backup task not found.'})
        status = {
            'status': task.status,
            'last_run': task.last_run,
            'next_run': task.next_run,
            'last_run_duration': task.last_run_duration
        }
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        current_app.logger.error(f"Error getting cloud backup status: {e}")
        return jsonify({'success': False, 'error': 'Could not get backup status.'})

@app.route('/api/cloud_backup/run', methods=['POST'])
@login_required
def api_cloud_backup_run():
    """Trigger a manual cloud backup run."""
    try:
        task = get_task('Cloud Backup')
        if not task:
            return jsonify({'success': False, 'error': 'Cloud backup task not found.'})
        task.start()
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error running cloud backup: {e}")
        return jsonify({'success': False, 'error': 'Could not start backup.'})

@app.route('/api/cloud_backup/mega/list_folders', methods=['POST'])
@login_required
def api_cloud_backup_mega_list_folders():
    """List folders at a given MEGA path using provided or stored credentials."""
    try:
        data = request.get_json() or {}
        path = data.get('path', '/')
        email = data.get('email')
        password = data.get('password')
        if email and password:
            # Use credentials from request (e.g., during setup)
            result = subprocess.run(["rclone", "obscure", password], stdout=subprocess.PIPE, check=True, text=True)
            obscured_pw = result.stdout.strip()
        else:
            # Use stored credentials ONLY if BOTH are missing or null
            email = config_manager.get_value('backup', 'mega_email', '')
            obscured_pw = config_manager.get_value('backup', 'mega_pass', '')
            current_app.logger.info(f"Using stored credentials - email: {email[:10]}..., obscured_pw: {obscured_pw[:10] if obscured_pw else 'None'}...")
            if not email or not obscured_pw:
                return jsonify({'success': False, 'error': 'No MEGA credentials stored.'})
        # Build temp rclone config
        config_text = f"""
[mega]\ntype = mega\nuser = {email}\npass = {obscured_pw}\n"""
        with NamedTemporaryFile(delete=False, mode="w", prefix="rclone-", suffix=".conf") as config_file:
            config_file.write(config_text)
            config_path = config_file.name
        try:
            lsjson = subprocess.run([
                "rclone", "lsjson", f"mega:{path}", "--config", config_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if lsjson.returncode != 0:
                error_msg = lsjson.stderr.strip() if lsjson.stderr else 'Unknown rclone error'
                current_app.logger.error(f"Rclone error listing MEGA folders: {error_msg}")
                return jsonify({'success': False, 'error': f'Failed to list MEGA folders: {error_msg}'})
            import json as pyjson
            items = pyjson.loads(lsjson.stdout)
            folders = [item['Name'] for item in items if item['IsDir']]
            parent = '/'.join(path.rstrip('/').split('/')[:-1]) or '/'
            return jsonify({'success': True, 'folders': folders, 'path': path, 'parent': parent})
        finally:
            import os
            os.remove(config_path)
    except Exception as e:
        current_app.logger.error(f"Error listing MEGA folders: {e}")
        return jsonify({'success': False, 'error': 'Could not list MEGA folders.'})


@app.route('/api/cloud_backup/mega/create_folder', methods=['POST'])
@login_required
def api_cloud_backup_mega_create_folder():
    """Create a MEGA folder using provided or stored credentials."""
    try:
        data = request.get_json() or {}
        folder_name = (data.get('folder_name') or '').strip()
        path = data.get('path', '/')
        email = data.get('email')
        password = data.get('password')

        if not folder_name:
            return jsonify({'success': False, 'error': 'Folder name is required.'})

        if email and password:
            result = subprocess.run(["rclone", "obscure", password], stdout=subprocess.PIPE, check=True, text=True)
            obscured_pw = result.stdout.strip()
        else:
            email = config_manager.get_value('backup', 'mega_email', '')
            obscured_pw = config_manager.get_value('backup', 'mega_pass', '')
            if not email or not obscured_pw:
                return jsonify({'success': False, 'error': 'No MEGA credentials stored.'})

        config_text = f"""
[mega]
type = mega
user = {email}
pass = {obscured_pw}
"""
        with NamedTemporaryFile(delete=False, mode="w", prefix="rclone-", suffix=".conf") as config_file:
            config_file.write(config_text)
            config_path = config_file.name

        try:
            full_path = f"{path.rstrip('/')}/{folder_name}" if path != '/' else f"/{folder_name}"
            mkdir = subprocess.run(
                ["rclone", "mkdir", f"mega:{full_path}", "--config", config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if mkdir.returncode != 0:
                error_msg = mkdir.stderr.strip() if mkdir.stderr else 'Unknown rclone error'
                current_app.logger.error(f"Rclone error creating MEGA folder: {error_msg}")
                return jsonify({'success': False, 'error': f'Failed to create folder: {error_msg}'})

            return jsonify({'success': True})
        finally:
            os.remove(config_path)
    except Exception as e:
        current_app.logger.error(f"Error creating MEGA folder: {e}")
        return jsonify({'success': False, 'error': 'Could not create MEGA folder.'})

@app.route('/api/cloud_backup/schedule', methods=['GET'])
@login_required
def api_cloud_backup_get_schedule():
    """Get only the backup schedule and bandwidth limit."""
    try:
        config = config_manager.get_all_config()
        schedule = config.get('schedule', {})
        backup = config.get('backup', {})
        return jsonify({
            'success': True,
            'backup_cloud_time': schedule.get('backup_cloud_time', ''),
            'bandwidth_limit': backup.get('bandwidth_limit', '')
        })
    except Exception as e:
        current_app.logger.error(f"Error getting backup schedule: {e}")
        return jsonify({'success': False, 'error': 'Could not load schedule.'})

@app.route('/api/cloud_backup/schedule', methods=['POST'])
@login_required
def api_cloud_backup_set_schedule():
    """Set only the backup schedule and bandwidth limit."""
    try:
        data = request.get_json()
        backup_time = data.get('backup_cloud_time')
        bandwidth_limit = data.get('bandwidth_limit')
        if backup_time:
            config_manager.set_value('schedule', 'backup_cloud_time', backup_time)
        if bandwidth_limit is not None:
            config_manager.set_value('backup', 'bandwidth_limit', bandwidth_limit)
        
        if runtime.is_fake:
            return jsonify({'success': True})

        # Update systemd timers and configuration after saving schedule
        config = config_manager.get_all_config()
        
        # Update the systemd config file
        ok, err = system_utils.create_systemd_config_file(config)
        if not ok:
            return jsonify({'success': False, 'error': f'Failed to update systemd config: {err}'})
        
        # Update systemd services and timers
        ok, err = system_utils.install_systemd_services_and_timers(config)
        if not ok:
            return jsonify({'success': False, 'error': f'Failed to update systemd timers: {err}'})
        
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error saving backup schedule: {e}")
        return jsonify({'success': False, 'error': 'Could not save schedule.'})

@app.route('/api/cloud_backup/mega/validate', methods=['POST'])
@login_required
def api_cloud_backup_mega_validate():
    """Validate MEGA credentials using rclone and save them if valid."""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required.'})
        # Obscure password using rclone
        result = subprocess.run(["rclone", "obscure", password], stdout=subprocess.PIPE, check=True, text=True)
        obscured_pw = result.stdout.strip()
        # Build temp rclone config
        config_text = f"""
[mega]
type = mega
user = {email}
pass = {obscured_pw}
"""
        with NamedTemporaryFile(delete=False, mode="w", prefix="rclone-", suffix=".conf") as config_file:
            config_file.write(config_text)
            config_path = config_file.name
        try:
            # List folders at root to validate credentials
            lsjson = subprocess.run([
                "rclone", "lsjson", "mega:/", "--config", config_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if lsjson.returncode != 0:
                return jsonify({'success': False, 'error': 'Failed to connect to MEGA. Check credentials.'})
            
            # If validation succeeds, save the credentials to config
            config_manager.set_value('backup', 'cloud_mode', 'mega')
            config_manager.set_value('backup', 'mega_email', email)
            config_manager.set_value('backup', 'mega_pass', obscured_pw)
            
            # Write rclone config for MEGA
            mega_rclone_config = f"""[mega]\ntype = mega\nuser = {email}\npass = {obscured_pw}\n"""
            if not system_utils.setup_rclone(mega_rclone_config):
                return jsonify({'success': False, 'error': 'Failed to write rclone config for MEGA.'})
            
            return jsonify({'success': True})
        finally:
            import os
            os.remove(config_path)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error connecting to MEGA: {str(e)}'})

# Global error handler for API routes to return JSON instead of HTML
@app.errorhandler(401)
def handle_unauthorized(e):
    if request.path.startswith('/api/'):
        return make_response(jsonify({'success': False, 'error': 'Unauthorized'}), 401)
    return e

@app.errorhandler(403)
def handle_forbidden(e):
    if request.path.startswith('/api/'):
        return make_response(jsonify({'success': False, 'error': 'Forbidden'}), 403)
    return e

@app.errorhandler(404)
def handle_not_found(e):
    if request.path.startswith('/api/'):
        return make_response(jsonify({'success': False, 'error': 'Not found'}), 404)
    return e

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static/img', 'favicon.ico')

# Run the app locally
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the SimpleSaferServer Flask app.")
    parser.add_argument('--host', default='0.0.0.0', help='Host to listen on (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5000, help='Port to listen on (default: 5000)')
    parser.add_argument('--debug', dest='debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--no-debug', dest='debug', action='store_false', help='Disable debug mode')
    parser.set_defaults(debug=False)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)
