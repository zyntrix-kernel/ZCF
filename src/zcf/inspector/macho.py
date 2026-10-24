"""
Pure-Python Mach-O binary parser.
Parses Apple macOS / iOS thin and Universal Fat binaries, load commands, dylibs, and architectures.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional

from zcf.core.exceptions import UnsupportedFormatError
from zcf.core.models import Architecture, BinaryFormat, Subsystem


MACHO_CPU_MAP = {
    0x00000007: Architecture.I386,
    0x01000007: Architecture.X86_64,
    0x0000000C: Architecture.ARM,
    0x0100000C: Architecture.ARM64,
}

MACHO_MAGICS = {
    0xFEEDFACE: ("32", ">"),
    0xCEFAEDFE: ("32", "<"),
    0xFEEDFACF: ("64", ">"),
    0xCFFAEDFE: ("64", "<"),
}

FAT_MAGICS = {
    0xCAFEBABE: ">",
    0xBEBAFECA: "<",
}


class MachOParser:
    """Parses Mach-O thin and universal binaries."""

    def __init__(self, data: bytes):
        self.data = data
        self.length = len(data)

    def parse(self) -> Dict[str, Any]:
        if self.length < 32:
            raise UnsupportedFormatError("File too small for Mach-O header")

        magic = struct.unpack_from(">I", self.data, 0)[0]

        # Check for Universal Fat Binary
        if magic in FAT_MAGICS:
            endian = FAT_MAGICS[magic]
            nfat_arch = struct.unpack_from(f"{endian}I", self.data, 4)[0]
            architectures: List[str] = []
            for i in range(min(nfat_arch, 16)):
                arch_off = 8 + (i * 20)
                if arch_off + 20 <= self.length:
                    cputype, cpusubtype, offset, size, align = struct.unpack_from(f"{endian}IIIII", self.data, arch_off)
                    arch = MACHO_CPU_MAP.get(cputype, Architecture.UNKNOWN)
                    if arch.value not in architectures:
                        architectures.append(arch.value)

            return {
                "format": BinaryFormat.MACHO,
                "architecture": Architecture.UNIVERSAL,
                "subsystem": Subsystem.POSIX,
                "is_managed": False,
                "is_universal": True,
                "fat_architectures": architectures,
                "needed_libraries": [],
            }

        # Check for Thin Mach-O
        magic_le = struct.unpack_from("<I", self.data, 0)[0]
        bit_width = None
        endian = None

        if magic in MACHO_MAGICS:
            bit_width, endian = MACHO_MAGICS[magic]
        elif magic_le in MACHO_MAGICS:
            bit_width, endian = MACHO_MAGICS[magic_le]
        else:
            raise UnsupportedFormatError(f"Invalid Mach-O magic: 0x{magic:08x}")

        is_64bit = bit_width == "64"
        cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags = struct.unpack_from(f"{endian}IIIIII", self.data, 4)

        arch = MACHO_CPU_MAP.get(cputype, Architecture.UNKNOWN)
        header_size = 32 if is_64bit else 28

        # Parse Load Commands
        needed_libraries: List[str] = []
        has_signature = False
        cmd_offset = header_size

        for _ in range(ncmds):
            if cmd_offset + 8 > self.length:
                break
            cmd, cmdsize = struct.unpack_from(f"{endian}II", self.data, cmd_offset)
            if cmdsize < 8 or cmd_offset + cmdsize > self.length:
                break

            # LC_LOAD_DYLIB (0xC) or LC_LOAD_WEAK_DYLIB (0x80000018)
            if cmd in (0x0C, 0x80000018):
                str_offset = struct.unpack_from(f"{endian}I", self.data, cmd_offset + 8)[0]
                full_str_off = cmd_offset + str_offset
                if full_str_off < self.length:
                    end = self.data.find(b"\x00", full_str_off)
                    if end != -1:
                        dylib_name = self.data[full_str_off:end].decode("utf-8", errors="ignore")
                        if dylib_name and dylib_name not in needed_libraries:
                            needed_libraries.append(dylib_name)

            # LC_CODE_SIGNATURE (0x1D)
            elif cmd == 0x1D:
                has_signature = True

            cmd_offset += cmdsize

        return {
            "format": BinaryFormat.MACHO,
            "architecture": arch,
            "subsystem": Subsystem.POSIX,
            "is_managed": False,
            "is_universal": False,
            "is_64bit": is_64bit,
            "needed_libraries": needed_libraries,
            "has_digital_signature": has_signature,
        }
