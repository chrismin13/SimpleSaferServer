# Samba Effective Config Hardening PRD

## Problem Statement

The Samba discovery/config redesign moved SimpleSaferServer-managed shares into an owned shares
file, but the implementation still has a few pre-submit safety gaps. Administrators need
SimpleSaferServer to detect Unmanaged Samba Shares the same way Samba loads them, fail required
`smbd` paths when core file serving cannot run, recover cleanly from failed share publishes, and
remove owned Samba files during uninstall even when the main Samba config is missing.

The current implementation validates Samba configs with `testparm`, but unmanaged-share conflict
detection still scans the main Samba config text directly. That misses shares from non-SSS include
files and can allow a SimpleSaferServer-Managed Share to be created with a name Samba already loads
from another source. The installer also prepares Samba services without checking the required
service setup function's return value, share-publish rollback restores the old shares file without
restarting `smbd`, uninstall skips owned-file deletion when the main Samba config is absent, and
manual install docs use an import command that can fail outside the app directory.

## Solution

Harden the Samba redesign before submission. Use Samba's own include-aware parsing for Unmanaged
Samba Share detection by running `testparm` against a volatile stripped copy of the main Samba
config with SimpleSaferServer-owned include blocks removed. Keep the SimpleSaferServer-owned shares
file as the source of truth for SimpleSaferServer-Managed Shares. Treat write-safety verification as
fail-closed, and present read/UI verification problems as controlled warnings or errors instead of
pretending no unmanaged shares exist.

Make share publishing rollback complete by restarting `smbd` after restoring the previous
SimpleSaferServer-owned shares file. Make the installer honor required `smbd` failure while still
warning loudly, rather than failing, when boot-enable commands fail but `smbd` is active. Split
uninstall's include-block rewrite from owned-file deletion. Update manual install documentation so
the Samba layout helper command works from a copied app directory.

## User Stories

1. As an administrator, I want SimpleSaferServer to detect Samba shares from non-SSS include files, so that the app does not create duplicate share names.
2. As an administrator, I want setup to reject an unmanaged `backup` share loaded from any Samba include, so that setup does not silently override my manual Samba config.
3. As an administrator, I want the Network File Sharing page to warn about Unmanaged Samba Shares from the Effective Samba Config, so that the UI matches what Samba actually loads.
4. As an administrator, I want unmanaged-share verification failures to be visible, so that I do not mistake an inspection problem for a clean Samba config.
5. As an administrator using SD-card storage, I want temporary Samba inspection files to live under the volatile runtime directory, so that ordinary verification does not add avoidable disk wear.
6. As an administrator, I want share create and rename operations to fail closed when Samba's effective config cannot be inspected, so that SimpleSaferServer never relies on include precedence guesses.
7. As an administrator, I want editing an existing SimpleSaferServer-Managed Share to keep using the owned shares file, so that ownership remains file-path based.
8. As an administrator, I want deleting a SimpleSaferServer-Managed Share to avoid unnecessary unmanaged conflict checks, so that deletion stays focused on owned state.
9. As an administrator, I want a failed share publish to restore the old shares file and restart `smbd`, so that rollback attempts to return file serving to the previous working state.
10. As an administrator, I want rollback restart failures reported clearly, so that I know when Samba may still need manual recovery.
11. As an administrator, I want add/edit/delete/restart failures to appear in the existing modal or toast notification flow, so that errors are actionable in the Web UI.
12. As an administrator, I want the installer to stop when `smbd` is not active after service setup, so that a broken file server is not reported as a successful install.
13. As an administrator, I want loud installer warnings when `smbd` is active but enabling it at boot fails, so that I can fix reboot persistence before relying on file sharing.
14. As an administrator, I want discovery service failures to remain non-fatal, so that `nmbd` or `wsdd2` problems do not block direct SMB file serving.
15. As an administrator, I want uninstall to delete SimpleSaferServer-owned Samba files even if the main Samba config is missing, so that app-owned config is cleaned up predictably.
16. As an administrator, I want uninstall to avoid rewriting malformed main Samba config marker blocks, so that unrelated Samba config is not damaged.
17. As an administrator, I want uninstall to leave shared Samba packages and unrelated service state alone, so that host-level services are not unexpectedly removed or disabled.
18. As an administrator following manual install docs, I want the Samba layout helper command to work from the installed app directory, so that manual setup does not fail on Python import paths.
19. As a future maintainer, I want one tested path for Unmanaged Samba Share detection, so that UI warnings and write safety cannot drift apart.
20. As a future maintainer, I want the phrase Unmanaged Samba Share to mean include-aware Samba state, so that future code does not reintroduce direct `smb.conf` scanning.
21. As a future maintainer, I want temporary effective-config inspection to use the runtime volatile directory, so that the no-SD-card-wear reasoning is preserved in code and tests.
22. As a future maintainer, I want rollback tests to prove service recovery is attempted after restoring old config, so that publish failure handling remains operationally complete.
23. As a future maintainer, I want installer tests to cover the top-level function return handling, so that required service failures cannot be accidentally ignored again.
24. As a future maintainer, I want uninstall tests to cover missing main config plus owned-file deletion, so that cleanup is not coupled to one file's existence.
25. As a future maintainer, I want manual install documentation checked with the same import-path assumptions as the installer, so that docs do not drift from code behavior.

