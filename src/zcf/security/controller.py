"""
Security and Execution Controller for ZCF.
Enforces non-root execution, path validation, argument sanitization, and sandboxing bounds.
"""

from __future__ import annotations

import os
from typing import List, Optional

from zcf.core.exceptions import SecurityViolationError


class SecurityController:
    """Safeguards the host system from unauthorized or destructive binary operations."""

    def __init__(self, allow_root: bool = False, max_timeout_seconds: int = 60):
        self.allow_root = allow_root
        self.max_timeout_seconds = max_timeout_seconds

    def validate_execution_safety(self, artifact_path: str, args: Optional[List[str]] = None):
        # 1. Path Safety & Traversal Prevention
        real_path = os.path.realpath(artifact_path)
        if not os.path.exists(real_path):
            raise SecurityViolationError(f"Target path does not exist: {artifact_path}")

        # Block direct execution of critical host system binaries as untrusted targets
        forbidden_targets = ("/etc/shadow", "/etc/passwd", "/boot", "C:\\Windows\\System32\\ntoskrnl.exe")
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
                if any(char in arg for char in (";", "&&", "||", "`", "$(")):
                    raise SecurityViolationError(f"Command injection character detected in argument: {arg}")

    def sanitize_env_vars(self, env_vars: dict) -> dict:
        """Removes sensitive host credentials from application environment."""
        sanitized = env_vars.copy()
        sensitive_keys = ("AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY", "SSH_AUTH_SOCK")
        for key in sensitive_keys:
            sanitized.pop(key, None)
        return sanitized
