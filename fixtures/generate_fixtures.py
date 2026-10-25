"""
Generates deterministic synthetic binary fixtures for ZCF automated test suite.
Includes PE32+, ELF64 x86_64, ELF64 AArch64, Mach-O 64-bit, Android APK, and Shell Scripts.
"""

import io
import os
import struct
import zipfile

fixtures_dir = os.path.join(os.path.dirname(__file__), "synthetic")
os.makedirs(fixtures_dir, exist_ok=True)

# 1. Synthetic valid PE32+ (x86_64 console)
dos_header = bytearray(64)
dos_header[0:2] = b"MZ"
struct.pack_into("<I", dos_header, 0x3C, 64)

pe_sig = b"PE\x00\x00"
coff_hdr = struct.pack("<HHIIIHH", 0x8664, 2, 0, 0, 0, 112, 0x0022)

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
elf_hdr = struct.pack("<HHIQQQIHHHHHH", 2, 62, 1, 0x400000, 64, 0, 0, 64, 56, 0, 64, 0, 0)
with open(os.path.join(fixtures_dir, "valid_elf64_x86_64"), "wb") as f:
    f.write(e_ident + elf_hdr)

# 3. Synthetic valid ELF64 (AArch64 - machine 183 / 0xB7)
elf_arm64_hdr = struct.pack("<HHIQQQIHHHHHH", 2, 183, 1, 0x400000, 64, 0, 0, 64, 56, 0, 64, 0, 0)
with open(os.path.join(fixtures_dir, "valid_elf64_aarch64"), "wb") as f:
    f.write(e_ident + elf_arm64_hdr)

# 4. Synthetic valid Mach-O 64-bit (x86_64) - 32-byte header with reserved DWORD
# Magic: 0xFEEDFACF (64-bit big endian), cputype: 0x01000007 (x86_64), cpusubtype: 3, filetype: 2 (MH_EXECUTE), ncmds: 0, sizeofcmds: 0, flags: 0x85, reserved: 0
macho_hdr = struct.pack(">IIIIIIII", 0xFEEDFACF, 0x01000007, 3, 2, 0, 0, 0x85, 0)
with open(os.path.join(fixtures_dir, "valid_macho64"), "wb") as f:
    f.write(macho_hdr)

# 5. Synthetic valid Android APK
apk_buffer = io.BytesIO()
with zipfile.ZipFile(apk_buffer, "w") as zf:
    zf.writestr("AndroidManifest.xml", b"<manifest package='org.zyntrix.test'/>")
    zf.writestr("classes.dex", b"DEX\n035\x00")
    zf.writestr("lib/arm64-v8a/libnative.so", b"\x7fELFfake")
    zf.writestr("lib/x86_64/libnative.so", b"\x7fELFfake")
with open(os.path.join(fixtures_dir, "valid_app.apk"), "wb") as f:
    f.write(apk_buffer.getvalue())

# 6. Synthetic valid shell script
with open(os.path.join(fixtures_dir, "valid_script.sh"), "wb") as f:
    f.write(b"#!/bin/bash\necho 'ZCF Test Script'\n")

# 7. Corrupted binary
with open(os.path.join(fixtures_dir, "corrupted.bin"), "wb") as f:
    f.write(b"\x00\x01\x02\x03\x04\x05")

import hashlib
print("Generated all synthetic test fixtures successfully. Computed fixture hashes:")
for fname in sorted(os.listdir(fixtures_dir)):
    fpath = os.path.join(fixtures_dir, fname)
    if os.path.isfile(fpath):
        h = hashlib.sha256(open(fpath, "rb").read()).hexdigest()
        print(f"  {fname}: {h}")
