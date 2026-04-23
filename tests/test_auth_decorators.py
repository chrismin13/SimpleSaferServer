from unittest.mock import MagicMock, patch

from flask import Flask

from user_manager import admin_required, api_admin_required


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
