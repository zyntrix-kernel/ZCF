"""
Execution Orchestrator for ZCF.
Provides end-to-end application execution across the 9-phase lifecycle:
Inspect -> Collect Evidence -> Plan -> Validate -> Prepare Environment ->
Apply Security Policy -> Execute -> Diagnose -> Record Results.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional

from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.core.exceptions import ExecutionError, PlanningError
from zcf.core.models import (
    ApplicationDescription,
    CompatibilityPlan,
    ExecutionMode,
    ExecutionResult,
    Subsystem,
)
from zcf.desktop.notifier import DesktopNotifier
from zcf.desktop.ui import DesktopUI
from zcf.diagnostics.analyzer import DiagnosticEngine
from zcf.diagnostics.remediator import AutomatedRemediator
from zcf.environment.inspector import EnvironmentInspector
from zcf.execution.display import VirtualDisplayManager
from zcf.execution.installer import PackageInstallerBridge
from zcf.inspector.inspector import ApplicationInspector
from zcf.planner.engine import CompatibilityPlanner
from zcf.runtimes.prefix_manager import WinePrefixManager
from zcf.runtimes.registry import RuntimeRegistry
from zcf.security.controller import SecurityController
from zcf.security.sandbox import SandboxManager, SandboxPolicy


class ExecutionOrchestrator:
    """End-to-end execution runner coordinating all compatibility and isolation subsystems."""

    def __init__(self, prefix_root: Optional[str] = None):
        self.inspector = ApplicationInspector()
        self.env_inspector = EnvironmentInspector()
        self.planner = CompatibilityPlanner()
        self.registry = RuntimeRegistry()
        self.prefix_manager = WinePrefixManager(base_dir=prefix_root)
        self.sandbox_manager = SandboxManager()
        self.security_controller = SecurityController()
        self.diagnostic_engine = DiagnosticEngine()
        self.remediator = AutomatedRemediator()
        self.notifier = DesktopNotifier()
        self.desktop_ui = DesktopUI()
        self.installer_bridge = PackageInstallerBridge()
        self.db = CompatibilityDatabase()

    def execute_lifecycle(
        self,
        artifact_path: str,
        app_args: Optional[List[str]] = None,
        use_sandbox: bool = True,
        force_headless: bool = False,
        auto_install: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Executes an application across the full 9-phase compatibility lifecycle.
        Returns a rich structured ExecutionResult.
        """
        start_time = time.time()
        app_args = app_args or []

        # -------------------------------------------------------------
        # PHASE 1: Non-executing static binary inspection
        # -------------------------------------------------------------
        self.security_controller.validate_execution_safety(artifact_path, app_args)
        app = self.inspector.inspect(artifact_path)

        # -------------------------------------------------------------
        # PHASE 2: Collect Evidence (Database + Host Environment)
        # -------------------------------------------------------------
        db_evidence = self.db.get_by_sha256(app.sha256)
        env = self.env_inspector.inspect()

        # -------------------------------------------------------------
        # PHASE 3: Deterministic Capability-Driven Compatibility Plan
        # -------------------------------------------------------------
        plan = self.planner.plan(app, env, db_evidence=db_evidence)

        if plan.is_blocked:
            raise PlanningError(f"Compatibility planner blocked execution: {plan.blocker_summary}")

        if not plan.selected_runtime_id:
            raise PlanningError(
                f"Compatibility planner could not find a suitable runtime for {app.file_name}: {plan.reasoning}"
            )

        adapter = self.registry.get_adapter(plan.selected_runtime_id)
        if not adapter:
            raise PlanningError(f"No registered runtime adapter for '{plan.selected_runtime_id}'")

        # -------------------------------------------------------------
        # PHASE 4: Validate Adapter & Resolve Prerequisites
        # -------------------------------------------------------------
        if not adapter.is_available(env):
            generic_target = "wine" if "wine" in plan.selected_runtime_id else "qemu-user"
            if not auto_install and self.desktop_ui.is_gui_available():
                cmd_str = " ".join(self.installer_bridge.get_install_command(generic_target) or [])
                if self.desktop_ui.prompt_install_missing_runtime(app.file_name, adapter.get_name(), cmd_str):
                    auto_install = True

            if auto_install:
                installed = self.installer_bridge.install(generic_target, interactive=False)
                if installed:
                    env = self.env_inspector.inspect()

            if not adapter.is_available(env):
                raise PlanningError(
                    f"Required runtime '{adapter.get_name()}' is not installed.\n"
                    f"To install, run: {self.installer_bridge.get_install_command(generic_target)}"
                )

        validation = adapter.validate(app, env)
        if not validation.valid:
            err_msg = "; ".join(validation.errors)
            raise PlanningError(f"Validation failed for '{adapter.get_name()}': {err_msg}")

        # -------------------------------------------------------------
        # PHASE 5: Prepare Environment & Prefix Isolation
        # -------------------------------------------------------------
        display_mgr = VirtualDisplayManager()
        is_gui = app.subsystem == Subsystem.GUI
        needs_xvfb = force_headless or (is_gui and not VirtualDisplayManager.is_display_available())

        context = adapter.prepare_environment(app, plan.recommended_configuration)
        raw_env = context.get("environment_variables", os.environ.copy())

        if needs_xvfb and display_mgr.is_supported():
            xvfb_env = display_mgr.start()
            raw_env.update(xvfb_env)

        # -------------------------------------------------------------
        # PHASE 6: Apply Security Policy & Environment Sanitization
        # -------------------------------------------------------------
        security_policy = self.security_controller.build_execution_policy(app, use_sandbox=use_sandbox)
        sanitized_env = self.security_controller.sanitize_env_vars(raw_env, mode=security_policy.environment_mode)

        # Build raw command via the adapter
        raw_cmd = adapter.build_command(app, context, app_args)

        # Observable sandboxing wrapping
        final_cmd = raw_cmd
        working_dir = context.get("working_directory", os.path.dirname(os.path.abspath(app.artifact_path)))
        permitted_paths = [working_dir]

        prefix_path = context.get("prefix_path")
        if prefix_path:
            permitted_paths.append(prefix_path)

        security_warnings: List[str] = []
        sandbox_active = False

        if use_sandbox:
            if self.sandbox_manager.is_sandbox_available():
                sb_policy = SandboxPolicy(
                    isolate_network=security_policy.isolate_network,
                    read_only_root=security_policy.read_only_root,
                    disposable_tmp=security_policy.disposable_tmp,
                )
                if prefix_path:
                    os.makedirs(prefix_path, exist_ok=True)
                    sb_policy.bind_mounts.append(prefix_path)
                if os.path.exists("/run"):
                    sb_policy.bind_mounts.append("/run")

                final_cmd = self.sandbox_manager.wrap_command(raw_cmd, working_dir, sb_policy)
                sandbox_active = True
            else:
                security_warnings.append(
                    "Sandboxing requested but Bubblewrap ('bwrap') is not available on host. Proceeding unconfined."
                )

        # Notify user desktop
        self.notifier.notify_starting(app.file_name, adapter.get_name())

        # -------------------------------------------------------------
        # PHASE 7: Process Execution & Real-Time Output Streaming
        # -------------------------------------------------------------
        print(f"\n[ZCF Runner] Launching '{app.file_name}' via {adapter.get_name()}...")
        if sandbox_active:
            print("[ZCF Runner] Security Sandbox: Bubblewrap Active")
        if needs_xvfb and display_mgr.process:
            print(f"[ZCF Runner] Virtual Display: Ephemeral Xvfb Active ({display_mgr.display_str})")
        print("-" * 60)

        captured_stdout: List[str] = []
        exit_code = 0

        try:
            process = subprocess.Popen(
                final_cmd,
                env=sanitized_env,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            if process.stdout:
                for line in process.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    if stream_callback:
                        stream_callback(line)
                    captured_stdout.append(line)

            exit_code = process.wait(timeout=timeout)

        except subprocess.TimeoutExpired:
            process.kill()
            captured_stdout.append(f"\n[ZCF] Execution timed out after {timeout} seconds.")
            exit_code = 124
        except KeyboardInterrupt:
            print("\n[ZCF] Execution interrupted by user.")
            exit_code = 130
        except Exception as e:
            print(f"\n[ZCF] Execution failed to start: {e}")
            exit_code = 1
        finally:
            if needs_xvfb:
                display_mgr.stop()
            if hasattr(adapter, "cleanup"):
                adapter.cleanup(app, context)

        print("-" * 60)
        elapsed_seconds = time.time() - start_time
        full_output = "".join(captured_stdout)

        # -------------------------------------------------------------
        # PHASE 8: Automated Failure Diagnostics & Remediation
        # -------------------------------------------------------------
        diagnostics_data: List[Dict[str, Any]] = []
        if exit_code != 0:
            events = self.diagnostic_engine.analyze_log(full_output)
            if events:
                rem_plan = self.remediator.synthesize(app, env, events)
                for ev in events:
                    diagnostics_data.append(
                        {
                            "signature": ev.signature,
                            "root_cause": ev.root_cause,
                            "remediation": ev.remediation,
                        }
                    )
                print(f"\n[ZCF Diagnostic Engine] Application exited with error code {exit_code}.")
                for action in rem_plan.action_items:
                    print(f"  [Issue & Fix] {action}")
                if rem_plan.package_install_commands:
                    print(f"  [Package Install] {' && '.join(rem_plan.package_install_commands)}")
                if rem_plan.action_items:
                    self.notifier.notify_failure(app.file_name, rem_plan.action_items[0])
                    if self.desktop_ui.is_gui_available():
                        pkg_cmd = (
                            " && ".join(rem_plan.package_install_commands)
                            if rem_plan.package_install_commands
                            else None
                        )
                        self.desktop_ui.show_troubleshooting_wizard(
                            app.file_name, rem_plan.action_items[0], rem_plan.action_items[0], pkg_cmd
                        )
            else:
                print(f"\n[ZCF Runner] Process exited with status {exit_code}.")

        # -------------------------------------------------------------
        # PHASE 9: Record Results & Formulate Structured ExecutionRecord
        # -------------------------------------------------------------
        return ExecutionResult(
            success=exit_code == 0,
            exit_code=exit_code,
            stdout=full_output,
            stderr="",
            execution_time_seconds=elapsed_seconds,
            command=final_cmd,
            isolated_env_path=prefix_path,
            diagnostics=diagnostics_data,
            effective_runtime=adapter.get_id(),
            effective_security_policy=security_policy.to_dict(),
            permitted_writable_paths=permitted_paths,
            security_warnings=security_warnings,
        )

    def run(
        self,
        artifact_path: str,
        app_args: Optional[List[str]] = None,
        use_sandbox: bool = True,
        force_headless: bool = False,
        auto_install: bool = False,
    ) -> int:
        """
        Executes an application through its optimal compatibility pipeline.
        Returns the process exit code.
        """
        result = self.execute_lifecycle(
            artifact_path=artifact_path,
            app_args=app_args,
            use_sandbox=use_sandbox,
            force_headless=force_headless,
            auto_install=auto_install,
        )
        return result.exit_code
