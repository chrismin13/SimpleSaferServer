import unittest
from types import SimpleNamespace
from typing import Any, cast

from simple_safer_server.adapters.setup_commands import SetupCommandAdapter


class FakeCommandRunner:
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class SetupCommandAdapterTests(unittest.TestCase):
    def test_create_partition_rebuilds_disk_with_scriptable_gpt_command(self):
        runner = FakeCommandRunner()
        adapter = SetupCommandAdapter(command_runner=cast(Any, runner))

        adapter.create_partition("/dev/sdb", b"type=test\n")

        self.assertEqual(
            runner.calls[0][0],
            [
                "sfdisk",
                "--wipe",
                "always",
                "--wipe-partitions",
                "always",
                "--label",
                "gpt",
                "/dev/sdb",
            ],
        )
        self.assertEqual(runner.calls[0][1]["input"], b"type=test\n")
        self.assertTrue(runner.calls[0][1]["capture_output"])


if __name__ == "__main__":
    unittest.main()
