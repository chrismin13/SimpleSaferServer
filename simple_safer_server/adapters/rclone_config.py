"""Private rclone RC processes; credentials travel in JSON, never command argv."""

import base64
import json
import os
import secrets
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

from simple_safer_server.adapters.command_runner import DEVNULL, CommandRunner, TimeoutExpired
from simple_safer_server.adapters.rclone import RCLONE_WORKING_DIRECTORY
from simple_safer_server.services.file_persistence import atomic_write_text
from simple_safer_server.web.problems import ValidationProblem


class RcloneError(ValidationProblem):
    """An rclone configuration or provider error for the credential editor."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RcloneWorker:
    """Private authenticated RC process with an explicit, isolated config file."""

    def __init__(self, path: Path, runner: CommandRunner | None = None):
        self.runner = runner or CommandRunner()
        self.path = path
        self.process = None
        # A machine-wide HTTP proxy must never receive RC credentials or follow
        # a redirect away from the private loopback listener.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        self.start()

    def start(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}/'
        password = secrets.token_urlsafe(32)
        self.authorization = 'Basic ' + base64.b64encode(f'sss:{password}'.encode()).decode()
        # Each editor must see exactly its private config. Inherited RCLONE_*
        # overrides could silently select different credentials or destinations.
        env = {key: value for key, value in os.environ.items() if not key.startswith('RCLONE_')}
        env.update(RCLONE_RC_USER='sss', RCLONE_RC_PASS=password)
        self.process = self.runner.popen(
            [
                'rclone',
                'rcd',
                '--config',
                str(self.path),
                '--rc-addr',
                f'127.0.0.1:{port}',
                '--cache-dir',
                str(self.path.parent / 'cache'),
                '--temp-dir',
                str(self.path.parent / 'tmp'),
                '--ask-password=false',
            ],
            env=env,
            stdout=DEVNULL,
            stderr=DEVNULL,
            cwd=RCLONE_WORKING_DIRECTORY,
        )
        for _ in range(80):
            if self.process.poll() is not None:
                raise RcloneError('The private rclone process could not start.')
            try:
                self.call('rc/noop', timeout=0.2)
                return
            except RcloneError:
                time.sleep(0.05)
        self.close()
        raise RcloneError('The private rclone process did not become ready.')

    def call(self, endpoint, payload=None, *, timeout=30):
        request = urllib.request.Request(
            self.url + endpoint,
            data=json.dumps(payload or {}).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': self.authorization},
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read())
            except ValueError, UnicodeError:
                raise RcloneError(
                    'rclone returned an unreadable error. Retry this action.'
                ) from None
            # RC errors also contain the input object, which may hold credentials.
            # Return only its error message, never that input or the whole response.
            raise RcloneError(body.get('error', 'rclone could not complete this action.')) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RcloneError('rclone did not respond. Retry or cancel this connection.') from exc

    def replace(self, text):
        self.close()
        atomic_write_text(self.path, text, mode=0o600, durable=False)
        self.start()

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
