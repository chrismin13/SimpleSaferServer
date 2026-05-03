import unittest

from simple_safer_server.services.schedule_time import (
    ScheduleTimeError,
    normalize_legacy_schedule_time,
    normalize_ui_schedule_time,
    systemd_schedule_time,
)


class ScheduleTimeTests(unittest.TestCase):
    def test_ui_schedule_time_accepts_strict_two_digit_hh_mm(self):
        for value in ["00:00", "03:00", "23:59"]:
            self.assertEqual(normalize_ui_schedule_time(value), value)

    def test_ui_schedule_time_rejects_legacy_or_invalid_shapes(self):
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

    def test_legacy_schedule_time_normalizes_existing_config_shapes(self):
        cases = {
            "7:05": "07:05",
            "03:00": "03:00",
            "03:00:00": "03:00",
            "23:59:59": "23:59",
        }
        for value, expected in cases.items():
            self.assertEqual(normalize_legacy_schedule_time(value), expected)

    def test_legacy_schedule_time_rejects_unsafe_or_out_of_range_values(self):
        invalid_values = ["03", "24:00", "03:60", "+03:00", "03: 00", "bad:00"]
        for value in invalid_values:
            with self.assertRaises(ScheduleTimeError, msg=value):
                normalize_legacy_schedule_time(value)

    def test_systemd_schedule_time_expands_to_seconds(self):
        self.assertEqual(systemd_schedule_time("7:05"), (7, 5, "07:05:00"))
