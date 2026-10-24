"""
Generates deterministic synthetic binary fixtures for ZCF automated test suite.
"""

import os
import struct

fixtures_dir = os.path.join(os.path.dirname(__file__), "synthetic")
os.makedirs(fixtures_dir, exist_ok=True)

# 1. Synthetic valid PE32+ (x86_64 console)
# DOS Header: MZ, 0x3C points to offset 64 (0x40)
dos_header = bytearray(64)
dos_header[0:2] = b"MZ"
struct.pack_into("<I", dos_header, 0x3C, 64)

# PE Header: PE\0\0 (4 bytes), COFF Header (20 bytes), Optional Header (PE32+ 112 bytes)
pe_sig = b"PE\x00\x00"
coff_hdr = struct.pack("<HHIIIHH", 0x8664, 2, 0, 0, 0, 112, 0x0022)

# Optional Header PE32+ (Magic 0x20B)
opt_hdr = bytearray(112)
struct.pack_into("<H", opt_hdr, 0, 0x020B)        # Magic
struct.pack_into("<I", opt_hdr, 16, 0x00001000)   # Entry point
struct.pack_into("<H", opt_hdr, 68, 3)            # Subsystem = IMAGE_SUBSYSTEM_WINDOWS_CUI (3)
struct.pack_into("<I", opt_hdr, 108, 0)           # Num data dirs = 0

valid_pe_bytes = bytes(dos_header) + pe_sig + coff_hdr + bytes(opt_hdr)
with open(os.path.join(fixtures_dir, "valid_pe32plus.exe"), "wb") as f:
    f.write(valid_pe_bytes)

# 2. Synthetic valid ELF64 (x86_64) - full 64-byte header
e_ident = b"\x7fELF\x02\x01\x01\x00" + (b"\x00" * 8)
# e_type: 2 (ET_EXEC), e_machine: 62 (0x3E x86_64), e_version: 1, e_entry: 0x400000,
# e_phoff: 64, e_shoff: 0, e_flags: 0, e_ehsize: 64, e_phentsize: 56, e_phnum: 0,
# e_shentsize: 64, e_shnum: 0, e_shstrndx: 0
elf_hdr = struct.pack("<HHIQQQIHHHHHH", 2, 62, 1, 0x400000, 64, 0, 0, 64, 56, 0, 64, 0, 0)
with open(os.path.join(fixtures_dir, "valid_elf64_x86_64"), "wb") as f:
    f.write(e_ident + elf_hdr)

# 3. Synthetic valid ELF64 (AArch64 - machine 183 / 0xB7)
elf_arm64_hdr = struct.pack("<HHIQQQIHHHHHH", 2, 183, 1, 0x400000, 64, 0, 0, 64, 56, 0, 64, 0, 0)
with open(os.path.join(fixtures_dir, "valid_elf64_aarch64"), "wb") as f:
    f.write(e_ident + elf_arm64_hdr)

# 4. Synthetic valid shell script
with open(os.path.join(fixtures_dir, "valid_script.sh"), "wb") as f:
    f.write(b"#!/bin/bash\necho 'ZCF Test Script'\n")

# 5. Corrupted binary
with open(os.path.join(fixtures_dir, "corrupted.bin"), "wb") as f:
    f.write(b"\x00\x01\x02\x03\x04\x05")

print("Generated all synthetic test fixtures successfully.")
