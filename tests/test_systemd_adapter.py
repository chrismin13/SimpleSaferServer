from unittest.mock import MagicMock

from simple_safer_server.adapters.systemd import SystemdAdapter


def test_journal_uses_all_output_so_ansi_color_sequences_survive():
    runner = MagicMock()
    runner.run.return_value.stdout = "log"
    adapter = SystemdAdapter(runner)

    assert adapter.journal("app_update.service", 50) == "log"

    command = runner.run.call_args.args[0]
    assert command[:2] == ["journalctl", "-a"]
    assert command[2:] == ["-u", "app_update.service", "-n", "50", "--no-pager"]


def test_timer_disable_and_enable_use_systemd_timer_unit_only():
    runner = MagicMock()
    adapter = SystemdAdapter(runner)

    adapter.disable_timer_now("backup_cloud.timer")
    adapter.enable_timer_now("backup_cloud.timer")

    assert runner.run.call_args_list[0].args[0] == [
        "systemctl",
        "disable",
        "--now",
        "backup_cloud.timer",
    ]
    assert runner.run.call_args_list[1].args[0] == [
        "systemctl",
        "enable",
        "--now",
        "backup_cloud.timer",
    ]
