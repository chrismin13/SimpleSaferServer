# Cloud Backup Setup Service Refactor

## Context

The cloud backup management page already uses `CloudBackupService`, but the setup wizard still
implemented MEGA password obscuring, temporary rclone config generation, folder listing, folder
creation, and credential persistence inside the route module.

## Decision

Keep the existing setup wizard endpoint URLs and request field names as onboarding compatibility
wrappers. Delegate the actual cloud-backup behavior to `CloudBackupService` so onboarding and
post-setup management use the same rclone and configuration rules.

## Follow-up Checks

- Setup wizard tests should verify the legacy setup payloads are mapped to the shared service.
- Cloud backup service tests remain the behavior source for rclone command shape, timeouts,
  credential write ordering, and advanced rclone persistence.
