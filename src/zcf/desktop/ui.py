"""
Graphical User Experience (GUI) Engine for ZCF.
Provides beginner-friendly native desktop dialogs, install prompts, and crash repair wizards.
Supports Zenity (GTK), KDialog (KDE), and Python Tkinter fallback.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional


class DesktopUI:
    """Provides user-friendly graphical desktop dialogs for Linux beginners."""

    def __init__(self):
        self.zenity_bin = shutil.which("zenity")
        self.kdialog_bin = shutil.which("kdialog")
        self.has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    def is_gui_available(self) -> bool:
        """Checks if graphical dialogs can be displayed to the user."""
        if os.environ.get("ZCF_NON_INTERACTIVE") == "1":
            return False
        return self.has_display and bool(self.zenity_bin or self.kdialog_bin or self._has_tkinter())

    @staticmethod
    def _has_tkinter() -> bool:
        try:
            import tkinter  # noqa: F401
            return True
        except ImportError:
            return False

    def prompt_confirmation(self, title: str, message: str, ok_label: str = "Proceed", cancel_label: str = "Cancel", timeout_sec: int = 10) -> bool:
        """Prompts the user with a Yes/No question dialog."""
        if not self.is_gui_available():
            return False

        if self.zenity_bin:
            try:
                cmd = [
                    self.zenity_bin,
                    "--question",
                    f"--title={title}",
                    f"--text={message}",
                    f"--ok-label={ok_label}",
                    f"--cancel-label={cancel_label}",
                    f"--timeout={timeout_sec}",
                    "--width=420",
                ]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout_sec + 2)
                return res.returncode == 0
            except Exception:
                pass

        if self.kdialog_bin:
            try:
                cmd = [
                    self.kdialog_bin,
                    f"--title={title}",
                    f"--yesno={message}",
                    f"--yes-label={ok_label}",
                    f"--no-label={cancel_label}",
                ]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return res.returncode == 0
            except Exception:
                pass

        # Tkinter Fallback
        if self._has_tkinter():
            try:
                import tkinter as tk
                from tkinter import messagebox

                root = tk.Tk()
                root.withdraw()
                confirmed = messagebox.askyesno(title, message)
                root.destroy()
                return bool(confirmed)
            except Exception:
                pass

        return False

    def show_info(self, title: str, message: str, timeout_sec: int = 5) -> None:
        """Displays an informational message box."""
        if not self.is_gui_available():
            return

        if self.zenity_bin:
            try:
                subprocess.run([self.zenity_bin, "--info", f"--title={title}", f"--text={message}", f"--timeout={timeout_sec}", "--width=380"], timeout=timeout_sec + 2)
                return
            except Exception:
                pass

        if self.kdialog_bin:
            try:
                subprocess.run([self.kdialog_bin, f"--title={title}", f"--msgbox={message}"], timeout=timeout_sec + 2)
                return
            except Exception:
                pass

    def show_error(self, title: str, message: str, timeout_sec: int = 10) -> None:
        """Displays a friendly error/warning dialog with troubleshooting instructions."""
        if not self.is_gui_available():
            return

        formatted = (
            f"<span size='large' weight='bold'>Compatibility Issue Detected</span>\n\n"
            f"{message}"
        )

        if self.zenity_bin:
            try:
                subprocess.run([self.zenity_bin, "--error", f"--title={title}", f"--text={formatted}", f"--timeout={timeout_sec}", "--width=460"], timeout=timeout_sec + 2)
                return
            except Exception:
                pass

        if self.kdialog_bin:
            try:
                subprocess.run([self.kdialog_bin, f"--title={title}", f"--error={message}"], timeout=15)
                return
            except Exception:
                pass

    def prompt_install_missing_runtime(self, app_name: str, runtime_name: str, install_cmd: str) -> bool:
        """Beginner prompt when a required compatibility runtime is missing."""
        title = "ZCF Compatibility Assistant"
        msg = (
            f"<b>{app_name}</b> requires the <b>{runtime_name}</b> compatibility engine to run on Linux.\n\n"
            f"Would you like ZCF to automatically install it now?\n\n"
            f"<i>System command: {install_cmd}</i>"
        )
        return self.prompt_confirmation(title, msg, ok_label="Install Automatically", cancel_label="Cancel")

    def show_troubleshooting_wizard(self, app_name: str, issue: str, fix: str, install_cmd: Optional[str] = None) -> None:
        """Beginner wizard explaining why an application stopped and how to fix it."""
        title = f"ZCF Assistant: {app_name}"
        msg = (
            f"<b>Application:</b> {app_name}\n"
            f"<b>Issue:</b> {issue}\n\n"
            f"<b>Recommended Fix:</b>\n{fix}\n"
        )
        if install_cmd:
            msg += f"\n<b>Fix Command:</b>\n<code>{install_cmd}</code>"

        self.show_error(title, msg)
