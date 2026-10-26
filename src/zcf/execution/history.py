"""
Execution History Manager for ZCF.
Persists, indexes, queries, and compares chronological application execution and test runs.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionRecord:
    run_id: str
    timestamp: str
    artifact_path: str
    artifact_sha256: str
    application_name: str
    target_format: str
    target_architecture: str
    runtime_id: str
    runtime_name: str
    execution_mode: str
    dry_run: bool
    success: bool
    exit_code: int
    execution_time_seconds: float
    sandbox_active: bool
    network_isolated: bool
    command: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    environment: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExecutionHistoryManager:
    """Manages persistent chronological execution and test run records under ~/.zcf/runs."""

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or os.path.expanduser("~/.zcf/runs")
        os.makedirs(self.storage_dir, exist_ok=True)

    def _resolve_run_path(self, run_id: str) -> str:
        if not run_id or not re.match(r"^[a-zA-Z0-9_\-]+$", run_id):
            raise ValueError(f"Invalid run_id '{run_id}': illegal characters or path traversal attempt.")
        abs_storage = os.path.abspath(self.storage_dir)
        target_path = os.path.abspath(os.path.join(abs_storage, f"{run_id}.json"))
        if not target_path.startswith(abs_storage):
            raise ValueError(f"Path traversal detected in run_id '{run_id}'")
        return target_path

    def record_run(
        self,
        artifact_path: str,
        artifact_sha256: str,
        application_name: str,
        target_format: str,
        target_architecture: str,
        runtime_id: str,
        runtime_name: str,
        execution_mode: str,
        dry_run: bool,
        success: bool,
        exit_code: int,
        execution_time_seconds: float,
        sandbox_active: bool,
        network_isolated: bool,
        command: Optional[List[str]] = None,
        stdout: str = "",
        stderr: str = "",
        diagnostics: Optional[List[Dict[str, Any]]] = None,
        environment: Optional[Dict[str, Any]] = None,
    ) -> ExecutionRecord:
        now = datetime.datetime.now(datetime.timezone.utc)
        ts_str = now.strftime("%Y%m%d_%H%M%S")
        short_sha = (artifact_sha256[:8]) if artifact_sha256 else "00000000"
        short_id = uuid.uuid4().hex[:6]
        run_id = f"run_{ts_str}_{short_sha}_{short_id}"

        # Bounded stdout storage (up to 256 KB)
        bounded_stdout = stdout
        if len(bounded_stdout) > 256 * 1024:
            bounded_stdout = bounded_stdout[: 256 * 1024] + "\n[ZCF Notice] Output truncated for history storage.\n"

        record = ExecutionRecord(
            run_id=run_id,
            timestamp=now.isoformat(),
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha256,
            application_name=application_name,
            target_format=target_format,
            target_architecture=target_architecture,
            runtime_id=runtime_id,
            runtime_name=runtime_name,
            execution_mode=execution_mode,
            dry_run=dry_run,
            success=success,
            exit_code=exit_code,
            execution_time_seconds=round(execution_time_seconds, 4),
            sandbox_active=sandbox_active,
            network_isolated=network_isolated,
            command=command or [],
            stdout=bounded_stdout,
            stderr=stderr,
            diagnostics=diagnostics or [],
            environment=environment or {},
        )

        file_path = self._resolve_run_path(run_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, indent=2)

        return record

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        try:
            file_path = self._resolve_run_path(run_id)
        except ValueError:
            return None
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def list_runs(self, sha256: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        if not os.path.exists(self.storage_dir):
            return records

        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json") and fname.startswith("run_"):
                fpath = os.path.join(self.storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if sha256 and data.get("artifact_sha256", "").lower() != sha256.lower():
                            continue
                        records.append(data)
                except Exception:
                    continue

        # Sort descending by timestamp
        records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return records[:limit]

    def delete_run(self, run_id: str) -> bool:
        try:
            file_path = self._resolve_run_path(run_id)
        except ValueError:
            return False
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return True
            except OSError:
                return False
        return False

    def clear_runs(self) -> int:
        count = 0
        if not os.path.exists(self.storage_dir):
            return 0
        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json") and fname.startswith("run_"):
                fpath = os.path.join(self.storage_dir, fname)
                try:
                    os.remove(fpath)
                    count += 1
                except OSError:
                    pass
        return count

    def compare_runs(self, run_id_a: str, run_id_b: str) -> Dict[str, Any]:
        run_a = self.get_run(run_id_a)
        run_b = self.get_run(run_id_b)
        if not run_a or not run_b:
            raise ValueError(f"One or both run records not found: '{run_id_a}', '{run_id_b}'")

        time_delta = run_b.get("execution_time_seconds", 0.0) - run_a.get("execution_time_seconds", 0.0)
        exit_code_changed = run_a.get("exit_code") != run_b.get("exit_code")
        runtime_changed = run_a.get("runtime_id") != run_b.get("runtime_id")
        improved = (not run_a.get("success") and run_b.get("success")) or (run_a.get("exit_code") != 0 and run_b.get("exit_code") == 0)

        return {
            "run_a": {
                "run_id": run_a.get("run_id"),
                "timestamp": run_a.get("timestamp"),
                "application": run_a.get("application_name"),
                "runtime": run_a.get("runtime_name"),
                "exit_code": run_a.get("exit_code"),
                "success": run_a.get("success"),
                "execution_time_seconds": run_a.get("execution_time_seconds"),
                "dry_run": run_a.get("dry_run"),
                "sandbox_active": run_a.get("sandbox_active"),
            },
            "run_b": {
                "run_id": run_b.get("run_id"),
                "timestamp": run_b.get("timestamp"),
                "application": run_b.get("application_name"),
                "runtime": run_b.get("runtime_name"),
                "exit_code": run_b.get("exit_code"),
                "success": run_b.get("success"),
                "execution_time_seconds": run_b.get("execution_time_seconds"),
                "dry_run": run_b.get("dry_run"),
                "sandbox_active": run_b.get("sandbox_active"),
            },
            "differences": {
                "exit_code_changed": exit_code_changed,
                "runtime_changed": runtime_changed,
                "execution_time_delta_seconds": round(time_delta, 4),
                "outcome_improved": improved,
            },
        }
