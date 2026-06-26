from __future__ import annotations

from flask import Blueprint, abort, current_app, render_template

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.module_checks import check_module_requirements
from simple_safer_server.core.module_lifecycle import (
    ModuleLifecycleError,
    apply_module,
    uninstall_module,
)
from simple_safer_server.core.module_serialization import (
    module_check_data,
    module_data,
    module_plan_data,
    ownership_record_data,
)
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import ConflictProblem, NotFoundProblem, OperationProblem

modules = Blueprint("module_routes", __name__)


def _registry():
    return create_builtin_module_registry()


def _runtime():
    return current_app.extensions["simple_safer_server"].runtime


def _module_or_problem(slug: str):
    try:
        return _registry().module_for_slug(slug)
    except KeyError:
        return json_problem(
            NotFoundProblem(
                gettext("Unknown module: {slug}").format(slug=slug),
                slug="module-not-found",
            )
        )


@modules.route("/api/modules", methods=["GET"])
@api_admin_required
def api_modules_list():
    registry = _registry()
    runtime = _runtime()
    return json_data({"modules": [module_data(module, runtime) for module in registry.list_modules()]})


@modules.route("/api/modules/<slug>/plan", methods=["GET"])
@api_admin_required
def api_modules_plan(slug):
    module = _module_or_problem(slug)
    if not hasattr(module, "build_plan"):
        return module
    return json_data(
        {"module": module_data(module, _runtime()), "plan": module_plan_data(module.build_plan())}
    )


@modules.route("/fragments/modules/<slug>/plan", methods=["GET"])
@admin_required
def module_plan_fragment(slug):
    try:
        module = _registry().module_for_slug(slug)
    except KeyError:
        abort(404)
    return render_template(
        "partials/module_plan_preview.html",
        module=module_data(module, _runtime()),
        plan=module_plan_data(module.build_plan()),
    )


@modules.route("/api/modules/<slug>/check", methods=["GET"])
@api_admin_required
def api_modules_check(slug):
    module = _module_or_problem(slug)
    if not hasattr(module, "build_plan"):
        return module
    return json_data(
        {
            "module": module_data(module, _runtime()),
            "check": module_check_data(check_module_requirements(module)),
        }
    )


@modules.route("/api/modules/<slug>/apply", methods=["POST"])
@api_admin_required
def api_modules_apply(slug):
    module = _module_or_problem(slug)
    if not hasattr(module, "build_plan"):
        return module
    try:
        result = apply_module(module, _runtime())
    except ModuleLifecycleError as exc:
        return json_problem(ConflictProblem(str(exc), slug="module-apply-not-available"))
    except Exception:
        current_app.logger.exception("Could not apply module %s", slug)
        return json_problem(OperationProblem(gettext("Could not apply module.")))
    return json_data(
        {
            "module_slug": result.module_slug,
            "recorded": [ownership_record_data(record) for record in result.recorded],
        },
        message=gettext("Recorded ownership for module: {module_slug}").format(
            module_slug=result.module_slug
        ),
    )


@modules.route("/api/modules/<slug>/uninstall", methods=["POST"])
@api_admin_required
def api_modules_uninstall(slug):
    module = _module_or_problem(slug)
    if not hasattr(module, "build_plan"):
        return module
    try:
        result = uninstall_module(module, _runtime())
    except ModuleLifecycleError as exc:
        return json_problem(ConflictProblem(str(exc), slug="module-uninstall-not-available"))
    except Exception:
        current_app.logger.exception("Could not uninstall module %s", slug)
        return json_problem(OperationProblem(gettext("Could not uninstall module.")))
    return json_data(
        {
            "module_slug": result.module_slug,
            "removed": [ownership_record_data(record) for record in result.removed],
            "removed_paths": list(result.removed_paths),
        },
        message=gettext("Removed ownership records for module: {module_slug}").format(
            module_slug=result.module_slug
        ),
    )
