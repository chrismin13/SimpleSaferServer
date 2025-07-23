# SimpleSaferServer

## 🚀 Quick Installation

To install SimpleSaferServer on a clean Debian-based system, run the following command:

```bash
curl -fsSL https://sss.chrismin13.com/install.sh | sudo bash
```

- This script will install all dependencies, set up the service, and print your Web UI address.
- For more details and documentation, visit the [landing page](https://sss.chrismin13.com).
- For manual installation, see the [Manual Installation Guide](docs/manual_install.md).

---

# Documentation Index

This project includes detailed documentation for each main feature and page. See the following files for step-by-step guides and explanations:

- [manual_install.md](docs/manual_install.md)
- [setup.md](docs/setup.md)
- [login.md](docs/login.md)
- [dashboard.md](docs/dashboard.md)
- [drive_health.md](docs/drive_health.md)
- [cloud_backup.md](docs/cloud_backup.md)
- [network_file_sharing.md](docs/network_file_sharing.md)
- [users.md](docs/users.md)
- [alerts.md](docs/alerts.md)
- [task_detail.md](docs/task_detail.md)

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