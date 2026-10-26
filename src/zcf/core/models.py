"""
Core data models and type definitions for ZCF.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BinaryFormat(str, Enum):
    PE = "pe"
    ELF = "elf"
    MACHO = "macho"
    SCRIPT = "script"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


class Architecture(str, Enum):
    X86_64 = "x86_64"
    I386 = "i386"
    ARM64 = "arm64"
    ARM = "arm"
    RISCV64 = "riscv64"
    UNIVERSAL = "universal"
    ALL = "all"
    UNKNOWN = "unknown"


class Subsystem(str, Enum):
    CONSOLE = "console"
    GUI = "gui"
    NATIVE = "native"
    POSIX = "posix"
    UNKNOWN = "unknown"


class WorkloadType(str, Enum):
    DESKTOP_GUI = "desktop_gui"
    CLI_TOOL = "cli_tool"
    GAME = "game"
    INSTALLER = "installer"
    BACKGROUND_SERVICE = "background_service"
    UNKNOWN = "unknown"


class ExecutionMode(str, Enum):
    NATIVE = "native"
    TRANSLATION = "translation"
    EMULATION = "emulation"
    SANDBOXED = "sandboxed"
    BLOCKED = "blocked"


class CompatibilityStatus(str, Enum):
    VERIFIED_COMPATIBLE = "verified_compatible"
    COMPATIBLE_WITH_WORKAROUND = "compatible_with_workaround"
    PARTIALLY_COMPATIBLE = "partially_compatible"
    INCOMPATIBLE = "incompatible"
    UNTESTED = "untested"


class ProvenanceTier(str, Enum):
    DEMO_FIXTURE = "demo_fixture"
    COMMUNITY_UNTESTED = "community_untested"
    AUTOMATED_TEST = "automated_test"
    MAINTAINER_VERIFIED = "maintainer_verified"


class EvidenceStatus(str, Enum):
    UNTESTED = "untested"
    COMMUNITY_REPORTED = "community_reported"
    REPRODUCED = "reproduced"
    VERIFIED = "verified"
    INCOMPATIBLE = "incompatible"


class DisplayServer(str, Enum):
    X11 = "x11"
    WAYLAND = "wayland"
    WINDOWS = "windows"
    HEADLESS = "headless"
    UNKNOWN = "unknown"


@dataclass
class ApplicationDescription:
    artifact_path: str
    file_name: str
    sha256: str
    byte_size: int
    format: BinaryFormat
    architecture: Architecture
    subsystem: Subsystem
    is_managed: bool = False
    runtime_family: Optional[str] = None
    declared_dependencies: List[str] = field(default_factory=list)
    entry_point: Optional[str] = None
    security_indicators: Dict[str, bool] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    workload_type: WorkloadType = WorkloadType.UNKNOWN
    is_installer: bool = False
    installer_format: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["format"] = self.format.value
        d["architecture"] = self.architecture.value
        d["subsystem"] = self.subsystem.value
        d["workload_type"] = self.workload_type.value
        return d


@dataclass
class RuntimeInfo:
    runtime_id: str
    name: str
    installed: bool
    version: Optional[str] = None
    binary_path: Optional[str] = None
    supported_formats: List[str] = field(default_factory=list)
    supported_architectures: List[str] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EnvironmentReport:
    os_name: str
    architecture: str
    kernel_version: str
    available_runtimes: List[RuntimeInfo] = field(default_factory=list)
    distribution: Optional[str] = None
    release: Optional[str] = None
    cpu_model: Optional[str] = None
    logical_cores: int = 1
    total_memory_mb: int = 0
    display_server: DisplayServer = DisplayServer.UNKNOWN
    graphics_capabilities: Dict[str, Any] = field(default_factory=dict)
    isolation_features: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["display_server"] = self.display_server.value
        d["available_runtimes"] = [r.to_dict() for r in self.available_runtimes]
        return d


@dataclass
class CandidateEvaluation:
    runtime_id: str
    eligible: bool
    score: float
    notes: str
    blocked: bool = False
    blocker_reasons: List[str] = field(default_factory=list)
    prerequisites_met: bool = True
    missing_prerequisites: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompatibilityPlan:
    plan_id: str
    artifact_sha256: str
    selected_runtime_id: Optional[str]
    confidence_score: float
    reasoning: str
    selected_runtime_name: Optional[str] = None
    execution_mode: ExecutionMode = ExecutionMode.BLOCKED
    is_blocked: bool = False
    blocker_summary: Optional[str] = None
    satisfied_requirements: List[str] = field(default_factory=list)
    missing_requirements: List[str] = field(default_factory=list)
    candidate_evaluations: List[CandidateEvaluation] = field(default_factory=list)
    confidence_criteria: Dict[str, float] = field(default_factory=dict)
    recommended_configuration: Dict[str, Any] = field(default_factory=dict)
    safe_next_steps: List[str] = field(default_factory=list)
    evidence_type: str = "static_analysis"
    similar_profiles: List[Dict[str, Any]] = field(default_factory=list)
    applied_workarounds: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["execution_mode"] = self.execution_mode.value
        d["candidate_evaluations"] = [c.to_dict() for c in self.candidate_evaluations]
        return d


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExecutionSecurityPolicy:
    workload_type: WorkloadType = WorkloadType.DESKTOP_GUI
    isolate_network: bool = True
    read_only_root: bool = True
    disposable_tmp: bool = False
    allow_root: bool = False
    max_memory_mb: Optional[int] = None
    max_cpu_seconds: Optional[int] = None
    default_timeout_seconds: Optional[int] = None
    max_timeout_seconds: Optional[int] = None
    writable_paths: List[str] = field(default_factory=list)
    environment_mode: str = "minimized_desktop"
    network_mode: str = "isolated"
    resource_limits_status: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["workload_type"] = self.workload_type.value
        return d


@dataclass
class ExecutionResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time_seconds: float
    command: List[str] = field(default_factory=list)
    isolated_env_path: Optional[str] = None
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    effective_runtime: Optional[str] = None
    effective_security_policy: Dict[str, Any] = field(default_factory=dict)
    permitted_writable_paths: List[str] = field(default_factory=list)
    security_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompatibilityEntry:
    entry_id: str
    application_name: str
    target_sha256: str
    target_format: str
    target_architecture: str
    status: CompatibilityStatus
    last_verified: str
    version: Optional[str] = None
    recommended_runtime: Optional[str] = None
    verified_environment: Dict[str, Any] = field(default_factory=dict)
    workarounds: List[Dict[str, Any]] = field(default_factory=list)
    diagnostic_signatures: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "2.0"
    provenance_tier: ProvenanceTier = ProvenanceTier.MAINTAINER_VERIFIED
    evidence_status: EvidenceStatus = EvidenceStatus.VERIFIED
    host_environment: Dict[str, Any] = field(default_factory=dict)
    runtime_configuration: Dict[str, Any] = field(default_factory=dict)
    test_procedure: str = ""
    verification_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["provenance_tier"] = self.provenance_tier.value
        d["evidence_status"] = self.evidence_status.value
        return d
