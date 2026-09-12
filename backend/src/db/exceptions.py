"""Database layer exceptions."""

class RepositoryError(Exception):
    """Base exception for all repository-level errors."""

class DuplicateResourceError(RepositoryError):
    """Raised when an insert violates a unique constraint."""

class ReferenceError(RepositoryError):
    """Raised when an insert/update violates a foreign key constraint."""
