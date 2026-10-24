"""
Pure-Python Portable Executable (PE/COFF) binary parser.
Extracts architecture, subsystem, imports, and .NET CLI metadata without external dependencies.
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

        if opt_hdr_size > 0 and coff_offset + 20 + opt_hdr_size <= self.length:
            opt_offset = coff_offset + 20
            opt_magic = struct.unpack_from("<H", self.data, opt_offset)[0]

            if opt_magic in (0x10B, 0x20B):  # PE32 or PE32+
                entry_point_rva = struct.unpack_from("<I", self.data, opt_offset + 16)[0]
                entry_point = f"0x{entry_point_rva:08x}"

                # Subsystem offset differs between PE32 and PE32+
                subsystem_offset = opt_offset + (68 if opt_magic == 0x10B else 68)
                subsystem_id = struct.unpack_from("<H", self.data, subsystem_offset)[0]
                subsystem = PE_SUBSYSTEM_MAP.get(subsystem_id, Subsystem.UNKNOWN)

                # Data directories:
                # Number of Rva and Sizes is at offset 92 (PE32) or 108 (PE32+)
                dirs_count_offset = opt_offset + (92 if opt_magic == 0x10B else 108)
                if dirs_count_offset + 4 <= opt_offset + opt_hdr_size:
                    num_dirs = struct.unpack_from("<I", self.data, dirs_count_offset)[0]
                    # Directory 14 is IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR (.NET CLI Header)
                    if num_dirs > 14:
                        com_dir_offset = dirs_count_offset + 4 + (14 * 8)
                        if com_dir_offset + 8 <= opt_offset + opt_hdr_size:
                            com_rva, com_size = struct.unpack_from("<II", self.data, com_dir_offset)
                            if com_rva > 0 and com_size > 0:
                                is_managed = True

        return {
            "format": BinaryFormat.PE,
            "architecture": arch,
            "subsystem": subsystem,
            "is_managed": is_managed,
            "entry_point": entry_point,
            "machine_hex": f"0x{machine:04x}",
            "num_sections": num_sections,
            "is_64bit": opt_magic == 0x20B,
        }
