# Clean Self-Update Policy

## Goal

- Treat `/opt/SimpleSaferServer` as the application folder, not durable user storage.
- Keep normal self-updates conservative by requiring a fully clean Git checkout.
- Add an explicit cleanup update path for administrators when old installer behavior or manual troubleshooting leaves app-folder changes behind.

## Decisions

- Normal **Update Now** blocks on tracked edits and untracked files.
- **Clean Up and Update** is available only when local app-folder changes block the normal branch update path.
- Cleanup runs `git reset --hard HEAD`, `git clean -fd`, `git fetch --prune --tags origin`, `git pull --ff-only`, and `bash install.sh`.
- Ignored files are not removed because the cleanup path intentionally avoids `git clean -x`.
- Installer app, static, template, and bundled model syncs prune removed app-owned files with `rsync --delete`.

## Documentation

- `docs/system_updates.md` describes the app folder policy and cleanup behavior.
- `docs/manual_install.md` mirrors the installer sync commands.
- `index.html` already links to System Updates and manual install docs.

## Uninstall

- No new files, services, timers, config files, or state directories were added.
- Existing uninstall behavior already removes installed app files and `harddrive_model`.
