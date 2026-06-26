from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from simple_safer_server.core.ownership import OwnershipManifest
from simple_safer_server.core.privileged_actions import (
    PrivilegedActionError,
    create_builtin_privileged_action_registry,
)
from simple_safer_server.modules.storage.backup_drive_setup import BackupDriveSetupError
from simple_safer_server.privileged_helper import run


def run_helper(args, payload=""):
    stdout = StringIO()
    stderr = StringIO()
    exit_code = run(args, stdin=StringIO(payload), stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_helper_lists_allowlisted_actions():
    exit_code, stdout, stderr = run_helper(["list"])

    assert exit_code == 0
    assert stderr == ""
    assert "alerts.write-smtp-config" in stdout
    assert "cloud-backup.sync" in stdout
    assert "cloud-backup.write-rclone-config" in stdout
    assert "ddns.update" in stdout
    assert "drive-health.page-check" in stdout
    assert "drive-health.refresh-summary" in stdout
    assert "drive-health.scheduled-check" in stdout
    assert "file-sharing.remove-user" in stdout
    assert "file-sharing.reload" in stdout
    assert "file-sharing.sync-user" in stdout
    assert "file-sharing.write-shares" in stdout
    assert "storage.format" in stdout
    assert "storage.managed-drive" in stdout
    assert "storage.managed-unmount" in stdout
    assert "storage.mount" in stdout
    assert "storage.mount-check" in stdout
    assert "storage.safety-check" in stdout
    assert "storage.unmount" in stdout
    assert "system.poweroff" in stdout
    assert "system.reboot" in stdout


def test_helper_rejects_unknown_action():
    exit_code, stdout, stderr = run_helper(["run", "missing.action"], "{}")

    assert exit_code == 2
    assert stdout == ""
    assert "Unknown privileged action: missing.action" in stderr


def test_helper_rejects_non_object_json_payload():
    exit_code, stdout, stderr = run_helper(["run", "alerts.write-smtp-config"], "[]")

    assert exit_code == 2
    assert stdout == ""
    assert "payload must be a JSON object" in stderr


def test_smtp_action_writes_config_from_json_payload(tmp_path):
    runtime = SimpleNamespace(smtp_config_path=tmp_path / "smtp.conf", data_dir=tmp_path)
    payload = {
        "from_address": "server@example.com",
        "smtp_server": "smtp.example.com",
        "smtp_port": "587",
        "smtp_username": "server",
        "smtp_password": "secret",
    }

    result = create_builtin_privileged_action_registry().run(
        "alerts.write-smtp-config",
        payload,
        runtime=runtime,
    )

    assert result.action == "alerts.write-smtp-config"
    assert result.data == {"path": str(runtime.smtp_config_path)}
    content = runtime.smtp_config_path.read_text(encoding="utf-8")
    assert "host smtp.example.com" in content
    assert "password secret" in content
    assert runtime.smtp_config_path.stat().st_mode & 0o777 == 0o600
    records = OwnershipManifest(tmp_path / "ownership.json").list_records()
    assert len(records) == 1
    assert records[0].module_slug == "alerts"
    assert records[0].identifier == str(runtime.smtp_config_path)


def test_rclone_config_action_writes_managed_config(tmp_path):
    runtime = SimpleNamespace(rclone_config_dir=tmp_path / "rclone", data_dir=tmp_path)
    payload = {"rclone_config": "[remote]\ntype = test\n"}

    result = create_builtin_privileged_action_registry().run(
        "cloud-backup.write-rclone-config",
        payload,
        runtime=runtime,
    )

    config_path = runtime.rclone_config_dir / "rclone.conf"
    assert result.data == {"path": str(config_path)}
    assert config_path.read_text(encoding="utf-8") == "[remote]\ntype = test\n"
    assert config_path.stat().st_mode & 0o777 == 0o600
    records = OwnershipManifest(tmp_path / "ownership.json").list_records()
    assert len(records) == 1
    assert records[0].module_slug == "cloud-backup"
    assert records[0].identifier == str(config_path)


def test_rclone_config_action_rejects_empty_config(tmp_path):
    runtime = SimpleNamespace(rclone_config_dir=tmp_path / "rclone", data_dir=tmp_path)

    with pytest.raises(PrivilegedActionError, match="rclone_config is required"):
        create_builtin_privileged_action_registry().run(
            "cloud-backup.write-rclone-config",
            {"rclone_config": "  "},
            runtime=runtime,
        )

    assert not runtime.rclone_config_dir.exists()


def test_smtp_action_rejects_line_injection(tmp_path):
    runtime = SimpleNamespace(smtp_config_path=tmp_path / "smtp.conf", data_dir=tmp_path)
    payload = {
        "from_address": "server@example.com\naccount bad",
        "smtp_server": "smtp.example.com",
        "smtp_port": "587",
        "smtp_username": "server",
        "smtp_password": "secret",
    }

    with pytest.raises(PrivilegedActionError, match="line breaks"):
        create_builtin_privileged_action_registry().run(
            "alerts.write-smtp-config",
            payload,
            runtime=runtime,
        )

    assert not runtime.smtp_config_path.exists()


def test_helper_uses_stdin_json_for_smtp_payload(tmp_path):
    runtime = SimpleNamespace(smtp_config_path=tmp_path / "smtp.conf", data_dir=tmp_path)
    payload = {
        "from_address": "server@example.com",
        "smtp_server": "smtp.example.com",
        "smtp_port": "465",
        "smtp_username": "server",
        "smtp_password": "secret",
    }

    with patch("simple_safer_server.core.privileged_actions.get_runtime", return_value=runtime):
        exit_code, stdout, stderr = run_helper(
            ["run", "alerts.write-smtp-config"],
            json.dumps(payload),
        )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["action"] == "alerts.write-smtp-config"
    assert "password secret" in runtime.smtp_config_path.read_text(encoding="utf-8")


def test_job_action_runs_allowlisted_worker_job():
    with patch("simple_safer_server.modules.ddns.runner.run_update_job_direct", return_value=0) as job:
        result = create_builtin_privileged_action_registry().run("ddns.update", {})

    job.assert_called_once_with()
    assert result.data == {
        "job": "ddns-update",
        "message": "Job completed successfully.",
    }


def test_job_action_rejects_payload_fields():
    with pytest.raises(PrivilegedActionError, match="does not accept payload"):
        create_builtin_privileged_action_registry().run(
            "cloud-backup.sync",
            {"command": "anything"},
        )


def test_job_action_reports_nonzero_job_result():
    with patch("simple_safer_server.modules.cloud_backup.runner.run_backup_job_direct", return_value=1):
        with pytest.raises(PrivilegedActionError, match="exit code 1"):
            create_builtin_privileged_action_registry().run("cloud-backup.sync", {})


def test_scheduled_drive_health_action_runs_direct_job():
    with patch(
        "simple_safer_server.modules.drive_health.runner.run_drive_health_job_direct",
        return_value=0,
    ) as job:
        result = create_builtin_privileged_action_registry().run(
            "drive-health.scheduled-check",
            {},
        )

    job.assert_called_once_with()
    assert result.data == {
        "job": "drive-health",
        "message": "Job completed successfully.",
    }


def test_storage_mount_check_action_runs_direct_job():
    with patch(
        "simple_safer_server.modules.storage.runner.run_mount_check_job_direct",
        return_value=0,
    ) as job:
        result = create_builtin_privileged_action_registry().run("storage.mount-check", {})

    job.assert_called_once_with()
    assert result.data == {
        "job": "mount-check",
        "message": "Job completed successfully.",
    }


def test_drive_health_page_check_action_returns_probe_result():
    runtime = SimpleNamespace()
    page_result = {
        "smart": {"smart_194_raw": 31.0},
        "missing_attrs": [],
        "error": None,
        "hdsentinel_snapshot": None,
        "hdsentinel_drives": [],
        "smart_support_warning": None,
        "summary": {"detail": "SMART details were collected."},
    }

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager") as config_manager,
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils") as system_utils,
        patch(
            "simple_safer_server.core.privileged_job_actions.build_drive_health_page_result",
            return_value=page_result,
        ) as build_page,
    ):
        result = create_builtin_privileged_action_registry().run(
            "drive-health.page-check",
            {},
            runtime=runtime,
        )

    config_manager.assert_called_once_with(runtime=runtime)
    system_utils.assert_called_once_with(runtime=runtime)
    build_page.assert_called_once()
    assert result.data == page_result


