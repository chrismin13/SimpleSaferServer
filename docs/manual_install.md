# Manual Installation Guide

Use the automated installer when possible. Manual installation is useful when you need to inspect each step on a clean host.

## 1. Check Host Tools

The base app does not install APT packages. Before continuing, make sure the host has `curl`,
`systemctl`, `sudo`, and a running systemd environment.

```bash
command -v curl
command -v systemctl
command -v sudo
test -d /run/systemd/system
```

Do not install optional module tools during base setup unless you are about to use that module.
File Sharing needs Samba, Cloud Backup needs `rclone`, Drive Health can use `smartmontools` or
HDSentinel, managed-drive setup may need disk/filesystem tools such as `fdisk` and `ntfs-3g`, and
System Updates may use APT settings tools. Those are module requirements, not base requirements.

Install `uv` if it is not already available. SimpleSaferServer needs `uv 0.11.13` or newer because
that release line knows about stable CPython 3.14 downloads:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh
uv --version
```

## 2. Copy Application Files

```bash
getent group sss >/dev/null || sudo groupadd --system sss
id sss >/dev/null 2>&1 || sudo useradd --system --gid sss --home-dir /var/lib/SimpleSaferServer --no-create-home --shell /usr/sbin/nologin sss
sudo install -d -o sss -g sss -m 0750 /var/lib/SimpleSaferServer
sudo install -d -o sss -g sss -m 0750 /etc/SimpleSaferServer
sudo install -d -o sss -g sss -m 0750 /var/log/SimpleSaferServer
sudo install -d -o sss -g sss -m 0750 /run/SimpleSaferServer
sudo mkdir -p /opt/SimpleSaferServer
sudo find /opt/SimpleSaferServer -mindepth 1 -maxdepth 1 ! -name .venv -exec rm -rf -- {} +
sudo tar --exclude='./.git' --exclude='./.venv' --exclude='*/__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' -cf - . | sudo tar -xf - -C /opt/SimpleSaferServer
```

Durable app data, including HDSentinel state, belongs in `/var/lib/SimpleSaferServer`. Configuration belongs in `/etc/SimpleSaferServer`, logs in `/var/log/SimpleSaferServer`, and volatile runtime state in `/run/SimpleSaferServer`.

## 3. Sync Python Runtime And Dependencies

Run uv from the installed app directory so it reads `.python-version`, `pyproject.toml`, and `uv.lock`.

```bash
cd /opt/SimpleSaferServer
sudo uv python install
sudo uv sync --frozen --no-dev
```

The app environment is `/opt/SimpleSaferServer/.venv`. Do not use distro Python packages as the app runtime.

## 4. Install The CLI Wrappers And Services

Only `sss` and `sss-helper` belong in `/usr/local/bin`. Feature jobs live in Python modules and run
through the worker or helper.

```bash
sudo mkdir -p /usr/local/bin
sudo tee /usr/local/bin/sss >/dev/null <<'EOF'
#!/bin/sh
exec /opt/SimpleSaferServer/.venv/bin/python -m simple_safer_server.cli "$@"
EOF
sudo chmod +x /usr/local/bin/sss

sudo tee /usr/local/bin/sss-helper >/dev/null <<'EOF'
#!/bin/sh
exec /opt/SimpleSaferServer/.venv/bin/python -m simple_safer_server.privileged_helper "$@"
EOF
sudo chmod +x /usr/local/bin/sss-helper
echo 'sss ALL=(root) NOPASSWD: /usr/local/bin/sss-helper' | sudo tee /etc/sudoers.d/simple-safer-server >/dev/null
sudo chmod 0440 /etc/sudoers.d/simple-safer-server
sudo visudo -cf /etc/sudoers.d/simple-safer-server
sudo cp simple-safer-server-web.service /etc/systemd/system/simple-safer-server-web.service
sudo cp simple-safer-server-worker.service /etc/systemd/system/simple-safer-server-worker.service
sudo systemctl daemon-reload
sudo systemctl enable simple-safer-server-web.service
sudo systemctl enable simple-safer-server-worker.service
sudo systemctl restart simple-safer-server-web.service
sudo systemctl restart simple-safer-server-worker.service
```

The Web service runs Gunicorn from `/opt/SimpleSaferServer/.venv/bin/gunicorn` as the `sss` user
and serves `simple_safer_server.wsgi:app`. The worker service also runs as `sss`. Root-only web,
CLI, and worker actions go through `/usr/local/bin/sss-helper`. Do not add per-feature systemd
units.

## 5. Refresh Task Config

```bash
cd /opt/SimpleSaferServer
sudo -u sss ./.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '/opt/SimpleSaferServer')
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.system_utils import SystemUtils

rt = get_runtime()
config = ConfigManager(runtime=rt).get_all_config()
success, error = SystemUtils(runtime=rt).validate_worker_task_config(config)
if not success:
    raise SystemExit(error)
PY
```

Worker-managed jobs become active only after their module config allows them to run.

## 6. Open The Web UI

Start at:

```text
http://SERVER-IP:5000
```

Complete the setup wizard in the browser.

The base install does not open firewall ports. If the server firewall blocks port `5000`, open that
port with the firewall tool you already use for the host.

## Important Paths

- App folder: `/opt/SimpleSaferServer`
- uv-managed app environment: `/opt/SimpleSaferServer/.venv`
- Config: `/etc/SimpleSaferServer`
- Durable state: `/var/lib/SimpleSaferServer`
- Logs: `/var/log/SimpleSaferServer`
- Volatile state: `/run/SimpleSaferServer`
- Web service: `/etc/systemd/system/simple-safer-server-web.service`
- Worker service: `/etc/systemd/system/simple-safer-server-worker.service`
- CLI wrapper: `/usr/local/bin/sss`
- Privileged helper wrapper: `/usr/local/bin/sss-helper`
