# System Updates

The System Updates page manages Debian and Ubuntu package maintenance from the admin UI.

## Operating system support

- Shows the current Debian or Ubuntu release from `/etc/os-release`.
- Shows the standard support end date and the support date used for the status badge when SimpleSaferServer has a built-in date for that release.
- Returns the upstream release-date source URL in the support API response for diagnostics and future UI use.
- Debian support status uses the normal Debian release-table end-of-life date, not Debian LTS or ELTS columns.
- Ubuntu LTS support status includes Ubuntu Pro ESM dates because Ubuntu Pro has a free personal tier. Paid Legacy support add-on dates are not used.

## Apt operations

- **Update** runs `sudo apt-get update`.
- **Upgrade** runs `sudo env DEBIAN_FRONTEND=noninteractive apt-get -y upgrade`.
- **Stop** asks the SimpleSaferServer-started apt process group to terminate.
- The page keeps the apt log as the primary visible area and polls progress while an operation runs.
- Progress is estimated from apt output phases because apt does not provide one stable machine-readable progress stream for both update and upgrade.
- Operating system, support, automatic update, and Livepatch status stay visible above the log; only stale lock removal stays collapsed under Advanced.

## Shutdown and reboot lockout

Dashboard restart and shutdown actions are blocked while apt or dpkg is active.

The block checks:

- the apt operation started by SimpleSaferServer
- active apt, apt-get, dpkg, aptitude, or unattended-upgrades processes
- apt/dpkg lock files that are currently held by a process when `fuser` is available

## Automatic apt settings

Automatic update settings are stored in the `apt_updates` section of `config.conf`.

On real systems the page writes `/etc/apt/apt.conf.d/20auto-upgrades`:

- `APT::Periodic::Update-Package-Lists`
- `APT::Periodic::Unattended-Upgrade`
- `APT::Periodic::AutocleanInterval`

`unattended-upgrades` must be installed for unattended upgrades to actually run.

## Advanced stale lock removal

The advanced action removes stale apt lock files only when SimpleSaferServer cannot see an active apt or dpkg process. It is intended for recovery after a failed package operation, not for interrupting a running update.

## Ubuntu Livepatch

Livepatch status is shown only on Ubuntu.

- If `canonical-livepatch` is installed, the page runs `canonical-livepatch status --format json`.
- If it is not installed, setup uses `sudo snap install canonical-livepatch` and then `sudo canonical-livepatch enable <token>`.
- Livepatch setup requires a Canonical Livepatch token.

Ubuntu Livepatch status behavior follows Canonical's Livepatch client documentation:

https://ubuntu.com/security/livepatch/docs/livepatch/how-to/status
