"""Autonomous Healing Prescription Engine for ZCF.

Analyzes diagnostic events and execution crash signatures to synthesize
concrete, executable repair prescriptions (components to install, DLL overrides,
runner switches, and gaming tuning). Enables 1-click autonomous healing
with pre-repair safety snapshots.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zcf.diagnostics.analyzer import DiagnosticEvent
from zcf.runtimes.components import WindowsComponentManager
from zcf.runtimes.snapshots import PrefixSnapshotManager


@dataclass
class HealingPrescription:
    """Represents a concrete executable repair prescription synthesized for an application."""

    id: str
    target_app: str
    target_prefix: Optional[str]
    created_at: str
    root_causes: List[str]
    recommended_runner: Optional[str] = None
    components_to_install: List[str] = field(default_factory=list)
    dll_overrides_to_set: Dict[str, str] = field(default_factory=dict)
    env_vars_to_set: Dict[str, str] = field(default_factory=dict)
    recommended_tuning: Dict[str, Any] = field(default_factory=dict)
    is_executable: bool = True
    status: str = "pending"  # "pending", "applied", "failed"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HealingPrescription:
        return cls(
            id=str(data["id"]),
            target_app=str(data.get("target_app", "")),
            target_prefix=data.get("target_prefix"),
            created_at=str(data.get("created_at", "")),
            root_causes=list(data.get("root_causes") or []),
            recommended_runner=data.get("recommended_runner"),
            components_to_install=list(data.get("components_to_install") or []),
            dll_overrides_to_set=dict(data.get("dll_overrides_to_set") or {}),
            env_vars_to_set=dict(data.get("env_vars_to_set") or {}),
            recommended_tuning=dict(data.get("recommended_tuning") or {}),
            is_executable=bool(data.get("is_executable", True)),
            status=str(data.get("status", "pending")),
        )


class PrescriptionEngine:
    """Synthesizes and applies autonomous healing prescriptions."""

    def __init__(self, component_mgr: Optional[WindowsComponentManager] = None):
        self.component_mgr = component_mgr or WindowsComponentManager()
        self.snapshot_mgr = PrefixSnapshotManager()

    def synthesize(
        self,
        events: List[DiagnosticEvent],
        app_name: str,
        prefix_path: Optional[str] = None,
    ) -> HealingPrescription:
        """Synthesize an actionable healing prescription from diagnostic events."""
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rx_id = f"rx_{int(time.time())}"

        root_causes: List[str] = []
        components: List[str] = []
        overrides: Dict[str, str] = {}
        env_vars: Dict[str, str] = {}
        recommended_runner: Optional[str] = None
        recommended_tuning: Dict[str, Any] = {}

        for ev in events:
            root_causes.append(ev.root_cause)
            matched = ev.matched_text.lower()

            # 1. Missing DirectX / Shader components
            if ev.signature == "wine_directx_missing" or "d3d" in matched:
                if "d3dx" not in components:
                    components.append("d3dx9")
                if "d3dcompiler_47" not in components:
                    components.append("d3dcompiler_47")
                overrides["d3d11"] = "native,builtin"
                overrides["d3d9"] = "native,builtin"
                overrides["dxgi"] = "native"

            # 2. Missing Windows DLLs (VCRun, .NET, Media Foundation)
            elif ev.signature == "wine_dll_not_found":
                if any(v in matched for v in ("msvcp", "msvcr", "vcruntime", "mfc")):
                    if "vcrun2010" not in components:
                        components.append("vcrun2010")
                elif any(d in matched for d in ("mscoree", "system.data", "clr")):
                    if "dotnet48" not in components:
                        components.append("dotnet48")
                elif "d3d" in matched:
                    if "vkd3d" not in components:
                        components.append("vkd3d")
                    overrides["d3d12"] = "native,builtin"

            # 3. Vulkan ICD or driver issues -> Recommend Proton + DXVK fallback
            elif ev.signature == "vulkan_initialization_failure":
                recommended_runner = "runtime.proton"
                env_vars["PROTON_USE_WINED3D"] = "0"
                env_vars["DXVK_ASYNC"] = "1"

            # 4. Out of memory / 32-bit address space exhaustion
            elif "memory" in matched or "address space" in matched or ev.signature == "out_of_memory":
                env_vars["WINE_LARGE_ADDRESS_AWARE"] = "1"

            # 5. Display / Frame pacing issues
            elif ev.signature in ("missing_display", "display_error"):
                recommended_tuning = {
                    "enabled": True,
                    "use_gamescope": True,
                    "upscaling_filter": "fsr",
                    "use_gamemode": True,
                }

        # If gaming failure detected and no specific runner recommended, suggest Proton
        if (components or overrides) and not recommended_runner:
            recommended_runner = "runtime.proton"

        is_executable = bool(components or overrides or env_vars or recommended_runner)

        return HealingPrescription(
            id=rx_id,
            target_app=app_name,
            target_prefix=prefix_path,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            root_causes=root_causes or ["Generic execution instability detected"],
            recommended_runner=recommended_runner,
            components_to_install=components,
            dll_overrides_to_set=overrides,
            env_vars_to_set=env_vars,
            recommended_tuning=recommended_tuning,
            is_executable=is_executable,
            status="pending",
        )

    def apply(
        self,
        prescription: HealingPrescription,
        prefix_path: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Apply a healing prescription: creates safety snapshot, installs components, sets overrides."""
        prefix_real = os.path.realpath(prefix_path)
        if not os.path.isdir(prefix_real) and not dry_run:
            raise FileNotFoundError(f"Prefix directory not found: {prefix_path}")

        applied_actions: List[str] = []
        snapshot_id = None

        if dry_run:
            return {
                "prescription_id": prescription.id,
                "status": "dry_run",
                "snapshot_id": "dry_run_snapshot",
                "actions": [
                    f"Install components: {', '.join(prescription.components_to_install)}",
                    f"Apply DLL overrides: {prescription.dll_overrides_to_set}",
                    f"Set environment variables: {prescription.env_vars_to_set}",
                ],
            }

        # 1. Take safety snapshot before applying fixes
        try:
            snap = self.snapshot_mgr.create_snapshot(
                prefix_real,
                label=f"Pre-Healing: {prescription.id}",
                trigger="auto_pre_component",
                description=f"Automated Time-Machine snapshot before applying prescription {prescription.id}",
            )
            snapshot_id = snap.id
            applied_actions.append(f"Created safety restore point: {snap.id}")
        except Exception as e:
            applied_actions.append(f"Snapshot skipped: {e}")

        # 2. Install required Windows components
        for comp in prescription.components_to_install:
            try:
                self.component_mgr.install(prefix_real, comp)
                applied_actions.append(f"Installed component: {comp}")
            except Exception as e:
                applied_actions.append(f"Failed to install component {comp}: {e}")

        # 3. Apply DLL overrides to prefix metadata
        if prescription.dll_overrides_to_set:
            meta_path = os.path.join(prefix_real, "prefix_meta.json")
            meta_data: Dict[str, Any] = {}
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                except Exception:
                    pass

            existing_overrides = meta_data.setdefault("dll_overrides", {})
            existing_overrides.update(prescription.dll_overrides_to_set)

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)
            applied_actions.append(f"Applied DLL overrides: {prescription.dll_overrides_to_set}")

        prescription.status = "applied"

        return {
            "prescription_id": prescription.id,
            "status": "applied",
            "snapshot_id": snapshot_id,
            "actions": applied_actions,
            "recommended_runner": prescription.recommended_runner,
            "env_vars": prescription.env_vars_to_set,
        }