## Implementation Decisions

- Keep file-path ownership as the Samba management boundary.
- A SimpleSaferServer-Managed Share is still any share section sourced from the SimpleSaferServer-owned shares file.
- An Unmanaged Samba Share is any non-system share that Samba can load after SimpleSaferServer-owned include blocks are excluded.
- Do not use comments or legacy share marker blocks to determine SimpleSaferServer ownership.
- Do not use direct main-config scanning as the authority for unmanaged-share write safety.
- Add a deep, testable service/helper method for Unmanaged Samba Share inspection.
- The unmanaged-share inspector should read the live main Samba config, remove only SimpleSaferServer-owned include marker blocks, write the stripped candidate under the volatile runtime directory, run `testparm -s` on that candidate, parse non-system section names from the output, and delete the candidate.
- The volatile runtime directory is required for real-mode effective-config inspection. Do not fall back to `/tmp` for write-safety checks.
- Effective-config inspection failures should fail create, rename, and setup default-share writes with a controlled operation/validation response.
- The Network File Sharing page should use the same Unmanaged Samba Share detection path for its warning state. If inspection fails on this read path, return a controlled response that lets the UI show that unmanaged shares could not be verified.
- Managed share listing, editing, and deletion should continue parsing the SimpleSaferServer-owned shares file directly.
- Before creating a SimpleSaferServer-Managed Share, reject the target name if it appears as an Unmanaged Samba Share.
- Before renaming a SimpleSaferServer-Managed Share, reject the new name if it appears as an Unmanaged Samba Share.
- Updating an existing SimpleSaferServer-Managed Share without changing its name should not be blocked by that owned name appearing in the full live config.
- Share publish rollback should restore the previous SimpleSaferServer-owned shares file and then restart the required `smbd` service path.
- If rollback restart fails, expose a controlled operation error that states the share update failed and rollback could not restart `smbd`.
- Existing frontend modal/toast behavior should surface these controlled API problem details without creating a new UI pattern.
- The installer should check the return value from Samba service setup and exit when `smbd` is not active after service setup.
- The installer should treat `smbd` active state as the hard requirement. Failed `enable` or `start` commands should warn loudly when final active state is still `active`.
- Discovery services remain best-effort. `nmbd` and `wsdd2` enable/start/status failures should warn or show partial state, not fail install or share publish.
- Uninstall should rewrite the main Samba config only when it exists.
- Uninstall should delete SimpleSaferServer-owned Samba files regardless of whether the main Samba config exists.
- Malformed SimpleSaferServer include marker blocks should still prevent rewriting the main Samba config.
- Manual install docs should run the Samba layout helper from the installed app directory and insert the installed app path into `sys.path`, matching the automated installer's import assumptions.
- Do not edit `README.md`.
- Do not add startup auto-heal or status-polling writes.

Major modules to build or modify:

- Samba layout/helper service: expose reusable marker-block stripping or effective-config inspection behavior without duplicating parsing in unrelated modules.
- SMB command adapter: support `testparm` effective config inspection as a first-class command shape.
- SMB manager: use include-aware Unmanaged Samba Share detection for list warnings, create conflicts, rename conflicts, and setup default `backup` conflicts; complete rollback by restarting `smbd` after restore.
- SMB routes/API response mapping: preserve controlled Problem Details so the existing UI can display actionable modal/toast errors.
- Network File Sharing template: show a controlled verification warning if unmanaged-share inspection cannot be completed.
- Installer script: check required Samba service setup return value and add loud `smbd` enable/start warnings when active state still passes.
- Uninstaller script: split main-config rewrite from owned-file deletion.
- Manual install docs: update the Samba layout helper command.