def test_drive_health_refresh_summary_action_returns_summary():
    runtime = SimpleNamespace()
    summary = {"detail": "SMART details were collected."}

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager") as config_manager,
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils") as system_utils,
        patch(
            "simple_safer_server.core.privileged_job_actions.build_drive_health_summary",
            return_value=summary,
        ) as build_summary,
    ):
        result = create_builtin_privileged_action_registry().run(
            "drive-health.refresh-summary",
            {},
            runtime=runtime,
        )

    config_manager.assert_called_once_with(runtime=runtime)
    system_utils.assert_called_once_with(runtime=runtime)
    build_summary.assert_called_once()
    assert result.data == {"summary": summary}


def test_file_sharing_reload_action_restarts_services():
    runtime = SimpleNamespace()

    with patch("simple_safer_server.core.privileged_job_actions.SMBManager") as smb_manager:
        smb_manager.return_value.restart_services.return_value = True

        result = create_builtin_privileged_action_registry().run(
            "file-sharing.reload",
            {},
            runtime=runtime,
        )

    smb_manager.assert_called_once_with(runtime=runtime)
    smb_manager.return_value.restart_services.assert_called_once_with()
    assert result.data == {"message": "File sharing services reloaded."}


def test_file_sharing_reload_action_reports_failed_reload():
    with patch("simple_safer_server.core.privileged_job_actions.SMBManager") as smb_manager:
        smb_manager.return_value.restart_services.return_value = False

        with pytest.raises(PrivilegedActionError, match="did not reload cleanly"):
            create_builtin_privileged_action_registry().run("file-sharing.reload", {})


