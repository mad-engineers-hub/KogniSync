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
