import ast
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from user_manager import admin_required, api_admin_required


APP_SOURCE = Path(__file__).resolve().parents[1] / 'app.py'


def build_test_app():
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    @app.route('/login')
    def login():
        return 'login'

    @app.route('/page')
    @admin_required
    def page():
        return 'page ok'

    @app.route('/api/protected')
    @api_admin_required
    def api_protected():
        return {'success': True}

    return app


def test_admin_required_redirects_anonymous_users_to_login():
    app = build_test_app()

    with app.test_client() as client:
        response = client.get('/page')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')


def test_admin_required_clears_stale_non_admin_web_session():
    app = build_test_app()
    user_manager = MagicMock()
    user_manager.is_admin.return_value = False

    with patch('user_manager.UserManager', return_value=user_manager):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session['username'] = 'operator'

            response = client.get('/page')

            # A demoted account can still have a signed cookie from before the
            # role change, so the decorator has to clear that stale Web UI state.
            with client.session_transaction() as session:
                assert 'username' not in session

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')
    user_manager.is_admin.assert_called_once_with('operator')


def test_api_admin_required_returns_json_for_anonymous_users():
    app = build_test_app()

    with app.test_client() as client:
        response = client.get('/api/protected')

    assert response.status_code == 401
    assert response.get_json() == {'success': False, 'error': 'Please log in again.'}


def test_api_admin_required_clears_stale_non_admin_api_session():
    app = build_test_app()
    user_manager = MagicMock()
    user_manager.is_admin.return_value = False

    with patch('user_manager.UserManager', return_value=user_manager):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session['username'] = 'operator'

            response = client.get('/api/protected')

            with client.session_transaction() as session:
                assert 'username' not in session

    assert response.status_code == 403
    assert response.get_json() == {'success': False, 'error': 'Admin privileges required.'}
    user_manager.is_admin.assert_called_once_with('operator')


def test_api_admin_required_allows_admin_sessions():
    app = build_test_app()
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch('user_manager.UserManager', return_value=user_manager):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session['username'] = 'admin'

            response = client.get('/api/protected')

    assert response.status_code == 200
    assert response.get_json() == {'success': True}
    user_manager.is_admin.assert_called_once_with('admin')


def _decorator_name(decorator):
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
        return decorator.func.id
    return None


class AppRouteAuthorizationTests(unittest.TestCase):
    def test_system_update_api_routes_use_json_admin_guard(self):
        tree = ast.parse(APP_SOURCE.read_text())
        routes = {}

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            route_paths = []
            guard_names = set()
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == 'route' and decorator.args and isinstance(decorator.args[0], ast.Constant):
                        route_paths.append(decorator.args[0].value)
                else:
                    name = _decorator_name(decorator)
                    if name:
                        guard_names.add(name)
            for path in route_paths:
                routes[path] = guard_names

        system_update_api_routes = {
            path: guards
            for path, guards in routes.items()
            if path.startswith('/api/system_updates')
        }

        self.assertTrue(system_update_api_routes)
        self.assertTrue(all('api_admin_required' in guards for guards in system_update_api_routes.values()))
