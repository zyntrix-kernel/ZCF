"""
Virtual Display Manager for ZCF.
Provides transparent headless X11 (Xvfb) lifecycle automation for servers, containers, and WSL.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Dict, Optional


class VirtualDisplayManager:
    """Manages virtual framebuffer (Xvfb) lifecycle when physical display is absent."""

    def __init__(self, display_num: int = 99, screen: str = "1280x1024x24"):
        self.display_num = display_num
        self.screen = screen
        self.process: Optional[subprocess.Popen] = None
        self.display_str = f":{display_num}"
        self.xvfb_bin = shutil.which("Xvfb")
        self.xvfb_run_bin = shutil.which("xvfb-run")

    @staticmethod
    def is_display_available() -> bool:
        """Checks if a graphical display server (Wayland or X11) is currently accessible."""
        if os.environ.get("WAYLAND_DISPLAY"):
            return True
        display = os.environ.get("DISPLAY")
        if display and display.strip():
            return True
        return False

    def is_supported(self) -> bool:
        """Returns True if Xvfb or xvfb-run is available on the system."""
        return bool(self.xvfb_bin or self.xvfb_run_bin)

    def start(self) -> Dict[str, str]:
        """
        Starts an ephemeral Xvfb server and returns updated environment variables.
        """
        if not self.is_supported():
            return {}

        if self.xvfb_bin and not self.process:
            cmd = [
                self.xvfb_bin,
                self.display_str,
                "-screen",
                "0",
                self.screen,
                "-ac",
                "+extension",
                "GLX",
                "+render",
                "-noreset",
            ]
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(0.3)  # Wait for socket to bind
            except Exception:
                self.process = None

        return {"DISPLAY": self.display_str}

    def stop(self) -> None:
        """Stops the ephemeral virtual display server."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            finally:
                self.process = None

    def wrap_command(self, cmd: list[str]) -> list[str]:
        """
        Wraps a command using xvfb-run if standalone Xvfb process cannot be spawned.
        """
        if self.xvfb_run_bin:
            return [self.xvfb_run_bin, "-a", "--server-args=-screen 0 1280x1024x24"] + cmd
        return cmd

    def __enter__(self):
        env_updates = self.start()
        return env_updates

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