def test_file_sharing_write_shares_action_publishes_owned_config():
    runtime = SimpleNamespace(data_dir=Path.cwd(), samba_dir=Path("/etc/samba"))
    payload = {"shares_config": "[backup]\n   path = /media/backup\n"}

    with (
        patch("simple_safer_server.core.privileged_job_actions.SMBManager") as smb_manager,
        patch(
            "simple_safer_server.core.privileged_job_actions.record_runtime_owned_resource"
        ) as record_owned,
    ):
        result = create_builtin_privileged_action_registry().run(
            "file-sharing.write-shares",
            payload,
            runtime=runtime,
        )

    smb_manager.assert_called_once_with(runtime=runtime)
    smb_manager.return_value.publish_managed_shares.assert_called_once_with(
        payload["shares_config"]
    )
    assert record_owned.call_count == 2
    assert record_owned.call_args_list[0].args[:2] == (runtime, "file-sharing")
    assert record_owned.call_args_list[0].kwargs["identifier"] == (
        "/etc/samba/simple_safer_server_globals.conf"
    )
    assert record_owned.call_args_list[1].args[:2] == (runtime, "file-sharing")
    assert record_owned.call_args_list[1].kwargs["identifier"] == (
        "/etc/samba/simple_safer_server_shares.conf"
    )
    assert result.data == {"message": "File sharing shares file published."}


def test_file_sharing_write_shares_action_rejects_nul_bytes():
    with pytest.raises(PrivilegedActionError, match="NUL bytes"):
        create_builtin_privileged_action_registry().run(
            "file-sharing.write-shares",
            {"shares_config": "\x00"},
        )


def test_file_sharing_sync_user_action_syncs_samba_account():
    runtime = SimpleNamespace()

    with patch(
        "simple_safer_server.core.privileged_job_actions.sync_user_to_samba_account",
        return_value=True,
    ) as sync:
        result = create_builtin_privileged_action_registry().run(
            "file-sharing.sync-user",
            {"username": "operator", "password": "secret-pass"},
            runtime=runtime,
        )

    sync.assert_called_once_with("operator", "secret-pass", runtime=runtime)
    assert result.data == {"username": "operator", "message": "Samba user synced."}


