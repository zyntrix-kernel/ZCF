"""
Custom exception hierarchy for ZCF.
"""


class ZCFError(Exception):
    """Base exception for all ZCF runtime and operational errors."""
    pass


class InspectionError(ZCFError):
    """Raised when application or artifact inspection fails."""
    pass


class UnsupportedFormatError(InspectionError):
    """Raised when an inspected binary has an unsupported or corrupted format."""
    pass


class EnvironmentError(ZCFError):
    """Raised when environment inspection fails."""
    pass


class PlanningError(ZCFError):
    """Raised when compatibility planning encounters an unresolvable contradiction."""
    pass


class ExecutionError(ZCFError):
    """Raised when a runtime execution or test fails."""
    pass


class SecurityViolationError(ZCFError):
    """Raised when an execution violates sandboxing or security boundaries."""
    pass


class DatabaseError(ZCFError):
    """Raised when compatibility database validation or access fails."""
    pass
