# Add mount to fstab
echo "Adding mount to fstab..."
echo "# SimpleSaferServer backup drive mount" >> /etc/fstab
echo "UUID=$UUID $MOUNT_POINT ext4 defaults 0 2" >> /etc/fstab 