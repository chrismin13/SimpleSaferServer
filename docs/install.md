# Installation Guide

Use the automated installer on a clean Debian or Ubuntu based server:

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

The installer installs only OS-level tools from APT. The Python application runtime is managed by
`uv` under `/opt/SimpleSaferServer/.venv` using the repository's `uv.lock`, so Debian or Ubuntu's
system Python version does not decide which Python dependencies run the app. If `uv` is not already
installed, or if a different uv version is found, the installer installs the pinned uv version used by the project.

The installer prepares SimpleSaferServer-owned Samba include files in `/etc/samba` and starts
`smbd` as the required file-serving daemon. It also tries to enable `nmbd` for older Windows
NetBIOS discovery and installs `wsdd2` when the package is available for modern Windows Network
discovery. Discovery-service problems are reported in the installer summary but do not block Samba
file serving when `smbd` is active. If `smbd` enable or start commands fail but the service is
active afterward, the installer continues with a warning so you can fix reboot persistence or
service state before relying on the server. If `smbd` is not active, the installer stops and points
you to `systemctl status smbd` and `journalctl -u smbd --no-pager`.

After the installer finishes, open the printed Web UI URL and complete the setup wizard.

For step-by-step installation without the automated installer, use the
[Manual Installation Guide](manual_install.md).
