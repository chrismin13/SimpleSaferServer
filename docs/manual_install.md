# Manual Installation Guide for SimpleSaferServer

This guide explains how to manually install SimpleSaferServer on a clean Debian-based system without using the automated installer. It is written as a checklist so each step is easy to verify before you move on.

---

## 1. Install System Dependencies

- Run `sudo apt-get update`.
- Run `sudo apt-get install -y git python3 python3-pip python3-flask python3-flask-socketio python3-psutil python3-xgboost python3-joblib python3-pandas python3-sklearn python3-cryptography smartmontools samba msmtp rsync curl unzip`.

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
- Run `sudo rsync -a --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='telemetry.csv' --exclude='harddrive_model' --exclude='scripts' --exclude='static' --exclude='templates' ./ /opt/SimpleSaferServer/`.
- Run `sudo rsync -a static /opt/SimpleSaferServer/`.
- Run `sudo rsync -a templates /opt/SimpleSaferServer/`.

## 6. Install Scripts and Model Files

- Run `sudo mkdir -p /usr/local/bin`.
- Copy each file from `scripts/` into `/usr/local/bin/`.
- Mark each copied script as executable with `chmod +x`.
- Run `sudo mkdir -p /opt/SimpleSaferServer/harddrive_model`.
- Copy the contents of `harddrive_model/` into `/opt/SimpleSaferServer/harddrive_model/`.

## 7. Set Up the Systemd Service

- Copy `simple_safer_server_web.service` to `/etc/systemd/system/simple_safer_server_web.service`.
- Run `sudo systemctl daemon-reload`.
- Run `sudo systemctl enable simple_safer_server_web.service`.
- Run `sudo systemctl restart simple_safer_server_web.service`.
- After the service starts, use the Web UI setup flow to configure email alerts, backup settings, and the initial administrator account.

## 8. Open Firewall Port 5000 If Needed

- If you use UFW, run `sudo ufw allow 5000/tcp`.
- If you use firewalld, run `sudo firewall-cmd --permanent --add-port=5000/tcp`, then run `sudo firewall-cmd --reload`.
- If you manage firewall rules manually, allow inbound TCP traffic on port `5000`.

## 9. Access the Web UI

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
