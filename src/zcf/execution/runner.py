"""
Execution Orchestrator for ZCF.
Provides end-to-end application execution with automated planning, prefix management,
virtual display handling, Bubblewrap sandboxing, and runtime crash diagnostics.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Dict, List, Optional

from zcf.core.exceptions import ExecutionError, PlanningError
from zcf.core.models import BinaryFormat, CompatibilityPlan, Subsystem
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
        self.diagnostic_engine = DiagnosticEngine()
        self.remediator = AutomatedRemediator()
        self.notifier = DesktopNotifier()
        self.desktop_ui = DesktopUI()
        self.installer_bridge = PackageInstallerBridge()

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
        app_args = app_args or []
        SecurityController().validate_execution_safety(artifact_path, app_args)

        # 1. Non-executing static binary inspection
        app = self.inspector.inspect(artifact_path)

        # 2. Host environment audit & deterministic compatibility plan
        env = self.env_inspector.inspect()
        plan = self.planner.plan(app, env)

        # 3. Verify runtime availability
        if not plan.selected_runtime_id:
            raise PlanningError(f"Compatibility planner could not find a suitable runtime for {app.file_name}: {plan.reasoning}")

        adapter = self.registry.get_adapter(plan.selected_runtime_id)
        if not adapter:
            raise PlanningError(f"No registered runtime adapter for '{plan.selected_runtime_id}'")

        if not adapter.is_available(env):
            # Check if we can automatically install the missing runtime
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

        # 4. Display Management (Xvfb virtual display if headless or requested)
        display_mgr = VirtualDisplayManager()
        is_gui = app.subsystem == Subsystem.GUI
        needs_xvfb = force_headless or (is_gui and not VirtualDisplayManager.is_display_available())

        # 5. Environment & Prefix Preparation
        context = adapter.prepare_environment(app, plan.recommended_configuration)
        run_env = context.get("environment_variables", os.environ.copy())
        if needs_xvfb and display_mgr.is_supported():
            xvfb_env = display_mgr.start()
            run_env.update(xvfb_env)

        # 6. Command Line Construction
        abs_target = os.path.abspath(app.artifact_path)
        if "wine" in plan.selected_runtime_id:
            import shutil
            wine_bin = shutil.which("wine64") or shutil.which("wine") or "wine"
            raw_cmd = [wine_bin, abs_target] + (app_args or [])
        elif "qemu" in plan.selected_runtime_id:
            import shutil
            qemu_bin = shutil.which("qemu-aarch64") or "qemu-aarch64"
            raw_cmd = [qemu_bin, abs_target] + (app_args or [])
        else:
            raw_cmd = [abs_target] + (app_args or [])

        # 7. Security Sandboxing via Bubblewrap (if enabled and on Linux)
        final_cmd = raw_cmd
        working_dir = os.path.dirname(abs_target)
        if use_sandbox and self.sandbox_manager.is_sandbox_available():
            policy = SandboxPolicy(
                isolate_network=False,
                read_only_root=True,
                disposable_tmp=False,
            )
            prefix_path = context.get("prefix_path")
            if prefix_path:
                os.makedirs(prefix_path, exist_ok=True)
                policy.bind_mounts.append(prefix_path)
            if os.path.exists("/run"):
                policy.bind_mounts.append("/run")
            final_cmd = self.sandbox_manager.wrap_command(raw_cmd, working_dir, policy)

        # Notify user desktop
        self.notifier.notify_starting(app.file_name, adapter.get_name())

        # 8. Execution and Real-time Stream & Capture
        merged_env = os.environ.copy()
        merged_env.update(run_env)

        print(f"\n[ZCF Runner] Launching '{app.file_name}' via {adapter.get_name()}...")
        if use_sandbox and self.sandbox_manager.is_sandbox_available():
            print(f"[ZCF Runner] Security Sandbox: Bubblewrap Active")
        if needs_xvfb and display_mgr.process:
            print(f"[ZCF Runner] Virtual Display: Ephemeral Xvfb Active ({display_mgr.display_str})")
        print("-" * 60)

        captured_output: List[str] = []
        exit_code = 0

        try:
            process = subprocess.Popen(
                final_cmd,
                env=merged_env,
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
                    captured_output.append(line)

            exit_code = process.wait()

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

        # 9. Automated Diagnostics on Failure
        if exit_code != 0:
            full_log = "".join(captured_output)
            events = self.diagnostic_engine.analyze_log(full_log)
            if events:
                print(f"\n[ZCF Diagnostic Engine] Application exited with error code {exit_code}.")
                plan = self.remediator.synthesize(app, env, events)
                for action in plan.action_items:
                    print(f"  [Issue & Fix] {action}")
                if plan.package_install_commands:
                    print(f"  [Package Install] {' && '.join(plan.package_install_commands)}")
                if plan.action_items:
                    self.notifier.notify_failure(app.file_name, plan.action_items[0])
                    if self.desktop_ui.is_gui_available():
                        pkg_cmd = " && ".join(plan.package_install_commands) if plan.package_install_commands else None
                        self.desktop_ui.show_troubleshooting_wizard(app.file_name, plan.action_items[0], plan.action_items[0], pkg_cmd)
            else:
                print(f"\n[ZCF Runner] Process exited with status {exit_code}.")

        return exit_code
