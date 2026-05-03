from dataclasses import is_dataclass
from typing import Any, Dict, Optional

from flask import jsonify, request

from simple_safer_server.web.problems import ApiProblem, ValidationProblem


def serialize_api_data(value: Any) -> Any:
    """Convert app-level result objects into JSON-compatible data.

    Explicit `as_dict()` methods are preferred for objects that hide secrets or
    expose stable API aliases; dataclass field names are only used as a fallback.
    """
    if value is None:
        return None
    if hasattr(value, "as_dict"):
        return serialize_api_data(value.as_dict())
    if is_dataclass(value):
        return {
            field_name: serialize_api_data(getattr(value, field_name))
            for field_name in getattr(value, "__dataclass_fields__", {})
        }
    if isinstance(value, list):
        return [serialize_api_data(item) for item in value]
    if isinstance(value, tuple):
        return [serialize_api_data(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize_api_data(item) for key, item in value.items()}
    return value


def json_data(data: Any = None, message: Optional[str] = None, status_code: int = 200):
    payload = {"data": {} if data is None else serialize_api_data(data)}
    if message is not None:
        payload["message"] = message
    response = jsonify(payload)
    if status_code == 200:
        return response
    return response, status_code


def json_problem(problem: ApiProblem):
    response = jsonify(problem.to_problem())
    return response, problem.status_code


def json_request_data(message: str = "Request body must be a JSON object.") -> Dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationProblem(message, slug="request-body-must-be-json-object")
    return data
