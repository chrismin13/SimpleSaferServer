import unittest
from datetime import date

from simple_safer_server.services.os_support import get_support_info, parse_os_release_text


class OsSupportTests(unittest.TestCase):
    def test_parse_os_release_text_handles_quotes_and_comments(self):
        values = parse_os_release_text(
            """
            NAME="Linux Mint"
            VERSION_ID="22"
            # ignored
            ID=linuxmint
            ID_LIKE="ubuntu debian"
            """
        )

        self.assertEqual(values["ID"], "linuxmint")
        self.assertEqual(values["ID_LIKE"], "ubuntu debian")

    def test_debian_support_uses_major_version(self):
        support = get_support_info("debian", "12.7")

        self.assertTrue(support["known"])
        self.assertEqual(support["standard_eol"], "2026-06-10")
        self.assertEqual(support["max_eol"], "2028-06-30")

    def test_ubuntu_support_uses_major_minor_version(self):
        support = get_support_info("ubuntu", "24.04.4")

        self.assertTrue(support["known"])
        self.assertEqual(support["standard_eol_display"], "June 2029")
        self.assertEqual(support["max_eol_display"], "April 2034")

    def test_ubuntu_support_excludes_paid_legacy_add_on_dates(self):
        support = get_support_info("ubuntu", "22.04")

        self.assertTrue(support["known"])
        self.assertEqual(support["max_eol"], "2032-04-30")
        self.assertIn("excludes the paid Legacy", support["notes"])

    def test_support_warns_when_eol_is_within_six_months(self):
        support = get_support_info("debian", "11", today=date(2026, 3, 1))

        self.assertTrue(support["is_supported"])
        self.assertTrue(support["approaching_eol"])
        self.assertEqual(support["days_until_eol"], 183)

    def test_support_does_not_warn_more_than_six_months_before_eol(self):
        support = get_support_info("debian", "11", today=date(2026, 2, 28))

        self.assertTrue(support["is_supported"])
        self.assertFalse(support["approaching_eol"])
        self.assertEqual(support["days_until_eol"], 184)


if __name__ == "__main__":
    unittest.main()
