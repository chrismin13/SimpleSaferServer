import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Tuple

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_socketio import SocketIO

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.adapters.rclone import RcloneAdapter
from simple_safer_server.adapters.storage_commands import StorageCommandAdapter
from simple_safer_server.adapters.systemd import SystemdAdapter
from simple_safer_server.routes.alerts import alerts as alerts_routes
from simple_safer_server.routes.cloud_backup import cloud_backup as cloud_backup_routes
from simple_safer_server.routes.ddns import ddns as ddns_routes
from simple_safer_server.routes.drive_health import drive_health as drive_health_routes
from simple_safer_server.routes.server_identity import server_identity as server_identity_routes
from simple_safer_server.routes.setup_wizard import setup
from simple_safer_server.routes.smb import smb as smb_routes
from simple_safer_server.routes.storage import storage as storage_routes
from simple_safer_server.routes.system_updates import system_updates as system_updates_routes
from simple_safer_server.routes.tasks import tasks as task_routes
from simple_safer_server.routes.users import users as users_routes
from simple_safer_server.services.alert_notifications import AlertNotifier
from simple_safer_server.services.alerts_service import AlertsService
from simple_safer_server.services.app_updates import AppUpdateManager
from simple_safer_server.services.cloud_backup_service import CloudBackupService
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.container import AppServices
from simple_safer_server.services.ddns_service import DdnsService
from simple_safer_server.services.disabled_timers import DisabledTimerService
from simple_safer_server.services.drive_health import DriveHealthSummaryService
from simple_safer_server.services.runtime import get_fake_state, get_flask_secret_key, get_runtime
from simple_safer_server.services.server_identity import ServerIdentityService
from simple_safer_server.services.smb_manager import SMB_DOCS_URL, SMBManager
from simple_safer_server.services.storage_service import StorageService
from simple_safer_server.services.system_updates import SystemUpdatesManager
from simple_safer_server.services.system_utils import SystemUtils
from simple_safer_server.services.task_service import TaskService
from simple_safer_server.services.user_manager import UserManager, admin_required
from simple_safer_server.web.api import json_data, json_problem
from simple_safer_server.web.problems import (
    ApiProblem,
    ForbiddenProblem,
    NotFoundProblem,
    UnauthorizedProblem,
)


