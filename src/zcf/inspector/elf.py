"""
Pure-Python Executable and Linkable Format (ELF) binary parser.
Extracts architecture, endianness, interpreter, dynamic libraries (DT_NEEDED), sections, and RPATH without external dependencies.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Tuple

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

        # Parse Program Headers for PT_INTERP and PT_DYNAMIC
        interpreter = None
        dynamic_ph: Optional[Tuple[int, int]] = None  # (offset, size)

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
                elif p_type == 2:  # PT_DYNAMIC
                    dynamic_ph = (p_offset, p_filesz)

        # Parse Section Headers
        sections = []
        needed_libraries: List[str] = []
        rpath = None
        runpath = None

        if e_shoff > 0 and e_shnum > 0 and e_shentsize > 0 and e_shoff + (e_shnum * e_shentsize) <= self.length:
            raw_sections = []
            for i in range(e_shnum):
                s_off = e_shoff + (i * e_shentsize)
                if is_64bit:
                    sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_info, sh_align, sh_entsize = struct.unpack_from(
                        f"{endian}IIQQQQIIQQ", self.data, s_off
                    )
                else:
                    sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_info, sh_align, sh_entsize = struct.unpack_from(
                        f"{endian}IIIIIIIIII", self.data, s_off
                    )
                raw_sections.append({
                    "name_idx": sh_name,
                    "type": sh_type,
                    "offset": sh_offset,
                    "size": sh_size,
                    "link": sh_link,
                })

            # Read section names from shstrtab
            shstrtab_offset = 0
            shstrtab_size = 0
            if e_shstrndx < len(raw_sections):
                shstrtab_offset = raw_sections[e_shstrndx]["offset"]
                shstrtab_size = raw_sections[e_shstrndx]["size"]

            for sec in raw_sections:
                name = ""
                n_idx = sec["name_idx"]
                if shstrtab_offset > 0 and n_idx < shstrtab_size:
                    end = self.data.find(b"\x00", shstrtab_offset + n_idx)
                    if end != -1:
                        name = self.data[shstrtab_offset + n_idx : end].decode("utf-8", errors="ignore")
                sec["name"] = name
                if name:
                    sections.append(name)

            # Find .dynamic section and its linked string table
            for sec in raw_sections:
                if sec["type"] == 6:  # SHT_DYNAMIC
                    strtab_idx = sec["link"]
                    if strtab_idx < len(raw_sections):
                        dynstr_off = raw_sections[strtab_idx]["offset"]
                        dynstr_size = raw_sections[strtab_idx]["size"]
                        dyn_off = sec["offset"]
                        dyn_size = sec["size"]
                        entry_size = 16 if is_64bit else 8

                        curr = dyn_off
                        while curr + entry_size <= dyn_off + dyn_size and curr + entry_size <= self.length:
                            if is_64bit:
                                d_tag, d_val = struct.unpack_from(f"{endian}qQ", self.data, curr)
                            else:
                                d_tag, d_val = struct.unpack_from(f"{endian}iI", self.data, curr)

                            if d_tag == 0:  # DT_NULL
                                break
                            elif d_tag == 1:  # DT_NEEDED
                                if dynstr_off + d_val < dynstr_off + dynstr_size:
                                    end = self.data.find(b"\x00", dynstr_off + d_val)
                                    if end != -1:
                                        lib_name = self.data[dynstr_off + d_val : end].decode("utf-8", errors="ignore")
                                        if lib_name and lib_name not in needed_libraries:
                                            needed_libraries.append(lib_name)
                            elif d_tag == 15:  # DT_RPATH
                                if dynstr_off + d_val < dynstr_off + dynstr_size:
                                    end = self.data.find(b"\x00", dynstr_off + d_val)
                                    if end != -1:
                                        rpath = self.data[dynstr_off + d_val : end].decode("utf-8", errors="ignore")
                            elif d_tag == 29:  # DT_RUNPATH
                                if dynstr_off + d_val < dynstr_off + dynstr_size:
                                    end = self.data.find(b"\x00", dynstr_off + d_val)
                                    if end != -1:
                                        runpath = self.data[dynstr_off + d_val : end].decode("utf-8", errors="ignore")
                            curr += entry_size

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
            "needed_libraries": needed_libraries,
            "rpath": rpath or runpath,
            "sections": sections,
        }
