"""
Security and Execution Controller for ZCF.
Enforces non-root execution, path validation, argument sanitization, desktop environment minimization, and sandboxing bounds.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set

from zcf.core.exceptions import SecurityViolationError
from zcf.core.models import ApplicationDescription, ExecutionSecurityPolicy, WorkloadType


class SecurityController:
    """Safeguards the host system from unauthorized or destructive binary operations."""

    ALLOWLIST_DESKTOP_VARS: Set[str] = {
        # Core system & shell
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_MESSAGES",
        "USER",
        "LOGNAME",
        "HOME",
        "SHELL",
        "TERM",
        "PWD",
        # Graphical display servers
        "DISPLAY",
        "XAUTHORITY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "XDG_SESSION_TYPE",
        "GDK_BACKEND",
        "QT_QPA_PLATFORM",
        # Audio & IPC
        "DBUS_SESSION_BUS_ADDRESS",
        "PULSE_SERVER",
        "PIPEWIRE_RUNTIME_DIR",
        "ALSA_CARD",
        # GPU, Vulkan, & OpenGL
        "VK_ICD_FILENAMES",
        "VK_LAYER_PATH",
        "MESA_LOADER_DRIVER_OVERRIDE",
        "LIBGL_ALWAYS_SOFTWARE",
        "DRI_PRIME",
        "__NV_PRIME_RENDER_OFFLOAD",
        "__GLX_VENDOR_LIBRARY_NAME",
        # Compatibility engines
        "WINEPREFIX",
        "WINEDEBUG",
        "WINEDLLOVERRIDES",
        "WINEARCH",
        "STEAM_COMPAT_CLIENT_INSTALL_PATH",
        "STEAM_COMPAT_DATA_PATH",
        "PROTON_USE_WINED3D",
        "BOX64_DYNAREC",
        "BOX64_SHOWSEGV",
        "BOX64_LOG",
        "QEMU_LD_PREFIX",
        "WAYDROID_SESSION",
        "ZCF_NON_INTERACTIVE",
    }

    SENSITIVE_KEY_PATTERNS = (
        "TOKEN",
        "KEY",
        "SECRET",
        "PASSWORD",
        "PASSWD",
        "AUTHORIZATION",
        "AUTH_TOKEN",
        "CREDENTIAL",
        "PRIVATE",
        "SSH_",
        "AWS_",
        "GITHUB_",
    )

    def __init__(self, allow_root: bool = False, max_timeout_seconds: int = 60):
        self.allow_root = allow_root
        self.max_timeout_seconds = max_timeout_seconds

    def validate_execution_safety(self, artifact_path: str, args: Optional[List[str]] = None):
        """Enforces path safety, non-root constraints, and argument integrity."""
        # 1. Path Safety & Traversal Prevention
        real_path = os.path.realpath(artifact_path)
        if not os.path.exists(real_path):
            raise SecurityViolationError(f"Target path does not exist: {artifact_path}")

        # Block direct execution of critical host system binaries as untrusted targets
        forbidden_targets = (
            "/etc/shadow",
            "/etc/passwd",
            "/boot",
            "/proc",
            "/sys",
            "C:\\Windows\\System32\\ntoskrnl.exe",
        )
        for forbidden in forbidden_targets:
            if real_path.startswith(forbidden):
                raise SecurityViolationError(f"Execution of critical system file is forbidden: {real_path}")

        # 2. Non-Root Execution Enforcement
        if not self.allow_root and hasattr(os, "geteuid"):
            if os.geteuid() == 0:
                raise SecurityViolationError(
                    "Running compatibility orchestration as root is strictly prohibited for security. "
                    "Execute as a non-privileged user."
                )

        # 3. Argument Sanitization
        if args:
            for arg in args:
                if any(char in arg for char in (";", "&&", "||", "`", "$(", "\n", "\r")):
                    raise SecurityViolationError(f"Command injection character detected in argument: {arg}")

    def sanitize_env_vars(self, env_vars: Dict[str, str], mode: str = "minimized_desktop") -> Dict[str, str]:
        """
        Filters host credentials and tokens from application process environment.
        Modes:
        - 'filter_secrets': strips all sensitive credentials/tokens and preserves app/user variables.
        - 'minimized_desktop': strips sensitive credentials, restricts to ALLOWLIST_DESKTOP_VARS and compatibility/app prefixes.
        - 'strict_allowlist': strips sensitive credentials, strictly restricts to ALLOWLIST_DESKTOP_VARS and core ZCF/WINE keys.
        """
        valid_modes = {"filter_secrets", "minimized_desktop", "strict_allowlist"}
        if mode not in valid_modes:
            raise ValueError(f"Unknown environment sanitization mode: '{mode}'. Valid modes are: {sorted(valid_modes)}")

        sanitized: Dict[str, str] = {}
        for k, v in env_vars.items():
            upper_k = k.upper()

            # Explicit desktop display exception: XAUTHORITY is required for X11 authentication
            if k == "XAUTHORITY":
                sanitized[k] = v
                continue

            # Always reject sensitive credentials and keys
            if any(pattern in upper_k for pattern in self.SENSITIVE_KEY_PATTERNS):
                continue

            if mode == "strict_allowlist":
                if k in self.ALLOWLIST_DESKTOP_VARS or k.startswith("ZCF_") or k.startswith("WINE"):
                    sanitized[k] = v
            elif mode == "minimized_desktop":
                allowed_prefixes = ("ZCF_", "WINE", "PROTON_", "BOX64_", "QEMU_", "WAYDROID_", "APP_")
                if k in self.ALLOWLIST_DESKTOP_VARS or any(k.startswith(p) for p in allowed_prefixes):
                    sanitized[k] = v
            else:  # filter_secrets
                sanitized[k] = v

        return sanitized

    def build_execution_policy(
        self, app: ApplicationDescription, use_sandbox: bool = True
    ) -> ExecutionSecurityPolicy:
        """Constructs an observable security policy tailored to the specific workload type."""
        is_game = app.workload_type == WorkloadType.GAME
        is_installer = app.workload_type == WorkloadType.INSTALLER

        policy = ExecutionSecurityPolicy(
            workload_type=app.workload_type,
            isolate_network=not is_game and not is_installer,  # Network open for online games/installers
            read_only_root=True,
            disposable_tmp=not is_installer,
            allow_root=self.allow_root,
            max_memory_mb=4096 if is_game else 2048,
            max_cpu_seconds=None if is_game else 3600,
            writable_paths=[],  # Writable paths are restricted to the isolated prefix
            environment_mode="minimized_desktop",
        )
        return policy
