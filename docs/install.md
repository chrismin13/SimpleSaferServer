# Installation Guide

Use the automated installer on a clean Debian or Ubuntu based server.
Ubuntu Server 26.04 is the recommended server OS. The installer supports 64-bit
x86-64 (`amd64`) and ARM64 (`arm64`) userspaces.

```bash
curl -fsSL https://sss.chrismin13.com/install.sh | sudo bash
```

The installer checks that the host has the Debian-style tools SimpleSaferServer needs before it
installs packages:

- `apt-get`
- `dpkg`
- `systemctl`
- a running systemd host environment

It reads `/etc/os-release` or `/usr/lib/os-release` for OS-family diagnostics. Direct Debian and
Ubuntu systems continue normally. Debian/Ubuntu derivatives such as Linux Mint, Raspberry Pi OS, or
similar systems continue with a warning when `ID_LIKE` includes `debian` or `ubuntu`.

If a compatible host is not recognized by the OS-family check, run:

```bash
curl -fsSL https://sss.chrismin13.com/install.sh | sudo bash -s -- --unsupported-os-ok
```

That override only bypasses the OS-family block. Missing APT/systemd tools, package install
failures, and service setup failures still stop the install.

The installer supports `amd64` and `arm64` 64-bit userspaces. ARMv7, `armhf`, and other 32-bit ARM installs are not supported.

Before it starts the heavy work, the installer prints a short summary with the expected OS,
supported CPU types, package list, rough install time, and rough disk use. On a normal server and
network, plan for about 10-20 minutes and about 1-2 GB of extra disk use.

The main APT packages are:

- `git`
- `ca-certificates`
- `smartmontools`
- `samba`
- `openssh-server`
- `msmtp`
- `curl`
- `unzip`
- `rsync`
- `fdisk`
- `ntfs-3g`
- `unattended-upgrades`

The installer also tries to install `wsdd2` for Windows discovery when the package is available.

The installer installs only OS-level tools from APT. The Python application runtime is managed by
`uv` under `/opt/SimpleSaferServer/.venv` using the repository's `uv.lock`, so Debian or Ubuntu's
system Python version does not decide which Python dependencies run the app. If `uv` is already
installed and new enough to install Python 3.14, the installer uses it. If `uv` is missing or too
old, the installer installs the latest official standalone `uv` release into `/usr/local/bin`.

The installer installs and starts OpenSSH server so normal SSH access is available after install.
If the SSH service cannot start, the installer prints a warning and continues because the Web UI can
still be used locally.

The installer uses rclone's official installer. If root already has `/root/.config/rclone/rclone.conf`,
SimpleSaferServer backs it up to `/root/.config/rclone/rclone.conf.before-simplesaferserver` before
the app writes its managed cloud-backup config.

The installer prepares SimpleSaferServer-owned Samba include files in `/etc/samba` and starts
`smbd` as the required file-serving daemon. It also tries to enable `nmbd` for older Windows
NetBIOS discovery and installs `wsdd2` when the package is available for modern Windows Network
discovery. Discovery-service problems are reported in the installer summary but do not block Samba
file serving when `smbd` is active. If `smbd` enable or start commands fail but the service is
active afterward, the installer continues with a warning so you can fix reboot persistence or
service state before relying on the server. If `smbd` is not active, the installer stops and points
you to `systemctl status smbd` and `journalctl -u smbd --no-pager`.

After the installer finishes, it prints the Web UI URL and runs:

```bash
systemctl --no-pager status simple_safer_server_web.service
```

Use that status output if the Web UI does not open. Then open the printed Web UI URL and complete
the setup wizard.

For step-by-step installation without the automated installer, use the
[Manual Installation Guide](manual_install.md).
