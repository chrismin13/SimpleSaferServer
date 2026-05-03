# rclone Installer Exit Code

The upstream rclone installer can return a nonzero exit code when the latest rclone version is
already installed. The SimpleSaferServer installer now treats that case as acceptable only after
verifying that the `rclone` command is available.

Real download or install failures still stop the install because Cloud Backup depends on rclone.
Those failure messages include the curl or rclone installer exit code so operators have the useful
part of the upstream failure without digging through scrollback.
