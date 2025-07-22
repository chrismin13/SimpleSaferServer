#!/usr/bin/env python3

import os
import tempfile
import subprocess
from getpass import getpass

RCLONE_CONFIG_TEMPLATE = """
[mega]
type = mega
user = {email}
pass = {password}
"""

def encrypt_password(password):
    """
    Run `rclone obscure` to encrypt the MEGA password.
    This is what rclone expects in the config.
    """
    result = subprocess.run(["rclone", "obscure", password],
                            stdout=subprocess.PIPE, check=True, text=True)
    return result.stdout.strip()

def build_temp_config(email, obscured_pw):
    """
    Create a temporary rclone config file with MEGA credentials.
    """
    config_text = RCLONE_CONFIG_TEMPLATE.format(email=email, password=obscured_pw)
    config_file = tempfile.NamedTemporaryFile(delete=False, mode="w", prefix="rclone-", suffix=".conf")
    config_file.write(config_text)
    config_file.close()
    return config_file.name

def main():
    print("🔐  MEGA Backup Tool (Proof of Concept)")
    email = input("Enter your MEGA email: ")
    password = getpass("Enter your MEGA password: ")
    local_path = input("Enter path to file or folder to back up: ")
    remote_folder = input("Enter remote folder name on MEGA (e.g., backups): ")

    obscured_pw = encrypt_password(password)
    config_path = build_temp_config(email, obscured_pw)

    try:
        print(f"\n🚀 Uploading {local_path} to MEGA:{remote_folder} ...\n")
        subprocess.run([
            "rclone", "copy", local_path, f"mega:{remote_folder}",
            "--config", config_path,
            "--progress",
            "--transfers", "4",
            "--checkers", "8"
        ], check=True)
        print("\n✅ Backup completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ rclone failed: {e}")
    finally:
        os.remove(config_path)
        print(f"(Temporary config {config_path} removed)")

if __name__ == "__main__":
    main()
