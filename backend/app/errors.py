class DomainError(Exception):
    """Base class for business-rule violations raised by the service layer."""


class NotFoundError(DomainError):
    pass


class ValidationError(DomainError):
    pass
