"""The same credential editor for first-run setup and admin maintenance."""

import secrets

from flask import Blueprint, current_app, request, session

from simple_safer_server.routes.setup_wizard import setup_api_access_required
from simple_safer_server.services.user_manager import api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import (
    ApiProblem,
    ForbiddenProblem,
    OperationProblem,
    ValidationProblem,
)

rclone_config = Blueprint('rclone_config_routes', __name__)
READ_ACTIONS = {'state', 'providers', 'raw'}


def editor_action(action):
    # A custom header plus JSON requires a CORS preflight for cross-origin
    # requests. These routes deliberately do not enable CORS, including setup.
    if request.headers.get('X-SSS-Rclone') != '1':
        raise ForbiddenProblem('Open the connection editor in SimpleSaferServer.')
    if request.method == 'GET' and action not in READ_ACTIONS:
        raise ValidationProblem('This action requires a POST request.')
    request.max_content_length = 4 * 1024 * 1024
    data = json_request_data() if request.method == 'POST' else {}
    owner = session.setdefault('rclone_editor', secrets.token_urlsafe(32))
    try:
        service = current_app.extensions['simple_safer_server'].rclone_config_service
        return json_data(service.dispatch(owner, action, data))
    except ApiProblem:
        raise
    except Exception as exc:
        # Backend error strings and payloads can contain credentials. The
        # credential editor returns controlled provider errors without logging them.
        current_app.logger.error('Rclone editor failed (%s)', type(exc).__name__)
        return json_problem(
            OperationProblem(
                'Could not complete this connection action. Check that rclone is installed and retry.'
            )
        )


@rclone_config.route('/api/cloud_backup/rclone/<action>', methods=['GET', 'POST'])
@api_admin_required
def admin_action(action):
    return editor_action(action)


@rclone_config.route('/api/setup/cloud-backup/rclone/<action>', methods=['GET', 'POST'])
@setup_api_access_required
def setup_action(action):
    return editor_action(action)


@rclone_config.after_request
def no_credential_caching(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response
