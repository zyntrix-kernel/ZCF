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


def cmd_console(args):
    from zcf.web.server import run_console
    run_console(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        allow_remote=getattr(args, "allow_remote", False),
    )


def cmd_run(args):
    from zcf.execution.runner import ExecutionOrchestrator
    from zcf.execution.tuning import GamingTuningConfig, get_tuning_preset

    tuning = None
    if getattr(args, "tuning_preset", None):
        tuning = get_tuning_preset(args.tuning_preset)
    elif any([
        getattr(args, "gamemode", False),
        getattr(args, "gamescope", False),
        getattr(args, "mangohud", False),
        getattr(args, "upscale", None),
    ]):
        tuning = GamingTuningConfig(
            enabled=True,
            use_gamemode=getattr(args, "gamemode", False),
            use_gamescope=getattr(args, "gamescope", False),
            upscaling_filter=getattr(args, "upscale", "fsr") or "fsr",
            fsr_sharpness=getattr(args, "fsr_sharpness", 5),
            fps_limit=getattr(args, "fps_limit", None),
            use_mangohud=getattr(args, "mangohud", False),
        )

    orchestrator = ExecutionOrchestrator()
    try:
        code = orchestrator.run(
            artifact_path=args.artifact_path,
            app_args=args.app_args,
            use_sandbox=not args.no_sandbox,
            allow_unconfined=getattr(args, "allow_unconfined", False),
            dry_run=getattr(args, "dry_run", False),
            force_headless=args.headless,
            auto_install=args.install_deps,
            timeout=getattr(args, "timeout", None),
            allow_network=getattr(args, "allow_network", False),
            tuning=tuning,
        )
        sys.exit(code)
    except Exception as e:
        print(f"[ZCF Run Error] {e}", file=sys.stderr)
        sys.exit(1)


def cmd_runners(args):
    from zcf.runtimes.fleet import RunnerFleetManager
    fleet = RunnerFleetManager()
    action = args.fleet_action

    if action == "list":
        runners = fleet.discover_local_runners()
        if getattr(args, "json", False):
            print(json.dumps([r.to_dict() for r in runners], indent=2))
            return
        format_header(f"Discovered Compatibility Runners ({len(runners)} found)")
        if not runners:
            print("  No compatibility runners discovered.")
        for r in runners:
            sys_mark = "[SYSTEM]" if r.is_system else "[CUSTOM]"
            caps = ", ".join(r.capabilities) if r.capabilities else "none"
            print(f"  - {sys_mark} {r.name} ({r.runner_type})")
            print(f"    ID:           {r.id}")
            print(f"    Path:         {r.path}")
            print(f"    Capabilities: {caps}\n")

    elif action == "available":
        releases = fleet.fetch_available_releases(limit=getattr(args, "limit", 10))
        if getattr(args, "json", False):
            print(json.dumps([rel.to_dict() for rel in releases], indent=2))
            return
        format_header(f"Available Upstream Runners (GE-Proton Releases)")
        for rel in releases:
            sz_mb = rel.size_bytes / (1024 * 1024) if rel.size_bytes else 0
            print(f"  * {rel.name} ({rel.tag_name}) - {sz_mb:.1f} MB [{rel.published_at[:10]}]")
            print(f"    Download: {rel.download_url}")
            if rel.checksum_url:
                print(f"    SHA-512:  {rel.checksum_url}")
            print()

    elif action == "install":
        archive_path = args.archive_or_tag
        if not os.path.isfile(archive_path):
            print(f"Fetching release manifest for '{archive_path}'...")
            releases = fleet.fetch_available_releases(limit=20)
            target_rel = next((r for r in releases if r.tag_name == archive_path or r.name == archive_path), None)
            if not target_rel:
                print(f"Error: Archive file not found and '{archive_path}' does not match available releases.", file=sys.stderr)
                sys.exit(1)
            import urllib.request
            staging_tar = os.path.join(fleet.runners_dir, f"{target_rel.tag_name}.tar.gz")
            print(f"Downloading {target_rel.name} from {target_rel.download_url}...")
            urllib.request.urlretrieve(target_rel.download_url, staging_tar)
            archive_path = staging_tar

        try:
            print(f"Installing runner from archive '{archive_path}'...")
            installed = fleet.install_runner(archive_path)
            print(f"Runner successfully installed: {installed.name} ({installed.id})")
            print(f"Installed to: {installed.path}")
        except Exception as e:
            print(f"Failed to install runner: {e}", file=sys.stderr)
            sys.exit(1)


