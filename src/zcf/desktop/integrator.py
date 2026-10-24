"""
Desktop Application Integrator for ZCF.
Seamlessly integrates Windows and foreign applications into Linux desktop menus (GNOME, KDE, XFCE).
Adheres strictly to Freedesktop Desktop Entry Specification v1.5 with robust Unicode, escaping, and reversibility.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from zcf.desktop.notifier import DesktopNotifier
from zcf.inspector.inspector import ApplicationInspector
from zcf.security.controller import SecurityController


class DesktopIntegrator:
    """Creates and manages standard Freedesktop .desktop application launchers for managed apps."""

    def __init__(self, applications_dir: Optional[str] = None):
        self.app_dir = applications_dir or os.path.expanduser("~/.local/share/applications")
        os.makedirs(self.app_dir, exist_ok=True)
        self.inspector = ApplicationInspector()
        self.notifier = DesktopNotifier()

    @staticmethod
    def escape_exec_path(path: str) -> str:
        """
        Escapes paths for Freedesktop Exec keys according to specification:
        - Backslashes are escaped as '\\'
        - Double quotes are escaped as '\"'
        - Percent signs must be escaped as '%%' to prevent mistaken field-code expansion
        """
        escaped = path.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
        return f'"{escaped}"'

    def get_desktop_path_for_artifact(self, artifact_path: str, custom_name: Optional[str] = None) -> str:
        """Computes deterministic, collision-free .desktop filename for an artifact."""
        abs_path = os.path.abspath(artifact_path)
        sha_prefix = ""
        try:
            app = self.inspector.inspect(abs_path)
            sha_prefix = app.sha256[:8]
            base_name = custom_name or os.path.splitext(app.file_name)[0]
        except Exception:
            base_name = custom_name or os.path.splitext(os.path.basename(abs_path))[0]

        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", base_name).strip("_")[:24] or "app"
        file_name = f"zcf-{safe_slug}-{sha_prefix}.desktop" if sha_prefix else f"zcf-{safe_slug}.desktop"
        return os.path.join(self.app_dir, file_name)

    def integrate(
        self,
        artifact_path: str,
        custom_name: Optional[str] = None,
        icon_path: Optional[str] = None,
    ) -> str:
        """
        Generates a .desktop launcher for the target application and updates the desktop database.
        Returns the path to the created .desktop file.
        """
        abs_path = os.path.abspath(artifact_path)
        SecurityController().validate_execution_safety(abs_path)

        app = self.inspector.inspect(abs_path)
        app_name = custom_name or os.path.splitext(app.file_name)[0].replace("_", " ").title()

        desktop_path = self.get_desktop_path_for_artifact(abs_path, app_name)

        category = "Game;" if any("d3d" in d.lower() for d in app.declared_dependencies) else "Utility;Office;"
        escaped_exec = self.escape_exec_path(abs_path)
        icon_name = icon_path or "application-x-executable"

        desktop_entry = (
            "[Desktop Entry]\n"
            "Version=1.5\n"
            "Type=Application\n"
            f"Name={app_name}\n"
            f"GenericName=Managed Windows/Compatibility App\n"
            f"Comment=Launched seamlessly via Zyntrix Compatibility Fabric (ZCF)\n"
            f"Exec=zcf run {escaped_exec} %f\n"
            f"Icon={icon_name}\n"
            "Terminal=false\n"
            f"Categories={category}\n"
            "StartupNotify=true\n"
            f"X-ZCF-Artifact={abs_path}\n"
            f"X-ZCF-SHA256={app.sha256}\n"
            "MimeType=application/x-msdos-program;application/x-msdownload;\n"
        )

        with open(desktop_path, "w", encoding="utf-8") as f:
            f.write(desktop_entry)

        # Refresh the system desktop database so it appears instantly in the app launcher
        self._refresh_desktop_database()

        self.notifier.notify(
            title="App Added to Menu",
            message=f"'{app_name}' is now available in your Linux application menu!",
            urgency="normal",
            icon="system-run",
        )

        return desktop_path

    def unintegrate(self, artifact_path_or_id: str) -> bool:
        """
        Reversible desktop integration:
        Removes the .desktop launcher and refreshes the desktop database.
        """
        target_path: Optional[str] = None

        if os.path.isfile(artifact_path_or_id) and artifact_path_or_id.endswith(".desktop"):
            target_path = artifact_path_or_id
        else:
            abs_target = os.path.abspath(artifact_path_or_id)
            # Find matching .desktop by X-ZCF-Artifact header or calculated path
            for fname in os.listdir(self.app_dir):
                if fname.startswith("zcf-") and fname.endswith(".desktop"):
                    fpath = os.path.join(self.app_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            content = f.read()
                            if f"X-ZCF-Artifact={abs_target}" in content:
                                target_path = fpath
                                break
                    except Exception:
                        continue

            if not target_path:
                cand = self.get_desktop_path_for_artifact(abs_target)
                if os.path.exists(cand):
                    target_path = cand

        if target_path and os.path.exists(target_path):
            os.remove(target_path)
            self._refresh_desktop_database()
            return True
        return False

    def list_integrated_apps(self) -> List[Dict[str, str]]:
        """Lists all applications currently integrated into the Linux desktop menu via ZCF."""
        integrated: List[Dict[str, str]] = []
        if not os.path.exists(self.app_dir):
            return integrated

        for fname in os.listdir(self.app_dir):
            if fname.startswith("zcf-") and fname.endswith(".desktop"):
                fpath = os.path.join(self.app_dir, fname)
                entry_info: Dict[str, str] = {"file_name": fname, "file_path": fpath}
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("Name="):
                                entry_info["name"] = line.split("=", 1)[1].strip()
                            elif line.startswith("X-ZCF-Artifact="):
                                entry_info["artifact_path"] = line.split("=", 1)[1].strip()
                            elif line.startswith("X-ZCF-SHA256="):
                                entry_info["sha256"] = line.split("=", 1)[1].strip()
                    integrated.append(entry_info)
                except Exception:
                    continue
        return integrated

    def _refresh_desktop_database(self):
        update_db = shutil.which("update-desktop-database")
        if update_db:
            try:
                subprocess.run([update_db, self.app_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
