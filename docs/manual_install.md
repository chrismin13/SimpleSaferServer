# Manual Installation Guide for SimpleSaferServer

This guide explains how to manually install SimpleSaferServer on a clean Debian or Ubuntu based system without using the automated installer. It is written as a checklist so each step is easy to verify before you move on.

---

## 1. Install System Dependencies

- Run `sudo apt-get update`.
- Run `sudo apt-get install -y git python3 python3-pip python3-venv smartmontools samba msmtp rsync curl unzip fdisk ntfs-3g unattended-upgrades`.
- `ntfs-3g` is still installed because it is the default backup-drive driver. The `ntfs3` driver is kernel-provided on newer systems and can be selected later from the Drive Health backup-drive setup panel when the running kernel supports it.
- Optionally run `sudo apt-get install -y wsdd2` for modern Windows Network discovery. Continue
  without it if your distro release does not provide the package; `smbd` is the required
  file-serving daemon, while `nmbd` and `wsdd2` are discovery helpers.

## 2. Install rclone

- The Debian package for rclone is often outdated and missing cloud backends. Use the official script:
- Run `sudo -v ; curl https://rclone.org/install.sh | sudo bash`.
- Confirm the install by running `rclone version`.

## 3. Download the Repository

- Run `git clone https://github.com/chrismin13/SimpleSaferServer.git`.
- Run `cd SimpleSaferServer`.

## 4. Install HDSentinel

- Decide whether you want to install HDSentinel from the vendor site yourself or use the vendored archive included in this repository.
- The automated installer only uses the vendored files in `third_party/hdsentinel/` so it never downloads HDSentinel during `install.sh`.
- To identify your architecture, run `dpkg --print-architecture`. This is the most reliable option on Debian-based systems because it reports the userspace architecture.
- If `dpkg` is not available, run `uname -m` as a fallback and match the result to one of the supported families below.

Choose the matching HDSentinel package:

- `amd64` or values starting with `x86_64`: use the x64 Linux build.
- `arm64` or values starting with `aarch64`: use the ARMv8 Linux build.
- `armhf` or values starting with `armv7` or `armv8l`: use the ARMv7 Linux build.
- Older 32-bit ARM variants such as `armv6*` are not supported by the vendored HDSentinel binary, so do not force the ARMv7 build onto them.

If you want to use the vendor download:

- Open https://www.hdsentinel.com/hdslin.php
- Find the Linux download that matches your architecture.
- Download the archive to your machine with `wget` or a browser.
- For `amd64`, you can download the x64 build with `wget https://www.hdsentinel.com/hdslin/hdsentinel-020c-x64.zip`.
- For `arm64`, you can download the ARMv8 build with `wget https://www.hdsentinel.com/hdslin/hdsentinel-armv8.zip`.
- For `armhf` or `armv7*`, you can download the ARMv7 build with `wget https://www.hdsentinel.com/hdslin/hdsentinel-armv7.gz`.
- Extract `.zip` archives with `unzip /path/to/archive.zip`.
- Extract `.gz` archives with `gunzip /path/to/archive.gz`.
- If you downloaded the vendor ARMv7 build, note that the vendor ships it as a `.gz` file instead of a `.zip`, so you need to extract the `HDSentinel` binary from that gzip archive before installing it.

If you want to use the vendored copy from this repository:

- Open `third_party/hdsentinel/`.
- Use `hdsentinel-linux-amd64.zip` for `amd64`.
- Use `hdsentinel-linux-arm64.zip` for `arm64`.
- Use `hdsentinel-linux-armv7.zip` for `armhf` and other supported `armv7*` or `armv8l` systems. This file is repackaged in this repository because the vendor ARMv7 download is distributed as `.gz`.
- Extract the archive so you have the `HDSentinel` binary available as a normal file. For example, run `unzip third_party/hdsentinel/hdsentinel-linux-amd64.zip`.

Install the extracted binary:

- Run `sudo install -m 755 /path/to/HDSentinel /usr/local/bin/hdsentinel`.
- Confirm the install by running `/usr/local/bin/hdsentinel`.

## 5. Copy Application Files

- Run `sudo mkdir -p /opt/SimpleSaferServer`.
- Run `sudo mkdir -p /var/lib/SimpleSaferServer`.
- Run `sudo rsync -a --delete --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='telemetry.csv' --exclude='harddrive_model' --exclude='static' --exclude='templates' ./ /opt/SimpleSaferServer/`.
- Run `sudo rsync -a --delete static /opt/SimpleSaferServer/`.
- Run `sudo rsync -a --delete templates /opt/SimpleSaferServer/`.

`/opt/SimpleSaferServer` is the application folder. Keep durable app data, including drive-health telemetry and HDSentinel state, in `/var/lib/SimpleSaferServer`; configuration in `/etc/SimpleSaferServer`; logs in `/var/log/SimpleSaferServer`; and volatile runtime state in `/run/SimpleSaferServer`.

## 6. Set Up the Python Virtualenv

