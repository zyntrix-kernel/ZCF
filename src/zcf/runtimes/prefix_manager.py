"""
Wine Prefix and Environment Isolation Manager for ZCF.
Handles prefix creation, cloning, DLL overrides, registry injection, and wineserver coordination.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Dict, List, Optional


class WinePrefixManager:
    """Manages isolated WINEPREFIX directories and Windows registry overrides."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.expanduser("~/.zcf/prefixes")
        os.makedirs(self.base_dir, exist_ok=True)

    def get_prefix_path(self, app_id: str) -> str:
        safe_id = "".join(c for c in app_id if c.isalnum() or c in ("-", "_"))[:24]
        return os.path.join(self.base_dir, safe_id)

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

    def cleanup_prefix(self, prefix_path: str):
        """Cleanly terminates wineserver and removes disposable prefix."""
        self.kill_wineserver(prefix_path)
        if os.path.exists(prefix_path):
            shutil.rmtree(prefix_path, ignore_errors=True)
