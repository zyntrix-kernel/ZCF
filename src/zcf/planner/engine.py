"""
Explainable Compatibility Planner.
Evaluates application requirements against host environment capabilities using deterministic constraint satisfaction.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    CandidateEvaluation,
    CompatibilityPlan,
    EnvironmentReport,
    ExecutionMode,
)
from zcf.runtimes.registry import RuntimeRegistry


class CompatibilityPlanner:
    """Multi-criteria rule-based compatibility planning engine."""

    def __init__(self, registry: Optional[RuntimeRegistry] = None):
        self.registry = registry or RuntimeRegistry()

    def plan(self, app: ApplicationDescription, env: EnvironmentReport) -> CompatibilityPlan:
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        candidates: List[CandidateEvaluation] = []
        satisfied_reqs: List[str] = []
        missing_reqs: List[str] = []
        safe_steps: List[str] = []

        selected_id: Optional[str] = None
        selected_name: Optional[str] = None
        highest_score = -1.0
        reasoning = ""
        execution_mode = ExecutionMode.BLOCKED

        # Security check: ring-0 kernel driver requirement
        if app.security_indicators.get("requires_kernel_driver"):
            missing_reqs.append("Application requires Windows kernel-level ring-0 driver (unsupported in userspace)")

        is_graphics_heavy = any(
            d.lower() in ("d3d11.dll", "d3d12.dll", "dxgi.dll", "vulkan-1.dll", "opengl32.dll")
            for d in app.declared_dependencies
        )

        for adapter in self.registry.list_adapters():
            rid = adapter.get_id()
            validation = adapter.validate(app, env)
            installed = adapter.is_available(env)

            score = 0.0
            notes = ""

            if not validation.valid:
                eligible = False
                notes = f"Ineligible: {'; '.join(validation.errors)}"
            else:
                eligible = True
                if rid == "runtime.native":
                    if env.os_name == "windows" and app.format == BinaryFormat.PE:
                        score = 1.0
                        notes = "Native Windows execution on matching host"
                    elif env.os_name == "linux" and app.format == BinaryFormat.ELF and app.architecture.value == env.architecture:
                        score = 1.0
                        notes = "Native Linux execution with matching host architecture"
                    elif app.format == BinaryFormat.SCRIPT:
                        score = 0.95
                        notes = "Native script execution via host interpreter"
                    else:
                        score = 0.70
                        notes = "Native execution with potential runtime dependencies"

                elif rid == "runtime.proton":
                    if not installed:
                        score = 0.0
                        notes = "Proton runner is not installed in standard Steam paths"
                    else:
                        score = 0.95 if is_graphics_heavy else 0.88
                        notes = "Proton gaming runner with DXVK Vulkan acceleration"

                elif rid == "runtime.wine":
                    if not installed:
                        score = 0.0
                        notes = "Eligible architecture and format, but Wine is not installed on host"
                    else:
                        score = 0.90
                        if app.security_indicators.get("has_anti_cheat"):
                            score -= 0.35
                            notes = "Wine available; anti-cheat signatures may cause runtime failure"
                        elif app.is_managed:
                            score -= 0.10
                            notes = "Wine available; .NET application may require Wine Mono"
                        else:
                            notes = "Wine installed; direct Win32/Win64 API translation supported"

                elif rid == "runtime.box64":
                    if not installed:
                        score = 0.0
                        notes = "Box64 is not installed on host system"
                    elif env.architecture == "arm64":
                        score = 0.92
                        notes = "Box64 dynamic translation with native library wrapping (optimal for ARM64)"
                    else:
                        score = 0.60
                        notes = "Box64 available, but host CPU is not ARM64"

                elif rid == "runtime.qemu-user":
                    if not installed:
                        score = 0.0
                        notes = "Cross-architecture translation target, but QEMU user binary is not installed"
                    else:
                        score = 0.85
                        notes = f"QEMU user-mode translation ready for target {app.architecture.value}"

                elif rid == "runtime.android":
                    if not installed:
                        score = 0.0
                        notes = "Android APK format identified, but Waydroid is not installed"
                    else:
                        score = 0.90
                        notes = "Waydroid container runtime available for Android APK execution"

            candidates.append(
                CandidateEvaluation(
                    runtime_id=rid,
                    eligible=eligible,
                    score=score,
                    notes=notes,
                )
            )

            if eligible and installed and score > highest_score:
                highest_score = score
                selected_id = rid
                selected_name = adapter.get_name()

        # Resolve recommendation and reasoning
        if selected_id:
            if selected_id == "runtime.native":
                execution_mode = ExecutionMode.NATIVE
                satisfied_reqs.append(f"Host OS '{env.os_name}' and architecture '{env.architecture}' match target")
                reasoning = f"Direct native execution via {selected_name} is the optimal path."
                safe_steps.append("Execute via native process launcher or run dry-run verification.")

            elif selected_id in ("runtime.wine", "runtime.proton"):
                execution_mode = ExecutionMode.TRANSLATION
                satisfied_reqs.append(f"{selected_name} is installed and verified on host")
                satisfied_reqs.append("Windows PE binary structure validated")
                reasoning = f"Windows application on Linux host; routing to {selected_name}."
                safe_steps.append("Initialize isolated application prefix under ~/.zcf/prefixes.")
                safe_steps.append("Run dry-run or diagnostic trace to verify DLL dependencies.")

            elif selected_id in ("runtime.qemu-user", "runtime.box64"):
                execution_mode = ExecutionMode.EMULATION
                satisfied_reqs.append("Target ELF binary format validated")
                satisfied_reqs.append(f"{selected_name} available for {app.architecture.value}")
                reasoning = (
                    f"Host architecture ({env.architecture}) differs from target ({app.architecture.value}); "
                    f"routing to {selected_name}."
                )
                safe_steps.append("Verify target multiarch rootfs libraries if dynamically linked.")
                safe_steps.append("Execute in controlled userspace emulation.")

            elif selected_id == "runtime.android":
                execution_mode = ExecutionMode.TRANSLATION
                satisfied_reqs.append("Android APK package structure verified")
                satisfied_reqs.append("Waydroid container runtime detected")
                reasoning = "Android APK target package; routing to Waydroid container."
                safe_steps.append("Verify Waydroid container status ('waydroid status').")
                safe_steps.append("Install and launch APK inside container.")
        else:
            # Handle uninstalled candidate recommendations
            highest_score = 0.0
            if app.format == BinaryFormat.PE and env.os_name == "linux":
                selected_id = "runtime.wine"
                selected_name = "Wine Compatibility Layer"
                execution_mode = ExecutionMode.BLOCKED
                missing_reqs.append("Wine (wine64 / wine) is required but not installed on host Linux system")
                reasoning = "Target is a Windows executable; Wine installation is required to proceed."
                safe_steps.append("Install Wine package: 'sudo apt install wine64' or equivalent native package.")

            elif app.format == BinaryFormat.ELF and app.architecture.value != env.architecture:
                selected_id = "runtime.qemu-user"
                selected_name = "QEMU User-Mode Architecture Emulation"
                execution_mode = ExecutionMode.BLOCKED
                missing_reqs.append(f"QEMU user emulator for '{app.architecture.value}' is not installed")
                reasoning = f"Target ELF is built for {app.architecture.value}; QEMU user-mode translation required."
                safe_steps.append("Install QEMU user package: 'sudo apt install qemu-user' or equivalent.")

            elif app.format == BinaryFormat.ARCHIVE and app.runtime_family == "android-art":
                selected_id = "runtime.android"
                selected_name = "Waydroid Android Container Runtime"
                execution_mode = ExecutionMode.BLOCKED
                missing_reqs.append("Waydroid container runtime is not installed")
                reasoning = "Target is an Android APK package; Waydroid installation is required."
                safe_steps.append("Install Waydroid package: 'sudo apt install waydroid' and run 'waydroid init'.")

            else:
                execution_mode = ExecutionMode.BLOCKED
                reasoning = f"No compatible runtime available for {app.format.value} ({app.architecture.value})."
                missing_reqs.append(f"Unsupported binary format or unconfigured runtime: {app.format.value}")
                safe_steps.append("Inspect binary with REA to analyze architecture and dependencies.")

        return CompatibilityPlan(
            plan_id=plan_id,
            artifact_sha256=app.sha256,
            selected_runtime_id=selected_id,
            selected_runtime_name=selected_name,
            confidence_score=round(max(highest_score, 0.0), 2),
            execution_mode=execution_mode,
            reasoning=reasoning,
            satisfied_requirements=satisfied_reqs,
            missing_requirements=missing_reqs,
            candidate_evaluations=candidates,
            safe_next_steps=safe_steps,
        )
