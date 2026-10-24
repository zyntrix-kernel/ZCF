"""
Unit tests for ZCF Application Inspector.
"""

import os
import unittest

from zcf.core.exceptions import InspectionError
from zcf.core.models import Architecture, BinaryFormat, Subsystem
from zcf.inspector.inspector import ApplicationInspector


class TestApplicationInspector(unittest.TestCase):
    def setUp(self):
        self.inspector = ApplicationInspector()
        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "synthetic"))

    def test_inspect_pe(self):
        pe_path = os.path.join(self.fixtures_dir, "valid_pe32plus.exe")
        app = self.inspector.inspect(pe_path)

        self.assertEqual(app.format, BinaryFormat.PE)
        self.assertEqual(app.architecture, Architecture.X86_64)
        self.assertEqual(app.subsystem, Subsystem.CONSOLE)
        self.assertFalse(app.is_managed)
        self.assertEqual(app.entry_point, "0x00001000")
        self.assertEqual(len(app.sha256), 64)
        self.assertGreater(app.byte_size, 0)

    def test_inspect_elf_x86_64(self):
        elf_path = os.path.join(self.fixtures_dir, "valid_elf64_x86_64")
        app = self.inspector.inspect(elf_path)

        self.assertEqual(app.format, BinaryFormat.ELF)
        self.assertEqual(app.architecture, Architecture.X86_64)
        self.assertEqual(app.subsystem, Subsystem.POSIX)
        self.assertEqual(app.entry_point, "0x00400000")

    def test_inspect_elf_aarch64(self):
        elf_path = os.path.join(self.fixtures_dir, "valid_elf64_aarch64")
        app = self.inspector.inspect(elf_path)

        self.assertEqual(app.format, BinaryFormat.ELF)
        self.assertEqual(app.architecture, Architecture.ARM64)

    def test_inspect_script(self):
        script_path = os.path.join(self.fixtures_dir, "valid_script.sh")
        app = self.inspector.inspect(script_path)

        self.assertEqual(app.format, BinaryFormat.SCRIPT)
        self.assertEqual(app.architecture, Architecture.ALL)
        self.assertEqual(app.runtime_family, "posix-shell")

    def test_inspect_corrupted_file(self):
        corrupted_path = os.path.join(self.fixtures_dir, "corrupted.bin")
        app = self.inspector.inspect(corrupted_path)

        self.assertEqual(app.format, BinaryFormat.UNKNOWN)
        self.assertGreater(len(app.limitations), 0)

    def test_inspect_nonexistent_file(self):
        with self.assertRaises(InspectionError):
            self.inspector.inspect("/path/does/not/exist/foo.bin")


if __name__ == "__main__":
    unittest.main()
