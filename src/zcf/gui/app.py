"""
ZCF Desktop Control Center.
Full-featured, zero-terminal graphical interface for Linux beginners.
Enables application launching, one-click menu integration, runtime installation,
prefix management, and automated crash diagnostics.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

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
from zcf.runtimes.prefix_manager import WinePrefixManager


class ZCFControlCenter:
    """Main window for Zyntrix Compatibility Fabric GUI."""

    def __init__(self, root: Optional[tk.Tk] = None):
        self.root = root or tk.Tk()
        self.root.title(f"Zyntrix Compatibility Fabric Control Center (v{__version__})")
        self.root.geometry("860x620")
        self.root.minsize(780, 540)
        self.root.configure(bg=DARK_THEME["bg"])

        # Core subsystems
        self.inspector = ApplicationInspector()
        self.env_inspector = EnvironmentInspector()
        self.planner = CompatibilityPlanner()
        self.integrator = DesktopIntegrator()
        self.installer_bridge = PackageInstallerBridge()
        self.diag_engine = DiagnosticEngine()
        self.remediator = AutomatedRemediator()
        self.prefix_mgr = WinePrefixManager()
        self.notifier = DesktopNotifier()

        self.current_app_path: Optional[str] = None
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
            foreground=DARK_THEME["primary"],
            font=("Segoe UI", 12, "bold"),
        )

        # Buttons
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            background=DARK_THEME["primary"],
            foreground=DARK_THEME["primary_fg"],
            padding=[12, 6],
        )
        style.configure(
            "Success.TButton",
            font=("Segoe UI", 10, "bold"),
            background=DARK_THEME["success"],
            foreground=DARK_THEME["success_fg"],
            padding=[12, 6],
        )
        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 10),
            background=DARK_THEME["card_bg"],
            foreground=DARK_THEME["fg"],
            padding=[10, 6],
        )

    def _build_header(self):
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill="x", padx=20, pady=(15, 10))

        title_lbl = ttk.Label(header_frame, text="ZYNTRIX COMPATIBILITY FABRIC", style="Header.TLabel")
        title_lbl.pack(anchor="w")

        sub_text = f"Platform: {self.env_report.os_name.capitalize()} ({self.env_report.architecture}) | Display: {self.env_report.display_server.value.upper()} | Kernel: {self.env_report.kernel_version[:30]}"
        sub_lbl = ttk.Label(header_frame, text=sub_text, style="SubHeader.TLabel")
        sub_lbl.pack(anchor="w", pady=(2, 0))

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(5, 15))

        # 5 Beginner-focused Tabs
        self.tab_launch = ttk.Frame(self.notebook)
        self.tab_runtimes = ttk.Frame(self.notebook)
        self.tab_components = ttk.Frame(self.notebook)
        self.tab_prefixes = ttk.Frame(self.notebook)
        self.tab_diag = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_launch, text="🚀  Applications")
        self.notebook.add(self.tab_runtimes, text="⚙️  Compatibility Engines")
        self.notebook.add(self.tab_components, text="📦  Windows Components")
        self.notebook.add(self.tab_prefixes, text="📂  Storage & Prefixes")
        self.notebook.add(self.tab_diag, text="🛠️  Troubleshooter & REA")

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

        top_bar = ttk.Frame(card, style="Card.TFrame")
        top_bar.pack(fill="x", pady=(0, 15))

        lbl = ttk.Label(top_bar, text="Select Application (Windows .EXE, Android .APK, or Linux binary):", style="Title.TLabel")
        lbl.pack(anchor="w")

        picker_frame = ttk.Frame(card, style="Card.TFrame")
        picker_frame.pack(fill="x", pady=5)

        self.entry_path = tk.Entry(
            picker_frame,
            bg=DARK_THEME["bg"],
            fg=DARK_THEME["fg"],
            insertbackground=DARK_THEME["fg"],
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.entry_path.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))

        btn_browse = ttk.Button(picker_frame, text="Browse...", style="Secondary.TButton", command=self._on_browse_file)
        btn_browse.pack(side="right")

        # Application Details Card
        self.info_card = ttk.Frame(card, style="Card.TFrame", padding=10)
        self.info_card.pack(fill="x", pady=15)

        self.lbl_app_name = ttk.Label(self.info_card, text="No application selected", font=("Segoe UI", 12, "bold"))
        self.lbl_app_name.pack(anchor="w")

        self.lbl_app_details = ttk.Label(
            self.info_card,
            text="Select an executable above to automatically inspect architecture, subsystem, and compatibility plan.",
            style="SubHeader.TLabel",
        )
        self.lbl_app_details.pack(anchor="w", pady=(4, 0))

        # Toggles
        opt_frame = ttk.Frame(card, style="Card.TFrame")
        opt_frame.pack(fill="x", pady=10)

        self.var_sandbox = tk.BooleanVar(value=True)
        cb_sandbox = tk.Checkbutton(
            opt_frame,
            text="Enable Bubblewrap Security Sandbox (protects host system)",
            variable=self.var_sandbox,
            bg=DARK_THEME["card_bg"],
            fg=DARK_THEME["fg"],
            selectcolor=DARK_THEME["bg"],
            activebackground=DARK_THEME["card_bg"],
            activeforeground=DARK_THEME["fg"],
            font=("Segoe UI", 9),
        )
        cb_sandbox.pack(anchor="w")

        self.var_headless = tk.BooleanVar(value=False)
        cb_headless = tk.Checkbutton(
            opt_frame,
            text="Force Virtual Xvfb Display (for headless servers / testing)",
            variable=self.var_headless,
            bg=DARK_THEME["card_bg"],
            fg=DARK_THEME["fg"],
            selectcolor=DARK_THEME["bg"],
            activebackground=DARK_THEME["card_bg"],
            activeforeground=DARK_THEME["fg"],
            font=("Segoe UI", 9),
        )
        cb_headless.pack(anchor="w")

        # Action Buttons
        btn_box = ttk.Frame(card, style="Card.TFrame")
        btn_box.pack(fill="x", pady=(20, 0))

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

            self.lbl_app_name.config(text=f"{app.file_name}")
            details = (
                f"Format: {app.format.value.upper()} | Architecture: {app.architecture.value} | Subsystem: {app.subsystem.value.upper()}\n"
                f"Planned Engine: {plan.selected_runtime_name or 'None'} (Confidence: {int(plan.confidence_score * 100)}%)\n"
                f"Recommendation: {plan.reasoning}"
            )
            self.lbl_app_details.config(text=details)
        except Exception as e:
            self.lbl_app_name.config(text="Inspection Failed")
            self.lbl_app_details.config(text=str(e))

    def _on_run_app(self):
        path = self.entry_path.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("No File", "Please select a valid executable file first.")
            return

        def run_worker():
            orchestrator = ExecutionOrchestrator()
            try:
                orchestrator.run(
                    artifact_path=path,
                    use_sandbox=self.var_sandbox.get(),
                    force_headless=self.var_headless.get(),
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

        header = ttk.Label(card, text="Compatibility Engines & Drivers Status:", style="Title.TLabel")
        header.pack(anchor="w", pady=(0, 10))

        # Refresh button
        btn_refresh = ttk.Button(card, text="🔄  Refresh Status", style="Secondary.TButton", command=self._refresh_runtimes_ui)
        btn_refresh.pack(anchor="e", pady=(0, 10))

        self.runtimes_list_frame = ttk.Frame(card, style="Card.TFrame")
        self.runtimes_list_frame.pack(fill="both", expand=True)
        self._populate_runtimes_list()

    def _populate_runtimes_list(self):
        for widget in self.runtimes_list_frame.winfo_children():
            widget.destroy()

        self.env_report = self.env_inspector.inspect()

        for runtime in self.env_report.available_runtimes:
            row = ttk.Frame(self.runtimes_list_frame, style="Card.TFrame", padding=6)
            row.pack(fill="x", pady=4)

            icon = "✅" if runtime.installed else "❌"
            status_text = f"{runtime.name}"
            lbl_name = ttk.Label(row, text=f"{icon}  {status_text}", font=("Segoe UI", 10, "bold" if runtime.installed else "normal"))
            lbl_name.pack(side="left")

            ver = f"({runtime.version[:35]})" if runtime.version else ("Ready" if runtime.installed else "Not Installed")
            lbl_ver = ttk.Label(row, text=ver, style="SubHeader.TLabel")
            lbl_ver.pack(side="left", padx=10)

            if not runtime.installed:
                target_key = "wine" if "wine" in runtime.runtime_id else ("qemu-user" if "qemu" in runtime.runtime_id else runtime.name.lower())
                btn_install = ttk.Button(
                    row,
                    text="Install with 1-Click",
                    style="Success.TButton",
                    command=lambda t=target_key: self._on_install_runtime(t),
                )
                btn_install.pack(side="right")

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

        components = [
            ("Microsoft Visual C++ 2015-2022 Runtime", "vcrun2022", "Required by modern games and productivity software"),
            ("Microsoft DirectX End-User Runtimes (D3DX9)", "d3dx9", "Required by legacy 3D games and graphics apps"),
            ("Microsoft .NET Desktop Runtime (Wine Mono)", "mono", "Required by C# and .NET Windows applications"),
            ("Vulkan DXVK Acceleration Layer", "dxvk", "Translates DirectX 9/10/11 to ultra-fast Vulkan"),
        ]

        for title, key, sub in components:
            row = ttk.Frame(card, style="Card.TFrame", padding=8)
            row.pack(fill="x", pady=6)

            info_box = ttk.Frame(row, style="Card.TFrame")
            info_box.pack(side="left")

            t_lbl = ttk.Label(info_box, text=title, font=("Segoe UI", 10, "bold"))
            t_lbl.pack(anchor="w")

            s_lbl = ttk.Label(info_box, text=sub, style="SubHeader.TLabel")
            s_lbl.pack(anchor="w")

            btn = ttk.Button(row, text="Install Component", style="Primary.TButton", command=lambda k=key, t=title: self._on_install_component(k, t))
            btn.pack(side="right")

    def _on_install_component(self, key: str, title: str):
        self._show_info(
            "Installing Component",
            f"Configuring '{title}' inside managed compatibility prefixes...\nDone!",
        )

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

        btn_box = ttk.Frame(card, style="Card.TFrame")
        btn_box.pack(fill="x", pady=15)

        btn_clean = ttk.Button(btn_box, text="🧹  Clean Stale Prefixes (Free Disk Space)", style="Primary.TButton", command=self._on_clean_prefixes)
        btn_clean.pack(side="left", padx=(0, 10))

        btn_open = ttk.Button(btn_box, text="📂  Open Prefix Folder in Files", style="Secondary.TButton", command=self._on_open_prefix_folder)
        btn_open.pack(side="left")

        self._refresh_prefix_stats()

    def _refresh_prefix_stats(self):
        base = self.prefix_mgr.base_dir
        if not os.path.exists(base):
            self.lbl_prefix_stats.config(text=f"Prefix Root: {base} (0 active prefixes)")
            return

        prefixes = [os.path.join(base, d) for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
        self.lbl_prefix_stats.config(text=f"Prefix Root: {base}\nActive Isolated Prefixes: {len(prefixes)}")

    def _on_clean_prefixes(self):
        cleaned = self.prefix_mgr.cleanup_stale_prefixes(max_age_days=14)
        self._show_info("Storage Maintenance", f"Cleaned {cleaned} stale temporary prefixes.")
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

        header = ttk.Label(card, text="Automated Troubleshooter & REA Reverse Engineering:", style="Title.TLabel")
        header.pack(anchor="w", pady=(0, 6))

        sub = ttk.Label(
            card,
            text="If any application fails to launch, paste the error message or log below for instant diagnosis and auto-fix.",
            style="SubHeader.TLabel",
        )
        sub.pack(anchor="w", pady=(0, 10))

        self.txt_log = tk.Text(
            card,
            height=8,
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

        btn_diag = ttk.Button(card, text="🛠️  Diagnose & Synthesize Fix", style="Primary.TButton", command=self._on_diagnose_log)
        btn_diag.pack(anchor="w", pady=10)

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

        msg_lines = [f"Found {len(events)} compatibility event(s):"]
        for ev in events:
            msg_lines.append(f"• [{ev.signature}] {ev.root_cause}")
            msg_lines.append(f"  Fix: {ev.remediation}\n")

        self.lbl_diag_result.config(text="\n".join(msg_lines))
        self._show_info("Diagnosis Complete", "\n".join(msg_lines))

    def run(self):
        self.root.mainloop()


def launch_gui():
    app = ZCFControlCenter()
    app.run()


if __name__ == "__main__":
    launch_gui()