def create_app() -> Tuple[Flask, SocketIO]:
    runtime = get_runtime()
    fake_state = get_fake_state() if runtime.is_fake else None
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    # Keep the session secret stable across deploys so a restart does not
    # invalidate every login cookie when the app's config directory persists.
    app.secret_key = get_flask_secret_key(runtime)
    # Use Flask-SocketIO's threading backend unless a future real-time feature
    # needs a different async worker. Eventlet is deprecated and noisy in dev.
    socketio = SocketIO(app, async_mode="threading")
    user_manager = UserManager(runtime=runtime)

    system_utils = SystemUtils(runtime=runtime)
    smb_manager = SMBManager(runtime=runtime)

    log_dir = str(runtime.logs_dir)
    os.makedirs(log_dir, exist_ok=True)
    runtime.volatile_dir.mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
    )
    handler = next(
        (
            existing_handler
            for existing_handler in app.logger.handlers
            if isinstance(existing_handler, RotatingFileHandler)
            and existing_handler.baseFilename == os.path.abspath(log_file)
        ),
        None,
    )
    if handler is None:
        handler = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5)
        app.logger.addHandler(handler)
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)
    app.logger.info("SimpleSaferServer startup")

    if (
        runtime.is_fake
        and os.environ.get("RAILWAY_PROJECT_ID")
        and not os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    ):
        app.logger.warning(
            "Railway volume is not attached. Fake-mode config under %s is ephemeral, so setup state will reset on deploy.",
            runtime.data_dir,
        )

    config_manager = ConfigManager(runtime=runtime)
    command_runner = CommandRunner()
    systemd_adapter = SystemdAdapter(command_runner)
    rclone_adapter = RcloneAdapter(command_runner)
    storage_command_adapter = StorageCommandAdapter(command_runner)
    alert_notifier = AlertNotifier(config_manager, runtime, logger=app.logger)
    disabled_timer_service = DisabledTimerService(
        runtime,
        systemd_adapter,
        alert_notifier=alert_notifier,
        logger=app.logger,
    )
    system_updates_manager = SystemUpdatesManager(config_manager, runtime=runtime)
    app_update_manager = AppUpdateManager(runtime=runtime)
    task_service = TaskService(
        runtime=runtime,
        fake_state=fake_state,
        config_manager=config_manager,
        system_utils=system_utils,
        logger=app.logger,
        command_runner=command_runner,
        systemd_adapter=systemd_adapter,
        rclone_adapter=rclone_adapter,
        disabled_timer_service=disabled_timer_service,
    )
    ddns_service = DdnsService(
        runtime=runtime,
        config_manager=config_manager,
        task_service=task_service,
        logger=app.logger,
    )
    cloud_backup_service = CloudBackupService(
        runtime=runtime,
        config_manager=config_manager,
        system_utils=system_utils,
        task_service=task_service,
        logger=app.logger,
        command_runner=command_runner,
    )
    alerts_service = AlertsService(
        runtime=runtime,
        config_manager=config_manager,
        system_utils=system_utils,
    )
    server_identity_service = ServerIdentityService(
        config_manager=config_manager,
        runtime=runtime,
    )
    storage_service = StorageService(
        runtime=runtime,
        fake_state=fake_state,
        config_manager=config_manager,
        command_adapter=storage_command_adapter,
    )
    drive_health_summary_service = DriveHealthSummaryService()
    app.extensions["simple_safer_server"] = AppServices(
        runtime=runtime,
        fake_state=fake_state,
        command_runner=command_runner,
        config_manager=config_manager,
        system_utils=system_utils,
        system_updates_manager=system_updates_manager,
        app_update_manager=app_update_manager,
        smb_manager=smb_manager,
        user_manager=user_manager,
        task_service=task_service,
        ddns_service=ddns_service,
        cloud_backup_service=cloud_backup_service,
        alerts_service=alerts_service,
        server_identity_service=server_identity_service,
        storage_service=storage_service,
        drive_health_summary_service=drive_health_summary_service,
    )

    app.register_blueprint(setup)
    app.register_blueprint(task_routes)
    app.register_blueprint(ddns_routes)
    app.register_blueprint(cloud_backup_routes)
    app.register_blueprint(system_updates_routes)
    app.register_blueprint(alerts_routes)
    app.register_blueprint(server_identity_routes)
    app.register_blueprint(smb_routes)
    app.register_blueprint(users_routes)
    app.register_blueprint(storage_routes)
    app.register_blueprint(drive_health_routes)

    @app.route("/")
    def index():
        if not config_manager.is_setup_complete():
            return redirect(url_for("setup.setup_page"))
        return redirect(url_for("task_routes.dashboard"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not config_manager.is_setup_complete():
            return redirect(url_for("setup.setup_page"))
        if "username" in session:
            return redirect(url_for("task_routes.dashboard"))

        if request.method == "POST":
            user_manager.reload_users()

            username = request.form["username"]
            password = request.form["password"]

            if user_manager.verify_user(username, password):
                if user_manager.is_admin(username):
                    session["username"] = username
                    session.pop("skip_login_disabled", None)
                    if request.accept_mimetypes.best == "application/json":
                        return json_data({"redirect": url_for("task_routes.dashboard")})
                    return redirect(url_for("task_routes.dashboard"))
                msg = (
                    "This account does not have administrator privileges. Only administrators can access the "
                    "SimpleSaferServer management interface. Please contact your system administrator for access "
                    "or view the accompanying documentation for information on how to mount any network file "
                    "shares that you have been given access to."
                )
                if request.accept_mimetypes.best == "application/json":
                    return json_problem(
                        ForbiddenProblem(
                            msg,
                            title="Admin privileges required",
                            slug="login-admin-required",
                        )
                    )
                flash(msg, "error")
                return render_template("login.html")
            msg = "Invalid username or password"
            if request.accept_mimetypes.best == "application/json":
                return json_problem(
                    UnauthorizedProblem(msg, title="Login failed", slug="login-failed")
                )
            flash(msg, "error")

        return render_template("login.html")

    def get_auto_login_username():
        configured_username = config_manager.get_value("system", "username", "")
        user_manager.reload_users()
        return user_manager.get_preferred_admin_username(configured_username)

    @app.before_request
    def auto_login_fake_mode_user():
        if not runtime.is_fake or not runtime.skip_login:
            return None
        if request.endpoint in {"static"}:
            return None
        if session.get("skip_login_disabled"):
            return None
        if "username" in session:
            return None
        if not config_manager.is_setup_complete():
            return None

        username = get_auto_login_username()
        if username and user_manager.is_admin(username):
            session["username"] = username
            session["auto_logged_in"] = True
        return None

    @app.route("/network_file_sharing")
    @admin_required
    def network_file_sharing():
        backup_mount_point = config_manager.get_value(
            "backup", "mount_point", runtime.default_mount_point
        )
        return render_template(
            "network_file_sharing.html",
            username=session.get("username"),
            backup_mount_point=backup_mount_point,
            smb_docs_url=SMB_DOCS_URL,
        )

    @app.route("/logout")
    def logout():
        session.clear()
        if runtime.is_fake and runtime.skip_login:
            session["skip_login_disabled"] = True
        return redirect(url_for("login"))

    @app.context_processor
    def inject_template_context():
        username = session.get("username")

        def browser_title(page_name):
            hostname = ""
            try:
                # Page titles should identify the machine being administered,
                # but should not break page rendering if the host command is
                # unavailable during recovery or early setup.
                hostname = server_identity_service.current_identity().hostname.strip()
            except Exception:
                app.logger.exception("Failed to read hostname for browser title")
            host_label = hostname or "SimpleSaferServer"
            return f"{page_name} - {host_label}"

        return {
            "username": username,
            "runtime_mode": runtime.mode,
            "default_mount_point": runtime.default_mount_point,
            "browser_title": browser_title,
            # Expose admin status so templates can conditionally show admin-only nav items.
            "is_admin": user_manager.is_admin(username) if username else False,
        }

    @app.errorhandler(ApiProblem)
    def handle_api_problem(error):
        return json_problem(error)

    @app.errorhandler(401)
    def handle_unauthorized(error):
        if request.path.startswith("/api/"):
            return json_problem(UnauthorizedProblem("Unauthorized."))
        return error

    @app.errorhandler(403)
    def handle_forbidden(error):
        if request.path.startswith("/api/"):
            return json_problem(ForbiddenProblem("Forbidden."))
        return error

    @app.errorhandler(404)
    def handle_not_found(error):
        if request.path.startswith("/api/"):
            return json_problem(NotFoundProblem("Not found."))
        return error

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory("static/img", "favicon.ico")

    return app, socketio
