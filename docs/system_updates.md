# System Updates

The System Updates page shows Debian and Ubuntu package-maintenance state from the admin UI. It does
not change operating system update policy, run apt commands, remove apt locks, or set up Ubuntu
Livepatch.

The page shows its purpose and read-only setup note from the System Updates module contract in
`simple_safer_server/modules/system_updates/module.py`. Keep update-policy guidance there so the
Web UI, setup flow, CLI, and docs can reuse the same wording.

## Application version and updates

The base installer downloads a source archive, not a Git checkout. Normal installs therefore show
application update status as unavailable until SSS has a release archive or package updater.

`/opt/SimpleSaferServer` is the application folder. It is not user storage. SimpleSaferServer stores
durable operator state outside that folder:

- configuration in `/etc/SimpleSaferServer`
- logs in `/var/log/SimpleSaferServer`
- volatile runtime state in `/run/SimpleSaferServer`
- durable app data, including HDSentinel state, in `/var/lib/SimpleSaferServer`

The app update action is disabled while the replacement updater is being designed. It returns a
clear "not available" response instead of running git or changing files.

## Operating system support

- Shows the current Debian or Ubuntu release from `/etc/os-release`.
- Shows the standard support end date and the support date used for the status badge when SimpleSaferServer has a built-in date for that release.
- Returns the upstream release-date source URL in the support API response for diagnostics and future UI use.
- The support-date metadata lives in `simple_safer_server.services.os_support` so installer-adjacent tests and the System Updates page use the same Python source of truth.
- Debian support status includes Debian LTS dates, but excludes paid ELTS dates.
- Ubuntu LTS support status includes Ubuntu Pro ESM dates because Ubuntu Pro has a free personal tier. Paid Legacy support add-on dates are not used.
- The support badge turns amber with `EOL Soon` when the support end date is 183 days or less away.

## Apt status

- The page shows whether apt or dpkg appears busy.
- The page shows recent apt state and logs when that information is available.
- SSS does not run `apt-get update` or `apt-get upgrade`.
- SSS does not stop apt or dpkg.
- SSS does not remove apt lock files.

Manage operating system packages directly on the server with the normal OS tools. This keeps SSS out
of the job of owning package-manager state.

## Shutdown and reboot lockout

Dashboard restart and shutdown actions are blocked while apt or dpkg is active.

The block checks:

- the apt operation started by SimpleSaferServer
- active apt, apt-get, dpkg, aptitude, or unattended-upgrades processes
- apt/dpkg lock files that are currently held by a process when `fuser` is available

## Automatic apt settings

The page shows the current system apt periodic settings from
`/etc/apt/apt.conf.d/20auto-upgrades` when that file exists. These settings are read-only in
SimpleSaferServer. Manage OS update policy outside SSS, or add a future explicit System Updates
setup flow with a clear ownership plan.

SimpleSaferServer does not write `APT::Periodic::Update-Package-Lists`,
`APT::Periodic::Unattended-Upgrade`, or `APT::Periodic::AutocleanInterval`.

Uninstalling SimpleSaferServer does not remove or revert `/etc/apt/apt.conf.d/20auto-upgrades`.
These are normal operating system update settings, and an administrator may want them to keep
applying after the app is removed.

## Ubuntu Livepatch

Livepatch status is shown only on Ubuntu. Non-Ubuntu hosts keep the Livepatch summary hidden because
Canonical Livepatch is not actionable there.

- If `canonical-livepatch` is installed, the page runs `canonical-livepatch status --format json`.
- SSS does not attach Ubuntu Pro.
- SSS does not enable or disable Livepatch.
- SSS does not store Ubuntu Pro tokens.
- Uninstall does not detach Ubuntu Pro or disable Livepatch. Those are host-level subscription and
  security states, so the uninstaller leaves them for the admin to review.

Ubuntu Livepatch status behavior follows Canonical's Livepatch client documentation:

https://ubuntu.com/security/livepatch/docs/livepatch/how-to/status
