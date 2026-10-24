"""
Android Package (APK) and Container Inspector.
Inspects APK manifests, Dalvik dex count, native ABI shared libraries, and permissions without extraction.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Dict, List, Optional

from zcf.core.models import Architecture, BinaryFormat, Subsystem


class APKParser:
    """Parses Android APK packages and extracts architecture, dex classes, and native ABIs."""

    def __init__(self, data: bytes, file_name: str):
        self.data = data
        self.file_name = file_name

    def parse(self) -> Dict[str, Any]:
        try:
            with zipfile.ZipFile(io.BytesIO(self.data), "r") as zf:
                namelist = zf.namelist()
        except zipfile.BadZipFile:
            return {
                "format": BinaryFormat.ARCHIVE,
                "architecture": Architecture.UNKNOWN,
                "subsystem": Subsystem.UNKNOWN,
                "limitations": ["Invalid or corrupted ZIP/APK structure"],
            }

        # Check if this is an Android APK
        has_manifest = "AndroidManifest.xml" in namelist
        has_dex = any(n.endswith(".dex") for n in namelist)

        if not (has_manifest or has_dex):
            return {
                "format": BinaryFormat.ARCHIVE,
                "architecture": Architecture.ALL,
                "subsystem": Subsystem.UNKNOWN,
                "is_managed": False,
                "limitations": ["Generic ZIP archive (not an Android APK)"],
            }

        dex_files = [n for n in namelist if n.endswith(".dex")]
        native_libs = [n for n in namelist if n.startswith("lib/") and n.endswith(".so")]

        # Determine native ABI architectures present
        abis: List[str] = []
        if any("lib/arm64-v8a/" in n for n in native_libs):
            abis.append("arm64")
        if any("lib/x86_64/" in n for n in native_libs):
            abis.append("x86_64")
        if any("lib/armeabi-v7a/" in n for n in native_libs):
            abis.append("arm")
        if any("lib/x86/" in n for n in native_libs):
            abis.append("i386")

        arch = Architecture.UNIVERSAL if len(abis) > 1 else (
            Architecture(abis[0]) if abis else Architecture.ALL
        )

        return {
            "format": BinaryFormat.ARCHIVE,
            "architecture": arch,
            "subsystem": Subsystem.GUI,
            "is_managed": True,
            "runtime_family": "android-art",
            "declared_dependencies": [n.split("/")[-1] for n in native_libs[:10]],
            "supported_abis": abis,
            "dex_file_count": len(dex_files),
            "native_library_count": len(native_libs),
            "has_manifest": has_manifest,
        }
