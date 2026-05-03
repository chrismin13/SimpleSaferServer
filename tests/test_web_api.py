import unittest
from dataclasses import dataclass

from flask import Flask

from simple_safer_server.web.api import (
    json_data,
    json_problem,
    json_request_data,
    serialize_api_data,
)
from simple_safer_server.web.problems import ValidationProblem


@dataclass(frozen=True)
class ExampleResult:
    name: str
    count: int


class WebApiHelperTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_json_data_wraps_serialized_data(self):
        with self.app.app_context():
            response = json_data(ExampleResult(name="backup", count=2), message="Loaded")

        if isinstance(response, tuple):
            self.fail("Expected default json_data response to omit explicit status code.")
        self.assertEqual(
            response.get_json(),
            {"data": {"name": "backup", "count": 2}, "message": "Loaded"},
        )

    def test_json_problem_uses_problem_details_shape_and_status(self):
        with self.app.app_context():
            response, status_code = json_problem(
                ValidationProblem("Folder name is required.", slug="validation-error")
            )

        self.assertEqual(status_code, 400)
        self.assertEqual(
            response.get_json(),
            {
                "type": (
                    "https://github.com/chrismin13/SimpleSaferServer/blob/main/"
                    "docs/api_responses.md#validation-error"
                ),
                "title": "Validation error",
                "status": 400,
                "detail": "Folder name is required.",
            },
        )

    def test_json_request_data_raises_problem_for_missing_json_object(self):
        with self.app.test_request_context(json=[]):
            with self.assertRaises(ValidationProblem) as context:
                json_request_data()

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.slug, "request-body-must-be-json-object")

    def test_serialize_api_data_prefers_as_dict(self):
        class SecretBearingResult:
            def __init__(self):
                self.secret = "do-not-serialize"

            def as_dict(self):
                return {"public": "safe"}

        self.assertEqual(serialize_api_data(SecretBearingResult()), {"public": "safe"})

    def test_serialize_api_data_preserves_nested_none(self):
        self.assertEqual(serialize_api_data({"checked_at": None}), {"checked_at": None})


if __name__ == "__main__":
    unittest.main()
