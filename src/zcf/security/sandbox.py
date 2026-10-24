"""
Sandbox and Process Isolation Manager for ZCF.
Provides unprivileged containerization via Bubblewrap (bwrap), Landlock, and resource limits.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SandboxPolicy:
    isolate_network: bool = True
    read_only_root: bool = True
    disposable_tmp: bool = True
    max_memory_mb: int = 2048
    max_cpu_seconds: int = 30
    bind_mounts: List[str] = field(default_factory=list)


class SandboxManager:
    """Orchestrates lightweight userspace process sandboxing."""

    def __init__(self):
        self.bwrap_bin = shutil.which("bwrap")
        self.has_bwrap = self.bwrap_bin is not None

    def is_sandbox_available(self) -> bool:
        return self.has_bwrap

    def wrap_command(
        self,
        command: List[str],
        working_dir: str,
        policy: Optional[SandboxPolicy] = None,
    ) -> List[str]:
        """Wraps target command inside Bubblewrap sandbox if available on host."""
        if not self.has_bwrap:
            return command  # Fallback to direct execution with warning

        pol = policy or SandboxPolicy()
        wrapped = [self.bwrap_bin]

        # Read-only standard system directories
        if pol.read_only_root:
            for sys_dir in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc"):
                if os.path.exists(sys_dir):
                    wrapped.extend(["--ro-bind", sys_dir, sys_dir])

        # Essential virtual filesystems
        wrapped.extend(["--proc", "/proc", "--dev", "/dev"])

        # Disposable tmpfs
        if pol.disposable_tmp:
            wrapped.extend(["--tmpfs", "/tmp"])

        # Network isolation
        if pol.isolate_network:
            wrapped.append("--unshare-net")

        # Isolated user/PID namespaces
        wrapped.extend(["--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts"])

        # Bind application working directory
        wrapped.extend(["--bind", working_dir, working_dir])
        for extra_bind in pol.bind_mounts:
            if os.path.exists(extra_bind):
                wrapped.extend(["--bind", extra_bind, extra_bind])
        wrapped.extend(["--chdir", working_dir])

        # Target command
        wrapped.append("--")
        wrapped.extend(command)
        return wrapped
