# Installation Guide

Use the automated installer on a clean Debian or Ubuntu based server:

```bash
curl -fsSL https://sss.chrismin13.com/install.sh | sudo bash
```

The installer checks that the host has the tools SimpleSaferServer needs before it downloads the
app archive and configures services:

- `curl`
- `systemctl`
- `sudo`
- a running systemd host environment

It reads `/etc/os-release` or `/usr/lib/os-release` for OS-family diagnostics. Direct Debian and
Ubuntu systems continue normally. Debian/Ubuntu derivatives such as Linux Mint, Raspberry Pi OS, or
similar systems continue with a warning when `ID_LIKE` includes `debian` or `ubuntu`.

If a compatible host is not recognized by the OS-family check, run:

```bash
curl -fsSL https://sss.chrismin13.com/install.sh | sudo bash -s -- --unsupported-os-ok
```

That override only bypasses the OS-family block. Missing curl/systemd/sudo tools, failed downloads, and
service setup failures still stop the install.

The installer supports `amd64` and `arm64` 64-bit userspaces. ARMv7, `armhf`, and other 32-bit ARM installs are not supported.

File Sharing, Cloud Backup, Drive Health, managed-drive setup, and System Updates declare their
extra host tools as module requirements. The base installer does not install APT packages such as
`ca-certificates`, `curl`, `git`, Samba, `wsdd2`, `rclone`, `smartmontools`, HDSentinel,
`ntfs-3g`, `fdisk`, or `unattended-upgrades`.

The Python application runtime is managed by
`uv` under `/opt/SimpleSaferServer/.venv` using the repository's `uv.lock`, so Debian or Ubuntu's
system Python version does not decide which Python dependencies run the app. If `uv` is already
installed and new enough to install Python 3.14, the installer uses it. If `uv` is missing or too
old, the installer installs the latest official standalone `uv` release into `/usr/local/bin`.

The installer does not prepare Samba files, edit Samba config, or start Samba services. File
Sharing must become an explicit setup flow that shows the Samba plan before any host config is
written.

The installer does not open firewall ports. If the server firewall blocks port `5000`, open that
port with the firewall tool you already use for the host.

Feature jobs live in Python modules and run through the worker/helper path. The installer does not
copy the repository `scripts/` folder into production. Only the `sss` terminal command and the
`sss-helper` allowlisted helper command are installed into `/usr/local/bin`. It also registers two
SimpleSaferServer systemd services:

- `simple-safer-server-web.service` for the Web UI
- `simple-safer-server-worker.service` for the worker process that runs scheduled jobs

The installer creates a dedicated `sss` system user and group. The Web UI and worker run as that
user, not as root. When either service needs to perform a root-only action, it calls `sss-helper`
through a narrow sudoers rule that allows only `/usr/local/bin/sss-helper`.

SimpleSaferServer supports the current clean-install layout only. The installer is not a migration
tool for older layouts. Install it on a clean host and let the setup wizard enable only the modules
you want.

After the installer finishes, open the printed Web UI URL and complete the setup wizard.

For step-by-step installation without the automated installer, use the
[Manual Installation Guide](manual_install.md).
