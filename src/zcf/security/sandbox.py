"""
Sandbox and Process Isolation Manager for ZCF.
Provides unprivileged containerization via Bubblewrap (bwrap), namespace isolation, and resource limits.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SandboxPolicy:
    isolate_network: bool = True
    read_only_root: bool = True
    disposable_tmp: bool = True
    read_only_app: bool = True
    enable_x11: bool = True
    enable_wayland: bool = True
    max_memory_mb: int = 0      # 0 = unconstrained; enforced via POSIX rlimit on Linux
    max_cpu_seconds: int = 0    # 0 = unconstrained; enforced via POSIX rlimit on Linux
    bind_mounts: List[str] = field(default_factory=list)
    ro_bind_mounts: List[str] = field(default_factory=list)


class SandboxManager:
    """Orchestrates lightweight userspace process sandboxing via Bubblewrap."""

    def __init__(self):
        self.bwrap_bin = shutil.which("bwrap")
        self.has_bwrap = self.bwrap_bin is not None

    def is_sandbox_available(self) -> bool:
        return self.has_bwrap

    def get_sandbox_status(self) -> Dict[str, Any]:
        """Returns observable diagnostic status of the sandboxing subsystem."""
        return {
            "backend": "bubblewrap" if self.has_bwrap else "none",
            "available": self.has_bwrap,
            "binary_path": self.bwrap_bin,
            "supported_isolations": (
                [
                    "user_namespace",
                    "pid_namespace",
                    "net_namespace",
                    "ipc_namespace",
                    "ro_bind_mounts",
                    "tmpfs",
                    "x11_xauthority_ro",
                    "wayland_socket_bind",
                ]
                if self.has_bwrap
                else []
            ),
            "resource_enforcement": "posix_rlimit" if os.name != "nt" else "unsupported_on_windows",
        }

    def wrap_command(
        self,
        command: List[str],
        working_dir: str,
        policy: Optional[SandboxPolicy] = None,
        allow_unconfined: bool = False,
    ) -> List[str]:
        """
        Wraps target command inside Bubblewrap sandbox if available on host.
        Fails safely by raising SecurityViolationError if bwrap is missing and allow_unconfined is False.
        """
        if not self.has_bwrap:
            if not allow_unconfined:
                from zcf.core.exceptions import SecurityViolationError
                raise SecurityViolationError(
                    "Sandboxing is required by policy, but Bubblewrap ('bwrap') is not available on this host. "
                    "Aborting execution to prevent unconfined host access."
                )
            return command

        pol = policy or SandboxPolicy()
        wrapped = [self.bwrap_bin]

        # Read-only standard system directories
        if pol.read_only_root:
            for sys_dir in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc"):
                if os.path.exists(sys_dir):
                    wrapped.extend(["--ro-bind", sys_dir, sys_dir])

        # Essential virtual filesystems
        wrapped.extend(["--proc", "/proc", "--dev", "/dev"])

        # Disposable tmpfs or bound /tmp
        if pol.disposable_tmp:
            wrapped.extend(["--tmpfs", "/tmp"])
        elif os.path.exists("/tmp"):
            wrapped.extend(["--bind", "/tmp", "/tmp"])

        # Network isolation
        if pol.isolate_network:
            wrapped.append("--unshare-net")

        # Isolated user/PID namespaces
        wrapped.extend(["--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts"])

        # Bind application working directory (read-only by default unless explicitly granted writable)
        if os.path.exists(working_dir):
            if pol.read_only_app and working_dir not in pol.bind_mounts:
                wrapped.extend(["--ro-bind", working_dir, working_dir])
            else:
                wrapped.extend(["--bind", working_dir, working_dir])

        # Graphical display integration (explicitly restricted to display sockets/tokens, never entire runtime dirs)
        if pol.enable_x11:
            if os.path.exists("/tmp/.X11-unix"):
                wrapped.extend(["--ro-bind", "/tmp/.X11-unix", "/tmp/.X11-unix"])
            # Bind the specific Xauthority file if present
            xauth = os.environ.get("XAUTHORITY") or os.path.expanduser("~/.Xauthority")
            if xauth and os.path.isfile(xauth):
                wrapped.extend(["--ro-bind", xauth, xauth])

        if pol.enable_wayland:
            xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
            if xdg_runtime:
                wayland_display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
                wayland_sock = os.path.join(xdg_runtime, wayland_display)
                if os.path.exists(wayland_sock):
                    wrapped.extend(["--bind", wayland_sock, wayland_sock])

        # Extra read-only mounts (e.g. font configs, certificates)
        for ro_path in pol.ro_bind_mounts:
            if os.path.exists(ro_path) and ro_path not in wrapped:
                wrapped.extend(["--ro-bind", ro_path, ro_path])

        # Bind extra permitted writable locations (e.g. isolated application prefix)
        # Protect against accidental host system exposure: never mount sensitive root directories writable
        forbidden_writable = ("/", "/run", "/var", "/etc", "/usr", "/root", "/boot", "/sys")
        for extra_bind in pol.bind_mounts:
            if os.path.exists(extra_bind) and extra_bind not in forbidden_writable:
                wrapped.extend(["--bind", extra_bind, extra_bind])

        wrapped.extend(["--chdir", working_dir])

        # Target command
        wrapped.append("--")
        wrapped.extend(command)
        return wrapped
