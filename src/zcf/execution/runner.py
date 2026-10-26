"""
Execution Orchestrator for ZCF.
Provides end-to-end application execution across the 9-phase lifecycle:
Inspect -> Collect Evidence -> Plan -> Validate -> Prepare Environment ->
Apply Security Policy -> Execute -> Diagnose -> Record Results.
"""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.core.exceptions import ExecutionError, PlanningError, SecurityViolationError
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
from zcf.execution.history import ExecutionHistoryManager
from zcf.execution.installer import PackageInstallerBridge
from zcf.inspector.inspector import ApplicationInspector
from zcf.planner.engine import CompatibilityPlanner
from zcf.runtimes.prefix_manager import WinePrefixManager
from zcf.runtimes.registry import RuntimeRegistry
from zcf.security.controller import SecurityController
from zcf.security.sandbox import SandboxManager, SandboxPolicy


RUNTIME_PACKAGE_MAP: Dict[str, str] = {
    "runtime.wine": "wine",
    "runtime.proton": "proton",
    "runtime.box64": "box64",
    "runtime.qemu-user": "qemu-user",
    "runtime.android": "waydroid",
    "runtime.native": "native",
}


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
        self.history_mgr = ExecutionHistoryManager()

    def execute_lifecycle(
        self,
        artifact_path: str,
        app_args: Optional[List[str]] = None,
        use_sandbox: bool = True,
        allow_unconfined: bool = False,
        allow_network: Optional[bool] = None,
        dry_run: bool = False,
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
        similar_evidence = None
        if not db_evidence:
            similar_evidence = self.db.find_similar_profiles(
                name=app.file_name,
                format_type=app.format.value,
                arch=app.architecture.value,
            )
        env = self.env_inspector.inspect()

        # -------------------------------------------------------------
        # PHASE 3: Deterministic Capability-Driven Compatibility Plan
        # -------------------------------------------------------------
        plan = self.planner.plan(app, env, db_evidence=db_evidence, similar_evidence=similar_evidence)

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
            generic_target = RUNTIME_PACKAGE_MAP.get(
                plan.selected_runtime_id,
                "wine" if "wine" in plan.selected_runtime_id else "qemu-user",
            )
            if not auto_install and self.desktop_ui.is_gui_available():
                cmd_str = " ".join(self.installer_bridge.get_install_command(generic_target) or [])
                if self.desktop_ui.prompt_install_missing_runtime(app.file_name, adapter.get_name(), cmd_str):
                    auto_install = True

            if auto_install:
                installed = self.installer_bridge.install(generic_target, interactive=False)
                if installed:
                    env = self.env_inspector.inspect()

            if not adapter.is_available(env):
                cmd_needed = self.installer_bridge.get_install_command(generic_target)
                cmd_display = " ".join(cmd_needed) if cmd_needed else f"package for '{generic_target}'"
                raise PlanningError(
                    f"Required runtime '{adapter.get_name()}' is not installed.\n"
                    f"To install, run: {cmd_display}"
                )

        validation = adapter.validate(app, env)
        if not validation.valid:
            err_msg = "; ".join(validation.errors)
            raise PlanningError(f"Validation failed for '{adapter.get_name()}': {err_msg}")

        # -------------------------------------------------------------
        # PHASE 5: Prepare Environment & Prefix Isolation
        # -------------------------------------------------------------
        display_mgr = VirtualDisplayManager()
        display_started = False
        is_gui = app.subsystem == Subsystem.GUI
        needs_xvfb = (not dry_run) and (force_headless or (is_gui and not VirtualDisplayManager.is_display_available()))

        prep_config = dict(plan.recommended_configuration)
        prep_config["dry_run"] = dry_run
        context = adapter.prepare_environment(app, prep_config)
        raw_env = context.get("environment_variables", os.environ.copy())

        try:
            if needs_xvfb and display_mgr.is_supported():
                xvfb_env = display_mgr.start()
                display_started = True
                raw_env.update(xvfb_env)

            # -------------------------------------------------------------
            # PHASE 6: Apply Security Policy & Environment Sanitization
            # -------------------------------------------------------------
            security_policy = self.security_controller.build_execution_policy(
                app, use_sandbox=use_sandbox, allow_network=allow_network
            )
            sanitized_env = self.security_controller.sanitize_env_vars(raw_env, mode=security_policy.environment_mode)

            # Resolve effective timeout with workload-aware policy
            security_warnings: List[str] = []
            effective_timeout: Optional[int] = None
            if timeout is not None:
                if timeout < 0:
                    raise ValueError(f"Execution timeout must be non-negative (received {timeout}s). Use timeout=0 or None for unlimited.")
                elif timeout == 0:
                    effective_timeout = None  # Explicit intentional unlimited mode
                else:
                    if security_policy.max_timeout_seconds and timeout > security_policy.max_timeout_seconds:
                        effective_timeout = security_policy.max_timeout_seconds
                        security_warnings.append(
                            f"Requested timeout ({timeout}s) exceeds policy maximum ({security_policy.max_timeout_seconds}s); clamped to {effective_timeout}s."
                        )
                    else:
                        effective_timeout = timeout
            else:
                effective_timeout = security_policy.default_timeout_seconds

            # Build raw command via the adapter
            raw_cmd = adapter.build_command(app, context, app_args)

            # Observable sandboxing wrapping
            final_cmd = raw_cmd
            working_dir = context.get("working_directory", os.path.dirname(os.path.abspath(app.artifact_path)))
            prefix_path = context.get("prefix_path")

            permitted_paths: List[str] = []
            if prefix_path:
                permitted_paths.append(prefix_path)

            sandbox_active = False

            if use_sandbox:
                if not self.sandbox_manager.is_sandbox_available():
                    if not allow_unconfined:
                        raise SecurityViolationError(
                            "Sandboxing is required by policy (use_sandbox=True), but Bubblewrap ('bwrap') is not available on this host. "
                            "Execution halted to protect host system. Pass allow_unconfined=True or use_sandbox=False to run unconfined."
                        )
                    security_warnings.append(
                        "Sandboxing requested but Bubblewrap ('bwrap') is not available on host. Proceeding unconfined (allow_unconfined=True)."
                    )
                else:
                    allowed_roots = [
                        os.path.realpath(self.prefix_manager.base_dir),
                        os.path.realpath(os.path.expanduser("~/.local/share/zcf/proton_prefixes")),
                    ]
                    if prefix_path:
                        allowed_roots.append(os.path.realpath(os.path.dirname(os.path.abspath(prefix_path))))
                        if not dry_run:
                            os.makedirs(prefix_path, exist_ok=True)

                    sb_policy = SandboxPolicy(
                        isolate_network=security_policy.isolate_network,
                        read_only_root=security_policy.read_only_root,
                        disposable_tmp=security_policy.disposable_tmp,
                        read_only_app=True,
                        enable_x11=True,
                        enable_wayland=True,
                        max_memory_mb=security_policy.max_memory_mb or 0,
                        max_cpu_seconds=security_policy.max_cpu_seconds or 0,
                        prefix_path=prefix_path,
                        allowed_prefix_roots=allowed_roots,
                    )

                    final_cmd = self.sandbox_manager.wrap_command(
                        raw_cmd, working_dir, sb_policy, allow_unconfined=allow_unconfined
                    )
                    sandbox_active = True

            # Notify user desktop
            self.notifier.notify_starting(app.file_name, adapter.get_name())

            # -------------------------------------------------------------
            # PHASE 7: Process Execution & Real-Time Output Streaming
            # -------------------------------------------------------------
            if dry_run:
                print(f"\n[ZCF Runner Dry Run] Planned launch for '{app.file_name}' via {adapter.get_name()}")
                print(f"Command: {' '.join(final_cmd)}")
                dry_stdout = f"[Dry Run] Execution planned successfully via {adapter.get_name()}.\nCommand: {' '.join(final_cmd)}"
                dur = time.time() - start_time
                self.history_mgr.record_run(
                    artifact_path=artifact_path,
                    artifact_sha256=app.sha256,
                    application_name=app.file_name,
                    target_format=app.format.value,
                    target_architecture=app.architecture.value,
                    runtime_id=adapter.get_id(),
                    runtime_name=adapter.get_name(),
                    execution_mode=plan.execution_mode.value,
                    dry_run=True,
                    success=True,
                    exit_code=0,
                    execution_time_seconds=dur,
                    sandbox_active=sandbox_active,
                    network_isolated=security_policy.isolate_network,
                    command=final_cmd,
                    stdout=dry_stdout,
                    stderr="",
                    diagnostics=[],
                    environment={"os": env.os_name, "arch": env.architecture, "kernel": env.kernel_version},
                )
                return ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=dry_stdout,
                    stderr="",
                    execution_time_seconds=dur,
                    command=final_cmd,
                    isolated_env_path=prefix_path,
                    effective_runtime=adapter.get_id(),
                    effective_security_policy=security_policy.to_dict(),
                    permitted_writable_paths=permitted_paths,
                    security_warnings=security_warnings,
                )

            print(f"\n[ZCF Runner] Launching '{app.file_name}' via {adapter.get_name()}...")
            if sandbox_active:
                print("[ZCF Runner] Security Sandbox: Bubblewrap Active")
            print(f"[ZCF Runner] Network Access: {'ENABLED (explicit allow_network=True)' if not security_policy.isolate_network else 'ISOLATED (--unshare-net)'}")
            if display_started and display_mgr.process:
                print(f"[ZCF Runner] Virtual Display: Ephemeral Xvfb Active ({display_mgr.display_str})")
            print("-" * 60)

            MAX_CAPTURED_BYTES = 512 * 1024  # 512 KB
            captured_stdout: List[str] = []
            captured_bytes = 0
            output_truncated = False
            exit_code = 0
            timed_out = False

            # Truthful resource limit enforcement status
            resource_status: Dict[str, Any] = {
                "mechanism": "posix_rlimit" if os.name != "nt" else "unsupported_on_windows",
                "applied": False,
                "virtual_address_space_limit_mb": security_policy.max_memory_mb,
                "cpu_seconds_limit": security_policy.max_cpu_seconds,
                "status": "unsupported_on_platform" if os.name == "nt" else "not_configured",
                "details": (
                    "POSIX RLIMIT_AS enforces virtual address space limits per-process on Linux. "
                    "It does not enforce physical RAM (RSS) or aggregate process-tree memory."
                    if os.name != "nt"
                    else "POSIX rlimit controls are not supported on Windows."
                ),
                "error": None,
            }

            try:
                popen_kwargs: Dict[str, Any] = {
                    "env": sanitized_env,
                    "cwd": working_dir,
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.STDOUT,
                    "text": True,
                    "bufsize": 1,
                    "universal_newlines": True,
                }
                if os.name != "nt":
                    popen_kwargs["start_new_session"] = True
                    max_mem = security_policy.max_memory_mb or 0
                    max_cpu = security_policy.max_cpu_seconds or 0
                    if max_mem > 0 or max_cpu > 0:
                        def _preexec_limits(m_mb=max_mem, c_sec=max_cpu):
                            try:
                                import resource
                                if c_sec > 0:
                                    resource.setrlimit(resource.RLIMIT_CPU, (int(c_sec), int(c_sec) + 5))
                                if m_mb > 0:
                                    as_limit = int(m_mb) * 1024 * 1024
                                    resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_limit))
                            except Exception:
                                pass

                        popen_kwargs["preexec_fn"] = _preexec_limits
                        resource_status["applied"] = True
                        resource_status["status"] = "active"

                security_policy.resource_limits_status = resource_status

                process = subprocess.Popen(final_cmd, **popen_kwargs)

                # Threaded stdout reader feeding a bounded thread-safe queue
                out_queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=1000)

                def reader():
                    try:
                        if process.stdout:
                            if hasattr(process.stdout, "readline"):
                                for line in iter(process.stdout.readline, ""):
                                    if not line and process.poll() is not None:
                                        break
                                    try:
                                        out_queue.put(line, timeout=0.1)
                                    except queue.Full:
                                        pass
                            elif hasattr(process.stdout, "__iter__"):
                                for line in process.stdout:
                                    try:
                                        out_queue.put(line, timeout=0.1)
                                    except queue.Full:
                                        pass
                    except Exception:
                        pass
                    finally:
                        try:
                            out_queue.put(None, timeout=0.5)
                        except Exception:
                            pass

                reader_thread = threading.Thread(target=reader, daemon=True)
                reader_thread.start()

                deadline = (time.monotonic() + effective_timeout) if effective_timeout else None

                while True:
                    # 1. Drain available lines from queue in bounded slices
                    lines_read = 0
                    while lines_read < 25:
                        try:
                            line = out_queue.get_nowait()
                        except queue.Empty:
                            break

                        if line is None:
                            break

                        lines_read += 1
                        sys.stdout.write(line)
                        sys.stdout.flush()
                        if stream_callback:
                            try:
                                stream_callback(line)
                            except Exception:
                                pass

                        if captured_bytes < MAX_CAPTURED_BYTES:
                            captured_stdout.append(line)
                            captured_bytes += len(line.encode("utf-8", errors="replace"))
                            if captured_bytes >= MAX_CAPTURED_BYTES and not output_truncated:
                                output_truncated = True
                                trunc_msg = "\n[ZCF Warning] Process output exceeded 512 KB; subsequent output truncated from capture log.\n"
                                captured_stdout.append(trunc_msg)

                    # 2. Check monotonic deadline continuously
                    if deadline and time.monotonic() >= deadline:
                        timed_out = True
                        break

                    # 3. Check process completion
                    ret = process.poll()
                    if ret is not None:
                        reader_thread.join(timeout=0.4)
                        while True:
                            try:
                                line = out_queue.get_nowait()
                                if line is None:
                                    break
                                sys.stdout.write(line)
                                sys.stdout.flush()
                                if stream_callback:
                                    try:
                                        stream_callback(line)
                                    except Exception:
                                        pass
                                if captured_bytes < MAX_CAPTURED_BYTES:
                                    captured_stdout.append(line)
                                    captured_bytes += len(line.encode("utf-8", errors="replace"))
                            except queue.Empty:
                                break
                        if isinstance(ret, (int, float)):
                            exit_code = int(ret)
                        elif callable(getattr(process, "wait", None)):
                            try:
                                wait_res = process.wait(timeout=0.1)
                                exit_code = int(wait_res) if isinstance(wait_res, (int, float)) else 0
                            except Exception:
                                exit_code = 0
                        else:
                            exit_code = 0

                        try:
                            if process.stdout and hasattr(process.stdout, "close"):
                                process.stdout.close()
                        except Exception:
                            pass
                        try:
                            if process.stderr and hasattr(process.stderr, "close"):
                                process.stderr.close()
                        except Exception:
                            pass
                        break

                    if lines_read == 0:
                        time.sleep(0.05)

                if timed_out:
                    exit_code = 124
                    timeout_msg = f"\n[ZCF] Execution timed out after {effective_timeout} seconds. Terminating process group...\n"
                    captured_stdout.append(timeout_msg)
                    sys.stdout.write(timeout_msg)
                    sys.stdout.flush()

                    # Terminate entire process hierarchy
                    if os.name != "nt":
                        try:
                            child_pgid = process.pid
                            try:
                                os.killpg(child_pgid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                            time.sleep(0.4)
                            # Unconditionally SIGKILL surviving descendants in PGID even if parent exited
                            try:
                                os.killpg(child_pgid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        except Exception:
                            try:
                                process.kill()
                            except Exception:
                                pass
                    else:
                        try:
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                        except Exception:
                            try:
                                process.kill()
                            except Exception:
                                pass

                    # Explicitly close pipes to unblock reader threads if lingering subprocesses held them open
                    try:
                        if process.stdout and hasattr(process.stdout, "close"):
                            process.stdout.close()
                    except Exception:
                        pass
                    try:
                        if process.stderr and hasattr(process.stderr, "close"):
                            process.stderr.close()
                    except Exception:
                        pass

                    try:
                        process.wait(timeout=2)
                    except Exception:
                        pass
                    reader_thread.join(timeout=0.5)

            except KeyboardInterrupt:
                print("\n[ZCF] Execution interrupted by user.")
                exit_code = 130
            except Exception as e:
                print(f"\n[ZCF] Execution failed to start: {e}")
                exit_code = 1

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
            self.history_mgr.record_run(
                artifact_path=artifact_path,
                artifact_sha256=app.sha256,
                application_name=app.file_name,
                target_format=app.format.value,
                target_architecture=app.architecture.value,
                runtime_id=adapter.get_id(),
                runtime_name=adapter.get_name(),
                execution_mode=plan.execution_mode.value,
                dry_run=False,
                success=exit_code == 0,
                exit_code=exit_code,
                execution_time_seconds=elapsed_seconds,
                sandbox_active=sandbox_active,
                network_isolated=security_policy.isolate_network,
                command=final_cmd,
                stdout=full_output,
                stderr="",
                diagnostics=diagnostics_data,
                environment={"os": env.os_name, "arch": env.architecture, "kernel": env.kernel_version},
            )

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

        finally:
            if display_started:
                display_mgr.stop()
            if hasattr(adapter, "cleanup"):
                adapter.cleanup(app, context)

    def run(
        self,
        artifact_path: str,
        app_args: Optional[List[str]] = None,
        use_sandbox: bool = True,
        allow_unconfined: bool = False,
        dry_run: bool = False,
        force_headless: bool = False,
        auto_install: bool = False,
        timeout: Optional[int] = None,
        allow_network: Optional[bool] = None,
    ) -> int:
        """
        Executes an application through its optimal compatibility pipeline.
        Returns the process exit code.
        """
        result = self.execute_lifecycle(
            artifact_path=artifact_path,
            app_args=app_args,
            use_sandbox=use_sandbox,
            allow_unconfined=allow_unconfined,
            dry_run=dry_run,
            force_headless=force_headless,
            auto_install=auto_install,
            timeout=timeout,
            allow_network=allow_network,
        )
        return result.exit_code
