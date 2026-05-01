import unittest

from flask import Flask

from simple_safer_server.web.api import (
    json_error,
    json_payload_or_error,
    json_success,
    service_json_response,
)


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

    def test_json_payload_or_error_accepts_empty_payload(self):
        with self.app.test_request_context(json={}):
            data, error_response = json_payload_or_error()

        self.assertEqual(data, {})
        self.assertIsNone(error_response)

    def test_service_json_response_maps_failure_status(self):
        with self.app.app_context():
            result = service_json_response(
                {"success": False, "error": "Nope"},
                failure_status=400,
            )

        if not isinstance(result, tuple):
            self.fail("Expected failure response to include an HTTP status code")
        response, status_code = result
        self.assertEqual(status_code, 400)
        self.assertEqual(response.get_json(), {"success": False, "error": "Nope"})


if __name__ == "__main__":
    unittest.main()
