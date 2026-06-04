from dataclasses import dataclass, field
from typing import Any

from flask import g, jsonify
from werkzeug.exceptions import HTTPException


@dataclass
class APIError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def error_payload(status_code: int, code: str, message: str, details: dict | None = None) -> dict:
    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(g, "request_id", None),
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload


def register_error_handlers(app) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(error: APIError):
        return jsonify(error_payload(error.status_code, error.code, error.message, error.details)), error.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return (
            jsonify(error_payload(error.code or 500, error.name.lower().replace(" ", "_"), error.description)),
            error.code or 500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        app.logger.exception("Unhandled request failure")
        return (
            jsonify(error_payload(500, "internal_server_error", "An unexpected server error occurred.")),
            500,
        )
