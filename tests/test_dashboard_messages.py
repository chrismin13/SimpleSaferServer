import unittest
from datetime import datetime
from unittest.mock import patch

import dashboard_messages


class DashboardMessageTests(unittest.TestCase):
    def test_parse_server_datetime_accepts_systemd_style_timestamp(self):
        parsed = dashboard_messages.parse_server_datetime('Mon 2026-04-06 02:58:00 UTC')

        self.assertEqual(parsed, datetime(2026, 4, 6, 2, 58, 0))

    def test_format_future_delay_returns_compact_countdown(self):
        delay = dashboard_messages.format_future_delay(
            '2026-04-06 02:58:00',
            now=datetime(2026, 4, 6, 0, 45, 0),
        )

        self.assertEqual(delay, 'in about 2h 13m')

    def test_build_dashboard_unmount_success_message_includes_eta_when_available(self):
        with patch('dashboard_messages.format_future_delay', return_value='in about 2h 13m'):
            message = dashboard_messages.build_dashboard_unmount_success_message(
                'Drive unmounted and powered down. It is now safe to remove the drive.',
                'Mon 2026-04-06 02:58:00 UTC',
            )

        self.assertIn('safe to remove the drive', message)
        self.assertIn('next Check Mount run, in about 2h 13m', message)

    def test_build_dashboard_unmount_success_message_uses_schedule_fallback(self):
        with patch('dashboard_messages.format_future_delay', return_value=None):
            message = dashboard_messages.build_dashboard_unmount_success_message(
                'Drive unmounted and powered down. It is now safe to remove the drive.',
                'Retrieval Error',
            )

        self.assertIn('next scheduled Check Mount run', message)


if __name__ == '__main__':
    unittest.main()
