# SimpleSaferServer

> [!TIP]
> **🚀 Want to see it in action?**  
> Check out the [Live Management Demo](https://sssdemo.chrismin13.com) to explore the dashboard and features in a simulated environment!

## 🚀 Quick Installation

To install SimpleSaferServer on a clean Debian-based system, run the following command:

```bash
curl -fsSL https://sss.chrismin13.com/install.sh | sudo bash
```

- This script will install all dependencies, set up the service, and print your Web UI address.
- The management Web UI is admin-only. The first account created during setup becomes the initial administrator.
- For more details and the maintained documentation index, visit the [documentation section on the website](https://sss.chrismin13.com/#documentation).
- For manual installation, see the [Manual Installation Guide](docs/manual_install.md).

## Local Fake Mode

To run the app locally without touching system services, disks, or `/etc`, start it in fake mode:

```bash
bash install_dev.sh
bash run_fake.sh
```

To wipe fake-mode setup state and start over:

```bash
bash reset_fake_mode.sh
```

- Fake mode stores its state under `.dev-data/`.
- `reset_fake_mode.sh` deletes `.dev-data/` so you can rerun setup from a clean fake-mode state.
- Use the setup wizard's mount step to point the backup source at a local folder on your machine.
- Cloud backup can still use real `rclone` destinations such as MEGA when `rclone` is installed.
- `run_fake.sh` enables fake-mode auto-login by default. Set `SSS_SKIP_LOGIN=false` if you want the normal login screen.

---

# Documentation

The website keeps the most up-to-date documentation index in one place:

- [Documentation Index](https://sss.chrismin13.com/#documentation)

The underlying markdown files still live in [`docs/`](docs/). Start with [manual_install.md](docs/manual_install.md) if you want the repository copy of the installation guide.

---

## 🗑️ Uninstallation

To completely remove SimpleSaferServer from your system, you can:

**If you still have the repository folder:**
```bash
cd /path/to/SimpleSaferServer
sudo bash uninstall.sh
```

**Or, run directly from the web (recommended):**
```bash
curl -fsSL https://sss.chrismin13.com/uninstall.sh | sudo bash
```

This will:
- Remove all installed scripts, models, and application files
- Remove the systemd service and background tasks
- Clean up configuration, logs, and user data
- Remove Samba shares and related configuration

**Note:** This process is irreversible. Back up any important data before uninstalling.