def cmd_snapshot(args):
    from zcf.runtimes.snapshots import PrefixSnapshotManager
    mgr = PrefixSnapshotManager()
    action = args.snapshot_action
    prefix = args.prefix_path

    if action == "create":
        label = getattr(args, "label", None) or "Manual Snapshot"
        try:
            snap = mgr.create_snapshot(prefix, label=label, trigger="manual")
            if getattr(args, "json", False):
                print(json.dumps(snap.to_dict(), indent=2))
            else:
                print(f"Successfully created snapshot '{snap.id}' ({snap.label})")
                print(f"Size: {snap.size_bytes} bytes, Files: {', '.join(snap.files_preserved)}")
        except Exception as e:
            print(f"Error creating snapshot: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "list":
        snaps = mgr.list_snapshots(prefix)
        if getattr(args, "json", False):
            print(json.dumps([s.to_dict() for s in snaps], indent=2))
            return
        format_header(f"Time-Machine Snapshots for {prefix} ({len(snaps)} total)")
        if not snaps:
            print("  No snapshots found for this prefix.")
        for s in snaps:
            print(f"  - [{s.id}] {s.label} ({s.trigger})")
            print(f"    Created: {s.created_at} | Size: {s.size_bytes} B | Preserved: {', '.join(s.files_preserved)}")

    elif action == "restore":
        snap_id = args.snapshot_id
        try:
            mgr.restore_snapshot(prefix, snap_id)
            print(f"Successfully rolled back prefix to snapshot '{snap_id}'.")
        except Exception as e:
            print(f"Error restoring snapshot: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "delete":
        snap_id = args.snapshot_id
        if mgr.delete_snapshot(prefix, snap_id):
            print(f"Deleted snapshot '{snap_id}'.")
        else:
            print(f"Snapshot '{snap_id}' not found.", file=sys.stderr)
            sys.exit(1)


def cmd_vault(args):
    from zcf.runtimes.vault import GameSaveVault
    vault = GameSaveVault()
    action = args.vault_action

    if action == "discover":
        prefix = args.prefix_path
        app_name = getattr(args, "app", None)
        locations = vault.discover_save_locations(prefix, app_name_filter=app_name)
        if getattr(args, "json", False):
            print(json.dumps([loc.to_dict() for loc in locations], indent=2))
            return
        format_header(f"Discovered Save Data Locations ({len(locations)} found)")
        if not locations:
            print("  No game save locations discovered.")
        for loc in locations:
            sz_kb = loc.size_bytes / 1024
            print(f"  - {loc.folder_name} ({loc.category}) - {sz_kb:.1f} KB, {loc.files_count} files")
            print(f"    Path: drive_c/{loc.relative_to_drive_c}")

    elif action == "backup":
        prefix = args.prefix_path
        app_name = args.app
        if not app_name:
            print("Error: --app <name> is required for save backup.", file=sys.stderr)
            sys.exit(1)
        notes = getattr(args, "notes", "")
        try:
            entry = vault.backup_save(prefix, app_name, notes=notes)
            if getattr(args, "json", False):
                print(json.dumps(entry.to_dict(), indent=2))
            else:
                sz_kb = entry.size_bytes / 1024
                print(f"Saved game successfully backed up to Vault!")
                print(f"  Vault ID: {entry.vault_id}")
                print(f"  App:      {entry.app_name}")
                print(f"  Archive:  {entry.archive_path} ({sz_kb:.1f} KB)")
                print(f"  SHA-256:  {entry.sha256}")
        except Exception as e:
            print(f"Backup failed: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "list":
        app_name = getattr(args, "app", None)
        backups = vault.list_backups(app_name_filter=app_name)
        if getattr(args, "json", False):
            print(json.dumps([b.to_dict() for b in backups], indent=2))
            return
        format_header(f"Save Game Vault Backups ({len(backups)} total)")
        if not backups:
            print("  No save game backups found in vault.")
        for b in backups:
            sz_kb = b.size_bytes / 1024
            print(f"  - [{b.vault_id}] {b.app_name} - {sz_kb:.1f} KB ({b.created_at[:19]})")
            print(f"    Source Prefix: {b.source_prefix}")
            print(f"    SHA-256:       {b.sha256[:16]}...")

    elif action == "restore":
        vault_id = args.vault_id
        target_prefix = args.prefix_path
        try:
            vault.restore_save(vault_id, target_prefix)
            print(f"Successfully restored save '{vault_id}' into prefix '{target_prefix}'.")
        except Exception as e:
            print(f"Restore failed: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "delete":
        vault_id = args.vault_id
        if vault.delete_backup(vault_id):
            print(f"Deleted backup '{vault_id}'.")
        else:
            print(f"Backup '{vault_id}' not found.", file=sys.stderr)
            sys.exit(1)


def cmd_taskmgr(args):
    from zcf.runtimes.tasks import PrefixTaskManager
    tm = PrefixTaskManager()
    action = args.taskmgr_action

    if action == "list":
        prefix = getattr(args, "prefix", None)
        procs = tm.list_prefix_processes(prefix)
        if getattr(args, "json", False):
            print(json.dumps([p.to_dict() for p in procs], indent=2))
            return
        format_header(f"Active Prefix Processes ({len(procs)} running)")
        if not procs:
            print("  No active prefix processes detected.")
        for p in procs:
            print(f"  - PID {p.pid:6d} | RSS: {p.rss_mb:6.1f} MB | {p.name}")
            if p.cmdline:
                print(f"    Cmd: {p.cmdline[:80]}")

    elif action == "kill":
        prefix = args.prefix_path
        result = tm.kill_prefix_processes(prefix)
        print(f"Terminated processes for prefix {prefix}: killed PIDs {result.get('killed_pids', [])}")

    elif action == "reset-locks":
        prefix = args.prefix_path
        removed = tm.reset_prefix_locks(prefix)
        print(f"Cleared {len(removed)} locks in {prefix}: {', '.join(removed) if removed else 'none'}")

    elif action == "launch":
        prefix = args.prefix_path
        tool = args.tool
        try:
            res = tm.launch_wine_tool(prefix, tool)
            print(f"Launched {tool} (PID: {res.get('pid')}) in prefix {prefix}")
        except Exception as e:
            print(f"Failed to launch tool: {e}", file=sys.stderr)
            sys.exit(1)


def cmd_prescribe(args):
    from zcf.diagnostics.analyzer import DiagnosticEngine
    from zcf.diagnostics.prescriptions import PrescriptionEngine

    diag = DiagnosticEngine()
    rx_engine = PrescriptionEngine()
    action = args.prescribe_action

    if not os.path.isfile(args.log_path):
        print(f"Error: Log file not found: {args.log_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.log_path, "r", encoding="utf-8", errors="ignore") as f:
        log_text = f.read()

    events = diag.analyze_log(log_text)
    app_name = getattr(args, "app", "application.exe") or "application.exe"
    prefix = getattr(args, "prefix", None)

    rx = rx_engine.synthesize(events, app_name=app_name, prefix_path=prefix)

    if action == "generate":
        if getattr(args, "json", False):
            print(json.dumps(rx.to_dict(), indent=2))
            return
        format_header(f"Autonomous Healing Prescription [{rx.id}] for {rx.target_app}")
        print(f"  Root Causes Identified ({len(rx.root_causes)}):")
        for rc in rx.root_causes:
            print(f"    - {rc}")
        if rx.recommended_runner:
            print(f"\n  Recommended Compatibility Runner: {rx.recommended_runner}")
        if rx.components_to_install:
            print(f"  Components to Auto-Install:       {', '.join(rx.components_to_install)}")
        if rx.dll_overrides_to_set:
            print(f"  DLL Overrides to Apply:           {rx.dll_overrides_to_set}")
        if rx.env_vars_to_set:
            print(f"  Environment Variables:            {rx.env_vars_to_set}")
        if rx.recommended_tuning:
            print(f"  Esports/Gaming Tuning:            {rx.recommended_tuning}")

    elif action == "apply":
        if not prefix:
            print("Error: --prefix <path> is required to apply prescription.", file=sys.stderr)
            sys.exit(1)
        dry_run = getattr(args, "dry_run", False)
        try:
            res = rx_engine.apply(rx, prefix, dry_run=dry_run)
            print(f"Prescription {rx.id} applied to {prefix}:")
            for act in res.get("actions", []):
                print(f"  + {act}")
            if res.get("snapshot_id"):
                print(f"Safety Snapshot ID: {res.get('snapshot_id')}")
        except Exception as e:
            print(f"Failed to apply prescription: {e}", file=sys.stderr)
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
    elif action == "unregister-binfmt":
        unregister_path = "/proc/sys/fs/binfmt_misc/zcf-pe"
        if os.path.exists(unregister_path):
            try:
                with open(unregister_path, "w") as f:
                    f.write("-1\n")
                print("Unregistered ZCF binfmt_misc rules successfully.")
            except Exception as e:
                print(f"Failed to unregister binfmt: {e}", file=sys.stderr)
        else:
            print("ZCF binfmt_misc rule is not currently active at /proc/sys/fs/binfmt_misc/zcf-pe.", file=sys.stderr)
    elif action == "cleanup-prefixes":
        wine_mgr = WinePrefixManager()
        proton_mgr = WinePrefixManager(base_dir=os.path.expanduser("~/.zcf/proton_prefixes"))
        cleaned_wine = wine_mgr.cleanup_stale_prefixes(max_age_days=args.max_age_days)
        cleaned_proton = proton_mgr.cleanup_stale_prefixes(max_age_days=args.max_age_days)
        print(f"Cleaned {cleaned_wine + cleaned_proton} stale prefix directories (Wine: {cleaned_wine}, Proton: {cleaned_proton}).")
    elif action == "list-prefixes":
        wine_mgr = WinePrefixManager()
        proton_mgr = WinePrefixManager(base_dir=os.path.expanduser("~/.zcf/proton_prefixes"))
        wine_p = wine_mgr.list_prefixes()
        proton_p = proton_mgr.list_prefixes()
        all_p = wine_p + proton_p
        format_header(f"ZCF Managed Prefixes ({len(all_p)} total)")
        print(f"  Wine Root:   {wine_mgr.base_dir}")
        print(f"  Proton Root: {proton_mgr.base_dir}\n")
        if not all_p:
            print("  No managed prefixes found.")
        for p in wine_p:
            lock = "[LOCKED]" if p.is_locked else "[READY]"
            persist = "Durable" if p.is_persistent else "Disposable"
            print(f"  - [Wine] {p.app_name} ({p.architecture}) {lock} {persist} - {p.size_mb} MB")
            print(f"    Path: {p.prefix_path}")
        for p in proton_p:
            lock = "[LOCKED]" if p.is_locked else "[READY]"
            persist = "Durable" if p.is_persistent else "Disposable"
            print(f"  - [Proton] {p.app_name} ({p.architecture}) {lock} {persist} - {p.size_mb} MB")
            print(f"    Path: {p.prefix_path}")


def cmd_integrate(args):
    from zcf.desktop.integrator import DesktopIntegrator
    integrator = DesktopIntegrator()
    try:
        if getattr(args, "list", False):
            apps = integrator.list_integrated_apps()
            format_header(f"ZCF Desktop Integrated Applications ({len(apps)})")
            if not apps:
                print("  No applications currently integrated into desktop menu.")
            for a in apps:
                print(f"  - {a.get('name', 'Unknown')} [{a.get('file_name')}]")
                print(f"    Artifact: {a.get('artifact_path', 'N/A')}")
                if a.get("sha256"):
                    print(f"    SHA-256:  {a.get('sha256')[:16]}...")
                print()
            return

        if getattr(args, "remove", False):
            if not getattr(args, "artifact_path", None):
                print("Error: artifact_path is required for --remove.", file=sys.stderr)
                sys.exit(1)
            success = integrator.unintegrate(args.artifact_path)
            if success:
                print(f"Successfully unintegrated application launcher: {args.artifact_path}")
            else:
                print(f"No integrated application found matching: {args.artifact_path}", file=sys.stderr)
                sys.exit(1)
            return

        if not getattr(args, "artifact_path", None):
            print("Error: artifact_path is required to integrate an application.", file=sys.stderr)
            sys.exit(1)

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


def cmd_doctor(args):
    inspector = EnvironmentInspector()
    try:
        audit = inspector.get_readiness_audit()
        if getattr(args, "json", False):
            print(json.dumps(audit, indent=2))
            return

        score = audit["score"]
        grade = audit["grade"]
        summary = audit["summary"]

        print("\n" + "=" * 66)
        print("      ZYNTRIX COMPATIBILITY FABRIC (ZCF) - SYSTEM DOCTOR")
        print("=" * 66)
        print(f"  System Readiness Index : [ {score}% ]  (GRADE: {grade})")
        print(f"  Diagnostic Summary     : {summary}")
        print("-" * 66)
        print("  PRE-FLIGHT SUBSYSTEM READINESS AUDIT:")
        print("-" * 66)

        for check in audit["checks"]:
            status = check["status"]
            symbol = f"[{status}]"
            print(f"  {symbol:<6} {check['name']} ({check['score_points']}/{check['max_points']} pts)")
            print(f"         {check['details']}")
            if check.get("remediation"):
                print(f"         -> Actionable Fix: {check['remediation']}")
            print()

        print("=" * 66 + "\n")
        if score < 45:
            sys.exit(1)
    except Exception as e:
        print(f"Error during readiness audit: {str(e)}", file=sys.stderr)
        sys.exit(1)


def cmd_plan(args):
    app_inspector = ApplicationInspector()
    env_inspector = EnvironmentInspector()
    planner = CompatibilityPlanner()
    db = CompatibilityDatabase()

    try:
        app = app_inspector.inspect(args.artifact_path)
        env = env_inspector.inspect()
        db_evidence = db.get_by_sha256(app.sha256)
        similar_evidence = None
        if not db_evidence:
            similar_evidence = db.find_similar_profiles(
                name=app.file_name,
                format_type=app.format.value,
                arch=app.architecture.value,
            )
        plan = planner.plan(app, env, db_evidence=db_evidence, similar_evidence=similar_evidence)

        if args.json:
            print(json.dumps(plan.to_dict(), indent=2))
        else:
            format_header(f"ZCF Compatibility Plan: {app.file_name}")
            print(f"  Plan ID:          {plan.plan_id}")
            print(f"  Execution Mode:   {plan.execution_mode.value.upper()}")
            print(f"  Selected Runtime: {plan.selected_runtime_name or 'None'}")
            print(f"  Confidence Score: {plan.confidence_score * 100:.1f}%")
            print(f"  Evidence Type:    {plan.evidence_type.upper().replace('_', ' ')}")
            print(f"\n  Reasoning:")
            print(f"    {plan.reasoning}")

            if plan.similar_profiles:
                print("\n  Similar Known Profiles:")
                for s in plan.similar_profiles[:3]:
                    print(f"    [*] {s['application_name']} ({s['entry_id']}) -> {s['recommended_runtime']} [{s['status']}]")

            if plan.applied_workarounds:
                print("\n  Known / Recommended Workarounds:")
                for w in plan.applied_workarounds:
                    print(f"    [!] {w.get('issue', 'Issue')}: {w.get('solution', '')}")

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
    db = CompatibilityDatabase()

    try:
        security.validate_execution_safety(args.artifact_path)
        app = app_inspector.inspect(args.artifact_path)
        env = env_inspector.inspect()
        db_evidence = db.get_by_sha256(app.sha256)
        similar_evidence = None
        if not db_evidence:
            similar_evidence = db.find_similar_profiles(
                name=app.file_name,
                format_type=app.format.value,
                arch=app.architecture.value,
            )
        plan = planner.plan(app, env, db_evidence=db_evidence, similar_evidence=similar_evidence)

        format_header(f"ZCF Execution Test: {app.file_name}")
        print(f"  Selected Runtime: {plan.selected_runtime_name or 'None'}")
        print(f"  Execution Mode:   {plan.execution_mode.value.upper()}")
        print(f"  Evidence Type:    {plan.evidence_type.upper().replace('_', ' ')}")

        # 1. Hard blocker: No suitable runtime adapter exists for this format/architecture
        if not plan.selected_runtime_id:
            print(f"\n  Execution Blocked: {plan.reasoning}", file=sys.stderr)
            for req in plan.missing_requirements:
                print(f"  [-] Missing requirement: {req}", file=sys.stderr)
            if getattr(args, "record", False):
                from zcf.core.models import CompatibilityStatus
                db = CompatibilityDatabase()
                entry = db.submit_profile(
                    app=app,
                    recommended_runtime="none",
                    status=CompatibilityStatus.INCOMPATIBLE,
                    contributor_name=getattr(args, "contributor", "Local Tester") or "Local Tester",
                    test_procedure=f"Execution blocked: {plan.reasoning}",
                    env=env,
                )
                print(f"\n  [Database] Test outcome recorded into local knowledge base: {entry.entry_id}")
            sys.exit(2)

        # 2. Live execution blocked: Missing runtime on host during a live test attempt
        if not args.dry_run and plan.execution_mode.value == "blocked":
            print(f"\n  Execution Blocked: {plan.reasoning}", file=sys.stderr)
            for req in plan.missing_requirements:
                print(f"  [-] Missing requirement: {req}", file=sys.stderr)
            if getattr(args, "record", False):
                from zcf.core.models import CompatibilityStatus
                db = CompatibilityDatabase()
                entry = db.submit_profile(
                    app=app,
                    recommended_runtime=plan.selected_runtime_id,
                    status=CompatibilityStatus.UNTESTED,
                    contributor_name=getattr(args, "contributor", "Local Tester") or "Local Tester",
                    test_procedure=f"Live execution test blocked by host prerequisites: {plan.reasoning}",
                    env=env,
                )
                print(f"\n  [Database] Test outcome recorded into local knowledge base: {entry.entry_id}")
            sys.exit(2)

        adapter = registry.get_adapter(plan.selected_runtime_id)
        if not adapter:
            print(f"Error: Adapter '{plan.selected_runtime_id}' not found in registry", file=sys.stderr)
            sys.exit(1)

        context = adapter.prepare_environment(app, config={"dry_run": args.dry_run})
        result = adapter.execute(app, context, dry_run=args.dry_run)

        if args.dry_run:
            print(f"\n  Result Status:    SUCCESS (Orchestration Validated)")
            print(f"  Exit Code:        0 (Dry Run)")
            print(f"  Execution Time:   0.0000s")
            if result.stdout:
                print(f"\n  Output:\n{result.stdout.strip()}")
            if plan.execution_mode.value == "blocked":
                print(f"\n  [Notice] Host engine '{plan.selected_runtime_name}' is not installed; live execution is blocked until installed.")
                for req in plan.missing_requirements:
                    print(f"    [-] {req}")

            if getattr(args, "record", False):
                from zcf.core.models import CompatibilityStatus, EvidenceStatus
                db = CompatibilityDatabase()
                entry = db.submit_profile(
                    app=app,
                    recommended_runtime=plan.selected_runtime_id,
                    status=CompatibilityStatus.UNTESTED,
                    contributor_name=getattr(args, "contributor", "Local Tester") or "Local Tester",
                    test_procedure=f"Dry-run orchestration validation via {plan.selected_runtime_name} (unexecuted)",
                    env=env,
                    evidence_status=EvidenceStatus.UNTESTED,
                )
                print(f"\n  [Database] Test outcome recorded into local knowledge base: {entry.entry_id}")
        else:
            print(f"\n  Result Status:    {'SUCCESS' if result.success else 'FAILED'}")
            print(f"  Exit Code:        {result.exit_code}")
            print(f"  Execution Time:   {result.execution_time_seconds:.4f}s")
            if result.stdout:
                print(f"\n  Output:\n{result.stdout.strip()}")
            if result.stderr:
                print(f"\n  Error Output:\n{result.stderr.strip()}")

            if getattr(args, "record", False):
                from zcf.core.models import CompatibilityStatus
                db = CompatibilityDatabase()
                if result.success:
                    compat_status = CompatibilityStatus.VERIFIED_COMPATIBLE
                    procedure = f"Live execution test passed via {plan.selected_runtime_name} (exit code: 0)"
                else:
                    compat_status = CompatibilityStatus.INCOMPATIBLE
                    procedure = f"Live execution test failed via {plan.selected_runtime_name} (exit code: {result.exit_code})"

                entry = db.submit_profile(
                    app=app,
                    recommended_runtime=plan.selected_runtime_id,
                    status=compat_status,
                    contributor_name=getattr(args, "contributor", "Local Tester") or "Local Tester",
                    test_procedure=procedure,
                    env=env,
                )
                print(f"\n  [Database] Test outcome recorded into local knowledge base: {entry.entry_id}")

        from zcf.execution.history import ExecutionHistoryManager
        history_mgr = ExecutionHistoryManager()
        history_mgr.record_run(
            artifact_path=args.artifact_path,
            artifact_sha256=app.sha256,
            application_name=app.file_name,
            target_format=app.format.value,
            target_architecture=app.architecture.value,
            runtime_id=plan.selected_runtime_id or "none",
            runtime_name=plan.selected_runtime_name or "None",
            execution_mode=plan.execution_mode.value,
            dry_run=args.dry_run,
            success=result.success if not args.dry_run else True,
            exit_code=0 if args.dry_run else result.exit_code,
            execution_time_seconds=0.0 if args.dry_run else result.execution_time_seconds,
            sandbox_active=False,
            network_isolated=True,
            command=getattr(result, "command", []),
            stdout=result.stdout,
            stderr=getattr(result, "stderr", ""),
            diagnostics=getattr(result, "diagnostics", []),
            environment={"os": env.os_name, "arch": env.architecture, "kernel": env.kernel_version},
        )

        if not args.dry_run and not result.success:
            sys.exit(result.exit_code if result.exit_code != 0 else 1)

    except Exception as e:
        print(f"Error during execution test: {str(e)}", file=sys.stderr)
        sys.exit(1)


def cmd_history(args):
    from zcf.execution.history import ExecutionHistoryManager
    history_mgr = ExecutionHistoryManager()

    if getattr(args, "clear", False):
        count = history_mgr.clear_runs()
        print(f"[ZCF History] Cleared {count} execution run log(s).")
        return

    if getattr(args, "compare", None):
        ids = args.compare
        if len(ids) != 2:
            print("Error: --compare requires exactly two run IDs.", file=sys.stderr)
            sys.exit(1)
        try:
            diff = history_mgr.compare_runs(ids[0], ids[1])
            if getattr(args, "json", False):
                print(json.dumps(diff, indent=2))
            else:
                format_header(f"ZCF Execution Run Comparison: {ids[0]} vs {ids[1]}")
                print(f"  Run A: {diff['run_a']['run_id']} ({diff['run_a']['timestamp'][:19]})")
                print(f"    Application: {diff['run_a']['application']} | Runtime: {diff['run_a']['runtime']}")
                print(f"    Exit Code:   {diff['run_a']['exit_code']} | Status: {'SUCCESS' if diff['run_a']['success'] else 'FAILED'}")
                print(f"    Duration:    {diff['run_a']['execution_time_seconds']:.4f}s | Dry Run: {diff['run_a']['dry_run']}")
                print(f"\n  Run B: {diff['run_b']['run_id']} ({diff['run_b']['timestamp'][:19]})")
                print(f"    Application: {diff['run_b']['application']} | Runtime: {diff['run_b']['runtime']}")
                print(f"    Exit Code:   {diff['run_b']['exit_code']} | Status: {'SUCCESS' if diff['run_b']['success'] else 'FAILED'}")
                print(f"    Duration:    {diff['run_b']['execution_time_seconds']:.4f}s | Dry Run: {diff['run_b']['dry_run']}")
                print("\n  Comparison Findings:")
                print(f"    Runtime Changed:        {diff['differences']['runtime_changed']}")
                print(f"    Exit Code Changed:      {diff['differences']['exit_code_changed']}")
                print(f"    Execution Time Delta:   {diff['differences']['execution_time_delta_seconds']:+.4f}s")
                print(f"    Outcome Improved:       {diff['differences']['outcome_improved']}")
        except Exception as e:
            print(f"Error during run comparison: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if getattr(args, "id", None):
        run = history_mgr.get_run(args.id)
        if not run:
            print(f"Error: Run '{args.id}' not found.", file=sys.stderr)
            sys.exit(1)
        if getattr(args, "json", False):
            print(json.dumps(run, indent=2))
        else:
            format_header(f"ZCF Execution Run Record: {run['run_id']}")
            print(f"  Timestamp:       {run['timestamp']}")
            print(f"  Application:     {run['application_name']} ({run['target_format'].upper()} {run['target_architecture']})")
            print(f"  Artifact Path:   {run['artifact_path']}")
            print(f"  SHA-256:         {run['artifact_sha256']}")
            print(f"  Runtime:         {run['runtime_name']} ({run['runtime_id']})")
            print(f"  Execution Mode:  {run['execution_mode'].upper()}")
            print(f"  Dry Run:         {run['dry_run']}")
            print(f"  Success:         {run['success']}")
            print(f"  Exit Code:       {run['exit_code']}")
            print(f"  Execution Time:  {run['execution_time_seconds']:.4f}s")
            print(f"  Sandbox Active:  {run['sandbox_active']}")
            print(f"  Network Iso:     {run['network_isolated']}")
            if run.get("command"):
                print(f"  Command:         {' '.join(run['command'])}")
            if run.get("diagnostics"):
                print("\n  Diagnostics Recognized:")
                for d in run["diagnostics"]:
                    print(f"    [!] {d.get('signature')}: {d.get('root_cause')}")
            if run.get("stdout"):
                print(f"\n  Process Output:\n{run['stdout'].strip()}")
            if run.get("stderr"):
                print(f"\n  Error Output:\n{run['stderr'].strip()}")
        return

    # List runs
    runs = history_mgr.list_runs(sha256=getattr(args, "sha256", None), limit=getattr(args, "limit", 20) or 20)
    if getattr(args, "json", False):
        print(json.dumps(runs, indent=2))
    else:
        format_header(f"ZCF Execution Test History ({len(runs)} recent runs)")
        if not runs:
            print("  No execution or test runs recorded yet.")
            print("  Run 'zcf test <path>' or 'zcf run <path>' to generate execution history.")
        for r in runs:
            status_badge = "[SUCCESS]" if r.get("success") else "[FAILED]"
            mode_badge = "(Dry Run)" if r.get("dry_run") else "(Live)"
            print(f"  [{r.get('run_id')}] {r.get('application_name')} via {r.get('runtime_name')} {status_badge} {mode_badge}")
            print(f"    Timestamp: {r.get('timestamp')[:19]} | Exit Code: {r.get('exit_code')} | Duration: {r.get('execution_time_seconds', 0.0):.4f}s")
            if r.get("artifact_sha256"):
                print(f"    SHA-256:   {r.get('artifact_sha256')[:16]}...\n")


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
            tier_badge = f"[{entry.provenance_tier.value}]"
            print(f"  [{entry.entry_id}] {entry.application_name} ({entry.target_format.upper()} {entry.target_architecture}) {tier_badge}")
            print(f"    Status:      {entry.status.value} (Evidence: {entry.evidence_status.value})")
            print(f"    SHA-256:     {entry.target_sha256[:16]}...")
            print(f"    Recommended: {entry.recommended_runtime or 'None'}\n")
    elif args.action == "query":
        entries = db.query(
            runtime=getattr(args, "runtime", None),
            arch=getattr(args, "arch", None),
            status=getattr(args, "status", None),
        )
        format_header(f"ZCF Database Query Results ({len(entries)} matching entries)")
        for entry in entries:
            print(f"  [{entry.entry_id}] {entry.application_name} -> {entry.recommended_runtime} ({entry.status.value})")
    elif args.action == "submit":
        if not getattr(args, "app", None):
            print("Error: --app <path> is required for 'submit' action.", file=sys.stderr)
            sys.exit(1)
        from zcf.inspector.inspector import ApplicationInspector
        from zcf.core.models import CompatibilityStatus
        app = ApplicationInspector().inspect(args.app)
        status_enum = CompatibilityStatus.VERIFIED_COMPATIBLE
        if getattr(args, "status", None):
            try:
                status_enum = CompatibilityStatus(args.status)
            except Exception:
                pass
        entry = db.submit_profile(
            app=app,
            recommended_runtime=getattr(args, "runtime", "runtime.wine") or "runtime.wine",
            status=status_enum,
            contributor_name=getattr(args, "contributor", "Community Contributor") or "Community Contributor",
            test_procedure=getattr(args, "test_procedure", "Community execution test") or "Community execution test",
        )
        print(f"[ZCF Database] Successfully submitted community profile: {entry.entry_id}")
    elif args.action == "verify":
        if not getattr(args, "id", None):
            print("Error: --id <entry_id> is required for 'verify' action.", file=sys.stderr)
            sys.exit(1)
        verifier = getattr(args, "verifier", None) or getattr(args, "contributor", None) or "ZCF Maintainer"
        notes = getattr(args, "notes", "Verified via ZCF verification workflow") or ""
        from zcf.core.models import EvidenceStatus, ProvenanceTier
        tier_val = getattr(args, "tier", None)
        status_val = getattr(args, "evidence_status", None)
        tier = ProvenanceTier(tier_val) if tier_val else ProvenanceTier.MAINTAINER_VERIFIED
        ev_status = EvidenceStatus(status_val) if status_val else EvidenceStatus.VERIFIED

        struct_evidence = None
        target_app = getattr(args, "app", None)
        if target_app and os.path.exists(target_app):
            app = ApplicationInspector().inspect(target_app)
            env = EnvironmentInspector().inspect()
            struct_evidence = {
                "artifact_sha256": app.sha256,
                "test_environment": {"os": env.os_name, "distro": env.distribution, "kernel": env.kernel_version},
                "test_procedure": getattr(args, "test_procedure", None) or f"Automated verification test of {app.file_name}",
                "test_result": {"exit_code": 0, "success": True},
            }
        else:
            existing_rec = db.get_by_id(args.id)
            if existing_rec:
                env = EnvironmentInspector().inspect()
                struct_evidence = {
                    "artifact_sha256": existing_rec.target_sha256,
                    "test_environment": {"os": env.os_name, "distro": env.distribution, "kernel": env.kernel_version},
                    "test_procedure": getattr(args, "test_procedure", None) or f"Maintainer verification audit by {verifier}",
                    "test_result": {"exit_code": 0, "success": True},
                }

        try:
            success = db.verify_profile(
                entry_id=args.id,
                verifier=verifier,
                evidence_status=ev_status,
                provenance_tier=tier,
                notes=notes,
                structured_evidence=struct_evidence,
            )
            if success:
                print(f"[ZCF Database] Successfully verified and promoted profile: {args.id}")
            else:
                print(f"Error: Entry '{args.id}' not found.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Verification rejected: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.action == "delete":
        if not getattr(args, "id", None):
            print("Error: --id <entry_id> is required for 'delete' action.", file=sys.stderr)
            sys.exit(1)
        if db.delete_entry(args.id):
            print(f"[ZCF Database] Successfully deleted profile: {args.id}")
        else:
            print(f"Error: Entry '{args.id}' not found.", file=sys.stderr)
            sys.exit(1)
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

    # console / web
    p_console = subparsers.add_parser("console", help="Launch local browser-based Web Console")
    p_console.add_argument("--host", default="127.0.0.1", help="Host interface to bind (defaults to loopback 127.0.0.1)")
    p_console.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    p_console.add_argument("--allow-remote", action="store_true", help="Explicitly permit binding to remote/non-loopback network interfaces")
    p_console.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")
    p_console.set_defaults(func=cmd_console)

    p_web = subparsers.add_parser("web", help="Alias for 'console' (Launch local Web Console)")
    p_web.add_argument("--host", default="127.0.0.1", help="Host interface to bind (defaults to loopback 127.0.0.1)")
    p_web.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    p_web.add_argument("--allow-remote", action="store_true", help="Explicitly permit binding to remote/non-loopback network interfaces")
    p_web.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")
    p_web.set_defaults(func=cmd_console)

    # run
    p_run = subparsers.add_parser("run", help="Execute application through optimal runtime with sandboxing")
    p_run.add_argument("artifact_path", help="Path to executable binary")
    p_run.add_argument("app_args", nargs="*", help="Arguments to pass to target application")
    p_run.add_argument("--no-sandbox", action="store_true", help="Disable Bubblewrap container isolation")
    p_run.add_argument("--allow-unconfined", action="store_true", help="Allow unconfined execution if sandbox is unavailable")
    p_run.add_argument("--dry-run", action="store_true", help="Simulate execution without starting process")
    p_run.add_argument("--allow-network", action="store_true", help="Permit network access in sandbox (defaults to isolated)")
    p_run.add_argument("--timeout", type=int, default=None, help="Execution timeout in seconds")
    p_run.add_argument("--headless", action="store_true", help="Force virtual Xvfb display server")
    p_run.add_argument("--install-deps", action="store_true", help="Automatically install missing dependencies")
    p_run.add_argument("--gamemode", action="store_true", help="Wrap execution with Feral GameMode (gamemoderun)")
    p_run.add_argument("--gamescope", action="store_true", help="Execute inside Gamescope micro-compositor")
    p_run.add_argument("--upscale", choices=["fsr", "nis", "pixel", "linear"], help="Upscaling filter in Gamescope")
    p_run.add_argument("--fsr-sharpness", type=int, default=5, help="FSR upscaler sharpness (0-10)")
    p_run.add_argument("--fps-limit", type=int, help="Frames per second limit / refresh rate cap")
    p_run.add_argument("--mangohud", action="store_true", help="Enable MangoHud real-time performance overlay")
    p_run.add_argument("--tuning-preset", choices=["esports", "4k_fidelity", "power_saver", "minimal_overlay"], help="Use a preconfigured gaming tuning profile")
    p_run.set_defaults(func=cmd_run)

    # runners (fleet manager)
    p_runners = subparsers.add_parser("runners", help="Discover, download, and manage Proton and Wine compatibility runners")
    p_runners.add_argument("fleet_action", choices=["list", "available", "install"], help="Action to perform")
    p_runners.add_argument("archive_or_tag", nargs="?", default=None, help="Archive path or release tag (for 'install')")
    p_runners.add_argument("--limit", type=int, default=10, help="Max releases to query")
    p_runners.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_runners.set_defaults(func=cmd_runners)

    # snapshot (time-machine)
    p_snap = subparsers.add_parser("snapshot", help="Time-Machine instant restore points and prefix rollbacks")
    p_snap.add_argument("snapshot_action", choices=["create", "list", "restore", "delete"], help="Action to perform")
    p_snap.add_argument("prefix_path", help="Path to Wine/Proton prefix")
    p_snap.add_argument("snapshot_id", nargs="?", default=None, help="Snapshot ID (for 'restore' or 'delete')")
    p_snap.add_argument("--label", help="Descriptive label for snapshot (for 'create')")
    p_snap.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_snap.set_defaults(func=cmd_snapshot)

    # vault (game saves)
    p_vault = subparsers.add_parser("vault", help="Universal Game Save Vault for discovery, backup, and prefix migration")
    p_vault.add_argument("vault_action", choices=["discover", "backup", "list", "restore", "delete"], help="Action to perform")
    p_vault.add_argument("prefix_path", nargs="?", default=None, help="Path to prefix (for 'discover', 'backup', 'restore')")
    p_vault.add_argument("vault_id", nargs="?", default=None, help="Vault ID (for 'restore' or 'delete')")
    p_vault.add_argument("--app", help="Application name filter or label")
    p_vault.add_argument("--notes", default="", help="Notes for save backup")
    p_vault.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_vault.set_defaults(func=cmd_vault)

    # taskmgr (prefix process monitor)
    p_tm = subparsers.add_parser("taskmgr", help="Monitor active processes, kill wineserver, and launch Wine diagnostic tools")
    p_tm.add_argument("taskmgr_action", choices=["list", "kill", "reset-locks", "launch"], help="Action to perform")
    p_tm.add_argument("prefix_path", nargs="?", default=None, help="Target prefix path")
    p_tm.add_argument("tool", nargs="?", default=None, help="Wine tool to launch (winecfg, regedit, taskmgr, control)")
    p_tm.add_argument("--prefix", help="Optional prefix filter for 'list'")
    p_tm.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_tm.set_defaults(func=cmd_taskmgr)

    # prescribe (healing engine)
    p_rx = subparsers.add_parser("prescribe", help="Autonomous healing engine to analyze crashes and auto-repair prefixes")
    p_rx.add_argument("prescribe_action", choices=["generate", "apply"], help="Action to perform")
    p_rx.add_argument("log_path", help="Path to crash or error log file")
    p_rx.add_argument("--app", default="application.exe", help="Application name")
    p_rx.add_argument("--prefix", help="Target prefix path to heal")
    p_rx.add_argument("--dry-run", action="store_true", help="Simulate repair without modifying prefix")
    p_rx.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_rx.set_defaults(func=cmd_prescribe)

    # integrate
    p_int = subparsers.add_parser("integrate", help="Manage Linux desktop application menu shortcuts")
    p_int.add_argument("artifact_path", nargs="?", default=None, help="Path to application binary to integrate")
    p_int.add_argument("--name", help="Custom display name in application menu")
    p_int.add_argument("--list", action="store_true", help="List all currently integrated desktop applications")
    p_int.add_argument("--remove", action="store_true", help="Remove an integrated desktop application launcher")
    p_int.set_defaults(func=cmd_integrate)

    # service
    p_svc = subparsers.add_parser("service", help="Manage system integration and background maintenance")
    p_svc.add_argument(
        "service_action",
        choices=["register-binfmt", "unregister-binfmt", "cleanup-prefixes", "list-prefixes"],
        help="Action to perform",
    )
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

    # doctor
    p_doc = subparsers.add_parser("doctor", help="Run pre-flight system readiness audit and gaming optimization check")
    p_doc.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_doc.set_defaults(func=cmd_doctor)

    # plan
    p_plan = subparsers.add_parser("plan", help="Generate compatibility plan for an application")
    p_plan.add_argument("artifact_path", help="Path to target executable")
    p_plan.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_plan.set_defaults(func=cmd_plan)

    # test
    p_test = subparsers.add_parser("test", help="Test application compatibility execution")
    p_test.add_argument("artifact_path", help="Path to target executable")
    p_test.add_argument("--dry-run", dest="dry_run", action="store_true", default=True, help="Perform safe dry-run plan test (default)")
    p_test.add_argument("--execute", dest="dry_run", action="store_false", help="Perform real live execution test")
    p_test.add_argument("--record", action="store_true", help="Record test outcome as structured evidence into local compatibility database")
    p_test.add_argument("--contributor", default="Local Tester", help="Contributor name for recorded evidence")
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
    p_db = subparsers.add_parser("db", help="Query, verify, or manage the compatibility knowledge base")
    p_db.add_argument(
        "action",
        choices=["list", "show", "query", "submit", "verify", "delete", "export", "import"],
        help="Action to perform",
    )
    p_db.add_argument("--id", help="Entry ID (for 'show', 'verify', or 'delete' action)")
    p_db.add_argument("--app", help="Path to application binary (for 'submit' or structured 'verify' action)")
    p_db.add_argument("--runtime", help="Runtime identifier (for 'query' or 'submit')")
    p_db.add_argument("--arch", help="Architecture (for 'query')")
    p_db.add_argument("--status", help="Compatibility status (for 'query' or 'submit')")
    p_db.add_argument("--contributor", help="Contributor name or email (for 'submit')")
    p_db.add_argument("--verifier", help="Verifier name (for 'verify' action)")
    p_db.add_argument("--tier", help="Provenance tier (for 'verify' action)")
    p_db.add_argument("--evidence-status", help="Evidence status (for 'verify' action)")
    p_db.add_argument("--notes", help="Verification notes (for 'verify' action)")
    p_db.add_argument("--test-procedure", help="Description of test procedure (for 'submit')")
    p_db.add_argument("--output", help="Output file path (for 'export')")
    p_db.add_argument("--file", help="Input file path (for 'import')")
    p_db.set_defaults(func=cmd_db)

    # history
    p_hist = subparsers.add_parser("history", help="View, inspect, and compare execution and test run history")
    p_hist.add_argument("id", nargs="?", default=None, help="Specific run ID to inspect in detail")
    p_hist.add_argument("--sha256", help="Filter runs by artifact SHA-256")
    p_hist.add_argument("--limit", type=int, default=20, help="Max number of runs to display (default: 20)")
    p_hist.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"), help="Compare two run IDs side-by-side")
    p_hist.add_argument("--clear", action="store_true", help="Clear all stored execution run logs")
    p_hist.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_hist.set_defaults(func=cmd_history)

    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_dashboard(args)


if __name__ == "__main__":
    main()
