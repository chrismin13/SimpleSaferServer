# Samba Discovery and Config Ownership PRD

## Problem Statement

SimpleSaferServer currently assumes that installing the `samba` package leaves both `smbd` and
`nmbd` installed, enabled, and active. On Ubuntu 26.04, the `samba` package installs `/usr/sbin/nmbd`
and `nmbd.service`, but systemd skips `nmbd.service` because Samba's `ExecCondition` says NetBIOS is
not configured. The app then reports file sharing as partial or broken even though the daemon exists.

The current Samba ownership model is also too broad and too comment-dependent. SimpleSaferServer
writes managed share blocks directly into `/etc/samba/smb.conf` and treats marker comments as the
ownership boundary. That makes uninstall and future config changes harder than necessary, and it
forces the app to edit a system/admin-owned file for every share change.

Administrators need SimpleSaferServer to configure Samba discovery predictably, support modern
Windows network discovery through `wsdd2` where available, keep legacy NetBIOS discovery enabled
where Samba supports it, and avoid overwriting existing Samba configuration. The Web UI should track
the actual state of `smbd`, `nmbd`, and `wsdd2` without adding complicated diagnostics.

## Solution

Move SimpleSaferServer's Samba ownership boundary from comments in `smb.conf` to owned include files.
The main Samba config remains the system/admin-owned entrypoint. SimpleSaferServer only inserts
small marker-wrapped include blocks into `smb.conf`:

- a global include inside `[global]`, late before the first non-global section
- a shares include at the end of the file

SimpleSaferServer owns two files:

- `/etc/samba/simple_safer_server_globals.conf`
- `/etc/samba/simple_safer_server_shares.conf`

The globals file is generated from a repository template and may be refreshed during install/update
paths. It contains only defensible global policy that SimpleSaferServer depends on:

- `map to guest = never`
- `disable netbios = no`

The shares file is the source of truth for SimpleSaferServer-managed shares. Any share section in
that file is managed by SimpleSaferServer. Comments in the file are for human guidance only, not
ownership detection. Manual edits should not crash the app, but unsupported Samba directives may be
overwritten the next time that share is edited in the Web UI.

Add an idempotent Samba layout helper that can safely auto-heal the owned layout during explicit
install/update/setup/share-management paths. It should create missing owned files, refresh the
globals template, ensure include placement, validate the effective Samba config with `testparm`, and
roll back if validation or required service restart fails. It should not run on ordinary app startup
or status polling.

Install `wsdd2` as an optional discovery dependency where available. Do not support a custom `wsdd`
systemd wrapper for older distros. `smbd` is required; `nmbd` and `wsdd2` are desired discovery
services. The Web UI should track all three. Overall file-sharing status is operational only when
all three are active, partial when `smbd` is active but discovery is incomplete, and down when
`smbd` is not active.

Uninstall removes only SimpleSaferServer-owned Samba include blocks and owned files. It leaves
shared packages and unrelated service state alone.

## User Stories

