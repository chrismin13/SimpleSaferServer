# sudo apt install python3-flask python3-psutil python3-xgboost python3-joblib python3-pandas smartmontools python3-sklearn python3-flask-socketio
from flask import Flask, render_template, jsonify, request, abort, url_for, redirect, send_file, session, flash, current_app, make_response, send_from_directory
import subprocess
import psutil
from datetime import datetime, timedelta
import json
import os
import queue
import threading
from config_manager import ConfigManager
from drive_health import (
    SMART_FIELDS,
    append_telemetry,
    collect_hdsentinel_snapshot,
    get_hdsentinel_display_snapshot,
    get_hdsentinel_settings,
    get_optimal_threshold,
    get_smart_attributes,
    predict_failure_probability,
    run_scheduled_drive_health_check,
    save_hdsentinel_settings,
)
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

optimal_threshold = get_optimal_threshold(runtime)


def read_msmtp_config():
    """Read the current msmtp config and return the parsed values that this app manages."""
    msmtp_config = {}
    try:
        with open(runtime.msmtp_config_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        return msmtp_config

    for line in content.split('\n'):
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

    return msmtp_config


# a service can either be running right now, or could have succeeded or failed last time it ran
class Status:
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILURE = "Failure"
    MISSING = "Missing"
    NOT_RUN_YET = "Not Run Yet"
    ERROR = "Error"
    STOPPED = "Stopped"

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
            with fake_task_lock:
                thread = fake_task_threads.get(self.name)
                cancel_event = fake_task_cancel_events.get(self.name)
                is_running = bool(thread and thread.is_alive() and cancel_event)
                if is_running:
                    cancel_event.set()
            if is_running:
                fake_state.append_task_log(self.name, f"Stopped {self.name} in fake mode.")
            else:
                fake_state.append_task_log(self.name, f"Stop requested for {self.name}, but it was not running.")
            # Keep stop idempotent in fake mode so the UI does not fail on repeated clicks.
            fake_state.set_task_state(self.name, status=Status.STOPPED)
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
                if request.accept_mimetypes.best == 'application/json':
                    return jsonify({"success": True, "redirect": url_for('dashboard')})
                return redirect(url_for('dashboard'))
            else:
                msg = 'This account does not have administrator privileges. Only administrators can access the SimpleSaferServer management interface. Please contact your system administrator for access or view the accompanying documentation for information on how to mount any network file shares that you have been given access to.'
                if request.accept_mimetypes.best == 'application/json':
                    return jsonify({"success": False, "message": msg})
                flash(msg, 'error')
                return render_template('login.html')
        else:
            msg = 'Invalid username or password'
            if request.accept_mimetypes.best == 'application/json':
                return jsonify({"success": False, "message": msg})
            flash(msg, 'error')
    
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
        app.logger.exception("Failed to stop task %s", task_name)
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({"success": False, "message": str(e)}), 500
        return redirect(url_for("task_detail", task_name=task_name))


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
    missing_attrs = []
    settings_message = None
    settings_error = None
    hdsentinel_settings = get_hdsentinel_settings(config_manager)
    hdsentinel_snapshot = get_hdsentinel_display_snapshot(
        config_manager,
        system_utils,
        runtime=runtime,
    )

    if request.method == "POST":
        form_action = request.form.get("form_action", "run_health_check")
        if form_action == "save_hdsentinel_settings":
            try:
                save_hdsentinel_settings(
                    config_manager,
                    enabled=request.form.get("hdsentinel_enabled") == "on",
                    health_change_alert=request.form.get("hdsentinel_health_change_alert") == "on",
                )
                hdsentinel_settings = get_hdsentinel_settings(config_manager)
                # Refresh the snapshot after saving settings so the UI immediately
                # reflects the current monitoring state (including when monitoring
                # has just been enabled).
                hdsentinel_snapshot = collect_hdsentinel_snapshot(
                    config_manager,
                    system_utils,
                    runtime=runtime,
                )
                settings_message = "HDSentinel settings saved successfully."
            except Exception as exc:
                settings_error = f"Failed to save HDSentinel settings: {exc}"
        else:
            smart, missing_attrs = get_smart_attributes(
                config_manager,
                system_utils,
                runtime=runtime,
            )
            if smart is None:
                error = "Could not retrieve SMART data"
            else:
                prob = predict_failure_probability(smart, runtime=runtime)
                if prob is not None:
                    prediction = int(prob >= optimal_threshold)
                    probability = prob
                    append_telemetry(smart, prediction, runtime=runtime)
                else:
                    error = "Model not loaded"

            if hdsentinel_settings["enabled"]:
                hdsentinel_snapshot = collect_hdsentinel_snapshot(
                    config_manager,
                    system_utils,
                    runtime=runtime,
                )

    return render_template(
        "drive_health.html",
        smart=smart,
        prediction=prediction,
        probability=probability,
        error=error,
        missing_attrs=missing_attrs,
        smart_fields=SMART_FIELDS,
        hdsentinel_settings=hdsentinel_settings,
        hdsentinel_snapshot=hdsentinel_snapshot,
        settings_message=settings_message,
        settings_error=settings_error,
    )


@app.route("/download_telemetry")
@login_required
def download_telemetry():
    if runtime.telemetry_path.exists():
        return send_file(runtime.telemetry_path, as_attachment=True)
    abort(404)


def run_fake_cloud_backup(cancel_event: threading.Event):
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

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

    def _drain_stream(stream, stream_name: str):
        try:
            for line in iter(stream.readline, ''):
                output_queue.put((stream_name, line))
        finally:
            stream.close()

    stdout_thread = threading.Thread(
        target=_drain_stream,
        args=(proc.stdout, 'stdout'),
        name='fake-cloud-backup-stdout',
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_stream,
        args=(proc.stderr, 'stderr'),
        name='fake-cloud-backup-stderr',
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    while True:
        while True:
            try:
                stream_name, chunk = output_queue.get_nowait()
            except queue.Empty:
                break
            if stream_name == 'stdout':
                stdout_chunks.append(chunk)
            else:
                stderr_chunks.append(chunk)

        if proc.poll() is not None:
            break
        if cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            break
        time.sleep(0.1)

    stdout_thread.join(timeout=1.0)
    stderr_thread.join(timeout=1.0)
    while True:
        try:
            stream_name, chunk = output_queue.get_nowait()
        except queue.Empty:
            break
        if stream_name == 'stdout':
            stdout_chunks.append(chunk)
        else:
            stderr_chunks.append(chunk)

    output = ''.join(stdout_chunks + stderr_chunks)
    if output.strip():
        fake_state.append_task_log('Cloud Backup', output.strip())
    if cancel_event.is_set():
        raise RuntimeError('Cloud backup was cancelled.')
    if proc.returncode != 0:
        raise RuntimeError(output.strip() or 'Cloud backup failed.')


fake_task_threads: dict[str, threading.Thread] = {}
fake_task_cancel_events: dict[str, threading.Event] = {}
fake_task_lock = threading.Lock()


def start_fake_task(task_name: str):
    with fake_task_lock:
        existing_thread = fake_task_threads.get(task_name)
        if existing_thread and existing_thread.is_alive():
            raise RuntimeError(f'{task_name} is already running.')

        cancel_event = threading.Event()
        fake_task_cancel_events[task_name] = cancel_event

        fake_state.set_task_state(task_name, status=Status.RUNNING)
        fake_state.append_task_log(task_name, f'Starting {task_name} in fake mode.')

        thread = threading.Thread(
            target=run_fake_task,
            args=(task_name, cancel_event),
            name=f'fake-task-{task_name.lower().replace(" ", "-")}',
            daemon=True,
        )
        fake_task_threads[task_name] = thread
        thread.start()


def run_fake_task(task_name: str, cancel_event: threading.Event):
    start_time = datetime.now()
    try:
        if task_name == 'Check Mount':
            mount_point = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
            if not os.path.isdir(mount_point):
                raise RuntimeError(f'Backup source folder not found: {mount_point}')
            if cancel_event.is_set():
                raise RuntimeError('Task was cancelled.')
            if not fake_state.is_mounted(mount_point):
                fake_state.set_mount(True, mount_point=mount_point)
                fake_state.append_task_log(task_name, f'Found local backup source at {mount_point}; marking it as connected.')
            fake_state.append_task_log(task_name, f'Backup source available at {mount_point}.')
        elif task_name == 'Drive Health Check':
            if cancel_event.is_set():
                raise RuntimeError('Task was cancelled.')
            result = run_scheduled_drive_health_check(config_manager, system_utils, runtime=runtime)
            probability = result.get('probability')
            if probability is not None:
                fake_state.append_task_log(task_name, f'Drive health probability: {probability:.4f}')
            else:
                fake_state.append_task_log(task_name, 'Model unavailable; using sample SMART data only.')

            hdsentinel_snapshot = result.get('hdsentinel', {}).get('snapshot')
            if hdsentinel_snapshot and hdsentinel_snapshot.get('available'):
                fake_state.append_task_log(
                    task_name,
                    (
                        'HDSentinel status: '
                        f"health {hdsentinel_snapshot.get('health_pct')}%, "
                        f"performance {hdsentinel_snapshot.get('performance_pct')}%, "
                        f"temperature {hdsentinel_snapshot.get('temperature_c')}C"
                    ),
                )
            elif hdsentinel_snapshot and hdsentinel_snapshot.get('error'):
                fake_state.append_task_log(task_name, f"HDSentinel unavailable: {hdsentinel_snapshot['error']}")
        elif task_name == 'Cloud Backup':
            run_fake_cloud_backup(cancel_event)

        if cancel_event.is_set():
            raise RuntimeError('Task was cancelled.')

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
        if cancel_event.is_set():
            fake_state.set_task_state(
                task_name,
                status=Status.STOPPED,
                last_run=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                last_run_duration=f'{duration}s',
            )
        else:
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
                fake_task_cancel_events.pop(task_name, None)


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
@app.route('/api/alerts/generate-test', methods=['POST'])
@admin_required
def api_generate_test_alerts():
    """Debug route: Generate test alerts for UI testing. Only available in fake/dev mode."""
    if not runtime.is_fake:
        return jsonify({'success': False, 'error': 'Not available in production mode'}), 403
    try:
        config_manager.log_alert("Test Error", "This is a simulated error message to verify UI styling.", alert_type="error", source="System Test")
        config_manager.log_alert("Test Warning", "This is a simulated warning message. Things might be wrong.", alert_type="warning", source="System Test")
        config_manager.log_alert("Test Success", "This is a simulated success message. Everything is great!", alert_type="success", source="System Test")
        config_manager.log_alert("Test Info", "This is a simulated info message just letting you know something happened.", alert_type="info", source="System Test")
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("Error generating test alerts")
        return jsonify({'success': False, 'error': 'Failed to generate test alerts'}), 500

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
        msmtp_config = read_msmtp_config()
        # Get email address and from address from config manager as well
        email_address = config_manager.get_value('backup', 'email_address', '')
        from_address = config_manager.get_value('backup', 'from_address', '')
        if email_address and 'email_address' not in msmtp_config:
            msmtp_config['email_address'] = email_address
        if from_address and 'from_address' not in msmtp_config:
            msmtp_config['from_address'] = from_address

        has_smtp_password = bool(msmtp_config.get('smtp_password'))
        msmtp_config.pop('smtp_password', None)

        return jsonify({'success': True, 'config': msmtp_config, 'has_smtp_password': has_smtp_password})
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
        smtp_password = (data.get('smtp_password') or '').strip()

        if not all([email, from_address, smtp_server, smtp_port, smtp_username]):
            return jsonify({'success': False, 'error': 'Email, from address, SMTP server, port, and username are required'})

        if not smtp_password:
            smtp_password = read_msmtp_config().get('smtp_password', '')
        if not smtp_password:
            return jsonify({'success': False, 'error': 'SMTP password is required'})

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
        return jsonify({'success': True, 'message': f'User {username} deleted successfully'})
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
        smart, missing_attrs = get_smart_attributes(config_manager, system_utils, runtime=runtime)
        if smart is None:
            return jsonify({'status': 'unknown', 'probability': None, 'temperature': None})
        prob = predict_failure_probability(smart, runtime=runtime)
        if prob is not None:
            temperature = smart.get('smart_194_raw', None)
            status = 'good' if prob < optimal_threshold else 'warning'
            response = {
                'status': status,
                'probability': prob,
                'temperature': temperature
            }
            hdsentinel_snapshot = get_hdsentinel_display_snapshot(config_manager, system_utils, runtime=runtime)
            hdsentinel_settings = get_hdsentinel_settings(config_manager)
            hdsentinel_enabled = False
            if isinstance(hdsentinel_settings, dict):
                hdsentinel_enabled = bool(hdsentinel_settings.get('enabled'))
            else:
                hdsentinel_enabled = bool(getattr(hdsentinel_settings, 'enabled', False))
            if hdsentinel_enabled and hdsentinel_snapshot and hdsentinel_snapshot.get('available'):
                response['hdsentinel_health'] = hdsentinel_snapshot.get('health_pct')
                response['hdsentinel_performance'] = hdsentinel_snapshot.get('performance_pct')
            return jsonify(response)
        else:
            return jsonify({'status': 'unknown', 'probability': None, 'temperature': None})
    except Exception as e:
        return jsonify({'status': 'unknown', 'probability': None, 'temperature': None})

@app.route("/mount", methods=["POST"])
@login_required
def dashboard_mount_drive():
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
        return jsonify({'success': False, 'error': 'Could not load backup settings.'})

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
        return jsonify({'success': False, 'error': 'Could not save backup settings.'})

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
