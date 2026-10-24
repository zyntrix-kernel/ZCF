"""
Runtime Adapter Interface for ZCF.
Defines the versioned contract for integrating compatibility engines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    EnvironmentReport,
    ExecutionResult,
    ValidationResult,
    WorkloadType,
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

    def get_version(self, env: Optional[EnvironmentReport] = None) -> Optional[str]:
        """Returns the installed version string of this compatibility engine if available."""
        return None

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Returns declared adapter capabilities:
        - supported_formats: List[str]
        - supported_architectures: List[str]
        - supported_workloads: List[str]
        - requires_vulkan: bool
        - requires_wayland: bool
        - supports_sandboxing: bool
        - supports_virtual_display: bool
        - isolation_features: List[str]
        - known_limitations: List[str]
        """
        return {
            "supported_formats": [],
            "supported_architectures": [],
            "supported_workloads": [w.value for w in WorkloadType],
            "requires_vulkan": False,
            "requires_wayland": False,
            "supports_sandboxing": True,
            "supports_virtual_display": True,
            "isolation_features": ["filesystem", "environment"],
            "known_limitations": [],
        }

    @abstractmethod
    def is_available(self, env: EnvironmentReport) -> bool:
        """Checks if the required runtime binaries and dependencies are present in the environment."""
        pass

    def check_prerequisites(self, app: ApplicationDescription, env: EnvironmentReport) -> List[str]:
        """Returns a list of missing prerequisites before validation or execution."""
        missing: List[str] = []
        if not self.is_available(env):
            missing.append(f"Engine binary for '{self.get_name()}' is not installed or discoverable.")
        return missing

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

    def build_command(
        self, app: ApplicationDescription, context: Dict[str, Any], args: Optional[List[str]] = None
    ) -> List[str]:
        """
        Constructs the exact command line invocation array for this application and runtime.
        Structured arrays prevent shell injection vulnerabilities.
        """
        return [app.artifact_path] + (args or [])

    @abstractmethod
    def execute(
        self,
        app: ApplicationDescription,
        context: Dict[str, Any],
        args: Optional[List[str]] = None,
        dry_run: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Executes the application within the prepared context and captures execution diagnostics."""
        pass

    def cleanup(self, app: ApplicationDescription, context: Dict[str, Any]) -> None:
        """Cleans up ephemeral resources, locks, or child background servers."""
        pass


class BaseRuntimeAdapter(RuntimeAdapterInterface):
    """Convenience base class providing standardized process execution and lifecycle management."""

    def _execute_process(
        self,
        cmd: List[str],
        context: Dict[str, Any],
        dry_run: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        if dry_run:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[Dry Run] Validated execution plan for {self.get_name()}:\nCommand: {' '.join(cmd)}",
                stderr="",
                execution_time_seconds=0.0,
                command=cmd,
                isolated_env_path=context.get("prefix_path"),
                effective_runtime=self.get_id(),
            )

        start_time = time.time()
        env_vars = context.get("environment_variables", os.environ.copy())
        working_dir = context.get("working_directory", os.path.dirname(cmd[-1]) if cmd else None)

        captured_stdout: List[str] = []
        captured_stderr: List[str] = []
        exit_code = 0

        try:
            process = subprocess.Popen(
                cmd,
                env=env_vars,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Stream stdout if callback provided
            if stream_callback and process.stdout:
                for line in process.stdout:
                    stream_callback(line)
                    captured_stdout.append(line)
                stdout_tail, stderr_out = process.communicate(timeout=timeout)
                if stdout_tail:
                    captured_stdout.append(stdout_tail)
                if stderr_out:
                    captured_stderr.append(stderr_out)
            else:
                out, err = process.communicate(timeout=timeout)
                if out:
                    captured_stdout.append(out)
                if err:
                    captured_stderr.append(err)

            exit_code = process.returncode

        except subprocess.TimeoutExpired:
            process.kill()
            captured_stderr.append(f"\n[ZCF] Process exceeded timeout limit of {timeout} seconds.")
            exit_code = 124
        except Exception as e:
            captured_stderr.append(f"\n[ZCF] Subprocess execution error: {str(e)}")
            exit_code = 1

        elapsed = time.time() - start_time
        return ExecutionResult(
            success=exit_code == 0,
            exit_code=exit_code,
            stdout="".join(captured_stdout),
            stderr="".join(captured_stderr),
            execution_time_seconds=elapsed,
            command=cmd,
            isolated_env_path=context.get("prefix_path"),
            effective_runtime=self.get_id(),
        )
