# Manual Installation Guide

Use the automated installer when possible. Manual installation is useful when you need to inspect each step or recover an existing install.

## 1. Install System Packages

SimpleSaferServer uses APT packages for host tools and `uv` for the Python app runtime.

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates smartmontools samba msmtp rsync curl unzip fdisk ntfs-3g unattended-upgrades
```

Install `uv` if it is not already available. SimpleSaferServer needs `uv 0.11.13` or newer because
that release line knows about stable CPython 3.14 downloads:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh
uv --version
```

## 2. Install rclone

The automated installer uses rclone's official installer because distro rclone packages can miss newer cloud backends.

```bash
curl -fsSL https://rclone.org/install.sh -o /tmp/rclone-install.sh
sudo bash /tmp/rclone-install.sh
rm -f /tmp/rclone-install.sh
```

## 3. Install HDSentinel

HDSentinel is optional but recommended for the Drive Health page and the dashboard health meter.

Choose the matching HDSentinel package:

- `amd64`: `third_party/hdsentinel/hdsentinel-linux-amd64.zip`
- `arm64`: `third_party/hdsentinel/hdsentinel-linux-arm64.zip`

Use a 64-bit OS/userspace. SimpleSaferServer does not support ARMv7 or other 32-bit ARM installs.

Extract the archive and install the `HDSentinel` binary as `/usr/local/bin/hdsentinel`:

```bash
unzip third_party/hdsentinel/hdsentinel-linux-amd64.zip -d /tmp/hdsentinel
sudo install -m 755 /tmp/hdsentinel/HDSentinel /usr/local/bin/hdsentinel
/usr/local/bin/hdsentinel
```

## 4. Copy Application Files

```bash
sudo mkdir -p /opt/SimpleSaferServer /var/lib/SimpleSaferServer
sudo rsync -a --delete --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='static' --exclude='templates' ./ /opt/SimpleSaferServer/
sudo rsync -a --delete static /opt/SimpleSaferServer/
sudo rsync -a --delete templates /opt/SimpleSaferServer/
```

Durable app data, including HDSentinel state, belongs in `/var/lib/SimpleSaferServer`. Configuration belongs in `/etc/SimpleSaferServer`, logs in `/var/log/SimpleSaferServer`, and volatile runtime state in `/run/SimpleSaferServer`.

## 5. Sync Python Runtime And Dependencies

Run uv from the installed app directory so it reads `.python-version`, `pyproject.toml`, and `uv.lock`.

```bash
cd /opt/SimpleSaferServer
sudo uv python install
sudo uv sync --frozen --no-dev
```

The app environment is `/opt/SimpleSaferServer/.venv`. Do not use distro Python packages as the app runtime.

## 6. Install Helper Scripts

```bash
sudo mkdir -p /usr/local/bin
sudo cp scripts/* /usr/local/bin/
sudo chmod +x /usr/local/bin/check_mount.sh /usr/local/bin/check_health.sh /usr/local/bin/check_health.py /usr/local/bin/backup_cloud.sh /usr/local/bin/validate_storage_source.py /usr/local/bin/app_update.sh /usr/local/bin/app_update.py /usr/local/bin/log_alert.py /usr/local/bin/ddns_update.sh /usr/local/bin/ddns_update.py /usr/local/bin/restore_disabled_timers.py
```

## 7. Prepare Samba Layout

```bash
cd /opt/SimpleSaferServer
sudo ./.venv/bin/python -c "import sys; sys.path.insert(0, '/opt/SimpleSaferServer'); from simple_safer_server.services.samba_layout import SambaLayoutService; SambaLayoutService().ensure_layout()"
sudo systemctl enable smbd
sudo systemctl restart smbd
sudo systemctl enable nmbd || true
sudo systemctl start nmbd || true
sudo apt-get install -y wsdd2 || true
sudo systemctl enable wsdd2 || true
sudo systemctl start wsdd2 || true
```

`smbd` is required for file serving. `nmbd` and `wsdd2` are discovery helpers and may be unavailable on some supported hosts.

## 8. Install The Web Service

```bash
sudo cp simple_safer_server_web.service /etc/systemd/system/simple_safer_server_web.service
sudo systemctl daemon-reload
sudo systemctl enable simple_safer_server_web.service
sudo systemctl restart simple_safer_server_web.service
```

The service runs Gunicorn from `/opt/SimpleSaferServer/.venv/bin/gunicorn` and serves `simple_safer_server.wsgi:app`.

## 9. Generate Background Units

```bash
cd /opt/SimpleSaferServer
sudo ./.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '/opt/SimpleSaferServer')
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.system_utils import SystemUtils

rt = get_runtime()
config = ConfigManager(runtime=rt).get_all_config()
setup_complete = str(config.get('system', {}).get('setup_complete', 'false')).lower() == 'true'
success, error = SystemUtils(runtime=rt).install_systemd_services_and_timers(
    config,
    activate_timers=setup_complete,
)
if not success:
    raise SystemExit(error)
PY
```

Recurring timers become active only after setup is complete.

## 10. Open The Web UI

Start at:

```text
http://SERVER-IP:5000
```

Complete the setup wizard in the browser.

## Important Paths

- App checkout: `/opt/SimpleSaferServer`
- uv-managed app environment: `/opt/SimpleSaferServer/.venv`
- Config: `/etc/SimpleSaferServer`
- Durable state: `/var/lib/SimpleSaferServer`
- Logs: `/var/log/SimpleSaferServer`
- Volatile state: `/run/SimpleSaferServer`
- Web service: `/etc/systemd/system/simple_safer_server_web.service`
- HDSentinel binary: `/usr/local/bin/hdsentinel`
