from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from simple_safer_server.core.module_contract import OwnedResource
from simple_safer_server.services.file_persistence import locked_json_update, read_json


@dataclass(frozen=True)
class OwnershipRecord:
    module_slug: str
    kind: str
    identifier: str
    reason: str

    @classmethod
    def from_resource(cls, module_slug: str, resource: OwnedResource) -> OwnershipRecord:
        return cls(
            module_slug=module_slug,
            kind=resource.kind,
            identifier=resource.identifier,
            reason=resource.reason,
        )


class OwnershipManifest:
    """Records host resources that SimpleSaferServer owns by module."""

    VERSION = 1

    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_suffix(f"{path.suffix}.lock")

    def list_records(self) -> tuple[OwnershipRecord, ...]:
        payload = read_json(self.path, self._empty_payload())
        return tuple(
            OwnershipRecord(
                module_slug=str(item.get("module_slug", "")),
                kind=str(item.get("kind", "")),
                identifier=str(item.get("identifier", "")),
                reason=str(item.get("reason", "")),
            )
            for item in payload.get("resources", [])
            if item.get("module_slug") and item.get("kind") and item.get("identifier")
        )

    def record_module_resources(
        self,
        module_slug: str,
        resources: tuple[OwnedResource, ...],
    ) -> tuple[OwnershipRecord, ...]:
        new_records = tuple(
            OwnershipRecord.from_resource(module_slug, resource) for resource in resources
        )

        def update(payload):
            records = self._records_by_key(payload)
            for record in new_records:
                records[self._record_key(record)] = asdict(record)
            return self._payload_from_records(records.values())

        locked_json_update(
            self.path,
            self.lock_path,
            self._empty_payload(),
            update,
            file_mode=0o600,
            lock_mode=0o600,
        )
        return new_records

    def remove_module_records(self, module_slug: str) -> tuple[OwnershipRecord, ...]:
        removed: tuple[OwnershipRecord, ...] = ()

        def update(payload):
            nonlocal removed
            kept = []
            removed_items = []
            for record in self.list_records_from_payload(payload):
                if record.module_slug == module_slug:
                    removed_items.append(record)
                else:
                    kept.append(asdict(record))
            removed = tuple(removed_items)
            return self._payload_from_records(kept)

        locked_json_update(
            self.path,
            self.lock_path,
            self._empty_payload(),
            update,
            file_mode=0o600,
            lock_mode=0o600,
        )
        return removed

    def remove_resource(
        self,
        module_slug: str,
        *,
        kind: str,
        identifier: str,
    ) -> tuple[OwnershipRecord, ...]:
        removed: tuple[OwnershipRecord, ...] = ()

        def update(payload):
            nonlocal removed
            kept = []
            removed_items = []
            for record in self.list_records_from_payload(payload):
                if (
                    record.module_slug == module_slug
                    and record.kind == kind
                    and record.identifier == identifier
                ):
                    removed_items.append(record)
                else:
                    kept.append(asdict(record))
            removed = tuple(removed_items)
            return self._payload_from_records(kept)

        locked_json_update(
            self.path,
            self.lock_path,
            self._empty_payload(),
            update,
            file_mode=0o600,
            lock_mode=0o600,
        )
        return removed

    @classmethod
    def list_records_from_payload(cls, payload) -> tuple[OwnershipRecord, ...]:
        return tuple(
            OwnershipRecord(
                module_slug=str(item.get("module_slug", "")),
                kind=str(item.get("kind", "")),
                identifier=str(item.get("identifier", "")),
                reason=str(item.get("reason", "")),
            )
            for item in payload.get("resources", [])
            if item.get("module_slug") and item.get("kind") and item.get("identifier")
        )

    @classmethod
    def _empty_payload(cls):
        return {"version": cls.VERSION, "resources": []}

    @classmethod
    def _record_key(cls, record: OwnershipRecord) -> tuple[str, str, str]:
        return (record.module_slug, record.kind, record.identifier)

    @classmethod
    def _records_by_key(cls, payload):
        return {
            cls._record_key(record): asdict(record)
            for record in cls.list_records_from_payload(payload)
        }

    @classmethod
    def _payload_from_records(cls, records):
        sorted_records = sorted(
            records,
            key=lambda item: (
                str(item.get("module_slug", "")),
                str(item.get("kind", "")),
                str(item.get("identifier", "")),
            ),
        )
        return {"version": cls.VERSION, "resources": sorted_records}


def record_runtime_owned_resource(
    runtime,
    module_slug: str,
    *,
    kind: str,
    identifier: str,
    reason: str,
) -> OwnershipRecord:
    """Record one host resource written by a runtime action."""
    manifest = OwnershipManifest(Path(runtime.data_dir) / "ownership.json")
    records = manifest.record_module_resources(
        module_slug,
        (OwnedResource(kind=kind, identifier=identifier, reason=reason),),
    )
    return records[0]


def remove_runtime_owned_resource(
    runtime,
    module_slug: str,
    *,
    kind: str,
    identifier: str,
) -> tuple[OwnershipRecord, ...]:
    """Remove one host resource ownership record after the resource is gone."""
    manifest = OwnershipManifest(Path(runtime.data_dir) / "ownership.json")
    return manifest.remove_resource(module_slug, kind=kind, identifier=identifier)
