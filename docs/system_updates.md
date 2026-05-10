# System Updates

The System Updates page manages Debian and Ubuntu package maintenance from the admin UI.

## Application version and updates

The page shows the installed SimpleSaferServer source state:

- branch, tag, detached checkout, or unavailable Git state
- current commit
- cached remote check time
- whether the checkout is up to date, behind, ahead, diverged, dirty, pinned, or unavailable

Remote Git status is checked only when an administrator clicks **Refresh**. This avoids doing a
network fetch every time the page loads. The page uses the cached remote result until Refresh runs
again or the installed commit changes.

`/opt/SimpleSaferServer` is the application folder. It is not user storage, and application update
cleanup may return it to the selected Git branch state. SimpleSaferServer stores durable operator
state outside that folder:

- configuration in `/etc/SimpleSaferServer`
- logs in `/var/log/SimpleSaferServer`
- volatile runtime state in `/run/SimpleSaferServer`
- durable app data, including drive-health telemetry and HDSentinel state, in `/var/lib/SimpleSaferServer`

**Update Now** is enabled only when the installed checkout is:

- on a branch
- clean of tracked local file edits and untracked files
- configured with an upstream
- behind that upstream

Tag and detached checkouts are shown as pinned. They are useful as install snapshots, but the
automatic updater does not move them to another commit.

When changed or extra files in `/opt/SimpleSaferServer` block the normal update path, the page shows
**Clean Up and Update**. That action resets tracked app files to the selected branch, removes
untracked files from the app folder, fetches the remote, fast-forwards the branch, and reruns the
installer. It does not remove settings, users, logs, backups, or system configuration stored outside
`/opt/SimpleSaferServer`. Ignored files are not removed by this cleanup path. The confirmation dialog
shows the changed and extra app-folder paths reported by Git so administrators can review what will
be reset or removed before continuing.

Application updates run through the `App Update` scheduled task. The task runs `git pull --ff-only`
from the installed checkout and then reruns the full installer from that checkout. Full installer
updates keep Python dependencies, systemd units, helper scripts, templates, and static assets in
sync with the pulled code. Fast-forward-only pulls prevent the updater from creating merge commits
or resolving branch divergence without an administrator.

When an administrator starts **Update Now** or **Clean Up and Update** from the System Updates page,
the browser opens `/task/App Update` so the administrator can watch the task journal. The journal
includes the Git and `install.sh` output from the update run. The web service may briefly restart
while the installer refreshes service files; the task page keeps retrying log refreshes so it can
resume after the session reconnects.

The scheduled task runs as root. During install, SimpleSaferServer registers
`/opt/SimpleSaferServer` as a Git `safe.directory` in the system Git config so root-run services can
inspect a checkout owned by the installing administrator. The installer preserves file modes inside
the app checkout and only forces executable bits on the `/usr/local/bin` helper-script copies, so
routine installs do not create script-mode changes in Git status.

The daily `App Update` timer is generated with the other SimpleSaferServer timers and runs 15
minutes before `Check Mount`. It is also visible on the Dashboard scheduled-task table, where admins
can inspect logs or start the task manually.

## Operating system support

- Shows the current Debian or Ubuntu release from `/etc/os-release`.
- Shows the standard support end date and the support date used for the status badge when SimpleSaferServer has a built-in date for that release.
- Returns the upstream release-date source URL in the support API response for diagnostics and future UI use.
- The support-date metadata lives in `simple_safer_server.services.os_support` so installer-adjacent tests and the System Updates page use the same Python source of truth.
- Debian support status includes Debian LTS dates, but excludes paid ELTS dates.
- Ubuntu LTS support status includes Ubuntu Pro ESM dates because Ubuntu Pro has a free personal tier. Paid Legacy support add-on dates are not used.
- The support badge turns amber with `EOL Soon` when the support end date is 183 days or less away.

## Apt operations