## Testing Decisions

Good tests should verify external behavior and safety boundaries rather than private implementation
details. The important behavior is that SimpleSaferServer uses Samba's include-aware config loading
for Unmanaged Samba Share detection, never overwrites a user share by name, avoids non-volatile temp
writes for write-safety inspection, completes rollback service recovery, fails required `smbd`
installer paths, and cleans up owned files on uninstall.

Modules and behaviors to test:

- Effective config / unmanaged-share inspection:
  - Runs `testparm` against a stripped candidate config with SimpleSaferServer-owned include blocks removed.
  - Uses the volatile runtime directory for the candidate file.
  - Does not fall back to `/tmp` when the volatile runtime directory cannot be used for write safety.
  - Parses non-system share names from `testparm` output.
  - Respects non-SSS include files in the stripped config.
  - Fails closed when marker blocks are malformed.
  - Fails closed when `testparm` cannot run or returns failure.
- SMB manager:
  - Lists SimpleSaferServer-Managed Shares from the owned shares file.
  - Lists/warns about Unmanaged Samba Shares from stripped effective config.
  - Rejects create when the target name exists in stripped effective config.
  - Rejects rename when the new name exists in stripped effective config.
  - Rejects setup default `backup` when stripped effective config contains unmanaged `backup`.
  - Allows updating an existing owned share without treating itself as unmanaged.
  - Restores the old shares file after publish failure.
  - Restarts `smbd` after rollback restore.
  - Surfaces rollback restart failure as a controlled operation error.
- API/UI:
  - Add/edit/delete/restart failures continue displaying API detail text through existing modal/toast behavior.
  - Unmanaged-share verification failure on page load is visible and not silently treated as zero unmanaged shares.
- Installer:
  - Top-level installer exits when Samba service setup returns failure.
  - `smbd` inactive after start fails install.
  - `smbd` enable/start command failure with final active state still active emits a loud warning and continues.
  - `nmbd` and `wsdd2` failures remain non-fatal and are included in service summary behavior.
- Uninstaller:
  - Deletes SimpleSaferServer-owned Samba files when the main Samba config is missing.
  - Removes include blocks when the main Samba config exists.
  - Does not rewrite malformed marker blocks.
  - Leaves unmanaged shares, unrelated include lines, shared packages, and non-SSS service state alone.
- Documentation:
  - Manual install command works from the installed app directory and mirrors automated installer import-path behavior.
  - Network File Sharing docs match the Effective Samba Config and Unmanaged Samba Share terminology.

Prior art:

- Existing Samba layout tests cover marker placement, idempotency, malformed marker failure, validation, and rollback.
- Existing SMB manager tests cover SSS-file list/create/update/delete, unmanaged conflict rejection, validation failure rollback, restart behavior, and service status.
- Existing installer preflight/static tests cover optional `wsdd2`, required service behavior, service summary output, and helper invocation.
- Existing uninstall tests cover include block removal, owned file deletion, malformed marker rejection, and service-state preservation.
- Existing app factory/template tests cover Network File Sharing and Dashboard rendering behavior.

## Out of Scope

- Reworking the Samba ownership model beyond the existing SSS-owned include file design.
- Supporting custom `wsdd` wrappers or installing `wsdd`.
- Making SimpleSaferServer a general Samba editor.
- Preserving unsupported manual directives when a SimpleSaferServer-Managed Share is edited through the Web UI.
- Removing Samba, `wsdd2`, or other shared packages on uninstall.
- Adding startup auto-heal or Samba config rewrites on ordinary status polling.
- Editing `README.md`.

## Further Notes

This PRD is a follow-up to the Samba discovery/config redesign review. The core design remains
sound; this work closes pre-submit gaps found during review. The agreed terminology is recorded in
the root context glossary: SimpleSaferServer-Managed Share, Unmanaged Samba Share, and Effective
Samba Config.

The preferred implementation should keep the effective-config inspection logic deep and narrow:
callers should ask for Unmanaged Samba Shares without knowing how marker stripping, volatile temp
files, `testparm`, and output parsing are coordinated.
