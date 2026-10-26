"""Live Process Task Manager and Wine System Tools for ZCF.

Provides process tree inspection per Wine/Proton prefix, targeted wineserver
termination, lock clearing, and 1-click launchers for built-in diagnostic tools
(winecfg, regedit, taskmgr, control).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PrefixProcessInfo:
    """Represents a running process associated with a compatibility prefix."""

    pid: int
    name: str
    cmdline: str
    rss_mb: float
    cpu_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "cmdline": self.cmdline,
            "rss_mb": round(self.rss_mb, 2),
            "cpu_percent": round(self.cpu_percent, 1),
        }


class PrefixTaskManager:
    """Monitors and controls active runtime processes within a prefix."""

    SUPPORTED_WINE_TOOLS = {
        "winecfg": "winecfg",
        "regedit": "regedit",
        "taskmgr": "taskmgr",
        "control": "control",
        "cmd": "cmd",
        "explorer": "explorer",
    }

    def list_prefix_processes(self, prefix_path: Optional[str] = None) -> List[PrefixProcessInfo]:
        """Scan running processes and return those tied to the specified prefix."""
        prefix_real = os.path.realpath(prefix_path) if prefix_path else None
        processes: List[PrefixProcessInfo] = []

        if os.name != "nt" and os.path.isdir("/proc"):
            processes = self._scan_linux_proc(prefix_real)
        else:
            # Fallback for Windows or systems without direct /proc access
            processes = self._scan_generic_processes(prefix_real)

        return processes

    def _scan_linux_proc(self, prefix_real: Optional[str]) -> List[PrefixProcessInfo]:
        """Read /proc directly on Linux to find prefix processes without external dependencies."""
        results: List[PrefixProcessInfo] = []

        try:
            for entry in os.scandir("/proc"):
                if not entry.is_dir() or not entry.name.isdigit():
                    continue
                pid = int(entry.name)

                cmdline_path = os.path.join(entry.path, "cmdline")
                environ_path = os.path.join(entry.path, "environ")
                statm_path = os.path.join(entry.path, "statm")
                comm_path = os.path.join(entry.path, "comm")

                # Read process name
                pname = ""
                try:
                    with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                        pname = f.read().strip()
                except OSError:
                    continue

                # Read cmdline
                cmdline = ""
                try:
                    with open(cmdline_path, "rb") as f:
                        raw = f.read()
                        cmdline = " ".join(raw.decode("utf-8", errors="ignore").split("\x00")).strip()
                except OSError:
                    pass

                # Check if matches prefix
                matched = False
                if prefix_real:
                    try:
                        with open(environ_path, "rb") as f:
                            env_bytes = f.read()
                            env_entries = env_bytes.decode("utf-8", errors="ignore").split("\x00")
                            for ev in env_entries:
                                if ev.startswith("WINEPREFIX="):
                                    val = ev.split("=", 1)[1]
                                    if os.path.realpath(val) == prefix_real:
                                        matched = True
                                        break
                    except OSError:
                        pass

                    # Also check cmdline for prefix
                    if not matched and prefix_real in cmdline:
                        matched = True
                else:
                    # Match any Wine or Proton related process if no prefix specified
                    wine_keywords = ("wine", "wineserver", "proton", ".exe")
                    if any(kw in pname.lower() or kw in cmdline.lower() for kw in wine_keywords):
                        matched = True

                if matched:
                    # Read memory RSS (pages)
                    rss_mb = 0.0
                    try:
                        with open(statm_path, "r") as f:
                            parts = f.read().split()
                            if len(parts) >= 2:
                                rss_pages = int(parts[1])
                                rss_mb = (rss_pages * 4096) / (1024 * 1024)
                    except (OSError, ValueError):
                        pass

                    results.append(
                        PrefixProcessInfo(
                            pid=pid,
                            name=pname or os.path.basename(cmdline.split()[0]) if cmdline else f"pid_{pid}",
                            cmdline=cmdline,
                            rss_mb=rss_mb,
                        )
                    )
        except OSError:
            pass

        return results

    def _scan_generic_processes(self, prefix_real: Optional[str]) -> List[PrefixProcessInfo]:
        """Generic fallback process scanner."""
        # Returns empty list cleanly if OS does not have /proc
        return []

    def kill_prefix_processes(self, prefix_path: str, timeout: float = 3.0) -> Dict[str, Any]:
        """Terminate all processes and run wineserver -k for the target prefix."""
        prefix_real = os.path.realpath(prefix_path)
        killed_pids: List[int] = []

        # 1. First attempt wineserver -k if wineserver exists
        wineserver_bin = shutil.which("wineserver")
        if wineserver_bin and os.path.isdir(prefix_real):
            env = os.environ.copy()
            env["WINEPREFIX"] = prefix_real
            try:
                subprocess.run(
                    [wineserver_bin, "-k"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout,
                )
            except (subprocess.SubprocessError, OSError):
                pass

        # 2. Check remaining processes
        procs = self.list_prefix_processes(prefix_real)
        for p in procs:
            try:
                if os.name != "nt":
                    os.kill(p.pid, signal.SIGTERM)
                killed_pids.append(p.pid)
            except OSError:
                pass

        # If any remain after grace period, force SIGKILL
        if killed_pids and os.name != "nt":
            time.sleep(0.2)
            for pid in killed_pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass

        # 3. Clean up lock files
        self.reset_prefix_locks(prefix_real)

        return {
            "prefix_path": prefix_real,
            "killed_pids": killed_pids,
            "status": "cleared",
        }

    def reset_prefix_locks(self, prefix_path: str) -> List[str]:
        """Remove stale lock files or socket endpoints left by crashed runners."""
        prefix_real = os.path.realpath(prefix_path)
        removed_locks: List[str] = []

        lock_candidates = [
            os.path.join(prefix_real, ".update-timestamp"),
            os.path.join(prefix_real, ".wine-lock"),
        ]

        for lock_file in lock_candidates:
            if os.path.exists(lock_file):
                try:
                    if os.path.isdir(lock_file):
                        shutil.rmtree(lock_file)
                    else:
                        os.remove(lock_file)
                    removed_locks.append(os.path.basename(lock_file))
                except OSError:
                    pass

        return removed_locks

    def launch_wine_tool(
        self,
        prefix_path: str,
        tool_name: str,
        wine_bin: Optional[str] = None,
        background: bool = True,
    ) -> Dict[str, Any]:
        """Launch a built-in Wine management tool inside the specified prefix."""
        tool_key = tool_name.strip().lower()
        if tool_key not in self.SUPPORTED_WINE_TOOLS:
            raise ValueError(
                f"Unsupported Wine tool '{tool_name}'. Supported: {', '.join(self.SUPPORTED_WINE_TOOLS.keys())}"
            )

        cmd_executable = self.SUPPORTED_WINE_TOOLS[tool_key]
        wine_exec = wine_bin or shutil.which("wine") or "wine"

        env = os.environ.copy()
        env["WINEPREFIX"] = os.path.realpath(prefix_path)

        cmd = [wine_exec, cmd_executable]
        if background:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True if os.name != "nt" else False,
            )
            return {
                "tool": tool_key,
                "command": cmd,
                "pid": proc.pid,
                "status": "launched",
            }
        else:
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            return {
                "tool": tool_key,
                "command": cmd,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "status": "completed",
            }