- **Update** runs `apt-get update`.
- **Upgrade** runs `env DEBIAN_FRONTEND=noninteractive apt-get -y upgrade`.
- **Stop** asks the SimpleSaferServer-started apt process group to terminate.
- The page keeps the apt log as the primary visible area and polls progress while an operation runs.
- Progress is estimated from apt output phases because apt does not provide one stable machine-readable progress stream for both update and upgrade.
- Operating system, support, automatic update, and Livepatch status stay visible above the log; only stale lock removal stays collapsed under Advanced.
- If SimpleSaferServer restarts during an apt operation, the next status read reconciles the saved running state with the current process and lock state. The page will report active external apt work as busy, or mark the saved operation interrupted once apt is idle.
- Operation status and the live apt log are volatile runtime state. They are useful while managing
  updates but do not need to survive reboot.

## Shutdown and reboot lockout

Dashboard restart and shutdown actions are blocked while apt or dpkg is active.

The block checks:

- the apt operation started by SimpleSaferServer
- active apt, apt-get, dpkg, aptitude, or unattended-upgrades processes
- apt/dpkg lock files that are currently held by a process when `fuser` is available

## Automatic apt settings

Before the first save, the page shows the current system apt periodic settings. This keeps an existing server's automatic update policy visible without treating generated SimpleSaferServer defaults as an administrator choice.

After an administrator saves the form, SimpleSaferServer stores `managed = true` in the `apt_updates` section of `config.conf`. From then on, the saved app settings are the source of truth for the apt periodic values shown on this page.

On real systems, saving the form writes `/etc/apt/apt.conf.d/20auto-upgrades` with a SimpleSaferServer header and these values:

- `APT::Periodic::Update-Package-Lists`
- `APT::Periodic::Unattended-Upgrade`
- `APT::Periodic::AutocleanInterval`

`AutocleanInterval` is stored as a number of days. The checkbox stays simple in the UI: unchecked writes `0`, and checked writes a positive interval. When SimpleSaferServer first adopts an existing positive system interval, it preserves that number. If autoclean is enabled and there is no existing positive interval, the app uses 7 days.

Other apt configuration files under `/etc/apt/apt.conf.d/` may still define additional apt behavior that this page does not edit.

`unattended-upgrades` must be installed for unattended upgrades to actually run.

Uninstalling SimpleSaferServer does not remove or revert `/etc/apt/apt.conf.d/20auto-upgrades`. These are normal operating system update settings, and an administrator may want them to keep applying after the app is removed.

## Advanced stale lock removal

The advanced action removes stale apt lock files only when SimpleSaferServer cannot see an active apt or dpkg process. It is intended for recovery after a failed package operation, not for interrupting a running update.

## Ubuntu Livepatch

Livepatch status is shown only on Ubuntu.

- If `canonical-livepatch` is installed, the page runs `canonical-livepatch status --format json`.
- Setup requires the Ubuntu Pro Client (`pro`) and a Canonical Ubuntu Pro token.
- Setup writes the token to a temporary `0600` attach-config file, runs `pro attach --attach-config <file>`, removes the file, and then runs `pro enable livepatch`.
- The token is not passed as a command-line argument, because local process listings and process audit logs can expose argv while a command is running.
- After a successful real setup, SimpleSaferServer records `livepatch_managed = true` under `system_updates` in its config.
- Uninstall does not detach Ubuntu Pro or disable Livepatch. Those are host-level subscription and security states, so the uninstaller leaves them for the admin to review.
- The uninstall summary warns about retained Ubuntu Pro and Livepatch state only when SimpleSaferServer has recorded that it managed Livepatch setup.

Ubuntu Livepatch status behavior follows Canonical's Livepatch client documentation:

https://ubuntu.com/security/livepatch/docs/livepatch/how-to/status

Ubuntu Pro attach-config behavior follows Canonical's Ubuntu Pro Client documentation:

https://documentation.ubuntu.com/pro-client/en/latest/howtoguides/how_to_attach_with_config_file/