1. As an administrator, I want SimpleSaferServer to install Samba file sharing predictably, so that the backup share works after setup.
2. As an administrator, I want `smbd` to be required and checked, so that the app does not claim file sharing works when the file-serving daemon is down.
3. As an administrator, I want `nmbd` enabled when Samba supports it, so that older Windows network browsing paths can find the server.
4. As an administrator, I want `wsdd2` installed when available, so that modern Windows Network discovery can find the server.
5. As an administrator, I want installation to continue when `wsdd2` is unavailable, so that older Debian installs can still serve SMB shares.
6. As an administrator, I want installation to continue when `nmbd` is inactive, so that legacy discovery issues do not block core file sharing.
7. As an administrator, I want installation to fail if `smbd` cannot start, so that a non-working file server is not treated as installed.
8. As an administrator, I want a concise installer service summary, so that I can see whether `smbd`, `nmbd`, and `wsdd2` are active.
9. As an administrator, I want the Network File Sharing page to show `smbd`, `nmbd`, and `wsdd2`, so that discovery and file-serving state are visible in one place.
10. As an administrator, I want the Dashboard file-sharing summary to include `wsdd2`, so that the dashboard matches the dedicated file-sharing page.
11. As an administrator, I want `Windows Discovery (wsdd2)` labeled by purpose, so that I know it is for modern Windows Network discovery.
12. As an administrator, I want `NetBIOS Discovery (nmbd)` labeled by purpose, so that I know it is for older Windows browsing paths.
13. As an administrator, I want hover help for `wsdd2`, so that the UI explains the difference between modern and legacy discovery without adding a large panel.
14. As an administrator, I want the Restart Services button to restart all three services, so that file sharing and discovery refresh together.
15. As an administrator, I want `smbd` restart failure to fail the operation, so that the UI reports core file-sharing failure.
16. As an administrator, I want `nmbd` or `wsdd2` restart failure to show as partial status, so that discovery problems do not roll back valid share edits.
17. As an administrator, I want SimpleSaferServer to avoid overwriting existing Samba shares, so that installing the app does not break manually configured shares.
18. As an administrator, I want setup completion to reject an existing unmanaged `backup` share, so that SimpleSaferServer does not silently override it.
19. As an administrator, I want the existing `backup` share conflict message to be short, so that it fits in the setup notification.
20. As an administrator, I want to fix a `backup` share conflict manually and retry Complete Setup, so that setup values are not lost.
21. As an administrator, I want SimpleSaferServer-managed shares in a dedicated file, so that it is obvious which shares the app owns.
22. As an administrator, I want the SSS shares file to be plain Samba config, so that I can inspect or manually edit it if needed.
23. As an administrator, I want manual unsupported directives not to crash the Web UI, so that a hand-edited shares file remains recoverable.
24. As an administrator, I accept that unsupported manual directives may be overwritten by Web UI edits, so that the app does not become a full Samba editor.
25. As an administrator, I want comments in SSS-owned files to explain the behavior, so that future maintenance is easier.
26. As an administrator, I want comments not to determine ownership, so that accidental comment edits do not confuse the app.
27. As an administrator, I want uninstall to remove SSS-owned Samba files, so that app-owned config is cleaned up.
28. As an administrator, I want uninstall to remove only SSS include lines from `smb.conf`, so that unrelated Samba config survives.
29. As an administrator, I want uninstall to leave Samba and `wsdd2` packages installed, so that shared system packages are not unexpectedly removed.
30. As an administrator, I want uninstall not to blindly disable `wsdd2`, so that a service I had enabled outside SSS is not turned off.
31. As a future maintainer, I want one shared Samba layout helper, so that installer, setup, update, and share edits do not duplicate config-repair logic.
32. As a future maintainer, I want the layout helper to be idempotent, so that running it during updates can auto-heal missing SSS wiring safely.
33. As a future maintainer, I want auto-heal limited to explicit install paths, so that restarting the web app does not unexpectedly rewrite system config.
34. As a future maintainer, I want full-config validation with `testparm`, so that SSS never publishes a broken Samba config knowingly.
35. As a future maintainer, I want rollback behavior around Samba config writes, so that failed validation or required service restart does not leave partial edits.
36. As a future maintainer, I want conflict checks to account for effective Samba config, so that user include files are respected.
37. As a future maintainer, I want the normal app code to drop the legacy inline managed-share model, so that dead compatibility code does not burden maintenance.
38. As a future maintainer, I want docs to describe file-based ownership, so that the Web UI and uninstall behavior match operator expectations.
39. As a future maintainer, I want `index.html` documentation/uninstall copy checked, so that public docs match the new behavior.
40. As a future maintainer, I want no `README.md` edits in this work, so that repository instructions are respected.

## Implementation Decisions

