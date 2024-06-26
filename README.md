# SimpleSaferServer
Basic scripts designed to run on Debian-based (Raspberry Pi or Ubuntu Server) machines to back up data, monitor hard drive health and more.

# Install
## Preparation
### Install dependencies
Install git - will be used to download this script later
```
sudo apt install git
```

### Set up fstab to mount an external NTFS backup drive 
1. Find the NTFS partition UUID  by running `sudo lsblk -f | grep -v loop` and getting just the UUID of the partition you want
2. `sudo mkdir /media/backup`  to create the directory that will contain the partition
3. `sudo nano /etc/fstab` 
    
    ```
    # <uuid>		<dir>		<type>	<options>	<dump>	<pass>
    UUID=		/media/backup	ntfs-3g	defaults,nofail	0	0
    ```
    
    `nofail` is important, if missing the system won't boot if the drive is disconnected
    
4. `sudo mount -a` to apply the changes and remount the disks

### Download and set up rclone
1. Run `sudo -v ; curl https://rclone.org/install.sh | sudo bash`
2. Set up rclone by running `rclone config`. Some useful resources:
    1. https://rclone.org/drive/
    2. https://rclone.org/onedrive/
    3. https://rclone.org/crypt/ 
        1. USE OBFUSCATE to keep paths short
        2. Store your keys in a password manager!
3. Install screen for testing `sudo apt install screen`
4. Run `screen`
    1. `rclone sync /media/backup/ YourRemote: -P --create-empty-src-dirs` (Replace YourRemote: with your rclone mount point or folder etc.)
    2. If the script is running correctly, detach with Ctrl+A and Ctrl+D
    3. To resume, run `screen -r`.

### Download HDSentinel (temporary, see #4)
```bash
wget https://www.hdsentinel.com/hdslin/hdsentinel-armv8.bz2
bzip2 -d hdsentinel-armv8.bz2
chmod +x hdsentinel-armv8
sudo mv hdsentinel-armv8 /usr/local/bin/hdsentinel-armv8
```
### Set up SMTP Server for email alerts

1. `sudo apt install msmtp`
2. `sudo nano /etc/msmtprc`

```
# Set default values for all following accounts.
defaults
port 587
tls on
tls_trust_file /etc/ssl/certs/ca-certificates.crt

account gmail
host smtp.gmail.com
from YOUR_EMAIL_HERE
auth on
user YOUR_EMAIL_HERE
password YOUR_PASSOWRD_HERE
# Set a default account
account default : gmail
```
To use Gmail, you need to enable 2FA and add an application key that you'll use as your password.

## Actual scripts:

Find your Disk’s UUID and USB ID and keep them somewhere:
`sudo nano /etc/fstab`    
`lsusb`

Run:
```
bash <(curl -s sss.chrismin13.com)
```
