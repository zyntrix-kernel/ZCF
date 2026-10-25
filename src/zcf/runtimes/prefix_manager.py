"""
Wine Prefix and Environment Isolation Manager for ZCF.
Handles prefix creation, cloning, DLL overrides, registry injection, active use detection, and safe disk cleanup.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PrefixMetadata:
    prefix_id: str
    prefix_path: str
    app_name: str = "Unknown Windows Application"
    app_sha256: str = ""
    architecture: str = "win64"
    is_persistent: bool = True  # Durable application data is the safe default
    created_at: str = ""
    last_used_at: str = ""
    size_bytes: int = 0
    size_mb: float = 0.0
    installed_components: List[str] = field(default_factory=list)
    is_locked: bool = False
    metadata_valid: bool = True
    runtime_type: str = "wine"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WinePrefixManager:
    """Manages isolated WINEPREFIX directories, components, active processes, and safe disk maintenance."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = os.path.abspath(os.path.expanduser(base_dir or "~/.zcf/prefixes"))
        self.trash_dir = os.path.abspath(os.path.expanduser("~/.zcf/trash"))
        os.makedirs(self.base_dir, exist_ok=True)

    def get_prefix_path(self, app_id: str) -> str:
        safe_id = "".join(c for c in app_id if c.isalnum() or c in ("-", "_"))[:24]
        return os.path.join(self.base_dir, safe_id)

    def _is_safe_contained_path(self, prefix_path: str) -> bool:
        """Ensures the prefix path is strictly inside base_dir and not a symlink escape."""
        try:
            abs_base = os.path.abspath(os.path.realpath(self.base_dir))
            abs_target = os.path.abspath(os.path.realpath(prefix_path))
            if not abs_target.startswith(abs_base + os.sep):
                return False
            if os.path.islink(prefix_path):
                return False
            return True
        except Exception:
            return False

    def record_usage(
        self,
        prefix_path: str,
        app_name: str,
        app_sha256: str,
        is_persistent: bool = True,
        architecture: str = "win64",
        runtime_type: str = "wine",
    ):
        """
        Records or updates metadata for a prefix on execution.
        Defaults to is_persistent=True to safeguard application and user data.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        meta: Dict[str, Any] = {
            "prefix_id": os.path.basename(prefix_path),
            "prefix_path": prefix_path,
            "app_name": app_name,
            "app_sha256": app_sha256,
            "architecture": architecture,
            "is_persistent": is_persistent,
            "runtime_type": runtime_type,
            "last_used_at": now_iso,
        }

        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, dict):
                    meta["created_at"] = existing.get("created_at", now_iso)
                    meta["installed_components"] = existing.get("installed_components", [])
                    # Do not accidentally overwrite explicit disposable flag if not specified
                    if "is_persistent" in existing and is_persistent is True and existing.get("is_persistent") is False:
                        # Existing was explicitly marked disposable
                        meta["is_persistent"] = False
                else:
                    meta["created_at"] = now_iso
                    meta["installed_components"] = []
            except Exception:
                meta["created_at"] = now_iso
                meta["installed_components"] = []
        else:
            meta["created_at"] = now_iso
            meta["installed_components"] = []

        try:
            temp_file = f"{meta_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            os.replace(temp_file, meta_file)
        except Exception:
            pass

    def initialize_prefix(self, prefix_path: str, is_64bit: bool = True) -> bool:
        """Initializes a new isolated prefix directory."""
        os.makedirs(prefix_path, exist_ok=True)
        env = os.environ.copy()
        env["WINEPREFIX"] = prefix_path
        env["WINEARCH"] = "win64" if is_64bit else "win32"
        env["WINEDEBUG"] = "-all"

        wineboot = shutil.which("wineboot")
        if wineboot:
            try:
                subprocess.run([wineboot, "-i"], env=env, timeout=30, capture_output=True)
                return True
            except Exception:
                return False
        return True

    def set_dll_overrides(self, env_vars: Dict[str, str], overrides: Dict[str, str]) -> Dict[str, str]:
        """
        Sets WINEDLLOVERRIDES string.
        Syntax: "dll1,dll2=n,b;dll3=b" (n=native, b=builtin, d=disabled).
        """
        clauses = []
        for dll, mode in overrides.items():
            dll_clean = dll.removesuffix(".dll")
            clauses.append(f"{dll_clean}={mode}")

        existing = env_vars.get("WINEDLLOVERRIDES", "")
        new_clause = ";".join(clauses)
        if existing:
            env_vars["WINEDLLOVERRIDES"] = f"{existing};{new_clause}"
        else:
            env_vars["WINEDLLOVERRIDES"] = new_clause
        return env_vars

    def is_prefix_in_use(self, prefix_path: str) -> bool:
        """Detects if an active wineserver or application process is currently running in this prefix."""
        # 1. Linux /proc inspection
        if os.path.exists("/proc"):
            try:
                norm_prefix = os.path.realpath(prefix_path)
                for pid_dir in os.listdir("/proc"):
                    if not pid_dir.isdigit():
                        continue
                    environ_file = os.path.join("/proc", pid_dir, "environ")
                    try:
                        with open(environ_file, "rb") as f:
                            raw = f.read()
                            if f"WINEPREFIX={norm_prefix}".encode() in raw:
                                return True
                    except Exception:
                        continue
            except Exception:
                pass

        # 2. Check for active lockfile in prefix
        lock_file = os.path.join(prefix_path, ".zcf.lock")
        if os.path.exists(lock_file):
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    lock_pid = int(f.read().strip())
                # Check if PID is alive
                if os.name != "nt":
                    os.kill(lock_pid, 0)
                    return True
                else:
                    # Windows PID check
                    out = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {lock_pid}"],
                        capture_output=True,
                        text=True,
                    )
                    if str(lock_pid) in out.stdout:
                        return True
            except Exception:
                pass

        # 3. Check for active wineserver socket in /tmp/.wine-<uid>
        uid = os.getuid() if hasattr(os, "getuid") else None
        if uid is not None:
            wine_sock_dir = f"/tmp/.wine-{uid}"
            if os.path.exists(wine_sock_dir):
                for sock in os.listdir(wine_sock_dir):
                    if sock.startswith("server-"):
                        # If wineserver is running, check wineserver process table
                        pass
        return False

    def kill_wineserver(self, prefix_path: str):
        """Terminates wineserver instances running for a specific prefix."""
        wineserver = shutil.which("wineserver")
        if wineserver:
            env = os.environ.copy()
            env["WINEPREFIX"] = prefix_path
            try:
                subprocess.run([wineserver, "-k"], env=env, timeout=5, capture_output=True)
            except Exception:
                pass

    def get_prefix_size_bytes(self, prefix_path: str) -> int:
        """Computes approximate recursive disk size of a prefix directory."""
        total = 0
        try:
            for root, dirs, files in os.walk(prefix_path):
                for f in files:
                    fp = os.path.join(root, f)
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
        except Exception:
            pass
        return total

    def list_prefixes(self) -> List[PrefixMetadata]:
        """Lists all managed prefixes with disk size, architecture, persistence status, and lock status."""
        results: List[PrefixMetadata] = []
        if not os.path.exists(self.base_dir):
            return results

        for entry in os.listdir(self.base_dir):
            full_path = os.path.join(self.base_dir, entry)
            if not os.path.isdir(full_path):
                continue

            meta_file = os.path.join(full_path, "prefix_meta.json")
            meta_data: Dict[str, Any] = {}
            metadata_valid = False

            if os.path.isfile(meta_file):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        meta_data = data
                        metadata_valid = True
                except Exception:
                    metadata_valid = False

            size_b = self.get_prefix_size_bytes(full_path)
            locked = self.is_prefix_in_use(full_path)

            stat = os.stat(full_path)
            mtime_iso = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc).isoformat()

            # SAFE DEFAULT: If metadata is missing or corrupted, prefix is ALWAYS persistent!
            # It may only be disposable if valid metadata explicitly sets is_persistent to False.
            if metadata_valid and "is_persistent" in meta_data:
                is_persistent = bool(meta_data.get("is_persistent", True))
            else:
                is_persistent = True

            results.append(
                PrefixMetadata(
                    prefix_id=entry,
                    prefix_path=full_path,
                    app_name=meta_data.get("app_name", f"Prefix ({entry})"),
                    app_sha256=meta_data.get("app_sha256", ""),
                    architecture=meta_data.get("architecture", "win64"),
                    is_persistent=is_persistent,
                    created_at=meta_data.get("created_at", mtime_iso),
                    last_used_at=meta_data.get("last_used_at", mtime_iso),
                    size_bytes=size_b,
                    size_mb=round(size_b / (1024 * 1024), 2),
                    installed_components=meta_data.get("installed_components", []),
                    is_locked=locked,
                    metadata_valid=metadata_valid,
                    runtime_type=meta_data.get("runtime_type", "wine"),
                )
            )
        return results

    def is_eligible_for_cleanup(
        self,
        prefix_path: str,
        max_age_days: int = 14,
        include_disposable_only: bool = True,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether a prefix directory is strictly eligible for deletion.
        Shared contract used by both preview_cleanup and cleanup_prefix.
        """
        if not self._is_safe_contained_path(prefix_path):
            return False, "Path is not safely contained within prefix base directory"

        if not os.path.isdir(prefix_path):
            return False, "Prefix directory does not exist"

        # 1. Process lock check: NEVER delete if active
        if self.is_prefix_in_use(prefix_path):
            return False, "Prefix is currently locked or in use by an active process"

        # 2. Metadata & persistence check
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        if not os.path.isfile(meta_file):
            # Missing metadata -> Ambiguous / unknown policy state -> PRESERVE
            return False, "Metadata missing; persistence state is unknown (preserving user data)"

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
            if not isinstance(meta_data, dict):
                return False, "Metadata is corrupt or non-dict; preserving user data"
        except Exception:
            # Corrupt JSON / unreadable -> PRESERVE
            return False, "Metadata could not be read or parsed; preserving user data"

        is_persistent = meta_data.get("is_persistent", True)
        if include_disposable_only and is_persistent:
            return False, "Prefix is marked persistent"

        # 3. Age check
        cutoff = time.time() - (max_age_days * 86400)
        try:
            stat = os.stat(prefix_path)
            last_used = stat.st_mtime
            if "last_used_at" in meta_data:
                try:
                    dt = datetime.datetime.fromisoformat(meta_data["last_used_at"])
                    last_used = max(last_used, dt.timestamp())
                except Exception:
                    pass
            if last_used >= cutoff:
                return False, "Prefix is newer than maximum stale age cutoff"
        except Exception:
            return False, "Could not determine prefix age"

        return True, "Eligible for cleanup"

    def preview_cleanup(
        self, max_age_days: int = 14, include_disposable_only: bool = True
    ) -> Dict[str, Any]:
        """Previews which prefixes would be deleted, ensuring identical policy to actual cleanup."""
        candidates: List[PrefixMetadata] = []
        skipped_locked: List[str] = []
        skipped_persistent: List[str] = []
        skipped_unverified_metadata: List[str] = []
        reclaimable_bytes = 0

        for prefix in self.list_prefixes():
            eligible, reason = self.is_eligible_for_cleanup(
                prefix.prefix_path,
                max_age_days=max_age_days,
                include_disposable_only=include_disposable_only,
            )
            if eligible:
                candidates.append(prefix)
                reclaimable_bytes += prefix.size_bytes
            else:
                if "locked" in reason.lower() or "active process" in reason.lower():
                    skipped_locked.append(prefix.prefix_id)
                elif "persistent" in reason.lower():
                    skipped_persistent.append(prefix.prefix_id)
                elif "metadata" in reason.lower():
                    skipped_unverified_metadata.append(prefix.prefix_id)

        return {
            "candidates": [c.to_dict() for c in candidates],
            "total_reclaimable_bytes": reclaimable_bytes,
            "total_reclaimable_mb": round(reclaimable_bytes / (1024 * 1024), 2),
            "skipped_locked": skipped_locked,
            "skipped_persistent": skipped_persistent,
            "skipped_unverified_metadata": skipped_unverified_metadata,
        }

    def cleanup_prefix(
        self,
        prefix_path: str,
        max_age_days: Optional[int] = None,
        include_disposable_only: bool = True,
        backup: bool = False,
        force_explicit: bool = False,
    ) -> bool:
        """
        Safely removes a prefix directory.
        Re-evaluates is_eligible_for_cleanup immediately before removal unless force_explicit=True.
        """
        if not self._is_safe_contained_path(prefix_path):
            return False

        if not force_explicit:
            eligible, _ = self.is_eligible_for_cleanup(
                prefix_path,
                max_age_days=max_age_days if max_age_days is not None else 14,
                include_disposable_only=include_disposable_only,
            )
            if not eligible:
                return False
        else:
            if self.is_prefix_in_use(prefix_path):
                return False

        # Cleanly terminate wineserver
        self.kill_wineserver(prefix_path)

        # Re-check active lock immediately before filesystem deletion
        if self.is_prefix_in_use(prefix_path):
            return False

        if os.path.exists(prefix_path):
            if backup:
                os.makedirs(self.trash_dir, exist_ok=True)
                backup_dest = os.path.join(self.trash_dir, os.path.basename(prefix_path))
                try:
                    if os.path.exists(backup_dest):
                        shutil.rmtree(backup_dest, ignore_errors=True)
                    shutil.move(prefix_path, backup_dest)
                    return True
                except Exception:
                    pass
            shutil.rmtree(prefix_path, ignore_errors=True)
            return True
        return False

    def cleanup_stale_prefixes(self, max_age_days: int = 30) -> int:
        """Safely removes prefix directories older than max_age_days without affecting active or persistent ones."""
        preview = self.preview_cleanup(max_age_days=max_age_days, include_disposable_only=True)
        cleaned = 0
        for cand in preview["candidates"]:
            # cleanup_prefix will re-evaluate eligibility immediately before deletion
            if self.cleanup_prefix(
                cand["prefix_path"],
                max_age_days=max_age_days,
                include_disposable_only=True,
                force_explicit=False,
            ):
                cleaned += 1
        return cleaned