- `install.sh` creates the application virtualenv at `/opt/SimpleSaferServer/venv`, so use that same path for a manual install.
- Run `sudo python3 -m venv --system-site-packages /opt/SimpleSaferServer/venv`.
- Because the virtualenv lives under `/opt`, open a root shell with `sudo -s` before activating it so `pip` can write into that environment.
- In that root shell, run `source /opt/SimpleSaferServer/venv/bin/activate`.
- On Python 3.9 or newer, run `pip install --upgrade pip wheel`, then run `pip install -r /opt/SimpleSaferServer/requirements.txt`.
- On Python runtimes older than 3.9, including Debian 10 / Python 3.7 and Ubuntu 20.04 / Python 3.8, run `pip install --upgrade "pip<24.1" wheel`, then run `pip install -r /opt/SimpleSaferServer/requirements-legacy-py37.txt`.
- Older Python runtimes use a legacy dependency set because upstream security fixes for several packages require newer Python releases. Use Debian 13 or another Python 3.9+ platform for the strict security-supported baseline.
- Run `deactivate`, then run `exit` to leave the root shell when you are done installing Python packages.

## 7. Install Scripts and Model Files

- Run `sudo mkdir -p /usr/local/bin`.
- Copy each file from `scripts/` into `/usr/local/bin/`.
- Preserve the copied files' modes under `/opt/SimpleSaferServer/scripts`. Only the helper-script
  copies under `/usr/local/bin` need executable bits.
- Register the installed checkout for root-run Git commands:
  `sudo git config --system --add safe.directory /opt/SimpleSaferServer`.
- Run `sudo mkdir -p /opt/SimpleSaferServer/harddrive_model`.
- Run `sudo rsync -a --delete harddrive_model/ /opt/SimpleSaferServer/harddrive_model/`.

## 8. Set Up the Systemd Service

- Prepare the SimpleSaferServer-owned Samba include layout before starting the web service:
  ```bash
  cd /opt/SimpleSaferServer
  sudo ./venv/bin/python -c "import sys; sys.path.insert(0, '/opt/SimpleSaferServer'); from simple_safer_server.services.samba_layout import SambaLayoutService; SambaLayoutService().ensure_layout()"
  ```
  The explicit working directory and import path match the automated installer because the app is
  copied into `/opt/SimpleSaferServer` rather than installed as a Python package.
  This creates or refreshes `/etc/samba/simple_safer_server_globals.conf` and
  `/etc/samba/simple_safer_server_shares.conf` without creating the default `backup` share. The Web
  UI setup flow creates that share later after it knows the backup mount point.
- Enable and start Samba file serving: `sudo systemctl enable smbd && sudo systemctl start smbd`.
- Confirm `smbd` is active with `sudo systemctl is-active smbd`. Do not continue until it reports
  `active`; SimpleSaferServer depends on this daemon to serve files.
- Best-effort discovery services can be started with `sudo systemctl enable nmbd wsdd2` and
  `sudo systemctl start nmbd wsdd2`. Warnings or inactive states for these services mean network
  discovery may be degraded, but existing SMB clients can still connect directly when `smbd` is
  active.
- Copy `simple_safer_server_web.service` to `/etc/systemd/system/simple_safer_server_web.service`.
- `simple_safer_server_web.service` runs the package module entrypoint with `ExecStart=/opt/SimpleSaferServer/venv/bin/python -m simple_safer_server --host=0.0.0.0 --port=5000 --no-debug`, so `/opt/SimpleSaferServer/venv` must exist before you start the service.
- The module entrypoint is `simple_safer_server/__main__.py`; it starts the built-in Flask server path, so the `WEB_THREADS` variable has no effect on this systemd unit.
- Hosted deployments that need Gunicorn should use the `Procfile` command instead: it runs `gunicorn -k gthread --threads ${WEB_THREADS:-4}` and reads `WEB_THREADS` to tune concurrent request handling.
- This matches the `VENV_DIR="/opt/SimpleSaferServer/venv"` flow in `install.sh`, which is why the manual install should use the same venv path instead of distro Python packages for the app runtime.
- Run `sudo systemctl daemon-reload`.
- Run `sudo systemctl enable simple_safer_server_web.service`.
- Run `sudo systemctl restart simple_safer_server_web.service`.
- After the service starts, use the Web UI setup flow to configure email alerts, backup settings, and the initial administrator account.
- The recurring `check_mount`, `check_health`, `backup_cloud`, `ddns_update`, and `app_update`
  timers should stay inactive until the Web UI setup flow is complete. They use `Persistent=true`,
  so starting them before setup can immediately replay missed runs with incomplete backup and alert
  settings.
- The global `simple_safer_server_restore_schedules.timer` runs every five minutes with
  `Persistent=true`. It is safe before setup completion because it only acts on explicit
  SimpleSaferServer Disable Schedule records.

## 9. Open Firewall Port 5000 If Needed

- If you use UFW, run `sudo ufw allow 5000/tcp`.
- If you use firewalld, run `sudo firewall-cmd --permanent --add-port=5000/tcp`, then run `sudo firewall-cmd --reload`.
- If you manage firewall rules manually, allow inbound TCP traffic on port `5000`.

## 10. Access the Web UI

- Open `http://<your-server-ip>:5000` in a browser on your network.
- Follow the setup wizard to finish the installation.

---

## Troubleshooting

- Check service status with `sudo systemctl status simple_safer_server_web.service`.
- View logs with `journalctl -u simple_safer_server_web.service`.
- Make sure the HDSentinel binary is installed at `/usr/local/bin/hdsentinel` if you want drive health data from HDSentinel.

## Security Notes

- For production, consider running the service as a dedicated user instead of root.
- Only open the firewall ports you actually need.
- Keep your system packages and vendored binaries up to date.

---

For more help, see the [GitHub repository](https://github.com/chrismin13/SimpleSaferServer) or [landing page](https://sss.chrismin13.com).
