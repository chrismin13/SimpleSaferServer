from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.module_contract import (
    ModuleHelp,
    ModuleState,
    OwnedResource,
    SssModule,
)
from simple_safer_server.core.module_lifecycle import (
    ModuleLifecycleError,
    apply_module,
    module_is_applied,
    ownership_manifest_for_runtime,
    ownership_manifest_path,
    require_module_applied,
    uninstall_module,
)
from simple_safer_server.services.config_manager import ConfigManager


def _tool_path(name: str) -> str | None:
    if name == "update-ca-certificates":
        return "/usr/sbin/update-ca-certificates"
    return None


def test_apply_module_records_declared_resources(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    module = create_builtin_module_registry().module_for_slug("alerts")

    assert not module_is_applied(module, runtime)

    with patch("simple_safer_server.core.module_checks.shutil.which", side_effect=_tool_path):
        result = apply_module(module, runtime)

    assert result.module_slug == "alerts"
    assert [record.identifier for record in result.recorded] == [
        "<config>/smtp.conf",
        "<config>/alerts.json",
    ]
    assert ownership_manifest_path(runtime) == tmp_path / "ownership.json"
    assert ownership_manifest_for_runtime(runtime).list_records() == result.recorded
    assert module_is_applied(module, runtime)
    require_module_applied(module, runtime)


def test_require_module_applied_blocks_before_ownership_is_recorded(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    module = create_builtin_module_registry().module_for_slug("alerts")

    try:
        require_module_applied(module, runtime)
    except ModuleLifecycleError as exc:
        assert "must be applied before it can write config" in str(exc)
    else:
        raise AssertionError("host-writing modules must be applied before config writes")


def test_uninstall_module_removes_only_that_modules_records(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    smtp_config = config_dir / "smtp.conf"
    alerts_history = config_dir / "alerts.json"
    smtp_config.write_text("smtp", encoding="utf-8")
    alerts_history.write_text("[]", encoding="utf-8")
    runtime = SimpleNamespace(data_dir=tmp_path, config_dir=config_dir)
    registry = create_builtin_module_registry()
    alerts = registry.module_for_slug("alerts")
    storage = registry.module_for_slug("storage")
    with patch("simple_safer_server.core.module_checks.shutil.which", side_effect=_tool_path):
        apply_module(alerts, runtime)
    apply_module(storage, runtime)

    result = uninstall_module(alerts, runtime)

    assert result.module_slug == "alerts"
    assert {record.module_slug for record in result.removed} == {"alerts"}
    assert set(result.removed_paths) == {str(smtp_config), str(alerts_history)}
    assert not smtp_config.exists()
    assert not alerts_history.exists()
    remaining = ownership_manifest_for_runtime(runtime).list_records()
    assert remaining
    assert {record.module_slug for record in remaining} == {"storage"}


def test_read_only_module_cannot_be_applied_or_uninstalled(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    module = create_builtin_module_registry().module_for_slug("system-updates")

    try:
        apply_module(module, runtime)
    except ModuleLifecycleError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("read-only modules must not be applied")

    try:
        uninstall_module(module, runtime)
    except ModuleLifecycleError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("read-only modules must not be uninstalled")


def test_apply_module_blocks_when_required_tools_are_missing(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    module = create_builtin_module_registry().module_for_slug("cloud-backup")

    with patch("simple_safer_server.core.module_checks.shutil.which", return_value=None):
        try:
            apply_module(module, runtime)
        except ModuleLifecycleError as exc:
            assert "required tools are missing: update-ca-certificates, rclone" in str(exc)
        else:
            raise AssertionError("module apply must block when required tools are missing")

    assert not (tmp_path / "ownership.json").exists()


def test_uninstall_module_rejects_unsafe_app_owned_paths(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path, config_dir=tmp_path / "config")
    module = create_builtin_module_registry().module_for_slug("alerts")
    manifest = ownership_manifest_for_runtime(runtime)
    manifest.record_module_resources(
        "alerts",
        (
            OwnedResource(
                kind="config-file",
                identifier="<config>/../outside.conf",
                reason="Exercise path safety.",
            ),
        ),
    )

    try:
        uninstall_module(module, runtime)
    except ModuleLifecycleError as exc:
        assert "Unsafe app-owned path" in str(exc)
    else:
        raise AssertionError("unsafe app-owned paths must be rejected")


def test_uninstall_module_refuses_to_forget_host_resources(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path, config_dir=tmp_path / "config")
    module = create_builtin_module_registry().module_for_slug("storage")
    ownership_manifest_for_runtime(runtime).record_module_resources(
        "storage",
        (
            OwnedResource(
                kind="fstab-entry",
                identifier="/etc/fstab#SimpleSaferServer managed backup drive",
                reason="Mount only the explicitly managed backup drive.",
            ),
        ),
    )

    try:
        uninstall_module(module, runtime)
    except ModuleLifecycleError as exc:
        assert "cannot remove these owned resources safely" in str(exc)
        assert "fstab-entry /etc/fstab#SimpleSaferServer managed backup drive" in str(exc)
    else:
        raise AssertionError("generic uninstall must not forget host-owned resources")

    remaining = ownership_manifest_for_runtime(runtime).list_records()
    assert remaining
    assert {record.module_slug for record in remaining} == {"storage"}


def test_storage_apply_records_only_generic_config_ownership(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path, config_dir=tmp_path / "config")
    module = create_builtin_module_registry().module_for_slug("storage")

    result = apply_module(module, runtime)

    assert [(record.kind, record.identifier) for record in result.recorded] == [
        ("config-section", "<config>/config.conf[storage]")
    ]


def test_file_sharing_apply_records_only_setup_acceptance(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    module = create_builtin_module_registry().module_for_slug("file-sharing")

    with patch("simple_safer_server.core.module_checks.shutil.which", return_value="/usr/sbin/smbd"):
        result = apply_module(module, runtime)

    assert [(record.kind, record.identifier) for record in result.recorded] == [
        ("module-state", "<data>/ownership.json[file-sharing-applied]")
    ]


def test_uninstall_module_removes_safe_absolute_app_owned_files(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    owned_file = config_dir / "demo.conf"
    owned_file.write_text("demo", encoding="utf-8")
    runtime = SimpleNamespace(data_dir=tmp_path / "data", config_dir=config_dir)
    module = SssModule(
        slug="demo",
        title="Demo",
        description="Demo module.",
        state=ModuleState.ACTIVE,
        help=ModuleHelp(purpose="Exercise safe absolute app-owned cleanup."),
        owned_resources=(
            OwnedResource(
                kind="config-file",
                identifier=str(owned_file),
                reason="Exercise safe absolute cleanup.",
            ),
        ),
    )
    apply_module(module, runtime)

    result = uninstall_module(module, runtime)

    assert result.removed_paths == (str(owned_file),)
    assert not owned_file.exists()
    assert ownership_manifest_for_runtime(runtime).list_records() == ()


def test_uninstall_module_removes_owned_config_sections_and_secrets(tmp_path):
    runtime = SimpleNamespace(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        default_mount_point="/media/backup",
    )
    config_manager = ConfigManager(runtime=runtime)
    config_manager.set_value("ddns", "duckdns_domain", "home")
    config_manager.store_secret("duckdns_token", "duck-token")
    config_manager.store_secret("cloudflare_token", "cf-token")
    module = create_builtin_module_registry().module_for_slug("ddns")
    with patch("simple_safer_server.core.module_checks.shutil.which", side_effect=_tool_path):
        apply_module(module, runtime)

    result = uninstall_module(module, runtime)

    assert result.module_slug == "ddns"
    reloaded = ConfigManager(runtime=runtime)
    assert "ddns" not in reloaded.get_all_config()
    assert reloaded.get_secret("duckdns_token") is None
    assert reloaded.get_secret("cloudflare_token") is None
    assert ownership_manifest_for_runtime(runtime).list_records() == ()


def test_uninstall_module_removes_data_file_and_config_section(tmp_path):
    runtime = SimpleNamespace(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        default_mount_point="/media/backup",
    )
    runtime.data_dir.mkdir()
    hdsentinel_state = runtime.data_dir / "hdsentinel_state.json"
    hdsentinel_state.write_text("{}", encoding="utf-8")
    config_manager = ConfigManager(runtime=runtime)
    config_manager.set_value("hdsentinel", "enabled", "true")
    module = create_builtin_module_registry().module_for_slug("drive-health")
    apply_module(module, runtime)

    result = uninstall_module(module, runtime)

    assert result.module_slug == "drive-health"
    assert result.removed_paths == (str(hdsentinel_state),)
    assert not hdsentinel_state.exists()
    reloaded = ConfigManager(runtime=runtime)
    assert "hdsentinel" not in reloaded.get_all_config()
    assert ownership_manifest_for_runtime(runtime).list_records() == ()
