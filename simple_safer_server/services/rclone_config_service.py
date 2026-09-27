"""Guided rclone configuration, isolated drafts, and backup destination selection."""

import atexit
import configparser
import copy
import hashlib
import http.client
import io
import json
import logging
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from simple_safer_server.adapters.rclone_config import NoRedirect, RcloneError, RcloneWorker
from simple_safer_server.services.file_persistence import (
    atomic_write_json,
    atomic_write_text,
    locked_path,
)
from simple_safer_server.web.problems import ApiProblem, ConflictProblem, ValidationProblem

DRAFT_TTL_SECONDS = 1800
CLEANUP_INTERVAL_SECONDS = 60
MAX_DRAFTS = 4
MAX_CONFIG_BYTES = 1024 * 1024
# Match rclone's portable config names, including Unicode letters and digits.
REMOTE_NAME = re.compile(r'^[\w.+@][\w .+@-]*$', re.UNICODE)


class RcloneConfigParser(configparser.RawConfigParser):
    """Preserve rclone option names instead of INI's default lowercasing."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def parse_config(text: str) -> configparser.RawConfigParser:
    if len(text.encode()) > MAX_CONFIG_BYTES:
        raise ValidationProblem('The rclone configuration exceeds 1 MiB.')
    if text.lstrip().startswith('RCLONE_ENCRYPT_V'):
        raise ValidationProblem(
            'This rclone config is encrypted. Use rclone config to decrypt it before editing here.'
        )
    parser = RcloneConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error:
        # ConfigParser exceptions can quote secret-bearing lines.
        raise ValidationProblem(
            'Invalid rclone configuration. Check section names and keys.'
        ) from None
    if parser.defaults() or any(not parser.get(s, 'type', fallback='') for s in parser.sections()):
        raise ValidationProblem(
            'Each remote needs a [name] section and a type; DEFAULT is not a remote.'
        )
    return parser


def validate_name(name: str) -> str:
    if not REMOTE_NAME.fullmatch(name) or name.endswith(' ') or len(name) > 128:
        raise ValidationProblem(
            'Use letters, numbers, underscores, dots, +, @, spaces or hyphens (up to 128 characters). Do not start with a space or hyphen, or end with a space.'
        )
    return name


@dataclass
class ConfigDraft:
    owner: str
    name: str
    provider: str
    worker: RcloneWorker
    directory: Any
    base: str
    settings_base: tuple[str, str]
    purpose: str
    identifier: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    revision: int = 0
    touched: float = field(default_factory=time.monotonic)
    output: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    job: int | None = None
    oauth_supported: bool = False
    oauth: bool = False
    provider_lock: AbstractContextManager | None = None

    def view(self) -> dict:
        return {
            'id': self.identifier,
            'revision': self.revision,
            'name': self.name,
            'type': self.provider,
            'purpose': self.purpose,
            'phase': 'pending'
            if self.job is not None
            else ('question' if self.output.get('State') else 'ready'),
            'option': self.output.get('Option'),
            'error': self.output.get('Error', ''),
            'can_back': bool(self.history),
            'oauth': self.oauth,
            'oauth_supported': self.oauth_supported,
        }

    def close(self):
        self.worker.close()
        self.directory.cleanup()


class RcloneConfigService:
    """One expiring private rclone process per editor session, never an exposed RC proxy.

    The shipped web server uses one threaded worker. Draft IDs are intentionally
    process-local: after a restart clients must reopen from the durable config.
    """

    def __init__(self, runtime, config_manager, cloud_backup_service, worker_factory=RcloneWorker):
        self.runtime = runtime
        self.config_manager = config_manager
        self.cloud = cloud_backup_service
        self.worker_factory = worker_factory
        self.path = runtime.rclone_config_dir / 'rclone.conf'
        self.lock_path = self.path.with_suffix('.conf.sss.lock')
        self.root = runtime.volatile_dir / 'rclone'
        self.recovery_root = runtime.data_dir / 'rclone-recovery'
        self.lock = threading.RLock()
        self.drafts: dict[str, ConfigDraft] = {}
        self._providers: list | None = None
        self.version = ''
        self._stop = threading.Event()
        self._janitor = None
        atexit.register(self.close)
        # Credential recovery cannot depend on somebody opening the editor:
        # scheduled backups may be the first provider access after a restart.
        self._recover_pending()
        if any(self.recovery_root.glob('*.json')):
            self._start_janitor()

    def _read(self) -> str:
        try:
            return self.path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return ''

    def _settings(self) -> tuple[str, str]:
        self.config_manager.load_config()
        return (
            self.config_manager.get_value('backup', 'rclone_dir', ''),
            self.config_manager.get_value('backup', 'cloud_enabled', 'false'),
        )

    def _version(self, text=None, *, settings=None) -> str:
        return hashlib.sha256(
            (
                (self._read() if text is None else text)
                + repr(self._settings() if settings is None else settings)
            ).encode()
        ).hexdigest()

    def _workspace(self, text):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        # Normal exits explicitly clean up. A shutdown that cannot persist a
        # rotated token must be able to retain this workspace for recovery,
        # including after TemporaryDirectory's finalizer runs.
        directory = TemporaryDirectory(prefix='edit-', dir=self.root, delete=False)
        path = Path(directory.name) / 'rclone.conf'
        try:
            atomic_write_text(path, text, mode=0o600, durable=False)
            worker = self.worker_factory(path)
        except OSError, RcloneError:
            directory.cleanup()
            raise
        return directory, worker

    @contextmanager
    def _temporary_worker(self, text):
        directory, worker = self._workspace(text)
        try:
            yield worker
        finally:
            worker.close()
            directory.cleanup()

    def providers(self):
        if self._providers is None:
            with self._temporary_worker('') as worker:
                self._providers = worker.call('config/providers')['providers']
                self.version = worker.call('core/version')['version']
        return self._providers

    def snapshot(self, owner):
        text = self._read()
        configuration_error = ''
        try:
            parser = parse_config(text)
        except ValidationProblem as exc:
            # A broken or encrypted imported file must still be repairable in
            # Advanced without losing the saved destination or enable setting.
            parser = parse_config('')
            configuration_error = exc.detail
        settings = self._settings()
        destination, enabled = settings
        name, sep, path = destination.partition(':')
        return {
            'remotes': [{'name': s, 'type': parser.get(s, 'type')} for s in parser.sections()],
            'destination': {'name': name, 'path': path}
            if sep and name in parser.sections()
            else None,
            'destination_text': destination,
            'enabled': enabled == 'true',
            'source': self.config_manager.get_value('backup', 'mount_point', ''),
            'version': self._version(text, settings=settings),
            'configuration_error': configuration_error,
            'draft': self.drafts[owner].view() if owner in self.drafts else None,
        }

    def _expire(self):
        for owner, draft in list(self.drafts.items()):
            if time.monotonic() - draft.touched > DRAFT_TTL_SECONDS:
                try:
                    self._discard_draft(owner, draft)
                except ConflictProblem, OSError:
                    # A backup or failed write can delay publishing rotated
                    # tokens. Keep the original TTL so the next janitor pass
                    # retries; retained drafts still count toward MAX_DRAFTS.
                    continue

    def _cleanup_loop(self):
        while not self._stop.wait(CLEANUP_INTERVAL_SECONDS):
            try:
                with self.lock:
                    self._recover_pending()
                    for draft in list(self.drafts.values()):
                        if draft.provider_lock is not None:
                            try:
                                # A closed browser must not leave a completed
                                # configuration job blocking scheduled backups.
                                self._poll_draft(draft)
                            except RcloneError, OSError:
                                # Keep ownership until publication succeeds or
                                # expiration stops the worker and retries cleanup.
                                continue
                    self._expire()
            except Exception as exc:
                # This daemon is a background execution boundary. Unexpected
                # worker cleanup failures must not disable all future expiry,
                # and exception messages can contain credential-bearing paths.
                logging.getLogger(__name__).warning(
                    'Rclone draft cleanup failed (%s); retrying.', type(exc).__name__
                )

    def _start_janitor(self):
        if self._janitor is None:
            self._janitor = threading.Thread(
                target=self._cleanup_loop, name='rclone-draft-cleanup', daemon=True
            )
            self._janitor.start()

    def dispatch(self, owner, action, data):
        # Only this explicit vocabulary is exposed to HTTP. In particular there
        # is no route for rclone core/command, sync, or arbitrary RC endpoints.
        actions = {
            'state': lambda: self.snapshot(owner),
            'providers': self.providers,
            'start': lambda: self.start(owner, data),
            'poll': lambda: self.poll(owner, data),
            'advance': lambda: self.advance(owner, data),
            'back': lambda: self.back(owner, data),
            'cancel': lambda: self.cancel(owner, data),
            'folders': lambda: self.folders(owner, data),
            'mkdir': lambda: self.mkdir(owner, data),
            'save': lambda: self.save(owner, data),
            'raw': self.raw,
            'apply_raw': lambda: self.apply_raw(owner, data),
            'manage': lambda: self.manage(owner, data),
            'settings': lambda: self.settings(owner, data),
            'oauth_link': lambda: self.oauth_link(owner, data),
            'oauth_return': lambda: self.oauth_return(owner, data),
        }
        if action not in actions:
            raise ValidationProblem('Unknown connection action.')
        with self.lock:
            self._recover_pending()
            self._expire()
            self._start_janitor()
            return actions[action]()

    def require_draft(self, owner, data, *, changing=False):
        draft = self.drafts.get(owner)
        if not draft or draft.identifier != data.get('id'):
            raise ConflictProblem(
                'This connection session has ended. Reload and reopen the saved connection.'
            )
        if changing and data.get('revision') != draft.revision:
            raise ConflictProblem('This question changed in another tab. Reload before continuing.')
        draft.touched = time.monotonic()
        return draft

    def start(self, owner, data):
        if owner in self.drafts:
            raise ConflictProblem('Finish or cancel the open connection first.')
        if len(self.drafts) >= MAX_DRAFTS:
            raise ConflictProblem('Other connection editors are busy. Try again shortly.')
        name = validate_name(str(data.get('name', '')).strip())
        purpose = data.get('purpose', 'destination')
        if purpose not in {'destination', 'edit', 'add', 'choose'}:
            raise ValidationProblem('Unknown connection workflow.')
        source = self._read()
        parser = parse_config(source)
        editing = purpose in {'edit', 'choose'}
        if editing and not parser.has_section(name):
            raise ValidationProblem('That connection no longer exists.')
        if not editing and parser.has_section(name):
            raise ValidationProblem('That name is already in use. Choose another name.')
        provider = parser.get(name, 'type') if editing else data.get('type')
        if purpose != 'choose' and provider not in {item['Name'] for item in self.providers()}:
            raise ValidationProblem('Choose a provider supported by the installed rclone.')
        directory, worker = self._workspace(source)
        draft = ConfigDraft(
            owner, name, provider, worker, directory, source, self._settings(), purpose
        )
        self.drafts[owner] = draft
        try:
            endpoints = {entry['Path'] for entry in worker.call('rc/list')['commands']}
            draft.oauth_supported = 'config/oauthstatus' in endpoints
            if purpose == 'choose':
                return draft.view()
            with self._provider_operation(draft):
                draft.job = worker.call(
                    'config/update' if editing else 'config/create',
                    {
                        'name': name,
                        'type': provider,
                        'parameters': {'config_auth_no_browser': 'true'},
                        'opt': {'nonInteractive': True, 'all': True},
                        '_async': True,
                    },
                )['jobid']
            return self.poll(owner, {'id': draft.identifier})
        except ApiProblem, OSError:
            self.cancel(owner, {'id': draft.identifier})
            raise

    def advance(self, owner, data):
        draft = self.require_draft(owner, data, changing=True)
        if draft.job is not None or not draft.output.get('State'):
            raise ConflictProblem('Wait for the current question to finish.')
        answer = data.get('answer', '')
        if not isinstance(answer, str):
            raise ValidationProblem('The answer must be text.')
        option = draft.output.get('Option') or {}
        previous_default = option.get('DefaultStr')
        with self._provider_operation(draft):
            if option.get('Name') == 'token' and answer == previous_default:
                answer = option.get('DefaultStr', answer)
            if option.get('IsPassword') and answer and answer != option.get('DefaultStr'):
                # Continuation results bypass config/update's parameter obscuring.
                # Match rclone's CLI password widget using its own encoder, while
                # retaining an unchanged stored default without encoding it twice.
                answer = draft.worker.call('core/obscure', {'clear': answer})['obscured']
            draft.history.append((draft.worker.path.read_text(), copy.deepcopy(draft.output)))
            draft.job = draft.worker.call(
                'config/update',
                {
                    'name': draft.name,
                    'parameters': {'config_auth_no_browser': 'true'},
                    'opt': {
                        'nonInteractive': True,
                        'continue': True,
                        'state': draft.output['State'],
                        'result': answer,
                    },
                    '_async': True,
                },
            )['jobid']
        draft.revision += 1
        return self.poll(owner, data)

    def poll(self, owner, data):
        draft = self.require_draft(owner, data)
        self._poll_draft(draft)
        return draft.view()

    def _poll_draft(self, draft):
        if draft.job is not None:
            status = draft.worker.call('job/status', {'jobid': draft.job})
            if status['finished']:
                draft.job = None
                draft.oauth = False
                if status['success']:
                    draft.output = status['output']
                else:
                    # Empty State means success. An initial failure must never
                    # be mistaken for a successfully configured connection.
                    if not draft.output:
                        draft.output = {'State': 'failed', 'Option': None}
                    draft.output['Error'] = status['error']
                draft.revision += 1
            elif draft.oauth_supported:
                draft.oauth = draft.worker.call('config/oauthstatus')['status'] == 'running'
        if draft.job is None and draft.provider_lock is not None:
            self._finish_provider_operation(draft)

    def back(self, owner, data):
        draft = self.require_draft(owner, data, changing=True)
        if not draft.history:
            raise ValidationProblem('Cancel to choose another service.')
        if draft.provider_lock is not None:
            self._finish_provider_operation(draft)
        text, output = draft.history.pop()
        # rclone's opaque state has no undo. Restore the file and matching state,
        # and terminate any OAuth listener before returning to its question.
        draft.worker.replace(text)
        draft.output, draft.job, draft.oauth = output, None, False
        draft.revision += 1
        return draft.view()

    def _adopt_refreshed_base(self, draft, saved):
        """Keep this draft and its Back checkpoints on the published token lineage."""
        previous = draft.base
        updated = self._refreshed_config(previous, saved) or previous
        # Save compares bytes to catch external edits. Reuse the actual saved
        # formatting when token reconciliation accounts for its whole content.
        if parse_config(updated) == parse_config(saved):
            updated = saved
        before = parse_config(previous).get(draft.name, 'token', fallback='')
        after = parse_config(updated).get(draft.name, 'token', fallback='')
        if before != after:
            for output in [draft.output, *(output for _, output in draft.history)]:
                option = output.get('Option') or {}
                if option.get('Name') == 'token' and option.get('DefaultStr') == before:
                    # Keeping a displayed default must not submit a superseded
                    # refresh token after another backup/editor has renewed it.
                    option['DefaultStr'] = option['Default'] = after
        draft.history = [
            (self._refreshed_config(previous, updated, text) or text, output)
            for text, output in draft.history
        ]
        draft.base = updated

    def _prepare_provider_operation(self, draft):
        saved, text = self._read(), draft.worker.path.read_text()
        updated = self._refreshed_config(draft.base, saved, text) or text
        reconciled_base = self._refreshed_config(text, updated, draft.base) or draft.base
        if parse_config(reconciled_base) != parse_config(saved):
            # Never substitute credentials into an edited identity, or allow
            # an old draft to overwrite unrelated durable configuration later.
            raise ConflictProblem(
                'Saved configuration changed while editing. Cancel and reopen it to keep those changes.'
            )
        if updated != text:
            draft.worker.close()
            atomic_write_text(draft.worker.path, updated, mode=0o600, durable=False)
        # Advance the baseline only after the private write succeeds. Otherwise
        # cleanup could misread an older private token as a fresh rotation and
        # publish it over the newer durable credential after a reload failure.
        self._adopt_refreshed_base(draft, saved)
        if draft.worker.process is None or draft.worker.process.poll() is not None:
            draft.worker.start()

    def _release_provider_lock(self, draft):
        if draft.provider_lock is not None:
            draft.provider_lock.__exit__(None, None, None)
            draft.provider_lock = None

    def _finish_provider_operation(self, draft):
        # RC HTTP timeouts do not cancel rclone's work, and a backend can own
        # background token writers. Quiesce the process before taking its final
        # snapshot; the next question/operation restarts from this private file.
        draft.worker.close()
        draft.job, draft.oauth = None, False
        text, current = draft.worker.path.read_text(), self._read()
        refreshed = self._refreshed_config(draft.base, text, current)
        if refreshed is None and current == self._refreshed_config(draft.base, text):
            # A durable write can replace the file and then fail its fsync.
            # Retry that exact publication before acknowledging its baseline.
            refreshed = current
        if refreshed is not None:
            atomic_write_text(self.path, refreshed, mode=0o600)
            self._adopt_refreshed_base(draft, refreshed)
        # If persistence fails, keep ownership so a backup cannot consume an
        # invalidated token. Poll, cleanup, or cancellation can retry publication.
        self._release_provider_lock(draft)

    @contextmanager
    def _provider_operation(self, draft):
        if draft.provider_lock is not None:
            self._finish_provider_operation(draft)
        guard = self._publishing()
        guard.__enter__()
        draft.provider_lock = guard
        pending = False
        try:
            self._prepare_provider_operation(draft)
            yield
            pending = draft.job is not None
        finally:
            # Configuration calls run asynchronously, including browser OAuth.
            # Keep the same lock across requests until their job is finished,
            # cancelled, expired, or stopped by Back/shutdown.
            if not pending:
                self._finish_provider_operation(draft)

    @staticmethod
    def _refreshed_config(base: str, text: str, current: str | None = None) -> str | None:
        """Merge token-only changes into saved connections that still match their base."""
        try:
            original, updated = parse_config(base), parse_config(text)
            saved = parse_config(base if current is None else current)
        except ValidationProblem:
            return None
        changed = False
        # A new alias/crypt remote can refresh its existing upstream connection.
        # Discarding that wrapper must not discard a rotated, single-use token.
        # Compare each connection independently: unrelated durable edits must
        # survive, and neither a changed identity nor a newer saved token can
        # be replaced by credentials from an older draft.
        for name in original.sections():
            if not updated.has_section(name) or not saved.has_section(name):
                continue
            if dict(saved.items(name)) != dict(original.items(name)):
                continue
            before, after = dict(original.items(name)), dict(updated.items(name))
            old_token, token = before.pop('token', ''), after.pop('token', '')
            if token and token != old_token and before == after:
                saved.set(name, 'token', token)
                changed = True
        if not changed:
            return None
        if saved == updated:
            return text
        output = io.StringIO()
        saved.write(output)
        return output.getvalue()

    def _publish_refreshed(self, base, text):
        with self._publishing():
            if refreshed := self._refreshed_config(base, text, self._read()):
                atomic_write_text(self.path, refreshed, mode=0o600)

    def _recover_pending(self):
        """Retry token-only shutdown records without restoring unsaved edits."""
        for path in self.recovery_root.glob('*.json'):
            try:
                record = json.loads(path.read_text())
                base, text = record['base'], record['config']
                if not isinstance(base, str) or not isinstance(text, str):
                    raise ValueError('Invalid credential recovery record')
                parse_config(base)
                parse_config(text)
                self._publish_refreshed(base, text)
                # Repeating a published record is safe: its old token no longer
                # matches the saved one, so a crash before unlink cannot undo it.
                path.unlink(missing_ok=True)
            except ConflictProblem:
                # Backup ownership takes priority; startup and janitor never
                # wait for an unbounded sync just to replay credentials.
                continue
            except OSError, ValueError, KeyError, TypeError, ValidationProblem:
                logging.getLogger(__name__).error(
                    'Rclone credential recovery remains pending in %s.', path
                )

    def cancel(self, owner, data):
        draft = self.require_draft(owner, data)
        self._discard_draft(owner, draft)
        return {}

    def _discard_draft(self, owner, draft):
        draft.worker.close()
        if draft.provider_lock is not None:
            self._finish_provider_operation(draft)
        text = draft.worker.path.read_text()
        if refreshed := self._refreshed_config(draft.base, text):
            # Browsing can rotate refresh tokens, invalidating the saved ones.
            # Preserve those credentials without publishing unsaved edits, and
            # reconcile each remote against the saved file under its lock.
            self._publish_refreshed(draft.base, refreshed)
        draft.close()
        del self.drafts[owner]

    def _ready(self, owner, data, *, changing=False):
        draft = self.require_draft(owner, data, changing=changing)
        if draft.job is not None or draft.output.get('State'):
            raise ConflictProblem('Complete the connection questions first.')
        return draft

    @staticmethod
    def _path(data):
        path = data.get('path', '')
        if not isinstance(path, str) or '\x00' in path or '\n' in path or '\r' in path:
            raise ValidationProblem('Enter a valid folder path.')
        return path

    def folders(self, owner, data):
        draft = self._ready(owner, data)
        path = self._path(data)
        with self._provider_operation(draft):
            result = draft.worker.call(
                'operations/list',
                {
                    # RC's remote is relative to fs. Put the exact destination in
                    # fs so absolute paths retain the same meaning as rclone sync.
                    'fs': draft.name + ':' + path,
                    'remote': '',
                    'opt': {'dirsOnly': True, 'noModTime': True, 'noMimeType': True},
                },
            )
        return {'path': path, 'folders': result.get('list') or []}

    def mkdir(self, owner, data):
        draft = self._ready(owner, data)
        name = str(data.get('name', ''))
        if not name.strip() or name in {'.', '..'} or any(c in name for c in '/\\\x00\r\n'):
            raise ValidationProblem('Enter a folder name without slashes.')
        # A newly created folder should be selectable as a destination. INI
        # values lose trailing whitespace, even when rclone preserves the name.
        if name != name.rstrip():
            raise ValidationProblem(
                'Folder names cannot end with whitespace because backup destination settings '
                'cannot preserve it. Choose a different name.'
            )
        path = self._path(data)
        with self._provider_operation(draft):
            draft.worker.call('operations/mkdir', {'fs': draft.name + ':' + path, 'remote': name})
        return {}

    @contextmanager
    def _publishing(self):
        try:
            # SSS backup jobs take this same lock before reading their settings
            # and keep it while rclone may refresh tokens in the managed config.
            with locked_path(self.lock_path, mode=0o600, blocking=False):
                yield
        except BlockingIOError:
            raise ConflictProblem(
                'A cloud backup or another editor action is running. Wait for it to finish before continuing.'
            ) from None

    def _publish(self, text, destination, enabled):
        self._validate_destination_text(destination)
        old_text = self._read()
        atomic_write_text(self.path, text, mode=0o600)
        try:
            self.cloud.save_destination(destination, enabled)
        except OSError, ApiProblem:
            atomic_write_text(self.path, old_text, mode=0o600)
            raise

    def save(self, owner, data):
        draft = self._ready(owner, data, changing=True)
        use_destination = draft.purpose in {'choose', 'destination'}
        path = self._path(data)
        if use_destination and data.get('acknowledged') is not True:
            raise ValidationProblem(
                'Confirm that this folder is dedicated to backups from this server.'
            )
        with self._publishing():
            if self._read() != draft.base or self._settings() != draft.settings_base:
                raise ConflictProblem(
                    'Saved configuration changed while editing. Cancel and reopen it to keep those changes.'
                )
            destination, enabled = draft.settings_base
            if use_destination:
                destination, enabled = draft.name + ':' + path, 'true'
            self._publish(draft.worker.path.read_text(), destination, enabled == 'true')
        # Publication is complete; cleanup must not try to acquire the save lock again.
        draft.close()
        del self.drafts[owner]
        return self.snapshot(owner)

    def raw(self):
        text = self._read()
        settings = self._settings()
        destination, enabled = settings
        # The editor must populate every field from the snapshot this version
        # identifies, rather than combining fresh config with stale page state.
        return {
            'config': text,
            'destination_text': destination,
            'enabled': enabled == 'true',
            'version': self._version(text, settings=settings),
        }

    def _check_version(self, data):
        if data.get('version') != self._version():
            raise ConflictProblem(
                'Saved configuration changed. Reload before saving to keep those changes.'
            )

    def _no_draft(self, owner):
        if owner in self.drafts:
            raise ConflictProblem('Finish or cancel the open connection first.')

    @staticmethod
    def _validate_destination_text(destination):
        if not isinstance(destination, str) or any(c in destination for c in '\x00\r\n'):
            raise ValidationProblem('Enter an exact rclone destination.')
        # config.conf is shared with backup scripts through ConfigParser, which
        # strips value-edge whitespace on read. Never save a different sync target
        # from the one browsed and confirmed, including while backup is disabled.
        if destination != destination.strip():
            raise ValidationProblem(
                'Backup destinations cannot start or end with whitespace because the settings '
                'file cannot preserve it. Choose a different folder or path.'
            )

    @classmethod
    def _validate_destination(cls, destination, parser, enabled):
        cls._validate_destination_text(destination)
        if not destination:
            if enabled:
                raise ValidationProblem('Choose a backup destination before enabling cloud backup.')
            return
        name, separator, _ = destination.partition(':')
        # Advanced paths also allow an absolute local path, as rclone itself does.
        if not destination.startswith('/') and (not separator or name not in parser.sections()):
            raise ValidationProblem(
                'Use remote:folder from this configuration, or an absolute local path.'
            )

    def apply_raw(self, owner, data):
        self._no_draft(owner)
        text = data.get('config', '')
        if not isinstance(text, str):
            raise ValidationProblem('The configuration must be text.')
        parser = parse_config(text)
        destination = data.get('destination', '')
        enabled = data.get('enabled')
        if not isinstance(enabled, bool):
            raise ValidationProblem('Choose whether cloud backup is enabled.')
        self._validate_destination(destination, parser, enabled)
        if enabled and data.get('acknowledged') is not True:
            raise ValidationProblem('Confirm the destination can be synchronized with this server.')
        with self._temporary_worker(text) as worker:
            worker.call('config/dump')
        with self._publishing():
            self._check_version(data)
            self._publish(text, destination, enabled)
        return self.snapshot(owner)

    def manage(self, owner, data):
        self._no_draft(owner)
        name, operation = data.get('name'), data.get('operation')
        with self._publishing():
            self._check_version(data)
            parser = parse_config(self._read())
            if not parser.has_section(name):
                raise ValidationProblem('That connection no longer exists.')
            if operation not in {'rename', 'duplicate', 'delete'}:
                raise ValidationProblem('Unknown connection action.')
            dependents = [
                s
                for s in parser.sections()
                if s != name and any(f'{name}:' in value for _, value in parser.items(s))
            ]
            if operation in {'rename', 'delete'} and dependents:
                raise ValidationProblem(
                    'Referenced by '
                    + ', '.join(dependents)
                    + '. Update those references in Advanced first.'
                )
            destination, enabled = self._settings()
            active_name, separator, path = destination.partition(':')
            if operation == 'delete':
                if separator and active_name == name:
                    raise ValidationProblem(
                        'Choose another backup destination, or clear it in Advanced, before removing this connection.'
                    )
                parser.remove_section(name)
            else:
                new_name = validate_name(str(data.get('new_name', '')).strip())
                if parser.has_section(new_name):
                    raise ValidationProblem('That connection name is already in use.')
                parser.add_section(new_name)
                for key, value in parser.items(name):
                    parser.set(new_name, key, value)
                if operation == 'rename':
                    parser.remove_section(name)
                    if separator and active_name == name:
                        destination = new_name + ':' + path
            output = io.StringIO()
            parser.write(output)
            self._publish(output.getvalue(), destination, enabled == 'true')
        return self.snapshot(owner)

    def settings(self, owner, data):
        enabled = data.get('enabled')
        if not isinstance(enabled, bool):
            raise ValidationProblem('Choose whether cloud backup is enabled.')
        with self._publishing():
            self._check_version(data)
            destination, _ = self._settings()
            if enabled:
                self._validate_destination(destination, parse_config(self._read()), True)
            self.cloud.save_destination(destination, enabled)
        return self.snapshot(owner)

    def oauth_target(self, draft):
        if not draft.oauth_supported:
            raise ValidationProblem(
                'Update rclone to use browser sign-in, or use its authorization command.'
            )
        status = draft.worker.call('config/oauthstatus')
        if status['status'] != 'running':
            raise ConflictProblem(
                'No browser sign-in is waiting. Return to the connection questions.'
            )
        parsed = urllib.parse.urlsplit(status['authUrl'])
        if parsed.hostname not in {'localhost', '127.0.0.1'} or parsed.scheme != 'http':
            raise RcloneError('Unexpected rclone authorization address.')
        return parsed

    def oauth_link(self, owner, data):
        draft = self.require_draft(owner, data)
        target = self.oauth_target(draft)
        # Read the private listener's redirect without visiting the provider.
        # OAuth's registered loopback redirect is kept intact for every backend.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        try:
            with opener.open(target.geturl(), timeout=10):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                url = exc.headers.get('Location', '')
                if urllib.parse.urlsplit(url).scheme == 'https':
                    return {'url': url}
        except urllib.error.URLError, TimeoutError:
            raise RcloneError(
                'Could not open the rclone sign-in listener. Go back and retry.'
            ) from None
        raise RcloneError('rclone did not provide a secure sign-in link.')

    def oauth_return(self, owner, data):
        draft = self.require_draft(owner, data)
        target = self.oauth_target(draft)
        try:
            returned = urllib.parse.urlsplit(str(data.get('url', '')))
            query = urllib.parse.parse_qs(returned.query)
            expected = urllib.parse.parse_qs(target.query)
            valid = (
                returned.hostname in {'127.0.0.1', 'localhost'}
                and returned.scheme == 'http'
                and returned.port == target.port
                and returned.path in {'', '/'}
                and query.get('state') == expected.get('state')
                and bool(query.get('code'))
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValidationProblem(
                'Paste the complete localhost callback URL from this sign-in attempt.'
            )
        # Never request a pasted host or follow a redirect. Only the verified
        # state/code query reaches this draft's known loopback listener.
        url = urllib.parse.urlunsplit((target.scheme, target.netloc, '/', returned.query, ''))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        try:
            with opener.open(url, timeout=15) as response:
                response.read()
        except OSError, urllib.error.URLError, http.client.HTTPException:
            # rclone can close its one-shot listener as soon as it receives the
            # code, before an HTTP response is flushed. The configuration job,
            # not this socket, determines whether token exchange succeeded.
            return self.poll(owner, data)
        return self.poll(owner, data)

    def close(self):
        self._stop.set()
        with self.lock:
            for owner, draft in list(self.drafts.items()):
                try:
                    # Quiesce token writers before taking the shutdown snapshot.
                    draft.worker.close()
                    self._discard_draft(owner, draft)
                except Exception as exc:
                    # Shutdown is an execution boundary: failure for one draft
                    # must not prevent the other workers from being stopped.
                    try:
                        text = draft.worker.path.read_text()
                        refreshed = self._refreshed_config(draft.base, text)
                        if refreshed:
                            self.recovery_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                            self.recovery_root.chmod(0o700)
                            atomic_write_json(
                                self.recovery_root / f'{draft.identifier}.json',
                                {'base': draft.base, 'config': refreshed},
                                mode=0o600,
                            )
                            logging.getLogger(__name__).warning(
                                'Rclone refreshed credentials queued for recovery after restart.'
                            )
                        draft.close()
                        del self.drafts[owner]
                    except Exception as recovery_exc:
                        # Keep the only available credentials if even durable
                        # recovery fails (for example a full/read-only disk).
                        # The retained path is app-generated, never provider data.
                        logging.getLogger(__name__).error(
                            'Rclone shutdown recovery failed (%s, %s); private workspace '
                            'retained for manual credential recovery at %s.',
                            type(exc).__name__,
                            type(recovery_exc).__name__,
                            draft.worker.path,
                        )
                finally:
                    if draft.worker.process is None or draft.worker.process.poll() is not None:
                        self._release_provider_lock(draft)
