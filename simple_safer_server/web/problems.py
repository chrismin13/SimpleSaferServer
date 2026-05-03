from typing import Any, Dict, Optional

PROBLEM_DOCS_URL = "https://github.com/chrismin13/SimpleSaferServer/blob/main/docs/api_responses.md"


class ApiProblem(Exception):
    """Exception that can be rendered as an RFC 9457 Problem Details response."""

    status_code = 500
    title = "Operation failed"
    slug = "operation-failed"

    def __init__(
        self,
        detail: str,
        status_code: Optional[int] = None,
        title: Optional[str] = None,
        slug: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if title is not None:
            self.title = title
        if slug is not None:
            self.slug = slug
        self.extra = extra or {}

    @property
    def type_uri(self) -> str:
        return f"{PROBLEM_DOCS_URL}#{self.slug}"

    def to_problem(self) -> Dict[str, Any]:
        payload = {
            "type": self.type_uri,
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
        }
        payload.update(self.extra)
        return payload


class ValidationProblem(ApiProblem):
    status_code = 400
    title = "Validation error"
    slug = "validation-error"


class UnauthorizedProblem(ApiProblem):
    status_code = 401
    title = "Unauthorized"
    slug = "unauthorized"


class ForbiddenProblem(ApiProblem):
    status_code = 403
    title = "Forbidden"
    slug = "forbidden"


class NotFoundProblem(ApiProblem):
    status_code = 404
    title = "Not found"
    slug = "not-found"


class ConflictProblem(ApiProblem):
    status_code = 409
    title = "Conflict"
    slug = "conflict"


class OperationProblem(ApiProblem):
    status_code = 500
    title = "Operation failed"
    slug = "operation-failed"


class UnavailableProblem(ApiProblem):
    status_code = 503
    title = "Service unavailable"
    slug = "service-unavailable"
