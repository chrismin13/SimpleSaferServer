"""Storage module package."""

from simple_safer_server.modules.storage.location import (
    MODE_EXISTING_FOLDER,
    MODE_MANAGED_DRIVE,
    StorageLocation,
    StorageLocationError,
    get_storage_location,
    marker_path,
    storage_status,
    validate_storage_ready_for_backup,
)
from simple_safer_server.modules.storage.service import StorageService

__all__ = [
    "MODE_EXISTING_FOLDER",
    "MODE_MANAGED_DRIVE",
    "StorageLocation",
    "StorageLocationError",
    "StorageService",
    "get_storage_location",
    "marker_path",
    "storage_status",
    "validate_storage_ready_for_backup",
]
