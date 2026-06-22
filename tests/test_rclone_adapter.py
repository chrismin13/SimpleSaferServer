import unittest

from simple_safer_server.adapters.rclone import RcloneAdapter


class RcloneAdapterTests(unittest.TestCase):
    def test_sync_command_uses_filter_from_file_path(self):
        command = RcloneAdapter.build_sync_command(
            "/media/backup",
            "remote:/backup",
            config_path="/root/.config/rclone/rclone.conf",
            bandwidth_limit="4M",
            filter_from="/run/SimpleSaferServer/rclone-filter.txt",
        )

        self.assertEqual(
            command,
            [
                "rclone",
                "sync",
                "/media/backup",
                "remote:/backup",
                "--create-empty-src-dirs",
                "-v",
                "--config",
                "/root/.config/rclone/rclone.conf",
                "--bwlimit",
                "4M",
                "--filter-from",
                "/run/SimpleSaferServer/rclone-filter.txt",
            ],
        )


if __name__ == "__main__":
    unittest.main()
