"""
Pure-Python Executable and Linkable Format (ELF) binary parser.
Extracts architecture, endianness, interpreter, and dynamic libraries without external dependencies.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional

from zcf.core.exceptions import UnsupportedFormatError
from zcf.core.models import Architecture, BinaryFormat, Subsystem


ELF_MACHINE_MAP = {
    0x03: Architecture.I386,
    0x3E: Architecture.X86_64,    # 62
    0x28: Architecture.ARM,       # 40
    0xB7: Architecture.ARM64,     # 183
    0xF3: Architecture.RISCV64,   # 243
}


class ELFParser:
    """Parses standard Linux/BSD ELF32 and ELF64 binaries."""

    def __init__(self, data: bytes):
        self.data = data
        self.length = len(data)

    def parse(self) -> Dict[str, Any]:
        if self.length < 52:
            raise UnsupportedFormatError("File too small to contain a valid ELF header")

        if self.data[0:4] != b"\x7fELF":
            raise UnsupportedFormatError(f"Invalid ELF signature: {self.data[0:4].hex()}")

        ei_class = self.data[4]    # 1 = 32-bit, 2 = 64-bit
        ei_data = self.data[5]     # 1 = Little Endian, 2 = Big Endian

        if ei_class not in (1, 2):
            raise UnsupportedFormatError(f"Invalid ELF class: {ei_class}")

        endian = "<" if ei_data == 1 else ">"
        is_64bit = ei_class == 2

        if is_64bit:
            if self.length < 64:
                raise UnsupportedFormatError("File too small for ELF64 header")
            (
                e_type,
                e_machine,
                e_version,
                e_entry,
                e_phoff,
                e_shoff,
                e_flags,
                e_ehsize,
                e_phentsize,
                e_phnum,
                e_shentsize,
                e_shnum,
                e_shstrndx,
            ) = struct.unpack_from(f"{endian}HHIQQQIHHHHHH", self.data, 16)
        else:
            (
                e_type,
                e_machine,
                e_version,
                e_entry,
                e_phoff,
                e_shoff,
                e_flags,
                e_ehsize,
                e_phentsize,
                e_phnum,
                e_shentsize,
                e_shnum,
                e_shstrndx,
            ) = struct.unpack_from(f"{endian}HHIIIIIHHHHHH", self.data, 16)

        arch = ELF_MACHINE_MAP.get(e_machine, Architecture.UNKNOWN)

        # Parse Program Headers for PT_INTERP (dynamic interpreter)
        interpreter = None
        if e_phoff > 0 and e_phnum > 0 and e_phentsize > 0:
            for i in range(e_phnum):
                ph_offset = e_phoff + (i * e_phentsize)
                if ph_offset + e_phentsize > self.length:
                    break
                if is_64bit:
                    p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from(
                        f"{endian}IIQQQQQQ", self.data, ph_offset
                    )
                else:
                    p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = struct.unpack_from(
                        f"{endian}IIIIIIII", self.data, ph_offset
                    )

                if p_type == 3:  # PT_INTERP
                    if p_offset + p_filesz <= self.length:
                        raw_interp = self.data[p_offset : p_offset + p_filesz]
                        interpreter = raw_interp.split(b"\x00")[0].decode("utf-8", errors="ignore")
                    break

        return {
            "format": BinaryFormat.ELF,
            "architecture": arch,
            "subsystem": Subsystem.POSIX,
            "is_managed": False,
            "entry_point": f"0x{e_entry:08x}",
            "machine_hex": f"0x{e_machine:04x}",
            "is_64bit": is_64bit,
            "is_pie": e_type == 3,  # ET_DYN (PIE executable or shared library)
            "interpreter": interpreter,
        }
