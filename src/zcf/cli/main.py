"""
Command-Line Interface (CLI) for ZCF.
Provides user-facing commands for inspection, planning, testing, research, diagnostics, sync, and dashboard.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from zcf import __version__
from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.compatibility_db.sync import CompatibilitySyncManager
from zcf.diagnostics.analyzer import DiagnosticEngine
from zcf.diagnostics.remediator import AutomatedRemediator
from zcf.environment.inspector import EnvironmentInspector
from zcf.inspector.inspector import ApplicationInspector
from zcf.planner.engine import CompatibilityPlanner
from zcf.research.engine import CompatibilityResearchEngine
from zcf.runtimes.prefix_manager import WinePrefixManager
from zcf.runtimes.registry import RuntimeRegistry
from zcf.security.controller import SecurityController


def format_header(title: str):
    print(f"\n=======================================================")
    print(f"  {title}")
    print(f"=======================================================")


def cmd_gui(args):
    from zcf.gui.app import launch_gui
    launch_gui()


def cmd_run(args):
    from zcf.execution.runner import ExecutionOrchestrator
    orchestrator = ExecutionOrchestrator()
    try:
        code = orchestrator.run(
            artifact_path=args.artifact_path,
            app_args=args.app_args,
            use_sandbox=not args.no_sandbox,
            force_headless=args.headless,
            auto_install=args.install_deps,
        )
        sys.exit(code)
    except Exception as e:
        print(f"[ZCF Run Error] {e}", file=sys.stderr)
        sys.exit(1)


def cmd_service(args):
    action = args.service_action
    if action == "register-binfmt":
        binfmt_rule = ":zcf-pe:M::MZ::/usr/bin/zcf-runner:PC"
        register_path = "/proc/sys/fs/binfmt_misc/register"
        if os.path.exists(register_path):
            try:
                with open(register_path, "w") as f:
                    f.write(binfmt_rule + "\n")
                print("Registered ZCF binfmt_misc rules successfully.")
            except Exception as e:
                print(f"Failed to register binfmt: {e}", file=sys.stderr)
        else:
            print("binfmt_misc filesystem not mounted at /proc/sys/fs/binfmt_misc.", file=sys.stderr)
    elif action == "cleanup-prefixes":
        mgr = WinePrefixManager()
        cleaned = mgr.cleanup_stale_prefixes(max_age_days=args.max_age_days)
        print(f"Cleaned {cleaned} stale prefix directories.")


def cmd_integrate(args):
    from zcf.desktop.integrator import DesktopIntegrator
    integrator = DesktopIntegrator()
    try:
        path = integrator.integrate(args.artifact_path, custom_name=args.name)
        print(f"Successfully integrated application into desktop menu: {path}")
    except Exception as e:
        print(f"[ZCF Integration Error] {e}", file=sys.stderr)
        sys.exit(1)


def cmd_inspect(args):
    inspector = ApplicationInspector()
    try:
        app = inspector.inspect(args.artifact_path)
        if args.json:
            print(json.dumps(app.to_dict(), indent=2))
        else:
            format_header(f"ZCF Application Inspection: {app.file_name}")
            print(f"  File Path:      {app.artifact_path}")
            print(f"  SHA-256:        {app.sha256}")
            print(f"  Byte Size:      {app.byte_size:,} bytes")
            print(f"  Binary Format:  {app.format.value.upper()}")
            print(f"  Architecture:   {app.architecture.value}")
            print(f"  Subsystem:      {app.subsystem.value}")
            print(f"  Is Managed:     {'Yes (.NET / CLI / Dalvik)' if app.is_managed else 'No (Native)'}")
            if app.runtime_family:
                print(f"  Runtime Family: {app.runtime_family}")
            if app.entry_point:
                print(f"  Entry Point:    {app.entry_point}")
            if app.declared_dependencies:
                dep_sample = ", ".join(app.declared_dependencies[:6])
                more = f" ... and {len(app.declared_dependencies) - 6} more" if len(app.declared_dependencies) > 6 else ""
                print(f"  Dependencies:   {dep_sample}{more}")
            if app.limitations:
                print(f"  Limitations:    {', '.join(app.limitations)}")
    except Exception as e:
        print(f"Error during inspection: {str(e)}", file=sys.stderr)
        sys.exit(1)


def cmd_env(args):
    inspector = EnvironmentInspector()
    try:
        env = inspector.inspect()
        if args.json:
            print(json.dumps(env.to_dict(), indent=2))
        else:
            format_header("ZCF Host Environment Report")
            print(f"  Operating System: {env.os_name.capitalize()} ({env.distribution or 'generic'} {env.release or ''})")
            print(f"  Kernel:           {env.kernel_version}")
            print(f"  CPU Architecture: {env.architecture}")
            print(f"  Logical Cores:    {env.logical_cores}")
            print(f"  Total Memory:     {env.total_memory_mb:,} MB")
            print(f"  Display Server:   {env.display_server.value.upper()}")
            print("\n  Discovered Compatibility Runtimes:")
            for r in env.available_runtimes:
                status_str = f"INSTALLED ({r.version or 'active'})" if r.installed else "NOT INSTALLED"
                print(f"    - {r.name:<36} : {status_str}")
    except Exception as e:
        print(f"Error during environment inspection: {str(e)}", file=sys.stderr)
        sys.exit(1)


def cmd_plan(args):
    app_inspector = ApplicationInspector()
    env_inspector = EnvironmentInspector()
    planner = CompatibilityPlanner()

    try:
        app = app_inspector.inspect(args.artifact_path)
        env = env_inspector.inspect()
        plan = planner.plan(app, env)

        if args.json:
            print(json.dumps(plan.to_dict(), indent=2))
        else:
            format_header(f"ZCF Compatibility Plan: {app.file_name}")
            print(f"  Plan ID:          {plan.plan_id}")
            print(f"  Execution Mode:   {plan.execution_mode.value.upper()}")
            print(f"  Selected Runtime: {plan.selected_runtime_name or 'None'}")
            print(f"  Confidence Score: {plan.confidence_score * 100:.1f}%")
            print(f"\n  Reasoning:")
            print(f"    {plan.reasoning}")

            if plan.satisfied_requirements:
                print("\n  Satisfied Requirements:")
                for req in plan.satisfied_requirements:
                    print(f"    [+] {req}")

            if plan.missing_requirements:
                print("\n  Missing Requirements:")
                for req in plan.missing_requirements:
                    print(f"    [-] {req}")

            if plan.safe_next_steps:
                print("\n  Recommended Next Steps:")
                for step in plan.safe_next_steps:
                    print(f"    > {step}")
    except Exception as e:
        print(f"Error during planning: {str(e)}", file=sys.stderr)
        sys.exit(1)


def cmd_test(args):
    app_inspector = ApplicationInspector()
    env_inspector = EnvironmentInspector()
    registry = RuntimeRegistry()
    planner = CompatibilityPlanner(registry)
    security = SecurityController()

    try:
        security.validate_execution_safety(args.artifact_path)
        app = app_inspector.inspect(args.artifact_path)
        env = env_inspector.inspect()
        plan = planner.plan(app, env)

        format_header(f"ZCF Execution Test: {app.file_name}")
        print(f"  Selected Runtime: {plan.selected_runtime_name}")
        print(f"  Execution Mode:   {plan.execution_mode.value.upper()}")

        if not plan.selected_runtime_id or plan.execution_mode.value == "blocked":
            print(f"\n  Execution Blocked: {plan.reasoning}", file=sys.stderr)
            for req in plan.missing_requirements:
                print(f"  [-] Missing requirement: {req}", file=sys.stderr)
            sys.exit(2)

        adapter = registry.get_adapter(plan.selected_runtime_id)
        if not adapter:
            print(f"Error: Adapter '{plan.selected_runtime_id}' not found in registry", file=sys.stderr)
            sys.exit(1)

        context = adapter.prepare_environment(app)
        result = adapter.execute(app, context, dry_run=args.dry_run)

        print(f"\n  Result Status:    {'SUCCESS' if result.success else 'FAILED'}")
        print(f"  Exit Code:        {result.exit_code}")
        print(f"  Execution Time:   {result.execution_time_seconds:.4f}s")
        if result.stdout:
            print(f"\n  Output:\n{result.stdout.strip()}")
        if result.stderr:
            print(f"\n  Error Output:\n{result.stderr.strip()}")

    except Exception as e:
        print(f"Error during execution test: {str(e)}", file=sys.stderr)
        sys.exit(1)


def cmd_diag(args):
    diag = DiagnosticEngine()
    remediator = AutomatedRemediator()
    app_inspector = ApplicationInspector()
    env_inspector = EnvironmentInspector()

    try:
        with open(args.log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        events = diag.analyze_log(content)
        if args.json:
            print(json.dumps([e.to_dict() for e in events], indent=2))
        else:
            format_header(f"ZCF Diagnostic Log Analysis: {args.log_path}")
            if not events:
                print("  No known failure signatures recognized in log.")
            else:
                print(f"  Detected {len(events)} diagnostic event(s):\n")
                for i, ev in enumerate(events, 1):
                    print(f"  [{i}] Signature:  {ev.signature} (Confidence: {ev.confidence*100:.0f}%)")
                    print(f"      Matched:    {ev.matched_text}")
                    print(f"      Root Cause: {ev.root_cause}")
                    print(f"      Action:     {ev.remediation}\n")

                # If target artifact is provided, synthesize remediation plan
                if hasattr(args, "target") and args.target and os.path.exists(args.target):
                    app = app_inspector.inspect(args.target)
                    env = env_inspector.inspect()
                    rem_plan = remediator.synthesize(app, env, events)
                    format_header("Automated Remediation Actions")
                    if rem_plan.package_install_commands:
                        print("  Suggested Package Installation Command(s):")
                        for cmd in rem_plan.package_install_commands:
                            print(f"    $ {cmd}")
                    if rem_plan.dll_overrides:
                        print(f"  Wine DLL Overrides: {rem_plan.dll_overrides}")
                    if rem_plan.wrapper_prefix:
                        print(f"  Command Wrapper Prefix: {rem_plan.wrapper_prefix}")
    except Exception as e:
        print(f"Error during log analysis: {str(e)}", file=sys.stderr)
        sys.exit(1)


def cmd_research(args):
    engine = CompatibilityResearchEngine()
    try:
        with open(args.log_path, "r", encoding="utf-8", errors="ignore") as f:
            log_content = f.read()

        format_header(f"ZCF Compatibility Research Workflow: {os.path.basename(args.artifact_path)}")
        case = engine.investigate(args.artifact_path, log_content)

        print(f"  Case ID:          {case.case_id}")
        print(f"  Target SHA-256:   {case.target_sha256}")
        print(f"  Outcome Status:   {case.outcome_status.upper()}")
        if case.rea_evidence_id:
            print(f"  REA Evidence ID:  {case.rea_evidence_id}")

        print(f"\n  Formulated Hypotheses ({len(case.hypotheses)}):")
        for h in case.hypotheses:
            print(f"    [{h.hypothesis_id}] {h.statement} (Confidence: {h.confidence*100:.0f}%)")
            print(f"        Basis: {h.basis}")

        if case.verified_workarounds:
            print(f"\n  Verified Workarounds ({len(case.verified_workarounds)}):")
            for w in case.verified_workarounds:
                print(f"    [+] {w['issue']}: {w['solution']}")
                print(f"        Automated Apply: {w.get('automated_apply', False)}")

        print("\n  [Knowledge Base] Record successfully cataloged into local database.")
    except Exception as e:
        print(f"Error during research investigation: {str(e)}", file=sys.stderr)
        sys.exit(1)


def cmd_db(args):
    db = CompatibilityDatabase()
    sync = CompatibilitySyncManager(db)

    if args.action == "list":
        entries = db.list_all()
        format_header(f"ZCF Compatibility Database ({len(entries)} entries)")
        for entry in entries:
            print(f"  [{entry.entry_id}] {entry.application_name} ({entry.target_format.upper()} {entry.target_architecture})")
            print(f"    Status:      {entry.status.value}")
            print(f"    SHA-256:     {entry.target_sha256[:16]}...")
            print(f"    Recommended: {entry.recommended_runtime or 'None'}\n")
    elif args.action == "show":
        entry = db.get_by_id(args.id)
        if entry:
            print(json.dumps(entry.to_dict(), indent=2))
        else:
            print(f"Entry not found: {args.id}", file=sys.stderr)
            sys.exit(1)
    elif args.action == "export":
        out = sync.export_bundle(args.output or "zcf_evidence_bundle.json")
        print(f"Exported compatibility evidence bundle to: {out}")
    elif args.action == "import":
        cnt = sync.import_bundle(args.file)
        print(f"Imported and reconciled {cnt} compatibility records.")


def cmd_dashboard(args):
    env = EnvironmentInspector().inspect()
    db = CompatibilityDatabase()
    entries = db.list_all()

    print("\n" + "=" * 62)
    print("      ZYNTRIX COMPATIBILITY FABRIC (ZCF) - DASHBOARD")
    print("=" * 62)
    print(f"  Platform:         {env.os_name.capitalize()} {env.distribution or ''} ({env.architecture})")
    print(f"  Kernel Release:   {env.kernel_version[:35]}")
    print(f"  Active Display:   {env.display_server.value.upper()}")
    print(f"  Hardware Cores:   {env.logical_cores} Logical CPUs | Memory: {env.total_memory_mb:,} MB")
    print("-" * 62)
    print("  RUNTIME ORCHESTRATION STATUS:")
    for r in env.available_runtimes:
        symbol = "[*]" if r.installed else "[ ]"
        ver = f"({r.version})" if r.version else ("Ready" if r.installed else "Missing")
        print(f"    {symbol} {r.name:<34} : {ver}")
    print("-" * 62)
    print("  KNOWLEDGE BASE & RESEARCH STATUS:")
    print(f"    Cataloged Application Profiles : {len(entries)}")
    verified_count = sum(1 for e in entries if "compatible" in e.status.value)
    print(f"    Verified Compatible Entries    : {verified_count}")
    print(f"    REA Integration                : ACTIVE (Evidence Graphs Ready)")
    print("=" * 62 + "\n")


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(
        prog="zcf",
        description="Zyntrix Compatibility Fabric (ZCF) - Universal Application Compatibility Engine",
    )
    parser.add_argument("--version", action="version", version=f"ZCF {__version__} (Apache-2.0)")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Show system dashboard and compatibility status")
    p_dash.set_defaults(func=cmd_dashboard)

    # gui
    p_gui = subparsers.add_parser("gui", help="Open the graphical ZCF Control Center")
    p_gui.set_defaults(func=cmd_gui)

    # run
    p_run = subparsers.add_parser("run", help="Execute application through optimal runtime with sandboxing")
    p_run.add_argument("artifact_path", help="Path to executable binary")
    p_run.add_argument("app_args", nargs="*", help="Arguments to pass to target application")
    p_run.add_argument("--no-sandbox", action="store_true", help="Disable Bubblewrap container isolation")
    p_run.add_argument("--headless", action="store_true", help="Force virtual Xvfb display server")
    p_run.add_argument("--install-deps", action="store_true", help="Automatically install missing dependencies")
    p_run.set_defaults(func=cmd_run)

    # integrate
    p_int = subparsers.add_parser("integrate", help="Add application to Linux desktop application menu")
    p_int.add_argument("artifact_path", help="Path to application binary to integrate")
    p_int.add_argument("--name", help="Custom display name in application menu")
    p_int.set_defaults(func=cmd_integrate)

    # service
    p_svc = subparsers.add_parser("service", help="Manage system integration and background maintenance")
    p_svc.add_argument("service_action", choices=["register-binfmt", "unregister-binfmt", "cleanup-prefixes"], help="Action to perform")
    p_svc.add_argument("--max-age-days", type=int, default=30, help="Max prefix age in days for cleanup")
    p_svc.set_defaults(func=cmd_service)

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect an application binary or script")
    p_inspect.add_argument("artifact_path", help="Path to executable or script")
    p_inspect.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_inspect.set_defaults(func=cmd_inspect)

    # env
    p_env = subparsers.add_parser("env", help="Inspect host environment and compatibility runtimes")
    p_env.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_env.set_defaults(func=cmd_env)

    # plan
    p_plan = subparsers.add_parser("plan", help="Generate compatibility plan for an application")
    p_plan.add_argument("artifact_path", help="Path to target executable")
    p_plan.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_plan.set_defaults(func=cmd_plan)

    # test
    p_test = subparsers.add_parser("test", help="Test application compatibility execution")
    p_test.add_argument("artifact_path", help="Path to target executable")
    p_test.add_argument("--dry-run", action="store_true", default=True, help="Perform safe dry-run plan test")
    p_test.set_defaults(func=cmd_test)

    # diag
    p_diag = subparsers.add_parser("diag", help="Analyze failure log and recommend remediations")
    p_diag.add_argument("log_path", help="Path to error log file")
    p_diag.add_argument("--target", help="Optional path to target application for automated remediation plan")
    p_diag.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_diag.set_defaults(func=cmd_diag)

    # research
    p_research = subparsers.add_parser("research", help="Run 11-step compatibility research workflow")
    p_research.add_argument("artifact_path", help="Path to application binary")
    p_research.add_argument("log_path", help="Path to execution error log")
    p_research.set_defaults(func=cmd_research)

    # db
    p_db = subparsers.add_parser("db", help="Query or inspect the compatibility knowledge base")
    p_db.add_argument("action", choices=["list", "show", "export", "import"], help="Action to perform")
    p_db.add_argument("--id", help="Entry ID (for 'show' action)")
    p_db.add_argument("--output", help="Output file path (for 'export')")
    p_db.add_argument("--file", help="Input file path (for 'import')")
    p_db.set_defaults(func=cmd_db)

    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_dashboard(args)


if __name__ == "__main__":
    main()
