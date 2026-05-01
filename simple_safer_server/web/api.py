from typing import Any, Dict, Tuple

from flask import jsonify, request


def json_success(**payload: Any):
    response = {"success": True}
    response.update(payload)
    return jsonify(response)


def json_error(message: str, status_code: int = 200, key: str = "error"):
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
    if not isinstance(data, dict) or not data:
        return {}, json_error(message, status_code=400, key="message")
    return data, None