- Use file path ownership as the Samba management boundary.
- SimpleSaferServer owns `/etc/samba/simple_safer_server_globals.conf`.
- SimpleSaferServer owns `/etc/samba/simple_safer_server_shares.conf`.
- Comments in Samba files are explanatory only and must not be used to determine share ownership.
- Remove the old inline managed-share ownership model from normal application behavior.
- Do not keep legacy compatibility for marker-wrapped shares in the main Samba config.
- Main `smb.conf` should only be modified through small marker-wrapped include blocks.
- The global include must be inserted inside `[global]`, as late as possible before the first non-global section.
- The shares include must be inserted at the end of `smb.conf`.
- The global include file should not contain a `[global]` header because it is included from inside the existing `[global]` section.
- The shares include file should contain normal Samba share sections.
- New installs and update paths should refresh the globals file from a repository template.
- New installs and update paths should create the shares file with a header if it is missing.
- The shares file should not be wholesale regenerated during install/update when it already exists.
- The shares file header should state that the file is managed by SimpleSaferServer, normal edits should use the Web UI, and unsupported manual directives may be overwritten by Web UI edits.
- The globals file header should state that the installer/setup/update paths may refresh it and that site-specific overrides belong in `smb.conf` after the SSS global include if the admin intentionally wants to override SSS defaults.
- The initial globals template should include `map to guest = never`.
- The initial globals template should include `disable netbios = no`.
- Do not include `server role = standalone server` in the SSS globals template for this work.
- Write SSS Samba config files as root-owned `0644` files.
- Do not store secrets in the SSS Samba config files.
- Use a shared Samba layout helper rather than duplicating parsing and insertion logic in Bash, setup routes, and the share manager.
- The shared helper should be idempotent and safe to run repeatedly.
- The shared helper should create or repair only SSS-owned files and SSS include blocks.
- The shared helper should fail closed when it finds malformed SSS include marker blocks.
- The shared helper should not rewrite unrelated `smb.conf` content.
- The shared helper should validate the effective Samba config with `testparm`.
- The shared helper should roll back changes when validation fails.
- The shared helper should roll back share/config writes when `smbd` cannot restart after a publish.
- Run the shared helper only during explicit install/update/setup/share-management paths.
- Do not run auto-heal on app startup.
- Do not run auto-heal on status polling.
- Installer/update paths should prepare the Samba layout and services but should not create the default `backup` share.
- Setup completion should create or update the default `backup` share after the backup mount point is known.
- Setup completion should keep using persisted setup values so a failed `backup` share conflict can be fixed and retried.
- The short setup notification for an unmanaged `backup` conflict should be: `Samba share "backup" already exists. Rename or remove it, then retry.`
- Before creating a new managed share, reject the operation if that share name already exists outside the SSS shares file.
- Before renaming a managed share, reject the operation if the new name exists outside the SSS shares file.
- Use Samba's effective config where practical for conflict detection so non-SSS include files are respected.
- Avoid treating SSS-owned shares as conflicts when editing existing SSS shares.
- If effective-config conflict detection cannot prove safety, prefer rejecting the operation over relying on include precedence.
- The app should parse the SSS shares file directly for list/create/update/delete operations.
- The app should read only supported fields for Web UI display.
- Manual unsupported directives in the SSS shares file should not crash the UI.
- Editing a share through the Web UI may rewrite that share in the supported SSS format and drop unsupported directives.
- If the SSS shares file is structurally malformed enough that share sections cannot be parsed safely, return a clear API error instead of crashing.
- Install `wsdd2` as an optional dependency in a separate install attempt, not in the fatal core dependency command.
- Do not install or manage `wsdd`.
- Do not create a custom SimpleSaferServer systemd wrapper for `wsdd`.
- If `wsdd2` is unavailable, warn and continue.
- If `wsdd2` is installed, enable/start it best-effort and report its actual status.
- Do not remove the `wsdd2` package on uninstall.
- Do not blindly disable `wsdd2.service` on uninstall.
- Enable/start `smbd` and fail install/setup/share publish when core file serving cannot run.
- Enable/start `nmbd` and warn/partial if it is inactive or skipped.
- Track `smbd`, `nmbd`, and `wsdd2` with a flat API response.
- Use `unavailable` for `wsdd2` when the unit or service is missing.
- Keep the restart API simple: fail when `smbd` fails; allow status polling to reveal partial discovery state.
- The Network File Sharing page should show all three services.
- The Dashboard file-sharing summary should include all three services.
- Overall status should be `Operational` only when all three services are active.
- Overall status should be `Partial` when `smbd` is active and either discovery service is not active or unavailable.
- Overall status should be `Down` when `smbd` is not active.
- The Restart Services button should restart all three services.
- Service labels should be purpose-first with unit names in parentheses.
- `SMB Daemon (smbd)` tooltip should say it serves file shares.
- `NetBIOS Discovery (nmbd)` tooltip should say it helps older Windows network browsing find the server.
- `Windows Discovery (wsdd2)` tooltip should say it helps modern Windows network browsing find the server.
- Installer output may print a concise service summary after service setup.
- Uninstall should remove SSS include marker blocks from `smb.conf`.
- Uninstall should delete the SSS globals and shares files.
- Uninstall should leave unmanaged Samba shares and unrelated Samba config alone.
- Uninstall should leave shared packages installed.
- Uninstall should leave non-SSS service state alone.
- Update `docs/network_file_sharing.md` to describe file-based ownership, discovery services, conflict handling, and uninstall behavior.
- Update install/manual install docs to mention optional `wsdd2` discovery support and SSS-owned Samba include files.
- Update uninstall docs and public `index.html` uninstall copy to mention SSS-owned Samba include files.
- Do not edit `README.md`.

