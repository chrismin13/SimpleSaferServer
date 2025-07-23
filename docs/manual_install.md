# Manual Installation Guide for SimpleSaferServer

This guide explains how to manually install SimpleSaferServer on a clean Debian-based system, without using the automated install script. This is useful for advanced users, troubleshooting, or custom deployments.

---

## 1. Install System Dependencies

Open a terminal and run:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-flask python3-flask-socketio python3-psutil python3-xgboost python3-joblib python3-pandas python3-sklearn python3-cryptography smartmontools samba msmtp rsync curl
```

## 2. Install rclone (Official Script)

The Debian package for rclone is often outdated and missing cloud backends. Use the official script:

```bash
sudo -v
TMPFILE=$(mktemp)
curl -s https://rclone.org/install.sh -o "$TMPFILE"
sudo sh -c "bash $TMPFILE || true"
rm -f "$TMPFILE"
```

## 3. Download and Copy Application Files

Clone the repository and copy files to `/opt/SimpleSaferServer`:

```bash
git clone https://github.com/chrismin13/SimpleSaferServer.git
cd SimpleSaferServer
sudo mkdir -p /opt/SimpleSaferServer
sudo rsync -a --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='telemetry.csv' --exclude='harddrive_model' --exclude='scripts' --exclude='static' --exclude='templates' ./ /opt/SimpleSaferServer/
sudo rsync -a static /opt/SimpleSaferServer/
sudo rsync -a templates /opt/SimpleSaferServer/
```

## 4. Install Scripts and Model Files

```bash
sudo mkdir -p /usr/local/bin
for script in scripts/*.sh scripts/*.py; do
  sudo cp "$script" /usr/local/bin/
  sudo chmod +x /usr/local/bin/$(basename $script)
done
sudo mkdir -p /opt/SimpleSaferServer/harddrive_model
sudo cp harddrive_model/* /opt/SimpleSaferServer/harddrive_model/
```

## 5. Set Up the Systemd Service

## Email Setup
- **Email Address**: Enter the address for alerts.
- **From Address**: Enter the address that will appear in the From field of alert emails. This must be a valid, verified sender for your SMTP service (e.g., the authenticated SMTP user or a domain-verified address). Some SMTP providers will only deliver mail if the From address matches the authenticated user or a verified sender.
- **SMTP Configuration**: Enter SMTP server, port, username, and password.
- **Save Email Configuration**: Button to save settings.

Copy the service file and enable/start the service:

```bash
sudo cp simple_safer_server_web.service /etc/systemd/system/simple_safer_server_web.service
sudo systemctl daemon-reload
sudo systemctl enable simple_safer_server_web.service
sudo systemctl restart simple_safer_server_web.service
```

## 6. (Optional) Open Firewall Port 5000

If you use a firewall, open port 5000:

- For UFW:
  ```bash
  sudo ufw allow 5000/tcp
  ```
- For firewalld:
  ```bash
  sudo firewall-cmd --permanent --add-port=5000/tcp
  sudo firewall-cmd --reload
  ```
- For iptables:
  ```bash
  sudo iptables -C INPUT -p tcp --dport 5000 -j ACCEPT 2>/dev/null || sudo iptables -A INPUT -p tcp --dport 5000 -j ACCEPT
  ```

## 7. Access the Web UI

After installation, open a browser on any device in your network and go to:

```
http://<your-server-ip>:5000
```

Follow the setup wizard to complete configuration.

---

## Troubleshooting
- Check service status: `sudo systemctl status simple_safer_server_web.service`
- View logs: `journalctl -u simple_safer_server_web.service`
- Ensure all dependencies are installed and up to date.

## Security Notes
- For production, consider running the service as a dedicated user instead of root.
- Only open necessary ports on your firewall.
- Keep your system and dependencies updated.

---

For more help, see the [GitHub repository](https://github.com/chrismin13/SimpleSaferServer) or [landing page](https://sss.chrismin13.com). 