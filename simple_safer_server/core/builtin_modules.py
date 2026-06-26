from __future__ import annotations

from simple_safer_server.core.module_contract import ModuleRegistry
from simple_safer_server.modules.alerts.module import create_module as create_alerts_module
from simple_safer_server.modules.cloud_backup.module import (
    create_module as create_cloud_backup_module,
)
from simple_safer_server.modules.ddns.module import create_module as create_ddns_module
from simple_safer_server.modules.drive_health.module import (
    create_module as create_drive_health_module,
)
from simple_safer_server.modules.file_sharing.module import (
    create_module as create_file_sharing_module,
)
from simple_safer_server.modules.storage.module import create_module as create_storage_module
from simple_safer_server.modules.system_updates.module import (
    create_module as create_system_updates_module,
)


def create_builtin_module_registry() -> ModuleRegistry:
    return ModuleRegistry(
        (
            create_alerts_module(),
            create_cloud_backup_module(),
            create_ddns_module(),
            create_drive_health_module(),
            create_file_sharing_module(),
            create_storage_module(),
            create_system_updates_module(),
        )
    )