def test_file_sharing_sync_user_action_rejects_password_line_breaks():
    with pytest.raises(PrivilegedActionError, match="line breaks"):
        create_builtin_privileged_action_registry().run(
            "file-sharing.sync-user",
            {"username": "operator", "password": "secret\npass"},
        )


def test_file_sharing_remove_user_action_removes_samba_account():
    runtime = SimpleNamespace()

    with patch(
        "simple_safer_server.core.privileged_job_actions.remove_samba_account",
        return_value=True,
    ) as remove:
        result = create_builtin_privileged_action_registry().run(
            "file-sharing.remove-user",
            {"username": "operator"},
            runtime=runtime,
        )

    remove.assert_called_once_with("operator", runtime=runtime)
    assert result.data == {"username": "operator", "message": "Samba user removed."}


def test_storage_safety_check_action_reports_validated_location(tmp_path):
    runtime = SimpleNamespace()
    location = SimpleNamespace(mode="existing_folder", path=str(tmp_path))

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager") as config_manager,
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils") as system_utils,
        patch(
            "simple_safer_server.core.privileged_job_actions.validate_storage_ready_for_backup",
            return_value=location,
        ) as validate,
    ):
        result = create_builtin_privileged_action_registry().run(
            "storage.safety-check",
            {},
            runtime=runtime,
        )

    config_manager.assert_called_once_with(runtime=runtime)
    system_utils.assert_called_once_with(runtime=runtime)
    validate.assert_called_once()
    assert result.data == {"mode": "existing_folder", "path": str(tmp_path)}


def test_storage_mount_action_runs_storage_service(tmp_path):
    runtime = SimpleNamespace(
        is_fake=False,
        config_dir=tmp_path / "config",
        default_mount_point="/media/backup",
    )

    with patch("simple_safer_server.core.privileged_job_actions.StorageService") as storage_service:
        storage_service.return_value.mount_dashboard_drive.return_value = (
            "Drive mounted and available for use."
        )

        result = create_builtin_privileged_action_registry().run(
            "storage.mount",
            {},
            runtime=runtime,
        )

    storage_service.return_value.mount_dashboard_drive.assert_called_once_with()
    assert result.data == {"message": "Drive mounted and available for use."}


def test_storage_managed_drive_action_configures_drive():
    runtime = SimpleNamespace(default_mount_point="/media/backup")
    setup_result = {
        "message": "Successfully configured /dev/sdb1 at /mnt/backups",
        "mount_point": "/mnt/backups",
        "uuid": "DRIVE-UUID",
        "usb_id": "USB-ID",
        "ntfs_driver": "ntfs3",
    }

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager") as config_manager,
        patch("simple_safer_server.core.privileged_job_actions.SMBManager") as smb_manager,
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils") as system_utils,
        patch(
            "simple_safer_server.core.privileged_job_actions.configure_managed_drive_storage",
            return_value=setup_result,
        ) as configure,
        patch(
            "simple_safer_server.core.privileged_job_actions.record_runtime_owned_resource"
        ) as record_owned,
    ):
        result = create_builtin_privileged_action_registry().run(
            "storage.managed-drive",
            {
                "partition": " /dev/sdb1 ",
                "mount_point": " /mnt/backups ",
                "ntfs_driver": " ntfs3 ",
            },
            runtime=runtime,
        )

    config_manager.assert_called_once_with(runtime=runtime)
    smb_manager.assert_called_once_with(runtime=runtime)
    system_utils.assert_called_once_with(runtime=runtime)
    configure.assert_called_once_with(
        partition="/dev/sdb1",
        mount_point="/mnt/backups",
        config_manager=config_manager.return_value,
        smb_manager=smb_manager.return_value,
        system_utils=system_utils.return_value,
        runtime=runtime,
        ntfs_driver="ntfs3",
    )
    assert record_owned.call_count == 2
    assert record_owned.call_args_list[0].args[:2] == (runtime, "storage")
    assert record_owned.call_args_list[0].kwargs["identifier"] == (
        "/mnt/backups/.simple-safer-server/storage.json"
    )
    assert record_owned.call_args_list[1].args[:2] == (runtime, "storage")
    assert record_owned.call_args_list[1].kwargs["identifier"] == (
        "/etc/fstab#SimpleSaferServer managed backup drive"
    )
    assert result.data == setup_result


