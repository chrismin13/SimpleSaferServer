# API Response Contract Refactor

This task migrates API routes and services from ad hoc `success` dictionaries to a Data + Problem
contract.

Durable rules belong in `docs/api_responses.md`, `docs/development.md`, and `docs/architecture.md`.
This note tracks the migration context:

- Success responses use `{"data": ...}` with optional `message`.
- Error responses use Problem Details and real HTTP status codes.
- Services should return dataclasses or other plain Python objects and raise app-level problem
  exceptions instead of returning HTTP-shaped dictionaries.
- Existing low-level adapter `(ok, error)` pairs can remain where they are not API/service response
  contracts.
- CI stays advisory during the migration; focused tests should cover each migrated slice.
- The setup wizard API was migrated last because it had the most UI-specific error details:
  disk-format guidance, mounted partition details, and SMB-safe unmount retry hints.
- The legacy import package and `scripts/import_legacy.py` remain because they import bundles from
  https://github.com/chrismin13/SimpleSaferServer-old. Remove them after that migration path is no
  longer needed.
