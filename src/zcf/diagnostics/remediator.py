"""
Automated Remediation Engine for ZCF.
Synthesizes concrete fix actions, package install commands, DLL overrides, and wrapper configurations from diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from zcf.core.models import ApplicationDescription, EnvironmentReport
from zcf.diagnostics.analyzer import DiagnosticEvent


@dataclass
class RemediationPlan:
    plan_id: str
    target_app: str
    can_auto_remediate: bool
    package_install_commands: List[str] = field(default_factory=list)
    dll_overrides: Dict[str, str] = field(default_factory=dict)
    environment_variables: Dict[str, str] = field(default_factory=dict)
    wrapper_prefix: Optional[str] = None
    action_items: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "target_app": self.target_app,
            "can_auto_remediate": self.can_auto_remediate,
            "package_install_commands": self.package_install_commands,
            "dll_overrides": self.dll_overrides,
            "environment_variables": self.environment_variables,
            "wrapper_prefix": self.wrapper_prefix,
            "action_items": self.action_items,
        }


class AutomatedRemediator:
    """Translates diagnostic failure events into actionable environment patches."""

    def synthesize(
        self,
        app: ApplicationDescription,
        env: EnvironmentReport,
        events: List[DiagnosticEvent],
    ) -> RemediationPlan:
        plan_id = f"rem_{app.sha256[:8]}"
        pkg_cmds: List[str] = []
        dll_overrides: Dict[str, str] = {}
        env_vars: Dict[str, str] = {}
        wrapper_prefix: Optional[str] = None
        actions: List[str] = []

        distro = (env.distribution or "ubuntu").lower()

        for ev in events:
            if ev.signature == "missing_shared_library":
                lib_name = ev.matched_text.split(":")[-1].strip() if ":" in ev.matched_text else ""
                actions.append(f"Install missing system library: {ev.root_cause}")
                if "apt" in distro or distro in ("ubuntu", "debian"):
                    pkg_cmds.append(f"sudo apt update && sudo apt install -y $(apt-file search '{lib_name}' 2>/dev/null | cut -d: -f1 | head -n1)")
                elif distro in ("arch", "manjaro"):
                    pkg_cmds.append(f"sudo pacman -S --noconfirm $(pkgfile '{lib_name}' 2>/dev/null | head -n1)")
                elif distro in ("fedora", "rhel"):
                    pkg_cmds.append(f"sudo dnf install -y '*/{lib_name}'")

            elif ev.signature in ("wine_dll_not_found", "wine_directx_missing"):
                dll = "d3d11" if "d3d" in ev.matched_text.lower() else "native"
                dll_overrides[dll] = "n,b"
                actions.append(f"Set native DLL override for {dll}: WINEDLLOVERRIDES='{dll}=n,b'")

            elif ev.signature == "missing_display":
                wrapper_prefix = "xvfb-run -a"
                actions.append("Wrap command with headless virtual framebuffer ('xvfb-run -a')")

            elif ev.signature == "wine_mono_missing":
                actions.append("Install Wine Mono package for .NET support")
                if distro in ("ubuntu", "debian"):
                    pkg_cmds.append("sudo apt install -y wine-mono")
                elif distro in ("arch", "manjaro"):
                    pkg_cmds.append("sudo pacman -S --noconfirm wine-mono")

        can_auto = bool(dll_overrides or wrapper_prefix or pkg_cmds)

        return RemediationPlan(
            plan_id=plan_id,
            target_app=app.file_name,
            can_auto_remediate=can_auto,
            package_install_commands=pkg_cmds,
            dll_overrides=dll_overrides,
            environment_variables=env_vars,
            wrapper_prefix=wrapper_prefix,
            action_items=actions,
        )