def test_storage_managed_drive_action_defaults_mount_point_and_ntfs_driver():
    runtime = SimpleNamespace(default_mount_point="/media/backup")

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager"),
        patch("simple_safer_server.core.privileged_job_actions.SMBManager"),
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils"),
        patch(
            "simple_safer_server.core.privileged_job_actions.configure_managed_drive_storage",
            return_value={"mount_point": "/media/backup"},
        ) as configure,
        patch("simple_safer_server.core.privileged_job_actions.record_runtime_owned_resource"),
    ):
        result = create_builtin_privileged_action_registry().run(
            "storage.managed-drive",
            {"partition": "/dev/sdb1"},
            runtime=runtime,
        )

    assert configure.call_args.kwargs["mount_point"] == "/media/backup"
    assert configure.call_args.kwargs["ntfs_driver"] == "ntfs-3g"
    assert result.data == {
        "message": "Managed drive configured.",
        "mount_point": "/media/backup",
        "uuid": "",
        "usb_id": "",
        "ntfs_driver": "ntfs-3g",
    }


def test_storage_managed_drive_action_rejects_unknown_payload_fields():
    with pytest.raises(PrivilegedActionError, match="Unsupported privileged action payload field"):
        create_builtin_privileged_action_registry().run(
            "storage.managed-drive",
            {"partition": "/dev/sdb1", "command": "mkfs"},
        )


def test_storage_managed_drive_action_requires_partition():
    with pytest.raises(PrivilegedActionError, match="Missing required"):
        create_builtin_privileged_action_registry().run(
            "storage.managed-drive",
            {"mount_point": "/media/backup"},
        )


def test_storage_managed_drive_action_reports_setup_error():
    runtime = SimpleNamespace(default_mount_point="/media/backup")

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager"),
        patch("simple_safer_server.core.privileged_job_actions.SMBManager"),
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils"),
        patch(
            "simple_safer_server.core.privileged_job_actions.configure_managed_drive_storage",
            side_effect=BackupDriveSetupError("The selected partition must be formatted as NTFS."),
        ),
    ):
        with pytest.raises(PrivilegedActionError, match="formatted as NTFS"):
            create_builtin_privileged_action_registry().run(
                "storage.managed-drive",
                {"partition": "/dev/sdb1"},
                runtime=runtime,
            )


def test_storage_format_action_formats_selected_disk():
    runtime = SimpleNamespace(default_mount_point="/media/backup")
    format_result = {
        "disk": "/dev/sdb",
        "partition": "/dev/sdb1",
        "message": "Successfully formatted /dev/sdb1 as NTFS.",
    }

    with patch(
        "simple_safer_server.core.privileged_job_actions.format_backup_drive",
        return_value=format_result,
    ) as format_drive:
        result = create_builtin_privileged_action_registry().run(
            "storage.format",
            {"disk": " /dev/sdb "},
            runtime=runtime,
        )

    format_drive.assert_called_once_with("/dev/sdb", runtime=runtime)
    assert result.data == format_result


def test_storage_format_action_rejects_unknown_payload_fields():
    with pytest.raises(PrivilegedActionError, match="Unsupported privileged action payload field"):
        create_builtin_privileged_action_registry().run(
            "storage.format",
            {"disk": "/dev/sdb", "command": "mkfs"},
        )


def test_storage_unmount_action_unmounts_whole_disk_partitions():
    runtime = SimpleNamespace(default_mount_point="/media/backup")

    with (
        patch(
            "simple_safer_server.core.privileged_job_actions.unmount_disk_partitions",
            return_value="Successfully unmounted 2 partition(s).",
        ) as unmount_disk,
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager"),
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils"),
    ):
        result = create_builtin_privileged_action_registry().run(
            "storage.unmount",
            {"disk": "/dev/sdb"},
            runtime=runtime,
        )

    unmount_disk.assert_called_once_with("/dev/sdb", runtime=runtime)
    assert result.data == {"message": "Successfully unmounted 2 partition(s)."}


