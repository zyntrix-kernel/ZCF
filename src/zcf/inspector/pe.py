"""
Pure-Python Portable Executable (PE/COFF) binary parser.
Extracts architecture, subsystem, imports, exports, sections, digital signatures, and .NET CLI metadata without external dependencies.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Tuple

from zcf.core.exceptions import UnsupportedFormatError
from zcf.core.models import Architecture, BinaryFormat, Subsystem


PE_MACHINE_MAP = {
    0x014C: Architecture.I386,
    0x8664: Architecture.X86_64,
    0xAA64: Architecture.ARM64,
    0x01C0: Architecture.ARM,
    0x01C4: Architecture.ARM,
    0x5032: Architecture.RISCV64,
}

PE_SUBSYSTEM_MAP = {
    1: Subsystem.NATIVE,
    2: Subsystem.GUI,      # IMAGE_SUBSYSTEM_WINDOWS_GUI
    3: Subsystem.CONSOLE,  # IMAGE_SUBSYSTEM_WINDOWS_CUI
    7: Subsystem.POSIX,
}


class PEParser:
    """Parses Windows PE32 / PE32+ executables and dynamic link libraries."""

    def __init__(self, data: bytes):
        self.data = data
        self.length = len(data)
        self.sections: List[Dict[str, Any]] = []

    def parse(self) -> Dict[str, Any]:
        if self.length < 64:
            raise UnsupportedFormatError("File too small to contain a valid DOS header")

        # DOS Header check
        dos_sig = self.data[0:2]
        if dos_sig != b"MZ":
            raise UnsupportedFormatError(f"Invalid DOS header signature: {dos_sig.hex()}")

        # Offset to PE header located at 0x3C (DWORD)
        pe_offset = struct.unpack_from("<I", self.data, 0x3C)[0]
        if pe_offset + 24 > self.length:
            raise UnsupportedFormatError(f"PE header offset 0x{pe_offset:x} exceeds file size")

        pe_sig = self.data[pe_offset : pe_offset + 4]
        if pe_sig != b"PE\x00\x00":
            raise UnsupportedFormatError(f"Invalid PE header signature: {pe_sig.hex()}")

        # COFF File Header (20 bytes following PE signature)
        coff_offset = pe_offset + 4
        machine, num_sections, timedate, sym_table, num_syms, opt_hdr_size, characteristics = struct.unpack_from(
            "<HHIIIHH", self.data, coff_offset
        )

        arch = PE_MACHINE_MAP.get(machine, Architecture.UNKNOWN)

        subsystem = Subsystem.UNKNOWN
        is_managed = False
        entry_point = None
        opt_magic = None
        imported_dlls: List[str] = []
        has_signature = False
        has_tls = False

        opt_offset = coff_offset + 20
        sections_offset = opt_offset + opt_hdr_size

        # Parse Sections
        self.sections = self._parse_sections(sections_offset, num_sections)

        if opt_hdr_size > 0 and opt_offset + opt_hdr_size <= self.length:
            opt_magic = struct.unpack_from("<H", self.data, opt_offset)[0]

            if opt_magic in (0x10B, 0x20B):  # PE32 or PE32+
                entry_point_rva = struct.unpack_from("<I", self.data, opt_offset + 16)[0]
                entry_point = f"0x{entry_point_rva:08x}"

                subsystem_offset = opt_offset + 68
                if subsystem_offset + 2 <= self.length:
                    subsystem_id = struct.unpack_from("<H", self.data, subsystem_offset)[0]
                    subsystem = PE_SUBSYSTEM_MAP.get(subsystem_id, Subsystem.UNKNOWN)

                dirs_count_offset = opt_offset + (92 if opt_magic == 0x10B else 108)
                if dirs_count_offset + 4 <= opt_offset + opt_hdr_size:
                    num_dirs = struct.unpack_from("<I", self.data, dirs_count_offset)[0]
                    dirs_start = dirs_count_offset + 4

                    # Helper to get directory RVA & Size
                    def get_dir(idx: int) -> Tuple[int, int]:
                        if idx < num_dirs:
                            d_off = dirs_start + (idx * 8)
                            if d_off + 8 <= opt_offset + opt_hdr_size:
                                return struct.unpack_from("<II", self.data, d_off)
                        return (0, 0)

                    # Directory 1: Imports
                    import_rva, import_size = get_dir(1)
                    if import_rva > 0:
                        imported_dlls = self._parse_imports(import_rva)

                    # Directory 4: Certificate Table (Security)
                    sec_rva, sec_size = get_dir(4)
                    has_signature = sec_rva > 0 and sec_size > 0

                    # Directory 9: TLS
                    tls_rva, tls_size = get_dir(9)
                    has_tls = tls_rva > 0 and tls_size > 0

                    # Directory 14: COM Descriptor (.NET CLI)
                    com_rva, com_size = get_dir(14)
                    is_managed = com_rva > 0 and com_size > 0

        return {
            "format": BinaryFormat.PE,
            "architecture": arch,
            "subsystem": subsystem,
            "is_managed": is_managed,
            "entry_point": entry_point,
            "machine_hex": f"0x{machine:04x}",
            "num_sections": num_sections,
            "is_64bit": opt_magic == 0x20B,
            "imported_dlls": imported_dlls,
            "sections": [s["name"] for s in self.sections],
            "has_digital_signature": has_signature,
            "has_tls": has_tls,
        }

    def _parse_sections(self, offset: int, count: int) -> List[Dict[str, Any]]:
        sections = []
        for i in range(count):
            sec_off = offset + (i * 40)
            if sec_off + 40 > self.length:
                break
            name_bytes = self.data[sec_off : sec_off + 8]
            name = name_bytes.split(b"\x00")[0].decode("utf-8", errors="ignore")
            vsize, vaddr, raw_size, raw_offset = struct.unpack_from("<IIII", self.data, sec_off + 8)
            sections.append({
                "name": name,
                "virtual_size": vsize,
                "virtual_address": vaddr,
                "raw_size": raw_size,
                "raw_offset": raw_offset,
            })
        return sections

    def _rva_to_offset(self, rva: int) -> Optional[int]:
        for sec in self.sections:
            vstart = sec["virtual_address"]
            vsize = max(sec["virtual_size"], sec["raw_size"])
            if vstart <= rva < vstart + vsize:
                offset_into_section = rva - vstart
                if offset_into_section < sec["raw_size"]:
                    return sec["raw_offset"] + offset_into_section
        return None

    def _parse_imports(self, import_rva: int) -> List[str]:
        dll_names: List[str] = []
        file_offset = self._rva_to_offset(import_rva)
        if not file_offset or file_offset >= self.length:
            return dll_names

        # Each IMAGE_IMPORT_DESCRIPTOR is 20 bytes
        # struct { OriginalFirstThunk; TimeDateStamp; ForwarderChain; Name (RVA); FirstThunk; }
        curr = file_offset
        while curr + 20 <= self.length:
            orig_thunk, timedate, fwd_chain, name_rva, first_thunk = struct.unpack_from("<IIIII", self.data, curr)
            if orig_thunk == 0 and name_rva == 0 and first_thunk == 0:
                break  # Null descriptor terminates list

            name_offset = self._rva_to_offset(name_rva)
            if name_offset and name_offset < self.length:
                # Read null-terminated string
                end = self.data.find(b"\x00", name_offset)
                if end != -1:
                    dll_name = self.data[name_offset:end].decode("utf-8", errors="ignore")
                    if dll_name and dll_name not in dll_names:
                        dll_names.append(dll_name)
            curr += 20
        return dll_names
