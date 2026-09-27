"""Exercise the shipped editor protocol with real rclone and disposable local data."""

import shutil
import time
import urllib.parse
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from flask import Flask

from simple_safer_server.adapters.rclone import RcloneAdapter
from simple_safer_server.adapters.rclone_config import RcloneError
from simple_safer_server.services import runtime
from simple_safer_server.services.cloud_backup_service import CloudBackupService
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.file_persistence import locked_path
from simple_safer_server.services.rclone_config_service import (
    DRAFT_TTL_SECONDS,
    RcloneConfigService,
    parse_config,
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


@pytest.mark.parametrize('scope', ['drive.file', 'drive,drive.metadata.readonly'])
def test_drive_scope_exposes_suggestions_and_accepts_custom_values(service, scope):
    result = settle(service, call(service, 'start', {'name': 'cloud', 'type': 'drive'}))
    for name in ('client_id', 'client_secret'):
        assert result['option']['Name'] == name
        result = settle(service, call(service, 'advance', {**result, 'answer': ''}))
    option = result['option']
    assert option['Name'] == 'scope'
    assert option['Type'] == 'string'
    assert not option['Exclusive']
    assert {example['Value'] for example in option['Examples']} >= {
        'drive',
        'drive.readonly',
        'drive.file',
        'drive.appfolder',
        'drive.metadata.readonly',
    }
    result = settle(service, call(service, 'advance', {**result, 'answer': scope}))
    assert not result['error']
    assert result['option']['Name'] != 'scope'
    assert f'scope = {scope}' in service.drafts[OWNER].worker.path.read_text()
    # Stop before authorization: this regression uses real provider metadata
    # and parsing without contacting Google or needing an account.
    result = call(service, 'back', result)
    assert result['option'] == option
    call(service, 'cancel', result)


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


def test_editor_and_backup_resolve_the_same_destination_without_ambient_overrides(
    service, tmp_path, monkeypatch
):
    chosen = tmp_path / 'chosen'
    overridden = tmp_path / 'overridden'
    source = tmp_path / 'source'
    for directory in (chosen, overridden, source):
        directory.mkdir()
    (chosen / 'confirmed-folder').mkdir()
    (overridden / 'unrelated-file.txt').write_text('keep this data')
    (source / 'source-file.txt').write_text('backup data')
    monkeypatch.setenv('RCLONE_CONFIG_BACKUP_REMOTE', str(overridden))
    raw(service, f'[backup]\ntype = alias\nremote = {chosen}\n', 'backup:', True)
    result = call(service, 'start', {'name': 'backup', 'purpose': 'choose'})
    folders = call(service, 'folders', {**result, 'path': ''})['folders']
    assert [folder['Name'] for folder in folders] == ['confirmed-folder']
    call(service, 'cancel', result)

    # Browsing and sync must resolve the same remote: a hidden environment
    # override must never redirect deletion into an unconfirmed destination.
    process = RcloneAdapter().sync(str(source), 'backup:', config_path=str(service.path))
    _, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stderr
    assert [path.name for path in chosen.iterdir()] == ['source-file.txt']
    assert (chosen / 'source-file.txt').read_text() == 'backup data'
    assert [path.name for path in overridden.iterdir()] == ['unrelated-file.txt']
    assert (overridden / 'unrelated-file.txt').read_text() == 'keep this data'


@pytest.mark.parametrize('absolute', [False, True])
@pytest.mark.parametrize('wrapped', [False, True])
def test_folder_actions_use_the_same_destination_as_backup(
    service, tmp_path, monkeypatch, absolute, wrapped
):
    cwd = tmp_path / 'worker-cwd'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    destination = tmp_path / 'destination'
    destination.mkdir()
    (destination / 'intended').mkdir()
    path = str(destination) if absolute else str(destination).lstrip('/')
    # A plausible destination under Gunicorn's different working directory
    # must never be browsed or changed by either editor or backup operations.
    wrong_destination = cwd / path.lstrip('/')
    wrong_destination.mkdir(parents=True)
    (wrong_destination / 'wrong-directory').mkdir()
    text = '[disk]\ntype = local\n'
    name = 'disk'
    if wrapped:
        with service._temporary_worker('') as worker:
            password = worker.call('core/obscure', {'clear': 'local-test-password'})['obscured']
        text += (
            f'\n[alias]\ntype = alias\nremote = disk:{path}\n'
            '\n[encrypted]\ntype = crypt\nremote = alias:\n'
            f'password = {password}\nfilename_encryption = off\ndirectory_name_encryption = false\n'
        )
        name, path = 'encrypted', ''
    raw(service, text)
    result = call(service, 'start', {'name': name, 'purpose': 'choose'})
    listing = call(service, 'folders', {**result, 'path': path})
    assert [entry['Name'] for entry in listing['folders']] == ['intended']
    call(service, 'mkdir', {**result, 'path': path, 'name': 'created'})
    assert (destination / 'created').is_dir()
    assert not (wrong_destination / 'created').exists()
    saved_destination = name + ':' + path
    assert save(service, result, path)['destination_text'] == saved_destination

    source = tmp_path / 'source'
    source.mkdir()
    (source / 'synced.txt').write_text('backup content')
    process = RcloneAdapter().sync(str(source), saved_destination, config_path=str(service.path))
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stdout + stderr
    # Crypt keeps a .bin suffix even with filename encryption disabled.
    stored_name = 'synced.txt.bin' if wrapped else 'synced.txt'
    assert (destination / stored_name).is_file()
    assert not (wrong_destination / stored_name).exists()
    assert (wrong_destination / 'wrong-directory').is_dir()


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


@pytest.mark.parametrize('action', ['folders', 'mkdir'])
def test_provider_refresh_is_available_to_backup_while_draft_stays_open(
    service, monkeypatch, action
):
    """Use real Box token refreshes, with all HTTP confined to a local issuer/proxy."""
    import json
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    exchanges, lock_observations = [], []
    next_token = 0

    class TokenEndpoint(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal next_token
            parameters = urllib.parse.parse_qs(
                self.rfile.read(int(self.headers['Content-Length'])).decode()
            )
            token = parameters.get('refresh_token', [''])[0]
            exchanges.append(token)
            try:
                with locked_path(service.lock_path, blocking=False):
                    lock_observations.append(False)
            except BlockingIOError:
                lock_observations.append(True)
            accepted = token == f'refresh-{next_token}'
            if accepted:
                next_token += 1
                payload = {
                    'access_token': f'access-{next_token}',
                    'refresh_token': f'refresh-{next_token}',
                    'token_type': 'Bearer',
                    'expires_in': 3600,
                }
            else:
                payload = {'error': 'invalid_grant', 'error_description': 'Token already used'}
            body = json.dumps(payload).encode()
            self.send_response(200 if accepted else 400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_CONNECT(self):
            # Fail folder access after OAuth succeeds, without contacting Box.
            self.send_error(502, 'Provider API disabled in this test')

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), TokenEndpoint) as issuer:
        thread = threading.Thread(target=issuer.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f'http://127.0.0.1:{issuer.server_port}'
            for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
                monkeypatch.setenv(key, endpoint)
            for key in ('NO_PROXY', 'no_proxy'):
                monkeypatch.setenv(key, '127.0.0.1,localhost')
            token = json.dumps(
                {
                    'access_token': 'expired',
                    'refresh_token': 'refresh-0',
                    'token_type': 'Bearer',
                    'expiry': '2000-01-01T00:00:00Z',
                }
            )
            raw(
                service,
                '[box]\ntype = box\nclient_id = local-test\nclient_secret = local-test\n'
                f'token_url = {endpoint}/token\ntoken = {token}\n',
                'box:Backups',
                True,
            )
            result = call(service, 'start', {'name': 'box', 'purpose': 'choose'})
            draft = service.drafts[OWNER]
            with pytest.raises(RcloneError):
                call(service, action, {**result, 'path': '', 'name': 'New folder'})
            assert exchanges == ['refresh-0']
            saved = parse_config(service.path.read_text())
            assert json.loads(saved.get('box', 'token'))['refresh_token'] == 'refresh-1'
            assert draft.base == service.path.read_text()
            assert draft.worker.process.poll() is not None

            # Model the next backup needing a refresh, while this same draft
            # remains open. The issuer rejects a token as soon as it is used.
            with locked_path(service.lock_path):
                latest = json.loads(saved.get('box', 'token'))
                latest['expiry'] = '2000-01-01T00:00:00Z'
                service.path.write_text(
                    service.path.read_text().replace(saved.get('box', 'token'), json.dumps(latest))
                )
                backup = subprocess.run(
                    [
                        'rclone',
                        'lsd',
                        'box:',
                        '--config',
                        str(service.path),
                        '--retries',
                        '1',
                        '--low-level-retries',
                        '1',
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            assert 'invalid_grant' not in backup.stderr
            assert exchanges == ['refresh-0', 'refresh-1']
            assert lock_observations == [True, True]

            # Reusing the draft must adopt the backup's newer credential and
            # still permit Save, without accepting unrelated configuration edits.
            with pytest.raises(RcloneError):
                call(service, action, {**result, 'path': '', 'name': 'New folder'})
            assert exchanges == ['refresh-0', 'refresh-1']
            assert 'refresh-2' in draft.worker.path.read_text()
            assert draft.base == service.path.read_text()
            assert save(service, result)['destination_text'] == 'box:Backups'
        finally:
            issuer.shutdown()
            thread.join(5)


@pytest.mark.parametrize('action', ['folders', 'mkdir', 'advance'])
def test_provider_work_does_not_start_while_backup_owns_configuration(service, monkeypatch, action):
    result = local_draft(service)
    draft = service.drafts[OWNER]
    if action == 'advance':
        draft.output = {'State': 'question', 'Option': {'Name': 'value'}}
    calls = []
    monkeypatch.setattr(draft.worker, 'call', lambda *args, **kwargs: calls.append(args))
    with locked_path(service.lock_path):
        with pytest.raises(ConflictProblem, match='backup or another editor action'):
            call(service, action, {**result, 'name': 'New folder', 'answer': ''})
    assert calls == []
    assert draft.provider_lock is None


def test_busy_backup_does_not_leave_an_unreturned_configuration_draft(service):
    with locked_path(service.lock_path):
        with pytest.raises(ConflictProblem, match='backup or another editor action'):
            call(service, 'start', {'name': 'new', 'type': 'alias'})
    assert service.drafts == {}


def test_keeping_token_question_default_cannot_restore_a_superseded_token(service, monkeypatch):
    text = '[cloud]\ntype = box\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    draft.output = {'State': 'question', 'Option': {'Name': 'token', 'DefaultStr': 'old'}}
    service.path.write_text(text.replace('old', 'newer'))
    original_call = draft.worker.call
    answers = []

    def answer_question(endpoint, payload=None, **kwargs):
        if endpoint == 'config/update':
            answers.append(payload['opt']['result'])
            return {'jobid': 123}
        if endpoint == 'job/status':
            return {'finished': True, 'success': True, 'output': {}}
        return original_call(endpoint, payload, **kwargs)

    monkeypatch.setattr(draft.worker, 'call', answer_question)
    result = call(service, 'advance', {**result, 'answer': 'old'})
    assert answers == ['newer']
    result = call(service, 'back', result)
    assert result['option']['DefaultStr'] == 'newer'
    assert parse_config(draft.worker.path.read_text()).get('cloud', 'token') == 'newer'
    assert service.path.read_text() == draft.base


@pytest.mark.parametrize('failure', ['before-replace', 'after-replace'])
def test_failed_token_publication_keeps_backup_blocked_until_retry(service, monkeypatch, failure):
    from simple_safer_server.services import rclone_config_service as module

    text = '[cloud]\ntype = box\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    original_call, write = draft.worker.call, module.atomic_write_text

    def refresh(endpoint, *args, **kwargs):
        if endpoint == 'operations/list':
            draft.worker.path.write_text(text.replace('old', 'rotated'))
            return {'list': []}
        return original_call(endpoint, *args, **kwargs)

    def fail_saved_write(path, *args, **kwargs):
        if path == service.path:
            if failure == 'after-replace':
                write(path, *args, **kwargs)
            raise OSError('Cannot persist token')
        return write(path, *args, **kwargs)

    monkeypatch.setattr(draft.worker, 'call', refresh)
    monkeypatch.setattr(module, 'atomic_write_text', fail_saved_write)
    with pytest.raises(OSError, match='Cannot persist'):
        call(service, 'folders', result)
    assert draft.worker.process.poll() is not None
    assert draft.provider_lock is not None
    with pytest.raises(BlockingIOError), locked_path(service.lock_path, blocking=False):
        pytest.fail('Backup read invalidated credentials')
    monkeypatch.setattr(module, 'atomic_write_text', write)
    call(service, 'poll', result)
    with locked_path(service.lock_path, blocking=False):
        assert 'rotated' in service.path.read_text()
    assert draft.provider_lock is None
    assert draft.base == service.path.read_text()
    save(service, result)


@pytest.mark.parametrize(
    'completion', ['poll', 'failure', 'janitor', 'back', 'cancel', 'expire', 'close']
)
def test_async_config_owns_lock_until_tokens_are_published(service, monkeypatch, completion):
    text = '[cloud]\ntype = box\ntoken = old\n\n[backup]\ntype = alias\nremote = cloud:Saved\n'
    raw(service, text, 'backup:Backups', True)
    result = settle(service, call(service, 'start', {'name': 'backup', 'purpose': 'edit'}))
    draft = service.drafts[OWNER]
    original_call = draft.worker.call
    finished = False

    def configure(endpoint, *args, **kwargs):
        if endpoint == 'config/update':
            draft.worker.path.write_text(
                text.replace('token = old', 'token = rotated').replace(
                    'cloud:Saved', 'cloud:Unsaved'
                )
            )
            return {'jobid': 123}
        if endpoint == 'job/status':
            return {
                'finished': finished,
                'success': completion != 'failure',
                'output': {},
                'error': 'Provider rejected configuration',
            }
        if endpoint == 'config/oauthstatus':
            return {'status': 'stopped'}
        return original_call(endpoint, *args, **kwargs)

    monkeypatch.setattr(draft.worker, 'call', configure)
    result = call(service, 'advance', {**result, 'answer': 'cloud:Unsaved'})
    assert result['phase'] == 'pending'
    assert service.path.read_text() == text
    assert draft.worker.process.poll() is None
    with pytest.raises(BlockingIOError), locked_path(service.lock_path, blocking=False):
        pytest.fail('Backup ran while configuration could still rotate tokens')
    finished = True
    if completion == 'janitor':
        ticks = iter([False, True])
        touched = draft.touched
        janitor = SimpleNamespace(
            _stop=SimpleNamespace(wait=lambda timeout: next(ticks)),
            lock=service.lock,
            drafts=service.drafts,
            _recover_pending=service._recover_pending,
            _poll_draft=service._poll_draft,
            _expire=service._expire,
        )
        RcloneConfigService._cleanup_loop(janitor)
        assert draft.touched == touched
        result = draft.view()
    elif completion == 'expire':
        draft.touched -= DRAFT_TTL_SECONDS + 1
        call(service, 'state')
    elif completion == 'close':
        service.close()
    else:
        result = call(service, 'poll' if completion == 'failure' else completion, result)
    with locked_path(service.lock_path, blocking=False):
        saved = parse_config(service.path.read_text())
        assert saved.get('cloud', 'token') == 'rotated'
        assert saved.get('backup', 'remote') == 'cloud:Saved'
    assert draft.provider_lock is None
    if completion == 'back':
        assert parse_config(draft.worker.path.read_text()).get('cloud', 'token') == 'rotated'
        assert parse_config(draft.worker.path.read_text()).get('backup', 'remote') == 'cloud:Saved'
    else:
        assert draft.worker.process.poll() is not None
    if completion in {'poll', 'janitor'}:
        assert draft.base == service.path.read_text()
        save(service, result)
        assert parse_config(service.path.read_text()).get('backup', 'remote') == 'cloud:Unsaved'
    elif completion in {'cancel', 'expire', 'close'}:
        assert OWNER not in service.drafts
        assert not draft.worker.path.exists()


def test_provider_timeout_stops_worker_before_snapshot_and_unlock(service, monkeypatch):
    text = '[cloud]\ntype = box\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    original_call, close = draft.worker.call, draft.worker.close
    request_in_progress = False

    def timed_out(endpoint, *args, **kwargs):
        nonlocal request_in_progress
        if endpoint == 'operations/list':
            request_in_progress = True
            raise RcloneError('RC request timed out')
        return original_call(endpoint, *args, **kwargs)

    def stop_writer():
        nonlocal request_in_progress
        close()
        if request_in_progress:
            with pytest.raises(BlockingIOError), locked_path(service.lock_path, blocking=False):
                pytest.fail('Lock released while a timed-out request was still writing')
            # The HTTP caller timed out before rclone finished persisting its token.
            draft.worker.path.write_text(text.replace('old', 'rotated'))
            request_in_progress = False

    monkeypatch.setattr(draft.worker, 'call', timed_out)
    monkeypatch.setattr(draft.worker, 'close', stop_writer)
    with pytest.raises(RcloneError, match='timed out'):
        call(service, 'folders', result)
    with locked_path(service.lock_path, blocking=False):
        assert 'rotated' in service.path.read_text()
    assert draft.worker.process.poll() is not None
    assert draft.base == service.path.read_text()


@pytest.mark.parametrize('change', ['identity', 'unrelated', 'edited-identity-token'])
def test_provider_reconciliation_rejects_unsafe_concurrent_changes(service, monkeypatch, change):
    text = '[cloud]\ntype = box\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    if change == 'identity':
        saved = text + 'client_id = changed\n'
    elif change == 'unrelated':
        saved = text + '\n[other]\ntype = local\n'
    else:
        draft.worker.path.write_text(text + 'client_id = unsaved\n')
        saved = text.replace('old', 'newer')
    private = draft.worker.path.read_text()
    service.path.write_text(saved)
    calls = []
    monkeypatch.setattr(draft.worker, 'call', lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ConflictProblem, match='changed while editing'):
        call(service, 'folders', result)
    assert calls == []
    assert service.path.read_text() == saved
    assert draft.worker.path.read_text() == private
    assert draft.base == text
    with locked_path(service.lock_path, blocking=False):
        pass


def test_failed_private_token_reload_never_publishes_an_older_credential(service, monkeypatch):
    from simple_safer_server.services import rclone_config_service as module

    text = '[cloud]\ntype = box\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    newer = text.replace('old', 'newer')
    service.path.write_text(newer)
    write = module.atomic_write_text

    def fail_private_write(path, *args, **kwargs):
        if path == draft.worker.path:
            raise OSError('Cannot reload private credentials')
        return write(path, *args, **kwargs)

    monkeypatch.setattr(module, 'atomic_write_text', fail_private_write)
    with pytest.raises(OSError, match='Cannot reload'):
        call(service, 'folders', result)
    assert service.path.read_text() == newer
    assert draft.worker.path.read_text() == text
    assert draft.base == text
    assert draft.worker.process.poll() is not None
    with locked_path(service.lock_path, blocking=False):
        pass


@pytest.mark.parametrize(
    'candidate',
    [
        '[cloud]\ntype = dropbox\ntoken = old\n',
        '[cloud]\ntype=dropbox\ntoken=old\n',
        '[cloud]\ntype = drive\ntoken = refreshed\n',
        '[cloud]\ntype = dropbox\ntoken = refreshed\nclient_id = edited\n',
        '[cloud]\ntype = dropbox\n',
        '[cloud]\ntype = dropbox\ntoken =\n',
        '',
        'invalid config',
    ],
)
def test_cancel_discards_drafts_without_safe_refreshed_tokens(service, candidate):
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


@pytest.mark.parametrize('cleanup', ['cancel', 'expire'])
def test_cleanup_keeps_upstream_tokens_while_discarding_other_connection_edits(service, cleanup):
    text = (
        '[cloud]\ntype = box\ntoken = old\n'
        '\n[edited]\ntype = drive\nclient_id = original\ntoken = original\n'
        '\n[removed]\ntype = drive\ntoken = retained\n'
    )
    raw(service, text, 'cloud:Backups', True)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    # Browsing a new alias/crypt connection can rotate its saved upstream's
    # single-use token. Edits to other identities must still be discarded.
    draft.worker.path.write_text(
        '[cloud]\ntype = box\ntoken = refreshed\n'
        '\n[edited]\ntype = drive\nclient_id = changed\ntoken = other-identity\n'
        '\n[new]\ntype = alias\nremote = cloud:Backups\n'
    )
    if cleanup == 'expire':
        draft.touched -= DRAFT_TTL_SECONDS + 1
    with locked_path(service.lock_path):
        if cleanup == 'cancel':
            with pytest.raises(ConflictProblem, match='backup or another editor action'):
                call(service, 'cancel', result)
        else:
            assert call(service, 'state')['draft']['id'] == draft.identifier
        assert service.path.read_text() == text
        assert draft.worker.path.exists()

    if cleanup == 'cancel':
        call(service, 'cancel', result)
    else:
        assert call(service, 'state')['draft'] is None
    expected = parse_config(text)
    expected.set('cloud', 'token', 'refreshed')
    assert parse_config(service.path.read_text()) == expected
    assert service._settings() == ('cloud:Backups', 'true')
    assert service.path.stat().st_mode & 0o777 == 0o600
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


@pytest.mark.parametrize('cleanup', ['cancel', 'expire', 'close'])
def test_token_cleanup_preserves_unrelated_concurrent_connection_changes(service, cleanup):
    text = '[cloud]\ntype = box\ntoken = old\n\n[other]\ntype = local\n'
    raw(service, text, 'cloud:Backups', True)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    call(
        service,
        'manage',
        {
            'name': 'other',
            'operation': 'rename',
            'new_name': 'renamed',
            'version': call(service, 'raw')['version'],
        },
        owner='other-admin',
    )
    # Model a provider rotating a single-use token while the first admin
    # browses. A concurrent unrelated edit must not strand the old token.
    draft.worker.path.write_text(
        text.replace('token = old', 'token = rotated')
        + '\n[unsaved]\ntype = alias\nremote = cloud:Temporary\n'
    )
    with pytest.raises(ConflictProblem, match='changed while editing'):
        save(service, result)
    if cleanup == 'cancel':
        call(service, 'cancel', result)
    elif cleanup == 'expire':
        draft.touched -= DRAFT_TTL_SECONDS + 1
        call(service, 'state')
    else:
        service.close()
        service.close()  # Shutdown and its atexit hook may both run.
    saved = parse_config(service.path.read_text())
    assert saved.sections() == ['cloud', 'renamed']
    assert saved.get('cloud', 'token') == 'rotated'
    assert service._settings() == ('cloud:Backups', 'true')
    assert OWNER not in service.drafts
    assert not draft.worker.path.exists()
    assert draft.worker.process.poll() is not None


@pytest.mark.parametrize(
    'current',
    [
        '[cloud]\ntype = box\ntoken = newer\n',
        '[cloud]\ntype = box\ntoken = old\nclient_id = other-account\n',
        '[cloud]\ntype = drive\ntoken = old\n',
        '[renamed]\ntype = box\ntoken = old\n',
    ],
)
def test_token_cleanup_never_replaces_a_durably_changed_remote(service, current):
    text = '[cloud]\ntype = box\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    service.drafts[OWNER].worker.path.write_text(text.replace('old', 'rotated'))
    service.path.write_text(current)
    call(service, 'cancel', result)
    assert service.path.read_text() == current


@pytest.mark.parametrize('failure', ['backup-lock', 'config-write'])
def test_shutdown_queues_credentials_and_startup_retries_without_editor_requests(
    service, monkeypatch, failure
):
    import json

    from simple_safer_server.services import rclone_config_service as module

    text = '[cloud]\ntype = box\ntoken = old\n'
    raw(service, text, 'cloud:Backups', True)
    call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    draft.worker.path.write_text(
        text.replace('old', 'rotated') + '\n[unsaved]\ntype = ftp\npass = unsaved-secret\n'
    )
    write = module.atomic_write_text
    blocked = True

    def fail_config_write(path, *args, **kwargs):
        if path == service.path and blocked:
            raise OSError('Cannot publish configuration')
        return write(path, *args, **kwargs)

    @contextmanager
    def block_publication():
        if failure == 'backup-lock':
            with locked_path(service.lock_path):
                yield
        else:
            monkeypatch.setattr(module, 'atomic_write_text', fail_config_write)
            yield

    monkeypatch.setattr(module, 'CLEANUP_INTERVAL_SECONDS', 0.01)
    replacement = None
    try:
        with block_publication():
            start = time.monotonic()
            service.close()
            assert time.monotonic() - start < 3
            assert service.path.read_text() == text
            records = list(service.recovery_root.glob('*.json'))
            assert len(records) == 1
            record = json.loads(records[0].read_text())
            assert parse_config(record['config']).get('cloud', 'token') == 'rotated'
            assert 'unsaved-secret' not in records[0].read_text()
            assert records[0].stat().st_mode & 0o777 == 0o600
            assert service.recovery_root.stat().st_mode & 0o777 == 0o700
            assert draft.worker.process.poll() is not None
            assert not draft.worker.path.exists()
            assert not service.drafts

            # Construction must start retrying even if nobody loads a page.
            replacement = RcloneConfigService(
                service.runtime, service.config_manager, service.cloud
            )
            assert replacement._janitor.is_alive()
            assert records[0].exists()
        blocked = False
        deadline = time.monotonic() + 3
        while records[0].exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not records[0].exists()
        assert parse_config(service.path.read_text()).get('cloud', 'token') == 'rotated'
        assert service._settings() == ('cloud:Backups', 'true')

        # Replaying a record after a crash between publish and unlink must not
        # replace a newer saved credential or unrelated durable configuration.
        current = '[cloud]\ntype = box\ntoken = newest\n\n[other]\ntype = local\n'
        with replacement.lock:
            write(records[0], json.dumps(record), mode=0o600)
            write(service.path, current, mode=0o600)
            replacement._recover_pending()
        assert service.path.read_text() == current
        assert not records[0].exists()
    finally:
        if replacement:
            replacement.close()


def test_shutdown_retains_workspace_if_both_publication_and_recovery_writes_fail(
    service, monkeypatch, caplog
):
    import gc

    from simple_safer_server.services import rclone_config_service as module

    text = '[cloud]\ntype = box\ntoken = old\n'
    raw(service, text)
    call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    workspace = draft.worker.path
    workspace.write_text(text.replace('old', 'private-rotated-token'))

    def fail_write(*args, **kwargs):
        raise OSError('private error details')

    monkeypatch.setattr(module, 'atomic_write_text', fail_write)
    monkeypatch.setattr(module, 'atomic_write_json', fail_write)
    service.close()
    assert draft.worker.process.poll() is not None
    assert workspace.exists()
    assert service.path.read_text() == text
    assert 'retained for manual credential recovery' in caplog.text
    assert str(workspace) in caplog.text
    assert 'private-rotated-token' not in caplog.text
    assert 'private error details' not in caplog.text

    # Finalizing TemporaryDirectory must not erase the last recovery copy.
    del service.drafts[OWNER]
    del draft
    gc.collect()
    assert parse_config(workspace.read_text()).get('cloud', 'token') == 'private-rotated-token'
    shutil.rmtree(workspace.parent)


def test_cancel_keeps_refreshed_tokens_for_retry_when_backup_holds_lock(service):
    text = '[cloud]\ntype = dropbox\ntoken = old\n'
    raw(service, text)
    result = call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    refreshed = text.replace('old', 'refreshed')
    draft.worker.path.write_text(refreshed)
    with locked_path(service.lock_path):
        with pytest.raises(ConflictProblem, match='backup or another editor action'):
            call(service, 'cancel', result)
    assert service.path.read_text() == text
    assert service.drafts[OWNER] is draft
    assert draft.worker.path.read_text() == refreshed
    call(service, 'cancel', result)
    assert service.path.read_text() == refreshed
    assert OWNER not in service.drafts


def test_expiration_preserves_refreshed_tokens(service):
    text = '[cloud]\ntype = dropbox\ntoken = old\n'
    raw(service, text, 'cloud:Backups', True)
    call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    refreshed = text.replace('old', 'refreshed')
    draft.worker.path.write_text(refreshed)
    draft.touched -= DRAFT_TTL_SECONDS + 1

    assert call(service, 'state')['draft'] is None
    assert service.path.read_text() == refreshed
    assert service._settings() == ('cloud:Backups', 'true')
    assert draft.worker.process.poll() is not None
    assert not draft.worker.path.exists()


@pytest.mark.parametrize('changed_elsewhere', [False, True])
def test_expiration_retries_busy_token_publication_without_extending_ttl(
    service, changed_elsewhere
):
    text = '[cloud]\ntype = dropbox\ntoken = old\n'
    raw(service, text)
    call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    refreshed = text.replace('old', 'refreshed')
    draft.worker.path.write_text(refreshed)
    # Unchanged expired drafts need no publication and must still be cleaned
    # while another draft waits for the backup's token-writing lock.
    call(service, 'start', {'name': 'cloud', 'purpose': 'choose'}, owner='other')
    draft.touched -= DRAFT_TTL_SECONDS + 1
    expired_at = draft.touched
    service.drafts['other'].touched -= DRAFT_TTL_SECONDS + 1

    with locked_path(service.lock_path):
        for _ in range(2):
            assert call(service, 'state')['draft']['id'] == draft.identifier
            assert service.drafts == {OWNER: draft}
            assert draft.touched == expired_at
            assert draft.worker.path.read_text() == refreshed
        if changed_elsewhere:
            service.path.write_text(text.replace('old', 'external'))

    # A retry runs immediately once the lock is free, rather than waiting for
    # another full TTL, and cannot overwrite the backup's newer configuration.
    assert call(service, 'state')['draft'] is None
    assert service.path.read_text() == (
        text.replace('old', 'external') if changed_elsewhere else refreshed
    )
    assert not draft.worker.path.exists()


def test_expiration_retries_a_failed_token_write(service, monkeypatch):
    from simple_safer_server.services import rclone_config_service as module

    text = '[cloud]\ntype = dropbox\ntoken = old\n'
    raw(service, text)
    call(service, 'start', {'name': 'cloud', 'purpose': 'choose'})
    draft = service.drafts[OWNER]
    refreshed = text.replace('old', 'refreshed')
    draft.worker.path.write_text(refreshed)
    draft.touched -= DRAFT_TTL_SECONDS + 1
    write = module.atomic_write_text

    def fail_write(*args, **kwargs):
        raise OSError('Cannot publish configuration')

    monkeypatch.setattr(module, 'atomic_write_text', fail_write)
    assert call(service, 'state')['draft']['id'] == draft.identifier
    assert service.path.read_text() == text
    monkeypatch.setattr(module, 'atomic_write_text', write)
    assert call(service, 'state')['draft'] is None
    assert service.path.read_text() == refreshed


def test_cleanup_loop_survives_an_unexpected_worker_failure(caplog):
    import threading

    ticks = iter([False, False, True])
    attempts = []

    def expire():
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError('private credential detail')

    janitor = SimpleNamespace(
        _stop=SimpleNamespace(wait=lambda timeout: next(ticks)),
        lock=threading.RLock(),
        drafts={},
        _recover_pending=lambda: None,
        _expire=expire,
    )
    RcloneConfigService._cleanup_loop(janitor)
    assert len(attempts) == 2
    assert 'RuntimeError' in caplog.text
    assert 'private credential detail' not in caplog.text


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
        with pytest.raises(ConflictProblem, match='backup or another editor action'):
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
            # The saved identity is unchanged, so its token must be available
            # to backups even if the administrator leaves the editor open.
            assert 'test-refresh' in service.path.read_text()
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