Major modules to build or modify:

- Samba layout helper: own include placement, owned file creation, globals refresh, full-config validation, rollback, and idempotent auto-heal.
- SMB manager: move share list/create/update/delete to the SSS shares file, use layout helper before write operations, and detect conflicts with unmanaged/effective shares.
- SMB command adapter: add commands for `testparm`, service status, optional service availability, service restart/start/enable, and effective config inspection as needed.
- Installer/update path: call the shared layout helper, optional-install `wsdd2`, enable/start services, and print concise service status.
- Setup completion: ensure layout, create/update the default backup share from the configured mount point, fail only on `smbd` failure, and surface short conflict messages.
- Network File Sharing API and template: return/show `wsdd2`, restart all three services, and update overall state logic.
- Dashboard summary UI: include `wsdd2` in file-sharing health logic and details.
- Uninstaller: remove SSS include blocks/files and update final messaging without removing packages or unrelated service state.
- Documentation: update network file sharing, install, manual install, uninstall, and public documentation index copy.

## Testing Decisions

Good tests should verify external behavior and safety boundaries rather than private implementation
details. The most important assertions are that SimpleSaferServer touches only the owned Samba
surface, validates before publishing, does not overwrite existing user shares, fails when `smbd`
cannot serve files, and degrades cleanly when discovery services are missing.

Modules and behaviors to test:

- Samba layout helper:
  - Creates the globals file from the template with expected permissions.
  - Creates the shares file with the expected header when missing.
  - Inserts the global include inside `[global]` before the first non-global section.
  - Inserts the shares include at the end of `smb.conf`.
  - Does not duplicate include blocks when run repeatedly.
  - Leaves unrelated `smb.conf` content unchanged.
  - Fails closed when SSS include markers are malformed.
  - Runs full-config validation with `testparm`.
  - Rolls back when validation fails.
- Share manager:
  - Lists shares from the SSS shares file.
  - Creates shares in the SSS shares file.
  - Updates shares in the SSS shares file.
  - Deletes shares from the SSS shares file.
  - Does not rely on share marker comments for ownership.
  - Rejects creating `backup` when a non-SSS `backup` share exists in effective Samba config.
  - Rejects renaming a managed share to a name used outside the SSS shares file.
  - Does not crash when unsupported directives are present in the SSS shares file.
  - Returns a clear error when the SSS shares file is structurally malformed.
  - Rolls back a published share change when `smbd` cannot restart.
- Setup completion:
  - Creates the default `backup` share only after setup has a mount point.
  - Returns a short retryable error when an unmanaged `backup` share exists.
  - Does not lose persisted setup values after a `backup` share conflict.
  - Fails when `smbd` cannot start/restart.
  - Does not fail solely because `nmbd` or `wsdd2` is unavailable.
- Installer/update:
  - Optional `wsdd2` install failure does not fail the installer.
  - Core `smbd` failure does fail the relevant install/setup path.
  - Service summary prints all three service states.
  - The layout helper is invoked instead of duplicating Samba config edits in Bash where practical.
