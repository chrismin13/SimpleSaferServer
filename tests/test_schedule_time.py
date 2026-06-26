import unittest

from simple_safer_server.services.schedule_time import (
    ScheduleTimeError,
    normalize_ui_schedule_time,
    systemd_schedule_time,
)


class ScheduleTimeTests(unittest.TestCase):
    def test_ui_schedule_time_accepts_strict_two_digit_hh_mm(self):
        for value in ["00:00", "03:00", "23:59"]:
            self.assertEqual(normalize_ui_schedule_time(value), value)

    def test_ui_schedule_time_rejects_invalid_shapes(self):
        invalid_values = [
            "7:05",
            "03:00:00",
            "24:00",
            "03:60",
            "03",
            "+03:00",
            "03: 00",
            "bad:00",
            "",
            None,
        ]
        for value in invalid_values:
            with self.assertRaises(ScheduleTimeError, msg=str(value)):
                normalize_ui_schedule_time(value)

    def test_systemd_schedule_time_expands_to_seconds(self):
        self.assertEqual(systemd_schedule_time("07:05"), (7, 5, "07:05:00"))

    def test_systemd_schedule_time_rejects_invalid_shapes(self):
        with self.assertRaises(ScheduleTimeError):
            systemd_schedule_time("7:05")
