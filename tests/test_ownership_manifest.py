from types import SimpleNamespace

from simple_safer_server.core.module_contract import OwnedResource
from simple_safer_server.core.ownership import OwnershipManifest, record_runtime_owned_resource


def test_records_module_resources_with_private_manifest_file(tmp_path):
    manifest = OwnershipManifest(tmp_path / "ownership.json")

    manifest.record_module_resources(
        "cloud-backup",
        (
            OwnedResource(
                kind="config-file",
                identifier="/etc/SimpleSaferServer/rclone/rclone.conf",
                reason="Keep rclone config owned by SSS.",
            ),
        ),
    )

    records = manifest.list_records()
    assert len(records) == 1
    assert records[0].module_slug == "cloud-backup"
    assert records[0].identifier == "/etc/SimpleSaferServer/rclone/rclone.conf"
    assert manifest.path.stat().st_mode & 0o777 == 0o600


def test_recording_same_resource_updates_instead_of_duplicating(tmp_path):
    manifest = OwnershipManifest(tmp_path / "ownership.json")
    first_resource = OwnedResource(
        kind="config-file",
        identifier="/etc/example.conf",
        reason="Old reason.",
    )
    updated_resource = OwnedResource(
        kind="config-file",
        identifier="/etc/example.conf",
        reason="Updated reason.",
    )

    manifest.record_module_resources("demo", (first_resource,))
    manifest.record_module_resources("demo", (updated_resource,))

    records = manifest.list_records()
    assert len(records) == 1
    assert records[0].reason == "Updated reason."


def test_removes_only_records_for_requested_module(tmp_path):
    manifest = OwnershipManifest(tmp_path / "ownership.json")
    manifest.record_module_resources(
        "cloud-backup",
        (OwnedResource(kind="config-file", identifier="/etc/rclone.conf", reason="Cloud."),),
    )
    manifest.record_module_resources(
        "file-sharing",
        (OwnedResource(kind="config-file", identifier="/etc/samba/sss.conf", reason="Samba."),),
    )

    removed = manifest.remove_module_records("cloud-backup")

    assert [record.identifier for record in removed] == ["/etc/rclone.conf"]
    assert [record.module_slug for record in manifest.list_records()] == ["file-sharing"]


def test_removes_one_runtime_owned_resource(tmp_path):
    manifest = OwnershipManifest(tmp_path / "ownership.json")
    manifest.record_module_resources(
        "file-sharing",
        (
            OwnedResource(kind="samba-account", identifier="alice", reason="Samba."),
            OwnedResource(kind="system-user", identifier="alice", reason="Linux user."),
        ),
    )

    removed = manifest.remove_resource("file-sharing", kind="samba-account", identifier="alice")

    assert [(record.kind, record.identifier) for record in removed] == [
        ("samba-account", "alice")
    ]
    assert [(record.kind, record.identifier) for record in manifest.list_records()] == [
        ("system-user", "alice")
    ]


def test_records_runtime_owned_resource(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)

    record = record_runtime_owned_resource(
        runtime,
        "alerts",
        kind="config-file",
        identifier="/etc/SimpleSaferServer/smtp.conf",
        reason="SMTP config.",
    )

    assert record.module_slug == "alerts"
    assert record.identifier == "/etc/SimpleSaferServer/smtp.conf"
    records = OwnershipManifest(tmp_path / "ownership.json").list_records()
    assert records == (record,)
