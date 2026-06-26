from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.modules.system_updates.module import (
    create_module as create_system_updates_module,
)
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import ConflictProblem, OperationProblem

system_updates = Blueprint("system_updates_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _manager() -> Any:
    return _get_services().system_updates_manager


def _os_updates_read_only_problem():
    return json_problem(
        ConflictProblem(
            gettext(
                "Operating system update actions are read-only in SimpleSaferServer. "
                "Manage apt, stale locks, and Livepatch directly on the operating system."
            ),
            slug="system-updates-read-only",
        )
    )


def _system_updates_ui_text() -> dict[str, Any]:
    """Return the browser copy used by the System Updates page script."""
    _ = gettext
    return {
        "badges": {
            "eolSoon": _("EOL Soon"),
            "supported": _("Supported"),
            "pastSupport": _("Past support"),
            "datesPending": _("Dates pending"),
            "unknown": _("Unknown"),
            "locked": _("Locked"),
            "externalAptLock": _("External apt lock"),
            "free": _("Free"),
            "enabled": _("Enabled"),
            "manual": _("Manual"),
            "ubuntuOnly": _("Ubuntu only"),
            "installed": _("Installed"),
            "notInstalled": _("Not installed"),
            "upToDate": _("Up to date"),
            "updateAvailable": _("Update available"),
            "unavailable": _("Unavailable"),
        },
        "distribution": {
            "unknownLinux": _("Unknown Linux"),
            "unknown": _("Unknown"),
        },
        "operation": {
            "idle": _("Idle"),
            "packageManager": _("Package Manager"),
            "noAptOutput": _("No apt output yet."),
        },
        "settings": {
            "enabled": _("Enabled"),
            "disabled": _("Disabled"),
            "autocleanEveryDays": _("Every {days} day(s)"),
            "upgrades": _("Upgrades"),
            "listsOnly": _("Lists only"),
            "autoclean": _("Autoclean"),
            "manual": _("Manual"),
            "readOnlyHint": _(
                "Showing current system apt periodic policy. SSS does not install, enable, or configure automatic OS updates."
            ),
        },
        "livepatch": {
            "unavailableDetail": _("Livepatch status unavailable."),
            "notAvailable": _("Not available"),
            "protected": _("Protected"),
            "installed": _("Installed"),
            "notInstalled": _("Not installed"),
        },
        "application": {
            "title": _("Application"),
            "unavailableDetail": _("Application update status unavailable."),
            "installerArchive": _("Installer archive"),
            "package": _("Package"),
            "release": _("Release"),
            "unknown": _("Unknown"),
            "notTracked": _("Not tracked"),
            "notChecked": _("Not checked"),
            "refreshSuccess": _("Application update status refreshed."),
            "refreshFailure": _("Could not refresh application update status."),
            "started": _("Application update started."),
            "startFailure": _("Could not start application update."),
        },
        "errors": {
            "loadSummary": _("Could not load system updates."),
        },
    }


@system_updates.route("/system_updates")
@admin_required
def system_updates_page():
    return render_template(
        "system_updates.html",
        username=session.get("username"),
        system_updates_module=create_system_updates_module(),
        system_updates_ui_text=_system_updates_ui_text(),
    )


@system_updates.route("/api/system_updates/summary", methods=["GET"])
@api_admin_required
def api_system_updates_summary():
    try:
        manager = _manager()
        return json_data(
            {
                "distribution": manager.get_distribution_info(),
                "operation": manager.get_status(),
                "settings": manager.get_settings(),
                "livepatch": manager.get_livepatch_status(),
                "application": manager.get_application_update_status(fetch_remote=False),
            }
        )
    except Exception:
        current_app.logger.exception("Error loading system update summary")
        return json_problem(OperationProblem(gettext("Failed to load system update summary.")))


@system_updates.route("/api/system_updates/application/refresh", methods=["POST"])
@api_admin_required
def api_system_updates_application_refresh():
    try:
        return json_data({"application": _manager().get_application_update_status(fetch_remote=True)})
    except Exception:
        current_app.logger.exception("Error refreshing application update status")
        return json_problem(
            OperationProblem(gettext("Failed to refresh application update status."))
        )


@system_updates.route("/api/system_updates/application/update", methods=["POST"])
@api_admin_required
def api_system_updates_application_update():
    try:
        status = _manager().get_application_update_status(fetch_remote=False)
        return json_problem(
            ConflictProblem(
                status.get("message") or gettext("Application update is not available."),
                slug="application-update-not-available",
            )
        )
    except Exception:
        current_app.logger.exception("Could not start application update")
        return json_problem(OperationProblem(gettext("Could not start application update.")))


@system_updates.route("/api/system_updates/status", methods=["GET"])
@api_admin_required
def api_system_updates_status():
    try:
        return json_data({"operation": _manager().get_status()})
    except Exception:
        current_app.logger.exception("Error loading system update status")
        return json_problem(OperationProblem(gettext("Failed to load system update status.")))


@system_updates.route("/api/system_updates/<operation>/start", methods=["POST"])
@api_admin_required
def api_system_updates_start(operation):
    del operation
    return _os_updates_read_only_problem()


@system_updates.route("/api/system_updates/stop", methods=["POST"])
@api_admin_required
def api_system_updates_stop():
    return _os_updates_read_only_problem()


@system_updates.route("/api/system_updates/settings", methods=["POST"])
@api_admin_required
def api_system_updates_save_settings():
    return json_problem(
        ConflictProblem(
            gettext(
                "Automatic apt settings are read-only in SimpleSaferServer. "
                "Manage OS update policy outside SSS."
            ),
            slug="system-updates-settings-read-only",
        )
    )


@system_updates.route("/api/system_updates/remove_stale_locks", methods=["POST"])
@api_admin_required
def api_system_updates_remove_stale_locks():
    return _os_updates_read_only_problem()


@system_updates.route("/api/system_updates/livepatch/setup", methods=["POST"])
@api_admin_required
def api_system_updates_livepatch_setup():
    return _os_updates_read_only_problem()
