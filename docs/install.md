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

After the installer finishes, open the printed Web UI URL and complete the setup wizard.

For step-by-step installation without the automated installer, use the
[Manual Installation Guide](manual_install.md).
