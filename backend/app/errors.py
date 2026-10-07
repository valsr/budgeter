class DomainError(Exception):
    """Base class for business-rule violations raised by the service layer."""


class NotFoundError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class ConflictError(DomainError):
    """The request is well-formed but clashes with current state (a taken
    username, removing the last admin)."""


class AuthError(DomainError):
    """Credentials were rejected, or the action isn't open to the caller."""