- Service status API:
  - Returns a flat object containing `smbd`, `nmbd`, and `wsdd2`.
  - Returns `unavailable` for missing `wsdd2`.
  - Preserves existing behavior for `smbd` and `nmbd` active/inactive states.
- Restart API:
  - Attempts to restart all three services.
  - Fails when `smbd` restart fails.
  - Allows non-fatal discovery restart failures to be reflected through status polling.
- Network File Sharing UI:
  - Shows badges for all three services.
  - Shows `Operational` only when all three are active.
  - Shows `Partial` when `smbd` is active and one discovery service is inactive/unavailable.
  - Shows `Down` when `smbd` is inactive.
  - Includes concise tooltips for `smbd`, `nmbd`, and `wsdd2`.
- Dashboard UI:
  - Includes `wsdd2` in file-sharing summary details.
  - Uses the same overall state rules as the Network File Sharing page.
- Uninstall:
  - Removes only SSS include blocks from `smb.conf`.
  - Deletes the SSS globals and shares files.
  - Leaves unrelated include lines alone.
  - Leaves unmanaged Samba share blocks alone.
  - Leaves shared packages installed.
  - Does not blindly disable `wsdd2.service`.
  - Updates final uninstall messaging.
- Documentation:
  - Network File Sharing docs describe SSS-owned Samba files and discovery services.
  - Install docs mention optional `wsdd2`.
  - Manual install docs mention the layout/helper behavior.
  - Uninstall docs mention owned Samba include files.
  - Public `index.html` copy matches the new uninstall behavior.
  - `README.md` is not modified.

Prior art:

- Existing `SMBManager` tests cover share parsing, create/update/delete safety, rollback, and
  unmanaged-share rejection.
- Existing uninstaller tests cover marker-based Samba cleanup and should be replaced with include
  file cleanup tests.
- Existing setup wizard tests cover default backup share creation and unmanaged `backup` guidance.
- Existing Dashboard and Network File Sharing JavaScript already consume flat `smbd`/`nmbd` status
  values and can be extended to `wsdd2`.
- Existing development docs require system behavior behind services/adapters, validation/rollback
  for system-owned files, related documentation updates, and uninstall checks.

## Out of Scope

- Supporting a custom `wsdd` systemd wrapper.
- Installing or managing `wsdd`.
- Installing both `wsdd` and `wsdd2`.
- Removing Samba or `wsdd2` packages during uninstall.
- Blindly disabling `wsdd2.service` during uninstall.
- Persisting a separate manifest of whether SSS installed or enabled `wsdd2`.
- Keeping legacy inline managed-share compatibility in normal app code.
- Automatically migrating existing inline managed-share blocks from `smb.conf`.
- Building a general Samba configuration editor.
- Exposing every possible Samba share directive in the Web UI.
- Preserving unsupported manual directives during Web UI share edits.
- Adding a new visible setup step for Samba.
- Failing setup/install solely because `nmbd` or `wsdd2` is inactive/unavailable.
- Adding deep `nmbd` `ExecCondition` diagnostics to the UI.
- Hiding `wsdd2` from the UI on systems where it is unavailable.
- Running Samba layout auto-heal on ordinary app startup.
- Running Samba layout auto-heal on status polling.
- Changing the backup share name from `backup`.
- Editing `README.md`.

## Further Notes

- The observed Ubuntu 26.04 install did install `/usr/sbin/nmbd`, `/usr/sbin/smbd`, `pdbedit`, and
  `testparm`. `nmbd.service` existed but systemd skipped it due to Samba's `ExecCondition`.
- On the same Ubuntu 26.04 host, `wsdd` was installed as a binary but did not provide a
  `wsdd.service`. `wsdd2` was available from Ubuntu repositories but was not installed.
- Modern Windows Network discovery is better served by WSD discovery (`wsdd2`) than by only relying
  on NetBIOS (`nmbd`). `nmbd` remains useful for legacy browsing paths.
- The public UI should keep the explanation lightweight: labels and tooltips are enough for the
  first pass.
- The implementation should prefer small, testable deep modules around Samba layout and service
  orchestration instead of spreading Samba config edits through routes, installer Bash, and UI code.
