class RepositoryError(Exception):
    """Base exception for repository layer errors."""
    pass


class InventoryNotFoundError(RepositoryError):
    """Raised when a requested inventory_calendar record is not found."""
    pass


class InsufficientInventoryError(RepositoryError):
    """Raised when available units (total - booked - held) are insufficient."""
    pass


class RepositoryConflictError(RepositoryError):
    """Raised when a unique constraint or idempotency conflict occurs."""
    pass


class HoldNotFoundError(RepositoryError):
    """Raised when a requested hold record is not found."""
    pass


class HoldStatusError(RepositoryError):
    """Raised when an operation is invalid for the hold's current status."""
    pass


class HoldExpiredError(HoldStatusError):
    """Raised when an operation is attempted on an expired hold."""
    pass


class HoldNotActiveError(HoldStatusError):
    """Raised when an operation requires an active hold but status is different."""
    pass


class BookingNotFoundError(RepositoryError):
    """Raised when a requested booking record is not found."""
    pass


class PaymentFailedError(RepositoryError):
    """Raised when payment authorization or capture fails."""
    pass


class IdempotencyPayloadConflictError(RepositoryConflictError):
    """Raised when an idempotency key is reused with a conflicting payload."""
    pass

