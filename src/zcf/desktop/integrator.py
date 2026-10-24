"""
Desktop Application Integrator for ZCF.
Seamlessly integrates Windows and foreign applications into Linux desktop menus (GNOME, KDE, XFCE).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from zcf.desktop.notifier import DesktopNotifier
from zcf.inspector.inspector import ApplicationInspector
from zcf.security.controller import SecurityController


class DesktopIntegrator:
    """Creates standard Freedesktop .desktop application launchers for managed apps."""

    def __init__(self, applications_dir: Optional[str] = None):
        self.app_dir = applications_dir or os.path.expanduser("~/.local/share/applications")
        os.makedirs(self.app_dir, exist_ok=True)
        self.inspector = ApplicationInspector()
        self.notifier = DesktopNotifier()

    def integrate(self, artifact_path: str, custom_name: Optional[str] = None) -> str:
        """
        Generates a .desktop launcher for the target application and updates the desktop database.
        Returns the path to the created .desktop file.
        """
        abs_path = os.path.abspath(artifact_path)
        SecurityController().validate_execution_safety(abs_path)

        app = self.inspector.inspect(abs_path)
        app_name = custom_name or os.path.splitext(app.file_name)[0].replace("_", " ").title()
        safe_id = "".join(c for c in app_name.lower() if c.isalnum() or c == "-").strip("-")
        desktop_file_name = f"zcf-{safe_id}.desktop"
        desktop_path = os.path.join(self.app_dir, desktop_file_name)

        category = "Game;" if any("d3d" in d.lower() for d in app.declared_dependencies) else "Utility;Office;"

        desktop_entry = (
            "[Desktop Entry]\n"
            "Version=1.0\n"
            "Type=Application\n"
            f"Name={app_name}\n"
            f"GenericName=Managed Windows/Compatibility App\n"
            f"Comment=Launched seamlessly via Zyntrix Compatibility Fabric (ZCF)\n"
            f'Exec=zcf run "{abs_path}" %f\n'
            "Icon=application-x-executable\n"
            "Terminal=false\n"
            f"Categories={category}\n"
            "StartupNotify=true\n"
            "MimeType=application/x-msdos-program;application/x-msdownload;\n"
        )

        with open(desktop_path, "w", encoding="utf-8") as f:
            f.write(desktop_entry)

        # Refresh the system desktop database so it appears instantly in the app launcher
        update_db = shutil.which("update-desktop-database")
        if update_db:
            try:
                subprocess.run([update_db, self.app_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        self.notifier.notify(
            title="App Added to Menu",
            message=f"'{app_name}' is now available in your Linux application menu!",
            urgency="normal",
            icon="system-run",
        )

        return desktop_path
