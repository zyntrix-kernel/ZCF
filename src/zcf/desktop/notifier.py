"""
Desktop Notification Integration for ZCF.
Provides user-facing desktop notifications via notify-send and Freedesktop notification spec.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


class DesktopNotifier:
    """Emits desktop notifications when applications launch, configure, or fail."""

    def __init__(self):
        self.notify_bin = shutil.which("notify-send")
        self.enabled = bool(self.notify_bin and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")))

    def notify(self, title: str, message: str, urgency: str = "normal", icon: str = "system-run") -> bool:
        """
        Sends a desktop notification.
        Urgency can be: 'low', 'normal', 'critical'.
        """
        if not self.enabled or not self.notify_bin:
            return False

        try:
            cmd = [
                self.notify_bin,
                "-a",
                "Zyntrix Compatibility Fabric",
                "-u",
                urgency,
                "-i",
                icon,
                title,
                message,
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            return True
        except Exception:
            return False

    def notify_starting(self, app_name: str, runtime_name: str) -> None:
        self.notify(
            title=f"Launching {app_name}",
            message=f"Running with {runtime_name} compatibility runtime...",
            urgency="low",
            icon="system-run",
        )

    def notify_failure(self, app_name: str, reason: str) -> None:
        self.notify(
            title=f"Compatibility Error: {app_name}",
            message=f"Application stopped: {reason[:120]}",
            urgency="critical",
            icon="dialog-error",
        )
