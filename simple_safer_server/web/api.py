from typing import Any, Dict, Tuple

from flask import jsonify, request


def json_success(**payload: Any):
    response = {"success": True}
    response.update(payload)
    return jsonify(response)


def json_error(message: str, status_code: int = 200, key: str = "error"):
    """Return json_error(message, status_code, key) using the existing Flask shape.

    A 200 status_code returns a bare Response; any other status returns
    (Response, status_code), matching callers that distinguish application
    errors from HTTP errors.
    """
    payload = {"success": False, key: message}
    response = jsonify(payload)
    if status_code == 200:
        return response
    return response, status_code


def json_payload_or_error(
    message: str = "Request body must be a JSON object.",
) -> Tuple[Dict[str, Any], Any]:
    """Return a JSON object or a ready Flask error response for malformed bodies."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {}, json_error(message, status_code=400, key="message")
    return data, None


def service_json_response(payload: Dict[str, Any], failure_status: int = 500):
    """Return a service result with a predictable status based on its success flag."""
    if payload.get("success"):
        return jsonify(payload)
    return jsonify(payload), failure_status
