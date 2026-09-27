"""Managed rclone subprocesses share an explicit environment boundary."""

import base64
import os
from unittest.mock import Mock

import pytest

from simple_safer_server.adapters.rclone import RcloneAdapter
from simple_safer_server.adapters.rclone_config import RcloneWorker


@pytest.mark.parametrize('operation', ['editor', 'backup'])
def test_managed_process_environment_preserves_only_explicit_rclone_options(
    tmp_path, monkeypatch, operation
):
    overrides = {
        'RCLONE_CONFIG_BACKUP_REMOTE': '/unconfirmed-destination',
        'RCLONE_CONFIG_BACKUP_PASS': 'ambient-credential',
        'RCLONE_CONFIG': '/other/rclone.conf',
        'RCLONE_ALIAS_REMOTE': '/other-destination',
        'RCLONE_RC_USER': 'ambient-user',
        'RCLONE_RC_PASS': 'ambient-password',
    }
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv('SSS_TEST_PRESERVED', 'value with spaces\nand a newline')
    monkeypatch.setenv('AWS_PROFILE', 'managed-provider-profile')
    runner = Mock()
    runner.popen.return_value.poll.return_value = None
    worker = None
    if operation == 'editor':
        # Keep this subprocess contract test independent of installed rclone.
        monkeypatch.setattr(RcloneWorker, 'call', lambda *args, **kwargs: {})
        worker = RcloneWorker(tmp_path / 'rclone.conf', runner=runner)
    else:
        RcloneAdapter(runner).sync('/source', 'backup:', config_path='/managed/rclone.conf')
    try:
        environment = runner.popen.call_args.kwargs['env']
        assert environment['PATH'] == os.environ['PATH']
        assert environment['SSS_TEST_PRESERVED'] == 'value with spaces\nand a newline'
        assert environment['AWS_PROFILE'] == 'managed-provider-profile'
        rclone_names = {name for name in environment if name.startswith('RCLONE_')}
        if worker:
            assert rclone_names == {'RCLONE_RC_USER', 'RCLONE_RC_PASS'}
            assert environment['RCLONE_RC_USER'] == 'sss'
            assert environment['RCLONE_RC_PASS'] != overrides['RCLONE_RC_PASS']
            credentials = base64.b64decode(worker.authorization.removeprefix('Basic ')).decode()
            assert credentials == f"sss:{environment['RCLONE_RC_PASS']}"
        else:
            assert not rclone_names
        # Filtering belongs to the child, not the host or unrelated subprocesses.
        assert all(os.environ[name] == value for name, value in overrides.items())
    finally:
        if worker:
            worker.close()
