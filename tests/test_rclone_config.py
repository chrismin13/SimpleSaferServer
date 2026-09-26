"""Exercise the shipped editor protocol with real rclone and disposable local data."""

import shutil
import time
import urllib.parse
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from flask import Flask

from simple_safer_server.services import runtime
from simple_safer_server.services.cloud_backup_service import CloudBackupService
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.file_persistence import locked_path
from simple_safer_server.services.rclone_config_service import (
    DRAFT_TTL_SECONDS,
    RcloneConfigService,
)
from simple_safer_server.web.problems import ApiProblem, ConflictProblem, ValidationProblem

pytestmark = pytest.mark.skipif(not shutil.which('rclone'), reason='Requires installed rclone')
OWNER = 'operator'


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv('SSS_MODE', 'fake')
    monkeypatch.setenv('SSS_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(runtime, '_runtime', None)
    monkeypatch.setattr(runtime, '_fake_state', None)
    rt = runtime.get_runtime()
    config = ConfigManager(runtime=rt)
    cloud = CloudBackupService(rt, config, None, None)
    instance = RcloneConfigService(rt, config, cloud)
    yield instance
    instance.close()


@pytest.fixture
def oauth_listener(tmp_path_factory):
    # OAuth backends share rclone's fixed callback port, including across
    # pytest-xdist workers. Serialize just the tests that open that listener.
    root = tmp_path_factory.getbasetemp()
    if root.name.startswith('popen-gw'):
        root = root.parent
    with locked_path(root / 'oauth-listener.lock'):
        yield


def call(service, action, data=None, owner=OWNER):
    return service.dispatch(owner, action, data or {})


def settle(service, result):
    deadline = time.monotonic() + 8
    while result['phase'] == 'pending' and time.monotonic() < deadline:
        time.sleep(0.025)
        result = call(service, 'poll', result)
    assert result['phase'] != 'pending'
    return result


def local_draft(service, name='backup', purpose='destination', path=None):
    path = path or service.runtime.cloud_target_dir
    path.mkdir(parents=True, exist_ok=True)
    result = settle(
        service, call(service, 'start', {'name': name, 'type': 'alias', 'purpose': purpose})
    )
    for _ in range(10):
        if result['phase'] == 'ready':
            return result
        option = result['option']
        answer = str(path) if option['Name'] == 'remote' else option['DefaultStr']
        result = settle(service, call(service, 'advance', {**result, 'answer': answer}))
    pytest.fail('Alias did not finish configuration')


def save(service, result, path='Backups'):
    return call(service, 'save', {**result, 'path': path, 'acknowledged': True})


def raw(service, text, destination='', enabled=False):
    return call(
        service,
        'apply_raw',
        {
            'config': text,
            'destination': destination,
            'enabled': enabled,
            'acknowledged': True,
            'version': call(service, 'raw')['version'],
        },
    )


def manage(service, name, operation, new_name=''):
    return call(
        service,
        'manage',
        {
            'name': name,
            'operation': operation,
            'new_name': new_name,
            'version': call(service, 'state')['version'],
        },
    )


def test_dynamic_questions_back_cancel_and_private_file_permissions(service):
    result = settle(service, call(service, 'start', {'name': 'cloud', 'type': 's3'}))
    assert result['option']['Name'] == 'provider'
    assert any(item['Value'] == 'Cloudflare' for item in result['option']['Examples'])
    first = result['option']
    worker = service.drafts[OWNER].worker
    assert worker.path.stat().st_mode & 0o777 == 0o600
    assert worker.path.parent.stat().st_mode & 0o777 == 0o700
    result = settle(service, call(service, 'advance', {**result, 'answer': 'Cloudflare'}))
    assert result['option']['Name'] == 'env_auth'
    result = call(service, 'back', result)
    assert result['option'] == first
    assert call(service, 'state')['remotes'] == []
    call(service, 'cancel', result)
    assert worker.process.poll() is not None
    assert not worker.path.exists()
    assert not service.path.exists()


def test_create_folder_save_edit_and_reopen_durable_configuration(service):
    result = local_draft(service)
    call(service, 'mkdir', {**result, 'path': '', 'name': 'Server files'})
    assert call(service, 'folders', {**result, 'path': ''})['folders'][0]['Name'] == 'Server files'
    assert save(service, result, 'Server files')['destination']['path'] == 'Server files'
    assert service.path.stat().st_mode & 0o777 == 0o600
    edited = local_draft(service, purpose='edit')
    save(service, edited)
    other = RcloneConfigService(service.runtime, service.config_manager, service.cloud)
    try:
        assert call(other, 'state')['destination'] == {'name': 'backup', 'path': 'Server files'}
        assert call(other, 'state')['enabled']
    finally:
        other.close()


@pytest.mark.parametrize('absolute', [False, True])
def test_folder_actions_use_the_same_destination_as_backup(
    service, tmp_path, monkeypatch, absolute
):
    cwd = tmp_path / 'worker-cwd'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    destination = tmp_path / 'destination' if absolute else cwd / 'destination'
    destination.mkdir()
    (destination / 'intended').mkdir()
    path = str(destination) if absolute else 'destination'
    if absolute:
        # RC remote paths are relative to fs even when they begin with '/'.
        # A matching relative directory makes the wrong listing look valid.
        wrong_destination = cwd / path.lstrip('/')
        wrong_destination.mkdir(parents=True)
        (wrong_destination / 'wrong-directory').mkdir()

    raw(service, '[disk]\ntype = local\n')
    result = call(service, 'start', {'name': 'disk', 'purpose': 'choose'})
    listing = call(service, 'folders', {**result, 'path': path})
    assert [entry['Name'] for entry in listing['folders']] == ['intended']
    call(service, 'mkdir', {**result, 'path': path, 'name': 'created'})
    assert (destination / 'created').is_dir()
    if absolute:
        assert not (wrong_destination / 'created').exists()
    assert save(service, result, path)['destination_text'] == 'disk:' + path


def test_advanced_snapshot_refreshes_destination_and_enabled_with_its_version(service):
    text = '[disk]\ntype = local\n'
    old_page = raw(service, text, 'disk:old', True)
    raw(service, text, 'disk:new', False)
    snapshot = call(service, 'raw')
    assert snapshot['destination_text'] == 'disk:new'
    assert snapshot['enabled'] is False
    assert snapshot['version'] != old_page['version']

    result = call(
        service,
        'apply_raw',
        {
            'config': snapshot['config'],
            'destination': snapshot['destination_text'],
            'enabled': snapshot['enabled'],
            'version': snapshot['version'],
        },
    )
    assert result['destination_text'] == 'disk:new'
    assert result['enabled'] is False


def test_edit_preserves_unknown_values_and_other_existing_remotes(service):
    text = '[cloud]\ntype = s3\nprovider = Cloudflare\ncustom_key = 100% keep\n\n[other]\ntype = local\n'
    raw(service, text, 'cloud:bucket/path with spaces', True)
    result = settle(service, call(service, 'start', {'name': 'cloud', 'purpose': 'edit'}))
    assert result['option']['DefaultStr'] == 'Cloudflare'
    call(service, 'cancel', result)
    assert call(service, 'raw')['config'] == text
    assert call(service, 'state')['destination']['path'] == 'bucket/path with spaces'


@pytest.mark.parametrize('action', ['cancel', 'save'])
def test_token_only_draft_publishes_once_and_cleans_up(service, monkeypatch, action):
    text = '[cloud]\ntype = dropbox\ntoken = old\n\n[other]\ntype = drive\ntoken = old\n'
    raw(service, text, 'cloud:Backups', True)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    # Model rclone refreshing credentials in its private file during folder browsing.
    refreshed = text.replace('token = old', 'token = refreshed').replace('type =', 'type=')
    draft.worker.path.write_text(refreshed)
    publishing = service._publishing
    publications = []

    @contextmanager
    def track_publication():
        publications.append(True)
        with publishing():
            yield

    monkeypatch.setattr(service, '_publishing', track_publication)
    if action == 'cancel':
        # Cancellation must not roll back destination settings changed elsewhere.
        service.cloud.save_destination('other:Elsewhere', False)
        call(service, action, result)
        assert service._settings() == ('other:Elsewhere', 'false')
    else:
        save(service, result)
        assert service._settings() == ('cloud:Backups', 'true')
    assert service.path.read_text() == refreshed
    assert service.path.stat().st_mode & 0o777 == 0o600
    assert len(publications) == 1
    assert OWNER not in service.drafts
    assert draft.worker.process.poll() is not None
    assert not draft.worker.path.exists()


@pytest.mark.parametrize(
    'candidate',
    [
        '[cloud]\ntype = dropbox\ntoken = old\n',
        '[cloud]\ntype=dropbox\ntoken=old\n',
        '[cloud]\ntype = drive\ntoken = refreshed\n',
        '[cloud]\ntype = dropbox\ntoken = refreshed\nclient_id = edited\n',
        '[cloud]\ntype = dropbox\ntoken = refreshed\n\n[new]\ntype = local\n',
        '[cloud]\ntype = dropbox\n',
        '',
        'invalid config',
    ],
)
def test_cancel_discards_drafts_without_only_refreshed_tokens(service, candidate):
    text = '[cloud]\ntype = dropbox\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    draft.worker.path.write_text(candidate)
    with locked_path(service.lock_path):
        assert call(service, 'cancel', result) == {}
    assert service.path.read_text() == text
    assert OWNER not in service.drafts
    assert draft.worker.process.poll() is not None
    assert not draft.worker.path.exists()


def test_cancel_checks_saved_config_under_publication_lock(service, monkeypatch):
    text = '[cloud]\ntype = dropbox\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    draft.worker.path.write_text(text.replace('old', 'refreshed'))
    external = text.replace('old', 'externally-refreshed')
    publishing = service._publishing

    @contextmanager
    def concurrent_publication():
        with publishing():
            service.path.write_text(external)
            yield

    monkeypatch.setattr(service, '_publishing', concurrent_publication)
    call(service, 'cancel', result)
    assert service.path.read_text() == external
    assert OWNER not in service.drafts
    assert not draft.worker.path.exists()


def test_cancel_keeps_refreshed_tokens_for_retry_when_backup_holds_lock(service):
    text = '[cloud]\ntype = dropbox\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    refreshed = text.replace('old', 'refreshed')
    draft.worker.path.write_text(refreshed)
    with locked_path(service.lock_path):
        with pytest.raises(ConflictProblem, match='backup or another save'):
            call(service, 'cancel', result)
    assert service.path.read_text() == text
    assert service.drafts[OWNER] is draft
    assert draft.worker.path.read_text() == refreshed
    call(service, 'cancel', result)
    assert service.path.read_text() == refreshed
    assert OWNER not in service.drafts


def test_manage_and_dependency_guards(service):
    save(service, local_draft(service))
    manage(service, 'backup', 'duplicate', 'spare')
    state = manage(service, 'backup', 'rename', 'primary')
    assert state['destination']['name'] == 'primary'
    assert len(state['remotes']) == 2
    with pytest.raises(ValidationProblem, match='another backup destination'):
        manage(service, 'primary', 'delete')
    assert len(manage(service, 'spare', 'delete')['remotes']) == 1
    raw(
        service,
        service.path.read_text() + '\n[encrypted]\ntype = crypt\nremote = primary:secret\n',
        'primary:Backups',
        True,
    )
    with pytest.raises(ValidationProblem, match='Referenced by encrypted'):
        manage(service, 'primary', 'rename', 'newname')


def test_name_collision_and_stale_draft_do_not_overwrite_configuration(service):
    save(service, local_draft(service))
    with pytest.raises(ValidationProblem, match='already in use'):
        call(service, 'start', {'name': 'backup', 'type': 'local'})
    result = local_draft(service, name='another')
    service.path.write_text(service.path.read_text() + '\n[external]\ntype = local\n')
    with pytest.raises(ConflictProblem, match='changed while editing'):
        save(service, result)
    assert 'external' in service.path.read_text()


def test_raw_validation_stale_version_and_preserve_disabled_destination(service):
    save(service, local_draft(service))
    version = call(service, 'state')['version']
    with pytest.raises(ValidationProblem, match='remote:folder'):
        raw(service, '[new]\ntype = local\n', 'backup:Backups', True)
    call(service, 'settings', {'enabled': False, 'version': version})
    assert call(service, 'state')['destination']['name'] == 'backup'
    with pytest.raises(ConflictProblem, match='changed'):
        call(
            service,
            'apply_raw',
            {
                'config': '[new]\ntype = local\n',
                'destination': 'new:/tmp',
                'enabled': True,
                'acknowledged': True,
                'version': version,
            },
        )
    assert call(service, 'state')['remotes'][0]['name'] == 'backup'
    raw(service, '[new]\ntype = local\n', 'new:/tmp', True)
    assert call(service, 'state')['destination'] == {'name': 'new', 'path': '/tmp'}


def test_draft_ownership_revision_expiration_and_backup_lock(service):
    result = local_draft(service)
    with pytest.raises(ConflictProblem):
        call(service, 'poll', result, owner='another-browser')
    with pytest.raises(ConflictProblem, match='question changed'):
        save(service, {**result, 'revision': -1})
    with locked_path(service.lock_path):
        with pytest.raises(ConflictProblem, match='backup or another save'):
            save(service, result)
    worker = service.drafts[OWNER].worker
    service.drafts[OWNER].touched -= DRAFT_TTL_SECONDS + 1
    assert call(service, 'state')['draft'] is None
    assert worker.process.poll() is not None


def test_failed_settings_save_restores_rclone_file(service, monkeypatch):
    raw(service, '[keep]\ntype = local\n')
    result = local_draft(service)
    previous = service.path.read_text()

    def fail(*args):
        raise ApiProblem('Timer update failed')

    monkeypatch.setattr(service.cloud, 'save_destination', fail)
    with pytest.raises(ApiProblem):
        save(service, result)
    assert service.path.read_text() == previous
    assert call(service, 'state')['draft'] is not None


def test_external_callback_url_is_rejected_without_contacting_it(service, monkeypatch):
    result = local_draft(service)
    monkeypatch.setattr(
        service,
        'oauth_target',
        lambda draft: urllib.parse.urlsplit('http://127.0.0.1:53682/auth?state=expected'),
    )
    for url in [
        'https://example.com/?code=x&state=expected',
        'http://localhost:123/?code=x&state=expected',
        'http://localhost:53682/?code=x&state=wrong',
        'http://localhost:bad/?code=x&state=expected',
    ]:
        with pytest.raises(ValidationProblem, match='complete localhost callback'):
            call(service, 'oauth_return', {**result, 'url': url})


def test_oauth_browser_handoff_and_command_fallback(service, oauth_listener):
    result = settle(service, call(service, 'start', {'name': 'signin', 'type': 'drive'}))
    for _ in range(20):
        option = result['option']
        if option['Name'] == 'config_is_local':
            break
        result = settle(
            service, call(service, 'advance', {**result, 'answer': option['DefaultStr']})
        )
    else:
        pytest.fail('No shared OAuth choice')
    if not result['oauth_supported']:
        pytest.skip('Installed rclone lacks OAuth status API')
    result = call(service, 'advance', {**result, 'answer': 'true'})
    deadline = time.monotonic() + 5
    while result['phase'] == 'pending' and not result['oauth'] and time.monotonic() < deadline:
        time.sleep(0.025)
        result = call(service, 'poll', result)
    assert result['phase'] == 'pending' and result['oauth']
    # Resolve the loopback redirect only; no account or provider is contacted.
    address = urllib.parse.urlsplit(call(service, 'oauth_link', result)['url'])
    assert address.scheme == 'https' and address.hostname == 'accounts.google.com'
    result = call(service, 'back', result)
    assert result['option']['Name'] == 'config_is_local'
    assert service.drafts[OWNER].worker.call('config/oauthstatus')['status'] == 'stopped'
    result = settle(service, call(service, 'advance', {**result, 'answer': 'false'}))
    assert result['option']['Name'] == 'config_token'
    assert 'rclone authorize' in result['option']['Help']


def test_editor_routes_enforce_admin_setup_boundary_json_header_and_no_cache(service, monkeypatch):
    from simple_safer_server.routes import rclone_config as routes
    from simple_safer_server.services import user_manager
    from simple_safer_server.web.api import json_problem

    app = Flask(__name__)
    app.secret_key = 'testing-only'
    app.extensions['simple_safer_server'] = SimpleNamespace(rclone_config_service=service)
    app.register_blueprint(routes.rclone_config)
    app.register_error_handler(ApiProblem, json_problem)
    admin = SimpleNamespace(reload_users=lambda: None, is_admin=lambda name: name == 'admin')
    # Setup tests reload their module with test doubles. Patch the globals
    # captured by this blueprint's decorator, regardless of import order.
    setup_globals = routes.setup_api_access_required.__globals__
    monkeypatch.setitem(
        setup_globals, 'config_manager', SimpleNamespace(is_setup_complete=lambda: False)
    )
    monkeypatch.setattr(user_manager, 'UserManager', lambda: admin)
    client = app.test_client()
    headers = {'X-SSS-Rclone': '1'}
    base = '/api/setup/cloud-backup/rclone/'
    assert client.get(base + 'state').status_code == 403
    response = client.get(base + 'state', headers=headers)
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    assert 'config' not in response.json['data']
    assert client.post(base + 'start', json=[], headers=headers).status_code == 400
    assert client.get(base + 'save', headers=headers).status_code == 400
    assert client.post(base + 'core/command', json={}, headers=headers).status_code == 404
    monkeypatch.setitem(
        setup_globals, 'config_manager', SimpleNamespace(is_setup_complete=lambda: True)
    )
    assert client.get(base + 'state', headers=headers).status_code == 401
    assert client.get('/api/cloud_backup/rclone/state', headers=headers).status_code == 401
    monkeypatch.setitem(setup_globals, 'user_manager', admin)
    with client.session_transaction() as session:
        session['username'] = 'member'
    assert client.get(base + 'state', headers=headers).status_code == 403
    with client.session_transaction() as session:
        session['username'] = 'admin'
    assert client.get(base + 'raw', headers=headers).status_code == 200


def test_browser_callback_completes_real_rclone_token_exchange(service, oauth_listener):
    """Exercise the entire callback relay with a local OAuth token issuer."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    exchanges = []

    class TokenEndpoint(BaseHTTPRequestHandler):
        def do_POST(self):
            exchanges.append(
                urllib.parse.parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
            )
            body = json.dumps(
                {
                    'access_token': 'test-access',
                    'refresh_token': 'test-refresh',
                    'token_type': 'Bearer',
                    'expires_in': 3600,
                }
            ).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), TokenEndpoint) as issuer:
        thread = threading.Thread(target=issuer.serve_forever, daemon=True)
        thread.start()
        try:
            text = (
                '[oauth]\ntype = dropbox\nclient_id = local-test\nclient_secret = local-test-secret\n'
                'auth_url = https://example.invalid/authorize\n'
                f'token_url = http://127.0.0.1:{issuer.server_port}/token\n'
            )
            raw(service, text)
            result = settle(service, call(service, 'start', {'name': 'oauth', 'purpose': 'edit'}))
            for _ in range(30):
                option = result['option']
                if option['Name'] == 'config_is_local':
                    break
                result = settle(
                    service, call(service, 'advance', {**result, 'answer': option['DefaultStr']})
                )
            else:
                pytest.fail('No OAuth choice')
            if not result['oauth_supported']:
                pytest.skip('Installed rclone lacks OAuth status API')
            result = call(service, 'advance', {**result, 'answer': 'true'})
            deadline = time.monotonic() + 5
            while (
                result['phase'] == 'pending' and not result['oauth'] and time.monotonic() < deadline
            ):
                time.sleep(0.025)
                result = call(service, 'poll', result)
            assert result['oauth']
            link = urllib.parse.urlsplit(call(service, 'oauth_link', result)['url'])
            assert link.hostname == 'example.invalid'
            params = urllib.parse.parse_qs(link.query)
            callback = (
                params['redirect_uri'][0]
                + '?'
                + urllib.parse.urlencode({'state': params['state'][0], 'code': 'local-code'})
            )
            result = settle(service, call(service, 'oauth_return', {**result, 'url': callback}))
            assert result['phase'] == 'ready', result.get('error')
            assert exchanges[0]['code'] == ['local-code']
            # Tokens stay in the private draft until the administrator saves.
            assert 'test-refresh' not in service.path.read_text()
            save(service, result)
            assert 'test-refresh' in service.path.read_text()
        finally:
            issuer.shutdown()
            thread.join(5)


def test_password_questions_are_saved_in_rclone_obscured_form(service):
    result = settle(
        service, call(service, 'start', {'name': 'web', 'type': 'webdav', 'purpose': 'add'})
    )
    password_seen = False
    for _ in range(20):
        if result['phase'] == 'ready':
            break
        option = result['option']
        answer = {
            'url': 'https://example.invalid',
            'user': 'test-user',
            'pass': 'local-test-password',
        }.get(option['Name'], option['DefaultStr'])
        if option['Name'] == 'pass':
            assert option['IsPassword']
            password_seen = True
        result = settle(service, call(service, 'advance', {**result, 'answer': answer}))
    assert password_seen and result['phase'] == 'ready'
    save(service, result)
    assert 'local-test-password' not in service.path.read_text()
    assert 'pass = ' in service.path.read_text()
    original = service.path.read_text()
    result = settle(service, call(service, 'start', {'name': 'web', 'purpose': 'edit'}))
    for _ in range(20):
        if result['phase'] == 'ready':
            break
        result = settle(
            service, call(service, 'advance', {**result, 'answer': result['option']['DefaultStr']})
        )
    save(service, result)
    assert service.path.read_text() == original


def test_unreadable_import_keeps_destination_available_for_advanced_repair(service):
    service.cloud.save_destination('existing:Backups', True)
    service.path.parent.mkdir(parents=True, exist_ok=True)
    service.path.write_text('RCLONE_ENCRYPT_V0:\nencrypted-content\n')
    state = call(service, 'state')
    assert state['enabled'] is True
    assert state['destination_text'] == 'existing:Backups'
    assert 'encrypted' in state['configuration_error']
    assert state['remotes'] == []
    raw(service, '[existing]\ntype = local\n', 'existing:Backups', True)
    assert call(service, 'state')['configuration_error'] == ''
