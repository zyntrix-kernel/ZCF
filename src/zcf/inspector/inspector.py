"""
Unified Application and Artifact Inspector.
Orchestrates PE, ELF, Mach-O, APK, and Script parsers with cryptographic hashing.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional

from zcf.core.exceptions import InspectionError, UnsupportedFormatError
from zcf.core.models import ApplicationDescription, Architecture, BinaryFormat, Subsystem
from zcf.inspector.apk import APKParser
from zcf.inspector.elf import ELFParser
from zcf.inspector.macho import MachOParser
from zcf.inspector.pe import PEParser
from zcf.inspector.scripts import ScriptParser


class ApplicationInspector:
    """Inspects target executables, scripts, and archives safely without code execution."""

    def __init__(self, enable_rea_enrichment: bool = False):
        self.enable_rea_enrichment = enable_rea_enrichment

    def inspect(self, artifact_path: str) -> ApplicationDescription:
        if not os.path.exists(artifact_path):
            raise InspectionError(f"Artifact path does not exist: {artifact_path}")

        if not os.path.isfile(artifact_path):
            raise InspectionError(f"Artifact path is not a regular file: {artifact_path}")

        file_size = os.path.getsize(artifact_path)
        sha256 = self._compute_sha256(artifact_path)
        file_name = os.path.basename(artifact_path)

        # Read up to 2MB to capture sections, dynamic symbols, and import tables safely
        max_read = min(file_size, 2 * 1024 * 1024)
        with open(artifact_path, "rb") as f:
            header_bytes = f.read(max_read)

        parsed_info = self._detect_and_parse(header_bytes, file_name)
        security_indicators = self._detect_security_indicators(header_bytes)

        return ApplicationDescription(
            artifact_path=os.path.abspath(artifact_path),
            file_name=file_name,
            sha256=sha256,
            byte_size=file_size,
            format=parsed_info.get("format", BinaryFormat.UNKNOWN),
            architecture=parsed_info.get("architecture", Architecture.UNKNOWN),
            subsystem=parsed_info.get("subsystem", Subsystem.UNKNOWN),
            is_managed=parsed_info.get("is_managed", False),
            runtime_family=parsed_info.get("runtime_family"),
            declared_dependencies=parsed_info.get("declared_dependencies")
            or parsed_info.get("imported_dlls")
            or parsed_info.get("needed_libraries")
            or [],
            entry_point=parsed_info.get("entry_point"),
            security_indicators=security_indicators,
            limitations=parsed_info.get("limitations", []),
        )

    def _detect_and_parse(self, data: bytes, file_name: str) -> Dict[str, Any]:
        # 1. Windows PE
        if len(data) >= 2 and data[:2] == b"MZ":
            try:
                parser = PEParser(data)
                return parser.parse()
            except UnsupportedFormatError as e:
                return {
                    "format": BinaryFormat.PE,
                    "architecture": Architecture.UNKNOWN,
                    "subsystem": Subsystem.UNKNOWN,
                    "limitations": [f"Malformed PE header: {str(e)}"],
                }

        # 2. Linux / BSD ELF
        if len(data) >= 4 and data[:4] == b"\x7fELF":
            try:
                parser = ELFParser(data)
                return parser.parse()
            except UnsupportedFormatError as e:
                return {
                    "format": BinaryFormat.ELF,
                    "architecture": Architecture.UNKNOWN,
                    "subsystem": Subsystem.UNKNOWN,
                    "limitations": [f"Malformed ELF header: {str(e)}"],
                }

        # 3. Apple Mach-O (Thin & Universal Fat)
        macho_sigs = (
            b"\xfe\xed\xfa\xce",
            b"\xce\xfa\xed\xfe",
            b"\xfe\xed\xfa\xcf",
            b"\xcf\xfa\xed\xfe",
            b"\xca\xfe\xba\xbe",
            b"\xbe\xba\xfe\xca",
        )
        if len(data) >= 4 and data[:4] in macho_sigs:
            try:
                parser = MachOParser(data)
                return parser.parse()
            except UnsupportedFormatError as e:
                return {
                    "format": BinaryFormat.MACHO,
                    "architecture": Architecture.UNKNOWN,
                    "subsystem": Subsystem.POSIX,
                    "limitations": [f"Malformed Mach-O header: {str(e)}"],
                }

        # 4. ZIP Archive / Android APK
        if len(data) >= 4 and data[:4] == b"PK\x03\x04":
            parser = APKParser(data, file_name)
            return parser.parse()

        # 5. Scripts and Interpreted Files
        if data.startswith(b"#!") or any(file_name.endswith(ext) for ext in (".py", ".sh", ".js", ".bat", ".cmd")):
            parser = ScriptParser(data, file_name)
            return parser.parse()

        return {
            "format": BinaryFormat.UNKNOWN,
            "architecture": Architecture.UNKNOWN,
            "subsystem": Subsystem.UNKNOWN,
            "limitations": ["Unknown binary signature or unsupported file format"],
        }

    def _compute_sha256(self, file_path: str) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _detect_security_indicators(self, data: bytes) -> Dict[str, bool]:
        data_lower = data.lower()
        has_anti_cheat = any(ac in data_lower for ac in (b"easyanticheat", b"battleye", b"vanguard", b"denuvo"))
        has_drm = any(drm in data_lower for drm in (b"securom", b"safedisc", b"arxan"))
        requires_driver = b".sys" in data_lower

        return {
            "has_anti_cheat": has_anti_cheat,
            "has_drm": has_drm,
            "requires_kernel_driver": requires_driver,
        }
