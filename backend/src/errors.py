"""Typed application exceptions shared by backend services and API handlers."""

from __future__ import annotations


class BackendError(Exception):
    """Base class for expected backend failures."""

    status_code = 500
    error_code = "service_error"


class ResourceNotFoundError(BackendError):
    status_code = 404
    error_code = "not_found"


class ResourceConflictError(BackendError):
    status_code = 409
    error_code = "resource_conflict"


class InvalidStateTransitionError(ResourceConflictError):
    error_code = "invalid_state_transition"


class ConfigurationValidationError(BackendError):
    status_code = 400
    error_code = "configuration_validation_error"

    def __init__(self, message: str, field_errors: list[dict[str, object]] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or []
