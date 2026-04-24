# System Updates

The System Updates page manages Debian and Ubuntu package maintenance from the admin UI.

## Operating system support

- Shows the current Debian or Ubuntu release from `/etc/os-release`.
- Shows the standard support end date and the support date used for the status badge when SimpleSaferServer has a built-in date for that release.
- Returns the upstream release-date source URL in the support API response for diagnostics and future UI use.
- Debian support status includes Debian LTS dates, but excludes paid ELTS dates.
- Ubuntu LTS support status includes Ubuntu Pro ESM dates because Ubuntu Pro has a free personal tier. Paid Legacy support add-on dates are not used.
- The support badge turns amber with `EOL Soon` when the support end date is 183 days or less away.

## Apt operations

- **Update** runs `sudo apt-get update`.
- **Upgrade** runs `sudo env DEBIAN_FRONTEND=noninteractive apt-get -y upgrade`.
- **Stop** asks the SimpleSaferServer-started apt process group to terminate.
- The page keeps the apt log as the primary visible area and polls progress while an operation runs.
- Progress is estimated from apt output phases because apt does not provide one stable machine-readable progress stream for both update and upgrade.
- Operating system, support, automatic update, and Livepatch status stay visible above the log; only stale lock removal stays collapsed under Advanced.
- If SimpleSaferServer restarts during an apt operation, the next status read reconciles the saved running state with the current process and lock state. The page will report active external apt work as busy, or mark the saved operation interrupted once apt is idle.

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
- Setup writes the token to a temporary `0600` attach-config file, runs `sudo pro attach --attach-config <file>`, removes the file, and then runs `sudo pro enable livepatch`.
- The token is not passed as a command-line argument, because local process listings and process audit logs can expose argv while a command is running.

Ubuntu Livepatch status behavior follows Canonical's Livepatch client documentation:

https://ubuntu.com/security/livepatch/docs/livepatch/how-to/status

Ubuntu Pro attach-config behavior follows Canonical's Ubuntu Pro Client documentation:

https://documentation.ubuntu.com/pro-client/en/latest/howtoguides/how_to_attach_with_config_file/
