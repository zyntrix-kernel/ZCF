# Runtime Adapter Authoring Guide for ZCF

**Document:** `docs/ADAPTER_AUTHORING.md`  
**Target Audience:** Core Contributors, Compatibility Engineers, External Runtime Authors  
**Framework Version:** `v0.2.0`  

---

## 1. Overview

The **Zyntrix Compatibility Fabric (ZCF)** is designed as an extensible, modular coordination platform. Adapters translate an application's requirements into concrete environment preparation, process sandboxing, and execution commands.

Rather than hardcoding compatibility tools, ZCF defines a formal adapter interface in `zcf.runtimes.base.BaseRuntimeAdapter`. Every adapter—whether for Wine, Proton, QEMU, Box64, Waydroid, or future translation layers (e.g. FEX-Emu, Darling, Rosetta on Linux)—must implement this contract.

---

## 2. Adapter Architecture & Contract

Each adapter is an implementation of `BaseRuntimeAdapter` (or `RuntimeAdapterInterface`):

```python
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
from zcf.runtimes.base import BaseRuntimeAdapter

class CustomAdapter(BaseRuntimeAdapter):
    def get_id(self) -> str:
        """Returns unique stable identifier, e.g. 'runtime.custom'."""
        return "runtime.custom"

    def get_name(self) -> str:
        """Returns human-readable display name."""
        return "Custom Translation Engine"

    def get_version(self, env: Optional[EnvironmentReport] = None) -> Optional[str]:
        """Returns the installed engine version string."""
        return "1.0.0"

    def get_capabilities(self) -> Dict[str, Any]:
        """Declares supported formats, architectures, workloads, and requirements."""
        return {
            "supported_formats": [BinaryFormat.ELF.value],
            "supported_architectures": [Architecture.X86_64.value],
            "supported_workloads": [WorkloadType.DESKTOP_GUI.value, WorkloadType.CLI_TOOL.value],
            "requires_vulkan": False,
            "requires_wayland": False,
            "supports_sandboxing": True,
            "supports_virtual_display": True,
            "isolation_features": ["bubblewrap"],
            "known_limitations": ["Requires 64-bit host kernel."],
        }

    def is_available(self, env: EnvironmentReport) -> bool:
        """Checks if the required runtime binary is installed and operational."""
        return True

    def check_prerequisites(self, app: ApplicationDescription, env: EnvironmentReport) -> List[str]:
        """Returns any missing prerequisites before execution."""
        return []

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        """Validates target binary suitability."""
        errors = []
        if app.format != BinaryFormat.ELF:
            errors.append("Target must be an ELF binary.")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Prepares environment variables, prefixes, and working directories."""
        return {
            "environment_variables": os.environ.copy(),
            "working_directory": os.path.dirname(os.path.abspath(app.artifact_path)),
        }

    def build_command(
        self, app: ApplicationDescription, context: Dict[str, Any], args: Optional[List[str]] = None
    ) -> List[str]:
        """Constructs safe argument array for process execution."""
        return ["custom-engine", app.artifact_path] + (args or [])
```

---

## 3. Registration Lifecycle

Adapters are registered with the `RuntimeRegistry` in `src/zcf/runtimes/registry.py`:

```python
from zcf.runtimes.registry import RuntimeRegistry
from my_extension import CustomAdapter

registry = RuntimeRegistry()
registry.register(CustomAdapter())
```

Once registered, the `CompatibilityPlanner` automatically discovers the adapter, validates target binaries against its declared capabilities, and considers it during confidence scoring.

---

## 4. Best Practices

1. **Structured Commands:** Always return a `List[str]` in `build_command`. Never concatenate shell strings.
2. **Environment Isolation:** Do not mutate `os.environ` directly. Return modified environment dictionaries in `prepare_environment`.
3. **Idempotent Cleanup:** Ensure `cleanup(app, context)` safely terminates child background servers and removes ephemeral files without removing persistent user data.
