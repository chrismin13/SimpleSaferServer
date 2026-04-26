import unittest

from flask import Flask

from simple_safer_server.web.api import json_error, json_payload_or_error, json_success


class WebApiHelperTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_json_success_adds_success_flag(self):
        with self.app.app_context():
            response = json_success(message="Saved")

        self.assertEqual(response.get_json(), {"success": True, "message": "Saved"})

    def test_json_error_keeps_existing_default_status_behavior(self):
        with self.app.app_context():
            response = json_error("Nope")

        if isinstance(response, tuple):
            self.fail("Default json_error response should not include an explicit status code.")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"success": False, "error": "Nope"})

    def test_json_payload_or_error_rejects_empty_payload(self):
        with self.app.test_request_context(json={}):
            data, error_response = json_payload_or_error()

        self.assertEqual(data, {})
        response, status_code = error_response
        self.assertEqual(status_code, 400)
        self.assertEqual(response.get_json(), {"success": False, "message": "Invalid payload"})


if __name__ == "__main__":
    unittest.main()
