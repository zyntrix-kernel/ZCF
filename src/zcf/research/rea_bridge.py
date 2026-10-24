"""
REA (Reverse Engineer Anything) Bridge for ZCF.
Wraps REA CLI and MCP evidence pipelines to extract deep binary graphs and metadata.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict, Optional


class REABridge:
    """Interacts with local REA installation to collect authenticated Evidence JSON."""

    def __init__(self):
        self.rea_bin = shutil.which("rea")
        self.has_npx = shutil.which("npx") is not None or shutil.which("npx.cmd") is not None

    def is_available(self) -> bool:
        return self.rea_bin is not None or self.has_npx

    def inspect_artifact(self, artifact_path: str) -> Optional[Dict[str, Any]]:
        """Invokes 'rea inspect-artifact' and parses Evidence JSON."""
        abs_path = os.path.abspath(artifact_path)
        cmd = self._build_rea_command(["inspect-artifact", abs_path, "--format", "json"])
        if not cmd:
            return None

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except Exception:
            pass
        return None

    def inspect_managed_artifact(self, artifact_path: str) -> Optional[Dict[str, Any]]:
        """Invokes 'rea inspect-managed-artifact' to extract PE/CLI .NET metadata."""
        abs_path = os.path.abspath(artifact_path)
        cmd = self._build_rea_command(["inspect-managed-artifact", abs_path, "--format", "json"])
        if not cmd:
            return None

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except Exception:
            pass
        return None

    def _build_rea_command(self, args: list[str]) -> Optional[list[str]]:
        if self.rea_bin:
            return [self.rea_bin] + args
        npx_bin = shutil.which("npx.cmd") if os.name == "nt" else shutil.which("npx")
        if npx_bin:
            return [npx_bin, "-y", "rea-agents@6.7.0"] + args
        return None