def test_storage_unmount_action_reports_managed_retry_available():
    runtime = SimpleNamespace(default_mount_point="/media/backup")

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager") as config_manager,
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils") as system_utils,
        patch(
            "simple_safer_server.core.privileged_job_actions.unmount_selected_partition",
            side_effect=BackupDriveSetupError("Failed to unmount partition: target is busy"),
        ),
        patch(
            "simple_safer_server.core.privileged_job_actions.is_selected_partition_managed_backup_drive",
            return_value=True,
        ) as is_managed,
    ):
        config_manager.return_value.get_value.side_effect = ["/media/backup", "UUID-1"]

        result = create_builtin_privileged_action_registry().run(
            "storage.unmount",
            {"partition": "/dev/sdb1"},
            runtime=runtime,
        )

    is_managed.assert_called_once_with(
        "/dev/sdb1",
        "/media/backup",
        "UUID-1",
        system_utils.return_value,
        runtime=runtime,
    )
    assert result.data == {"can_retry_managed_unmount": True}


def test_storage_unmount_action_runs_managed_retry():
    runtime = SimpleNamespace(default_mount_point="/media/backup")

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager") as config_manager,
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils") as system_utils,
        patch(
            "simple_safer_server.core.privileged_job_actions.is_selected_partition_managed_backup_drive",
            return_value=True,
        ),
        patch(
            "simple_safer_server.core.privileged_job_actions.unmount_managed_backup_drive",
        ) as unmount_managed,
    ):
        config_manager.return_value.get_value.side_effect = ["/media/backup", "UUID-1"]

        result = create_builtin_privileged_action_registry().run(
            "storage.unmount",
            {"partition": "/dev/sdb1", "force_managed": True},
            runtime=runtime,
        )

    unmount_managed.assert_called_once_with(
        "/media/backup",
        "UUID-1",
        system_utils.return_value,
        runtime=runtime,
        power_down=False,
    )
    assert "SMB-safe retry" in result.data["message"]


def test_storage_managed_unmount_action_unmounts_configured_drive():
    runtime = SimpleNamespace(default_mount_point="/media/backup")

    with (
        patch("simple_safer_server.core.privileged_job_actions.ConfigManager") as config_manager,
        patch("simple_safer_server.core.privileged_job_actions.SystemUtils") as system_utils,
        patch(
            "simple_safer_server.core.privileged_job_actions.unmount_managed_backup_drive",
        ) as unmount_managed,
    ):
        config_manager.return_value.get_value.side_effect = ["/media/backup", "UUID-1"]

        result = create_builtin_privileged_action_registry().run(
            "storage.managed-unmount",
            {"power_down": True},
            runtime=runtime,
        )

    unmount_managed.assert_called_once_with(
        "/media/backup",
        "UUID-1",
        system_utils.return_value,
        runtime=runtime,
        power_down=True,
    )
    assert result.data == {
        "mount_point": "/media/backup",
        "uuid": "UUID-1",
        "power_down": True,
    }


def test_system_reboot_action_uses_storage_adapter():
    runtime = SimpleNamespace(is_fake=False)

    with patch("simple_safer_server.core.privileged_job_actions.StorageCommandAdapter") as adapter:
        result = create_builtin_privileged_action_registry().run(
            "system.reboot",
            {},
            runtime=runtime,
        )

    adapter.return_value.reboot.assert_called_once_with()
    assert result.data == {"message": "System is restarting..."}


def test_system_poweroff_action_uses_storage_adapter():
    runtime = SimpleNamespace(is_fake=False)

    with patch("simple_safer_server.core.privileged_job_actions.StorageCommandAdapter") as adapter:
        result = create_builtin_privileged_action_registry().run(
            "system.poweroff",
            {},
            runtime=runtime,
        )

    adapter.return_value.poweroff.assert_called_once_with()
    assert result.data == {"message": "System is shutting down..."}


def test_system_power_actions_reject_payload_fields():
    runtime = SimpleNamespace(is_fake=True)

    with pytest.raises(PrivilegedActionError, match="does not accept payload"):
        create_builtin_privileged_action_registry().run(
            "system.reboot",
            {"now": True},
            runtime=runtime,
        )
