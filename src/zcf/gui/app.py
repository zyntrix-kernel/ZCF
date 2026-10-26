"""
ZCF Desktop Control Center.
Full-featured, zero-terminal graphical interface for Linux beginners.
Enables application launching, one-click menu integration, runtime installation,
component management, prefix maintenance, and automated crash diagnostics.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from zcf import __version__
from zcf.desktop.integrator import DesktopIntegrator
from zcf.desktop.notifier import DesktopNotifier
from zcf.diagnostics.analyzer import DiagnosticEngine
from zcf.diagnostics.remediator import AutomatedRemediator
from zcf.environment.inspector import EnvironmentInspector
from zcf.execution.installer import PackageInstallerBridge
from zcf.execution.runner import ExecutionOrchestrator
from zcf.gui.theme import DARK_THEME
from zcf.inspector.inspector import ApplicationInspector
from zcf.planner.engine import CompatibilityPlanner
from zcf.runtimes.components import WindowsComponentManager
from zcf.runtimes.prefix_manager import WinePrefixManager


class ZCFControlCenter:
    """Main window for Zyntrix Compatibility Fabric GUI."""

    def __init__(self, root: Optional[tk.Tk] = None):
        self.root = root or tk.Tk()
        self.root.title(f"Zyntrix Compatibility Fabric Control Center (v{__version__})")
        self.root.geometry("920x660")
        self.root.minsize(820, 560)
        self.root.configure(bg=DARK_THEME["bg"])

        # Core subsystems
        self.inspector = ApplicationInspector()
        self.env_inspector = EnvironmentInspector()
        self.planner = CompatibilityPlanner()
        self.integrator = DesktopIntegrator()
        self.installer_bridge = PackageInstallerBridge()
        self.component_mgr = WindowsComponentManager()
        self.diag_engine = DiagnosticEngine()
        self.remediator = AutomatedRemediator()
        self.prefix_mgr = WinePrefixManager(base_dir=os.path.expanduser("~/.zcf/prefixes"))
        self.proton_prefix_mgr = WinePrefixManager(base_dir=os.path.expanduser("~/.zcf/proton_prefixes"))
        self.notifier = DesktopNotifier()

        self.current_app_path: Optional[str] = None
        self.current_plan: Optional[Any] = None
        self.last_remediation_commands: List[str] = []
        self.env_report = self.env_inspector.inspect()

        self._configure_styles()
        self._build_header()
        self._build_notebook()

    def _show_info(self, title: str, message: str):
        if os.environ.get("ZCF_NON_INTERACTIVE") == "1":
            return
        messagebox.showinfo(title, message)

    def _show_warning(self, title: str, message: str):
        if os.environ.get("ZCF_NON_INTERACTIVE") == "1":
            return
        messagebox.showwarning(title, message)

    def _show_error(self, title: str, message: str):
        if os.environ.get("ZCF_NON_INTERACTIVE") == "1":
            return
        messagebox.showerror(title, message)

    def _ask_yes_no(self, title: str, message: str) -> bool:
        if os.environ.get("ZCF_NON_INTERACTIVE") == "1":
            return False
        return bool(messagebox.askyesno(title, message))

    def _configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TNotebook", background=DARK_THEME["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=DARK_THEME["card_bg"],
            foreground=DARK_THEME["fg"],
            padding=[14, 8],
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", DARK_THEME["active_tab"])],
            foreground=[("selected", DARK_THEME["primary"])],
        )

        style.configure("TFrame", background=DARK_THEME["bg"])
        style.configure("Card.TFrame", background=DARK_THEME["card_bg"], relief="flat")
        style.configure(
            "TLabel",
            background=DARK_THEME["card_bg"],
            foreground=DARK_THEME["fg"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            background=DARK_THEME["bg"],
            foreground=DARK_THEME["fg"],
            font=("Segoe UI", 16, "bold"),
        )
        style.configure(
            "SubHeader.TLabel",
            background=DARK_THEME["bg"],
            foreground=DARK_THEME["fg_subtle"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Title.TLabel",
            background=DARK_THEME["card_bg"],
            foreground=DARK_THEME["fg"],
            font=("Segoe UI", 12, "bold"),
        )

        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=[12, 6],
            background=DARK_THEME["primary"],
            foreground="#FFFFFF",
        )
        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 9),
            padding=[8, 4],
            background=DARK_THEME["active_tab"],
            foreground=DARK_THEME["fg"],
        )
        style.configure(
            "Success.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=[12, 6],
            background=DARK_THEME["accent_green"],
            foreground="#FFFFFF",
        )

    def _build_header(self):
        header_frame = ttk.Frame(self.root, padding="15 12 15 8")
        header_frame.pack(fill="x")

        title_lbl = ttk.Label(header_frame, text="⚡ ZCF Control Center", style="Header.TLabel")
        title_lbl.pack(side="left")

        sub_text = f"Linux Application Compatibility Layer (v{__version__}) • Host: {self.env_report.os_name.title()} ({self.env_report.architecture})"
        sub_lbl = ttk.Label(header_frame, text=sub_text, style="SubHeader.TLabel")
        sub_lbl.pack(side="right", pady=(4, 0))

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # 5 Core Navigation Tabs
        self.tab_launch = ttk.Frame(self.notebook)
        self.tab_runtimes = ttk.Frame(self.notebook)
        self.tab_components = ttk.Frame(self.notebook)
        self.tab_prefixes = ttk.Frame(self.notebook)
        self.tab_diag = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_launch, text="  🚀 Quick Launcher  ")
        self.notebook.add(self.tab_runtimes, text="  ⚙️ Engines & Health  ")
        self.notebook.add(self.tab_components, text="  🧩 Windows Components  ")
        self.notebook.add(self.tab_prefixes, text="  💾 Storage & Prefixes  ")
        self.notebook.add(self.tab_diag, text="  🛠️ Troubleshooter & REA  ")

        self._build_launch_tab()
        self._build_runtimes_tab()
        self._build_components_tab()
        self._build_prefixes_tab()
        self._build_diag_tab()

    # =========================================================================
    # TAB 1: Applications & Quick Launcher
    # =========================================================================
    def _build_launch_tab(self):
        card = ttk.Frame(self.tab_launch, style="Card.TFrame", padding=15)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        # File Selection Row
        lbl_file = ttk.Label(card, text="Select Windows or Foreign Application:", style="Title.TLabel")
        lbl_file.pack(anchor="w", pady=(0, 6))

        file_box = ttk.Frame(card, style="Card.TFrame")
        file_box.pack(fill="x", pady=(0, 12))

        self.entry_path = tk.Entry(
            file_box,
            bg=DARK_THEME["bg"],
            fg=DARK_THEME["fg"],
            insertbackground=DARK_THEME["fg"],
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.entry_path.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 8))

        btn_browse = ttk.Button(file_box, text="📁 Browse...", style="Secondary.TButton", command=self._on_browse_file)
        btn_browse.pack(side="right")

        # Plan & Inspection Details Card
        self.plan_box = ttk.Frame(card, style="Card.TFrame", padding=10)
        self.plan_box.pack(fill="x", pady=8)

        self.lbl_app_name = ttk.Label(
            self.plan_box,
            text="No Application Selected",
            font=("Segoe UI", 12, "bold"),
            foreground=DARK_THEME["primary"],
        )
        self.lbl_app_name.pack(anchor="w")

        self.lbl_app_details = ttk.Label(
            self.plan_box,
            text="Select an executable (.exe, .msi, .apk, .elf, script) to inspect architecture, recommended runtime, and compatibility score.",
            style="SubHeader.TLabel",
        )
        self.lbl_app_details.pack(anchor="w", pady=(4, 0))

        # Candidate Runtimes Evaluation Tree
        lbl_candidates = ttk.Label(card, text="Evaluated Compatibility Candidates:", font=("Segoe UI", 10, "bold"))
        lbl_candidates.pack(anchor="w", pady=(10, 4))

        self.tree_candidates = ttk.Treeview(
            card,
            columns=("engine", "eligible", "score", "notes"),
            show="headings",
            height=4,
        )
        self.tree_candidates.heading("engine", text="Engine")
        self.tree_candidates.heading("eligible", text="Eligibility")
        self.tree_candidates.heading("score", text="Confidence")
        self.tree_candidates.heading("notes", text="Evaluation Notes")
        self.tree_candidates.column("engine", width=160)
        self.tree_candidates.column("eligible", width=90)
        self.tree_candidates.column("score", width=90)
        self.tree_candidates.column("notes", width=420)
        self.tree_candidates.pack(fill="x", pady=(0, 10))

        # Execution Options
        opt_box = ttk.Frame(card, style="Card.TFrame")
        opt_box.pack(fill="x", pady=6)

        self.var_sandbox = tk.BooleanVar(value=True)
        chk_sandbox = tk.Checkbutton(
            opt_box,
            text="Enable Bubblewrap Container Sandbox (Process Isolation)",
            variable=self.var_sandbox,
            bg=DARK_THEME["card_bg"],
            fg=DARK_THEME["fg"],
            selectcolor=DARK_THEME["bg"],
            activebackground=DARK_THEME["card_bg"],
            activeforeground=DARK_THEME["fg"],
            font=("Segoe UI", 9),
        )
        chk_sandbox.pack(anchor="w")

        self.var_headless = tk.BooleanVar(value=False)
        chk_headless = tk.Checkbutton(
            opt_box,
            text="Force Ephemeral Virtual Display (Xvfb Headless Server)",
            variable=self.var_headless,
            bg=DARK_THEME["card_bg"],
            fg=DARK_THEME["fg"],
            selectcolor=DARK_THEME["bg"],
            activebackground=DARK_THEME["card_bg"],
            activeforeground=DARK_THEME["fg"],
            font=("Segoe UI", 9),
        )
        chk_headless.pack(anchor="w")

        self.var_network = tk.BooleanVar(value=False)
        chk_network = tk.Checkbutton(
            opt_box,
            text="Permit Bridged Host Network Access (Defaults to isolated)",
            variable=self.var_network,
            bg=DARK_THEME["card_bg"],
            fg=DARK_THEME["fg"],
            selectcolor=DARK_THEME["bg"],
            activebackground=DARK_THEME["card_bg"],
            activeforeground=DARK_THEME["fg"],
            font=("Segoe UI", 9),
        )
        chk_network.pack(anchor="w")

        # Action Buttons
        btn_box = ttk.Frame(card, style="Card.TFrame")
        btn_box.pack(fill="x", pady=(15, 0))

        self.btn_run = ttk.Button(
            btn_box,
            text="▶  Launch Application",
            style="Primary.TButton",
            command=self._on_run_app,
        )
        self.btn_run.pack(side="left", padx=(0, 10))

        self.btn_menu = ttk.Button(
            btn_box,
            text="📌  Add to Start Menu",
            style="Success.TButton",
            command=self._on_add_to_menu,
        )
        self.btn_menu.pack(side="left", padx=5)

    def _on_browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Windows or Foreign Application",
            filetypes=[
                ("All Supported Binaries", "*.exe;*.msi;*.apk;*.sh;*"),
                ("Windows Executables (*.exe)", "*.exe"),
                ("Windows Installers (*.msi)", "*.msi"),
                ("Android Packages (*.apk)", "*.apk"),
                ("All Files", "*.*"),
            ],
        )
        if file_path:
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, file_path)
            self._inspect_and_update_ui(file_path)

    def _inspect_and_update_ui(self, path: str):
        self.current_app_path = path
        try:
            app = self.inspector.inspect(path)
            plan = self.planner.plan(app, self.env_report)
            self.current_plan = plan

            self.lbl_app_name.config(text=f"{app.file_name} ({app.workload_type.value.upper()})")
            details = (
                f"Format: {app.format.value.upper()} | Architecture: {app.architecture.value} | Subsystem: {app.subsystem.value.upper()}\n"
                f"Planned Engine: {plan.selected_runtime_name or 'None'} (Confidence: {int(plan.confidence_score * 100)}%)\n"
                f"Rationale: {plan.reasoning}"
            )
            self.lbl_app_details.config(text=details)

            # Update candidate evaluations treeview
            for item in self.tree_candidates.get_children():
                self.tree_candidates.delete(item)

            for cand in plan.candidate_evaluations:
                elig = "Yes" if cand.eligible else "No"
                score_str = f"{int(cand.score * 100)}%"
                self.tree_candidates.insert("", "end", values=(cand.runtime_id, elig, score_str, cand.notes))

        except Exception as e:
            self.lbl_app_name.config(text="Inspection Failed")
            self.lbl_app_details.config(text=str(e))

    def _on_run_app(self):
        path = self.entry_path.get().strip()
        if not path or not os.path.exists(path):
            self._show_warning("No File", "Please select a valid executable file first.")
            return

        use_sandbox = self.var_sandbox.get()
        force_headless = self.var_headless.get()
        allow_network = self.var_network.get()

        def run_worker():
            orchestrator = ExecutionOrchestrator()
            try:
                orchestrator.run(
                    artifact_path=path,
                    use_sandbox=use_sandbox,
                    force_headless=force_headless,
                    allow_network=allow_network,
                    auto_install=True,
                )
            except Exception as ex:
                self.root.after(0, lambda: self._show_error("Execution Error", str(ex)))

        threading.Thread(target=run_worker, daemon=True).start()
        self._show_info("Launching", f"Launching '{os.path.basename(path)}' with ZCF...")

    def _on_add_to_menu(self):
        path = self.entry_path.get().strip()
        if not path or not os.path.exists(path):
            self._show_warning("No File", "Please select a valid executable file first.")
            return

        try:
            desktop_path = self.integrator.integrate(path)
            self._show_info(
                "Added to Start Menu",
                f"Successfully added to your Linux Application Menu!\n\nLauncher: {desktop_path}",
            )
        except Exception as e:
            self._show_error("Integration Error", f"Could not create menu shortcut: {e}")

    # =========================================================================
    # TAB 2: Compatibility Engines & Health Status
    # =========================================================================
    def _build_runtimes_tab(self):
        card = ttk.Frame(self.tab_runtimes, style="Card.TFrame", padding=15)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        # System Readiness Index Banner
        audit = self.env_inspector.get_readiness_audit()
        readiness_frame = ttk.Frame(card, style="Card.TFrame", padding=8)
        readiness_frame.pack(fill="x", pady=(0, 12))

        lbl_score = ttk.Label(
            readiness_frame,
            text=f"Pre-Flight System Readiness: [ {audit['score']}% ]  •  GRADE: {audit['grade']}",
            font=("Segoe UI", 11, "bold"),
            foreground=DARK_THEME["primary"] if audit["score"] >= 70 else DARK_THEME["accent_amber"],
        )
        lbl_score.pack(side="left")

        btn_doctor = ttk.Button(
            readiness_frame,
            text="🩺  System Doctor Audit",
            style="Secondary.TButton",
            command=self._show_doctor_dialog,
        )
        btn_doctor.pack(side="right")

        header = ttk.Label(card, text="Compatibility Engines & Health Status:", style="Title.TLabel")
        header.pack(anchor="w", pady=(0, 10))

        btn_refresh = ttk.Button(card, text="🔄  Refresh Status", style="Secondary.TButton", command=self._refresh_runtimes_ui)
        btn_refresh.pack(anchor="e", pady=(0, 10))

        self.runtimes_container = ttk.Frame(card, style="Card.TFrame")
        self.runtimes_container.pack(fill="both", expand=True)

        self._populate_runtimes_list()

    def _show_doctor_dialog(self):
        audit = self.env_inspector.get_readiness_audit()
        summary_lines = [
            f"ZCF SYSTEM READINESS AUDIT",
            f"Readiness Score: {audit['score']}% ({audit['grade']})",
            f"Summary: {audit['summary']}",
            "-" * 50,
        ]
        for c in audit["checks"]:
            summary_lines.append(f"[{c['status']}] {c['name']} ({c['score_points']}/{c['max_points']} pts)")
            summary_lines.append(f"  {c['details']}")
            if c.get("remediation"):
                summary_lines.append(f"  -> Fix: {c['remediation']}")
            summary_lines.append("")

        self._show_info("ZCF System Doctor", "\n".join(summary_lines))

    def _populate_runtimes_list(self):
        for widget in self.runtimes_container.winfo_children():
            widget.destroy()

        self.env_report = self.env_inspector.inspect()

        runtimes = [
            ("Wine Compatibility Layer", "wine", "Direct Win32/Win64 API Translation", "runtime.wine"),
            ("Valve Proton Gaming Runtime", "proton", "DXVK Vulkan Gaming Translation", "runtime.proton"),
            ("QEMU Architecture Emulation", "qemu-user", "AArch64 / ARM / RISC-V Userspace Emulation", "runtime.qemu-user"),
            ("Box64 Dynamic Translator", "box64", "Optimized x86_64 Emulation on ARM64 Linux", "runtime.box64"),
            ("Waydroid Android Container", "waydroid", "LXC Android Container for APK Applications", "runtime.android"),
            ("Bubblewrap Process Sandbox", "bwrap", "Lightweight Userspace Security Container", "sandbox.bwrap"),
        ]

        for name, generic_pkg, desc, rid in runtimes:
            row = ttk.Frame(self.runtimes_container, style="Card.TFrame", padding=6)
            row.pack(fill="x", pady=4)

            # Check status
            installed = False
            version_str = ""
            for r in self.env_report.available_runtimes:
                if r.runtime_id == rid or generic_pkg in r.runtime_id:
                    installed = r.installed
                    version_str = r.version or ""
                    break
            if generic_pkg == "bwrap":
                installed = shutil.which("bwrap") is not None

            status_icon = "🟢 Installed" if installed else "🔴 Missing"
            status_color = DARK_THEME["accent_green"] if installed else DARK_THEME["accent_red"]

            lbl_info = ttk.Frame(row, style="Card.TFrame")
            lbl_info.pack(side="left", fill="x", expand=True)

            t_lbl = ttk.Label(lbl_info, text=f"{name}  [{status_icon}]", font=("Segoe UI", 10, "bold"))
            t_lbl.pack(anchor="w")

            sub_info = f"{desc} • Version: {version_str if version_str else 'N/A'}"
            s_lbl = ttk.Label(lbl_info, text=sub_info, style="SubHeader.TLabel")
            s_lbl.pack(anchor="w")

            if not installed:
                btn_install = ttk.Button(
                    row,
                    text="Install with 1-Click",
                    style="Primary.TButton",
                    command=lambda p=generic_pkg: self._on_install_runtime(p),
                )
                btn_install.pack(side="right", padx=5)

    def _refresh_runtimes_ui(self):
        self._populate_runtimes_list()
        self._show_info("Refreshed", "Environment status refreshed.")

    def _on_install_runtime(self, target: str):
        cmd = self.installer_bridge.get_install_command(target)
        if not cmd:
            self._show_error("Error", f"Could not determine install command for '{target}'.")
            return

        confirm = self._ask_yes_no(
            "Install Runtime",
            f"Would you like ZCF to install '{target}' using your system package manager?\n\nCommand: {' '.join(cmd)}",
        )
        if confirm:
            def install_worker():
                success = self.installer_bridge.install(target, interactive=False)
                if success:
                    self.root.after(0, lambda: self._show_info("Success", f"Successfully installed {target}!"))
                    self.root.after(0, self._populate_runtimes_list)
                else:
                    self.root.after(0, lambda: self._show_error("Error", f"Installation of {target} failed."))

            threading.Thread(target=install_worker, daemon=True).start()

    # =========================================================================
    # TAB 3: Windows Components (Zero-Terminal Winetricks)
    # =========================================================================
    def _build_components_tab(self):
        card = ttk.Frame(self.tab_components, style="Card.TFrame", padding=15)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        header = ttk.Label(card, text="One-Click Windows Components & Runtimes:", style="Title.TLabel")
        header.pack(anchor="w", pady=(0, 6))

        desc = ttk.Label(
            card,
            text="Install common Windows runtimes into your active compatibility containers with zero terminal commands.",
            style="SubHeader.TLabel",
        )
        desc.pack(anchor="w", pady=(0, 15))

        for comp in self.component_mgr.list_components():
            row = ttk.Frame(card, style="Card.TFrame", padding=8)
            row.pack(fill="x", pady=6)

            info_box = ttk.Frame(row, style="Card.TFrame")
            info_box.pack(side="left")

            t_lbl = ttk.Label(info_box, text=comp.name, font=("Segoe UI", 10, "bold"))
            t_lbl.pack(anchor="w")

            s_lbl = ttk.Label(info_box, text=comp.description, style="SubHeader.TLabel")
            s_lbl.pack(anchor="w")

            btn = ttk.Button(
                row,
                text="Install Component",
                style="Primary.TButton",
                command=lambda k=comp.key, n=comp.name: self._on_install_component(k, n),
            )
            btn.pack(side="right")

    def _on_install_component(self, key: str, title: str):
        # Determine prefix to install into
        prefix_path = os.path.join(self.prefix_mgr.base_dir, "default")
        if self.current_app_path:
            try:
                app = self.inspector.inspect(self.current_app_path)
                prefix_path = self.prefix_mgr.get_prefix_path(app.sha256)
            except Exception:
                pass

        def worker():
            res = self.component_mgr.install(prefix_path, key)
            if res.success:
                self.root.after(
                    0,
                    lambda: self._show_info(
                        "Component Installed",
                        f"Successfully installed and verified '{title}' inside prefix:\n{prefix_path}",
                    ),
                )
            else:
                self.root.after(
                    0,
                    lambda: self._show_error(
                        "Installation Failed",
                        f"Could not install '{title}':\n{res.error}",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()
        self._show_info("Installing", f"Configuring '{title}' inside compatibility prefix...\nThis may take a moment.")

    # =========================================================================
    # TAB 4: Storage & Prefix Manager
    # =========================================================================
    def _build_prefixes_tab(self):
        card = ttk.Frame(self.tab_prefixes, style="Card.TFrame", padding=15)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        header = ttk.Label(card, text="Isolated Storage & Prefix Management:", style="Title.TLabel")
        header.pack(anchor="w", pady=(0, 6))

        sub = ttk.Label(
            card,
            text="ZCF isolates each Windows application in its own lightweight prefix to prevent conflicts and clutter.",
            style="SubHeader.TLabel",
        )
        sub.pack(anchor="w", pady=(0, 15))

        self.lbl_prefix_stats = ttk.Label(card, text="Locating prefixes...", font=("Segoe UI", 10))
        self.lbl_prefix_stats.pack(anchor="w", pady=5)

        # Prefix treeview list
        self.tree_prefixes = ttk.Treeview(
            card,
            columns=("runtime", "name", "size", "arch", "persistent", "locked", "path"),
            show="headings",
            height=6,
        )
        self.tree_prefixes.heading("runtime", text="Runtime")
        self.tree_prefixes.heading("name", text="Application / ID")
        self.tree_prefixes.heading("size", text="Disk Size")
        self.tree_prefixes.heading("arch", text="Architecture")
        self.tree_prefixes.heading("persistent", text="Persistence")
        self.tree_prefixes.heading("locked", text="Active Lock")
        self.tree_prefixes.heading("path", text="Filesystem Location")
        self.tree_prefixes.column("runtime", width=80)
        self.tree_prefixes.column("name", width=160)
        self.tree_prefixes.column("size", width=80)
        self.tree_prefixes.column("arch", width=80)
        self.tree_prefixes.column("persistent", width=90)
        self.tree_prefixes.column("locked", width=80)
        self.tree_prefixes.column("path", width=260)
        self.tree_prefixes.pack(fill="both", expand=True, pady=8)

        btn_box = ttk.Frame(card, style="Card.TFrame")
        btn_box.pack(fill="x", pady=10)

        btn_clean = ttk.Button(
            btn_box,
            text="🧹  Clean Stale Disposable Prefixes (Safe)",
            style="Primary.TButton",
            command=self._on_clean_prefixes,
        )
        btn_clean.pack(side="left", padx=(0, 10))

        btn_open = ttk.Button(
            btn_box,
            text="📂  Open Prefix Folder in Files",
            style="Secondary.TButton",
            command=self._on_open_prefix_folder,
        )
        btn_open.pack(side="left")

        self._refresh_prefix_stats()

    def _refresh_prefix_stats(self):
        wine_prefixes = self.prefix_mgr.list_prefixes()
        proton_prefixes = self.proton_prefix_mgr.list_prefixes()
        all_prefixes = wine_prefixes + proton_prefixes
        total_mb = sum(p.size_mb for p in all_prefixes)
        self.lbl_prefix_stats.config(
            text=f"Wine Root: {self.prefix_mgr.base_dir} | Proton Root: {self.proton_prefix_mgr.base_dir}\n"
                 f"Managed Prefixes: {len(all_prefixes)} (Wine: {len(wine_prefixes)}, Proton: {len(proton_prefixes)}) • Total Storage: {round(total_mb, 2)} MB"
        )

        for item in self.tree_prefixes.get_children():
            self.tree_prefixes.delete(item)

        for p in wine_prefixes:
            locked_str = "🔒 Active" if p.is_locked else "Ready"
            persist_str = "Durable" if p.is_persistent else "Disposable"
            self.tree_prefixes.insert("", "end", values=("Wine", p.app_name, f"{p.size_mb} MB", p.architecture, persist_str, locked_str, p.prefix_path))

        for p in proton_prefixes:
            locked_str = "🔒 Active" if p.is_locked else "Ready"
            persist_str = "Durable" if p.is_persistent else "Disposable"
            self.tree_prefixes.insert("", "end", values=("Proton", p.app_name, f"{p.size_mb} MB", p.architecture, persist_str, locked_str, p.prefix_path))

    def _on_clean_prefixes(self):
        wine_preview = self.prefix_mgr.preview_cleanup(max_age_days=14, include_disposable_only=True)
        proton_preview = self.proton_prefix_mgr.preview_cleanup(max_age_days=14, include_disposable_only=True)
        candidates = wine_preview["candidates"] + proton_preview["candidates"]
        reclaim_mb = round(wine_preview["total_reclaimable_mb"] + proton_preview["total_reclaimable_mb"], 2)

        if not candidates:
            self._show_info("Storage Clean", "No stale disposable prefixes found eligible to clean.\nDurable application prefixes are preserved.")
            return

        confirm = self._ask_yes_no(
            "Confirm Safe Storage Cleanup",
            f"Found {len(candidates)} stale disposable prefix container(s) eligible for cleanup.\n\n"
            f"Recoverable Disk Space: {reclaim_mb} MB\n\n"
            f"All persistent application data will be preserved. Proceed?",
        )
        if confirm:
            cleaned_wine = self.prefix_mgr.cleanup_stale_prefixes(max_age_days=14)
            cleaned_proton = self.proton_prefix_mgr.cleanup_stale_prefixes(max_age_days=14)
            cleaned = cleaned_wine + cleaned_proton
            self._show_info("Storage Maintenance", f"Cleaned {cleaned} stale disposable prefixes ({reclaim_mb} MB freed).")
            self._refresh_prefix_stats()

    def _on_open_prefix_folder(self):
        base = self.prefix_mgr.base_dir
        os.makedirs(base, exist_ok=True)
        if shutil.which("xdg-open"):
            subprocess.run(["xdg-open", base])
        elif os.name == "nt":
            os.startfile(base)

    # =========================================================================
    # TAB 5: Troubleshooter & REA Diagnostics
    # =========================================================================
    def _build_diag_tab(self):
        card = ttk.Frame(self.tab_diag, style="Card.TFrame", padding=15)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        rea_active = shutil.which("rea") is not None
        badge_text = "⚡ REA Reverse-Engineering Engine Active" if rea_active else "Standard Diagnostic Engine Active"
        header = ttk.Label(card, text=f"Automated Troubleshooter ({badge_text}):", style="Title.TLabel")
        header.pack(anchor="w", pady=(0, 6))

        sub = ttk.Label(
            card,
            text="If any application fails to launch, paste the error message or log below for instant diagnosis and auto-fix.",
            style="SubHeader.TLabel",
        )
        sub.pack(anchor="w", pady=(0, 10))

        self.txt_log = tk.Text(
            card,
            height=7,
            bg=DARK_THEME["bg"],
            fg=DARK_THEME["fg"],
            insertbackground=DARK_THEME["fg"],
            relief="flat",
            font=("Consolas", 9),
        )
        self.txt_log.pack(fill="both", expand=True, pady=5)
        self.txt_log.insert(
            "1.0",
            "Sample: err:module:import_dll Library D3DX9_43.dll not found\nerror while loading shared libraries: libvulkan.so.1: cannot open shared object file",
        )

        btn_row = ttk.Frame(card, style="Card.TFrame")
        btn_row.pack(fill="x", pady=8)

        btn_diag = ttk.Button(btn_row, text="🛠️  Diagnose Failure", style="Primary.TButton", command=self._on_diagnose_log)
        btn_diag.pack(side="left", padx=(0, 10))

        self.btn_apply_fix = ttk.Button(
            btn_row,
            text="⚡  Apply Recommended Fix",
            style="Success.TButton",
            command=self._on_apply_remediation,
        )
        self.btn_apply_fix.pack(side="left")

        self.lbl_diag_result = ttk.Label(card, text="", font=("Segoe UI", 10))
        self.lbl_diag_result.pack(anchor="w", pady=5)

    def _on_diagnose_log(self):
        content = self.txt_log.get("1.0", tk.END).strip()
        if not content:
            self._show_warning("Empty Log", "Please paste or enter an error log.")
            return

        events = self.diag_engine.analyze_log(content)
        if not events:
            self.lbl_diag_result.config(text="No known fatal failure signatures detected. The application log appears normal.")
            return

        app_desc = self.inspector.inspect(self.current_app_path) if (self.current_app_path and os.path.exists(self.current_app_path)) else None
        if not app_desc:
            from zcf.core.models import ApplicationDescription, Architecture, BinaryFormat, Subsystem
            app_desc = ApplicationDescription(
                artifact_path="/tmp/unknown.exe",
                file_name="unknown.exe",
                sha256="0" * 64,
                byte_size=0,
                format=BinaryFormat.PE,
                architecture=Architecture.X86_64,
                subsystem=Subsystem.GUI,
            )

        rem_plan = self.remediator.synthesize(app_desc, self.env_report, events)
        self.last_remediation_commands = rem_plan.package_install_commands

        msg_lines = [f"Found {len(events)} compatibility event(s):"]
        for ev in events:
            msg_lines.append(f"• [{ev.signature}] {ev.root_cause}")
            msg_lines.append(f"  Fix: {ev.remediation}\n")

        if rem_plan.package_install_commands:
            msg_lines.append(f"Automated Command: {' && '.join(rem_plan.package_install_commands)}")

        self.lbl_diag_result.config(text="\n".join(msg_lines))
        self._show_info("Diagnosis Complete", "\n".join(msg_lines))

    def _on_apply_remediation(self):
        if not self.last_remediation_commands:
            self._show_info("No Fix Pending", "Diagnose a log first to discover recommended fixes.")
            return

        commands = list(self.last_remediation_commands)
        display_cmd = "\n".join(commands)
        confirm = self._ask_yes_no(
            "Apply Fix",
            f"Execute the following system remediation command(s)?\n\n{display_cmd}"
        )
        if confirm:
            def worker():
                try:
                    import shlex
                    for single_cmd in commands:
                        parsed_args = shlex.split(single_cmd)
                        if parsed_args:
                            subprocess.run(parsed_args, shell=False, check=True)
                    self.root.after(0, lambda: self._show_info("Fix Applied", "Successfully applied remediation!"))
                except Exception as e:
                    self.root.after(0, lambda: self._show_error("Fix Error", f"Remediation command failed: {e}"))

            threading.Thread(target=worker, daemon=True).start()

    def run(self):
        self.root.mainloop()


def launch_gui():
    app = ZCFControlCenter()
    app.run()


if __name__ == "__main__":
    launch_gui()
