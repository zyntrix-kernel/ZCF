"""
Runtime Adapter Interface for ZCF.
Defines the versioned contract for integrating compatibility engines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from zcf.core.models import (
    ApplicationDescription,
    EnvironmentReport,
    ExecutionResult,
    ValidationResult,
)


class RuntimeAdapterInterface(ABC):
    """Abstract base class for all ZCF runtime adapters."""

    @abstractmethod
    def get_id(self) -> str:
        """Returns the stable unique identifier for this runtime adapter."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Returns the human-readable display name."""
        pass

    @abstractmethod
    def is_available(self, env: EnvironmentReport) -> bool:
        """Checks if the required runtime binaries and dependencies are present in the environment."""
        pass

    @abstractmethod
    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        """Validates whether this adapter can execute the specific target application on this host."""
        pass

    @abstractmethod
    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Prepares isolated filesystem paths, environment variables, and prefixes before execution."""
        pass

    @abstractmethod
    def execute(
        self,
        app: ApplicationDescription,
        context: Dict[str, Any],
        args: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Executes the application within the prepared context and captures execution diagnostics."""
        pass
