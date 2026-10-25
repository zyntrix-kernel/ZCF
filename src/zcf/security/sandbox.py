"""
Sandbox and Process Isolation Manager for ZCF.
Provides unprivileged containerization via Bubblewrap (bwrap), namespace isolation, and strict mount validation.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from zcf.core.exceptions import SecurityViolationError


FORBIDDEN_WRITABLE_ROOTS = (
    "/",
    "/bin",
    "/sbin",
    "/usr",
    "/lib",
    "/lib64",
    "/etc",
    "/boot",
    "/root",
    "/sys",
    "/proc",
    "/dev",
    "/run",
    "/var",
    "/opt",
    "/media",
    "/mnt",
    "/srv",
)


def _sanitize_path_for_error(raw_path: str, canonical_path: str) -> str:
    """Produces an actionable diagnostic label for rejected paths without leaking private host details."""
    norm = os.path.normpath(canonical_path)
    for root in ("/etc", "/boot", "/usr", "/lib", "/lib64", "/bin", "/sbin", "/sys", "/proc", "/dev", "/run", "/var", "/root", "/opt"):
        if norm == root or norm.startswith(root + os.sep) or norm.startswith(root + "/"):
            parts = [p for p in norm.split(os.sep) if p]
            return f"{root}/{parts[-1]}" if len(parts) > 1 and f"/{parts[0]}" == root else root

    try:
        home = os.path.normpath(os.path.expanduser("~"))
        if norm == home:
            return "<user_home_root>"
        if norm.startswith(home + os.sep):
            rel = os.path.relpath(norm, home)
            first = rel.split(os.sep)[0]
            return f"~/{first}"
    except Exception:
        pass

    if os.name == "nt":
        drive, rest = os.path.splitdrive(norm)
        if rest in ("\\", "/", ""):
            return f"{drive}\\<drive_root>"
        parts = [p for p in rest.split(os.sep) if p]
        if parts and parts[0].lower() in ("windows", "program files", "program files (x86)", "users"):
            return f"{drive}\\{parts[0]}"

    base = os.path.basename(norm)
    return base or "root_filesystem"


def validate_writable_mount(
    mount_path: str,
    allowed_prefix_roots: Optional[List[str]] = None,
) -> str:
    """
    Validates that a candidate writable mount path does not escape sandbox bounds,
    resolve to a sensitive host directory, or bypass restrictions via symlinks or traversal.
    Returns the canonicalized absolute path.
    """
    if not mount_path or not str(mount_path).strip():
        raise SecurityViolationError("Writable sandbox mount rejected: empty mount path.")

    # 1. Reject paths containing embedded control characters or newlines
    raw_str = str(mount_path)
    if any(ord(c) < 32 for c in raw_str if c != "\t"):
        raise SecurityViolationError("Writable sandbox mount rejected: path contains invalid control characters.")

    # 1b. Reject relative traversal ('..' components in raw input path)
    raw_parts = [p for p in raw_str.replace("/", os.sep).replace("\\", os.sep).split(os.sep) if p]
    if ".." in raw_parts:
        raise SecurityViolationError("Writable sandbox mount rejected: relative traversal ('..') is strictly prohibited.")

    # 1c. Safe canonicalization accounting for existing symlink ancestors
    abs_path = os.path.abspath(raw_str)
    curr = abs_path
    unresolved_tail: List[str] = []
    while curr and not os.path.exists(curr):
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        unresolved_tail.insert(0, os.path.basename(curr))
        curr = parent

    real_ancestor = os.path.realpath(curr) if curr and os.path.exists(curr) else os.path.realpath(abs_path)
    if unresolved_tail:
        canonical = os.path.join(real_ancestor, *unresolved_tail)
    else:
        canonical = real_ancestor
    norm = os.path.normpath(canonical)

    # 2. Check root filesystem
    if norm in ("/", "\\") or (os.name == "nt" and len(norm) <= 3 and norm.endswith(":\\")):
        sanitized = _sanitize_path_for_error(raw_str, canonical)
        raise SecurityViolationError(f"Writable sandbox mount rejected: '{sanitized}' is the root filesystem.")

    # 3. Check forbidden sensitive system roots
    for forbidden in FORBIDDEN_WRITABLE_ROOTS:
        forbidden_norm = os.path.normpath(forbidden)
        if norm == forbidden_norm or norm.startswith(forbidden_norm + os.sep) or norm.startswith(forbidden_norm + "/"):
            sanitized = _sanitize_path_for_error(raw_str, canonical)
            raise SecurityViolationError(
                f"Writable sandbox mount rejected: '{sanitized}' targets a sensitive system directory."
            )

    # 4. Check Windows sensitive system roots
    if os.name == "nt":
        sys_root = os.environ.get("SystemRoot", "C:\\Windows")
        sys_norm = os.path.normpath(sys_root).lower()
        if norm.lower() == sys_norm or norm.lower().startswith(sys_norm + os.sep):
            sanitized = _sanitize_path_for_error(raw_str, canonical)
            raise SecurityViolationError(
                f"Writable sandbox mount rejected: '{sanitized}' targets a sensitive system directory."
            )

    # 5. Check user home root & sensitive user directories
    try:
        home_norm = os.path.normpath(os.path.expanduser("~"))
        if norm == home_norm:
            raise SecurityViolationError(
                "Writable sandbox mount rejected: user home root directory cannot be mounted writable directly."
            )
        for sensitive_sub in (".ssh", ".gnupg", ".pki"):
            sub_norm = os.path.normpath(os.path.join(home_norm, sensitive_sub))
            if norm == sub_norm or norm.startswith(sub_norm + os.sep):
                sanitized = _sanitize_path_for_error(raw_str, canonical)
                raise SecurityViolationError(
                    f"Writable sandbox mount rejected: '{sanitized}' targets a private credential directory."
                )
    except Exception as e:
        if isinstance(e, SecurityViolationError):
            raise

    # 6. Containment check within approved prefix roots (if specified)
    if allowed_prefix_roots:
        resolved_roots = [os.path.realpath(os.path.abspath(r)) for r in allowed_prefix_roots if r]
        within_allowed = any(
            norm == r or norm.startswith(r + os.sep) or norm.startswith(r + "/")
            for r in resolved_roots
        )
        if not within_allowed:
            sanitized = _sanitize_path_for_error(raw_str, canonical)
            raise SecurityViolationError(
                f"Writable sandbox mount rejected: '{sanitized}' escapes approved application prefix storage roots."
            )

    return canonical


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
    prefix_path: Optional[str] = None
    allowed_prefix_roots: List[str] = field(default_factory=list)
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
                    "strict_mount_validation",
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
        Strictly validates all writable mount paths against path traversal, symlink escapes,
        and sensitive system directories.
        """
        if not self.has_bwrap:
            if not allow_unconfined:
                raise SecurityViolationError(
                    "Sandboxing is required by policy, but Bubblewrap ('bwrap') is not available on this host. "
                    "Aborting execution to prevent unconfined host access."
                )
            return command

        pol = policy or SandboxPolicy()
        wrapped = [self.bwrap_bin]
        ro_targets: List[str] = []

        # 1. Read-only standard system directories
        if pol.read_only_root:
            for sys_dir in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc"):
                if os.path.exists(sys_dir):
                    canonical_sys = os.path.realpath(sys_dir)
                    if canonical_sys not in ro_targets:
                        ro_targets.append(canonical_sys)
                    wrapped.extend(["--ro-bind", sys_dir, sys_dir])

        # 2. Essential virtual filesystems
        wrapped.extend(["--proc", "/proc", "--dev", "/dev"])

        # 3. Disposable tmpfs or bound /tmp
        if pol.disposable_tmp:
            wrapped.extend(["--tmpfs", "/tmp"])
        elif os.path.exists("/tmp"):
            wrapped.extend(["--bind", "/tmp", "/tmp"])

        # 4. Network isolation
        if pol.isolate_network:
            wrapped.append("--unshare-net")

        # 5. Isolated user/PID namespaces
        wrapped.extend(["--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts"])

        # 6. Bind application working directory (read-only by default)
        if os.path.exists(working_dir):
            canonical_wd = os.path.realpath(working_dir)
            if pol.read_only_app:
                if canonical_wd not in ro_targets:
                    ro_targets.append(canonical_wd)
                wrapped.extend(["--ro-bind", working_dir, working_dir])
            else:
                validated_wd = validate_writable_mount(working_dir, pol.allowed_prefix_roots)
                wrapped.extend(["--bind", validated_wd, validated_wd])

        # 7. Graphical display integration: narrowly permitted tokens/sockets, never entire /run or /tmp
        if pol.enable_x11:
            if os.path.exists("/tmp/.X11-unix"):
                wrapped.extend(["--ro-bind", "/tmp/.X11-unix", "/tmp/.X11-unix"])
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

        # 8. Extra read-only mounts (e.g. font configs, certificates)
        for ro_path in pol.ro_bind_mounts:
            if ro_path and os.path.exists(ro_path):
                canonical_ro = os.path.realpath(ro_path)
                if canonical_ro not in ro_targets:
                    ro_targets.append(canonical_ro)
                if canonical_ro not in wrapped:
                    wrapped.extend(["--ro-bind", canonical_ro, canonical_ro])

        # 9. Application Prefix Mount (strictly validated)
        validated_writable_mounts: List[str] = []
        if pol.prefix_path:
            if os.path.exists(pol.prefix_path):
                canonical_prefix = validate_writable_mount(pol.prefix_path, pol.allowed_prefix_roots)
                validated_writable_mounts.append(canonical_prefix)

        # 10. Additional Writable Mounts (strictly validated)
        for extra_bind in pol.bind_mounts:
            if not extra_bind:
                continue
            canonical_extra = validate_writable_mount(extra_bind, pol.allowed_prefix_roots)
            if canonical_extra not in validated_writable_mounts:
                validated_writable_mounts.append(canonical_extra)

        # 11. Conflict check: ensure no writable mount targets or aliases an already read-only mount
        for w_mount in validated_writable_mounts:
            norm_w = os.path.normpath(w_mount)
            for ro_m in ro_targets:
                norm_ro = os.path.normpath(ro_m)
                if norm_w == norm_ro:
                    raise SecurityViolationError(
                        f"Conflicting mount configuration: '{w_mount}' is mounted read-only and cannot be mounted writable."
                    )
            wrapped.extend(["--bind", w_mount, w_mount])

        wrapped.extend(["--chdir", working_dir])
        wrapped.append("--")
        wrapped.extend(command)
        return wrapped
