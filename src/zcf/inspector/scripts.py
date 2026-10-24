"""
Script and interpreted package inspector.
Identifies shebangs, script interpreters, and target execution environments.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from zcf.core.models import Architecture, BinaryFormat, Subsystem


class ScriptParser:
    """Parses shell scripts, Python, Node, and batch files."""

    def __init__(self, data: bytes, file_name: str):
        self.data = data
        self.file_name = file_name.lower()

    def parse(self) -> Dict[str, Any]:
        first_line = ""
        try:
            first_line = self.data[:256].decode("utf-8", errors="ignore").splitlines()[0]
        except IndexError:
            pass

        interpreter = None
        if first_line.startswith("#!"):
            interpreter = first_line[2:].strip()

        runtime_family = None
        if interpreter:
            if "python" in interpreter:
                runtime_family = "python"
            elif "node" in interpreter:
                runtime_family = "node"
            elif "bash" in interpreter or "sh" in interpreter:
                runtime_family = "posix-shell"
            elif "perl" in interpreter:
                runtime_family = "perl"

        if not runtime_family:
            if self.file_name.endswith(".py"):
                runtime_family = "python"
            elif self.file_name.endswith(".js") or self.file_name.endswith(".mjs"):
                runtime_family = "node"
            elif self.file_name.endswith(".sh"):
                runtime_family = "posix-shell"
            elif self.file_name.endswith(".bat") or self.file_name.endswith(".cmd"):
                runtime_family = "windows-batch"

        return {
            "format": BinaryFormat.SCRIPT,
            "architecture": Architecture.ALL,
            "subsystem": Subsystem.CONSOLE,
            "is_managed": False,
            "entry_point": None,
            "runtime_family": runtime_family,
            "interpreter": interpreter,
        }
