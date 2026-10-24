"""
Unit tests for ZCF Mach-O parser.
"""

import os
import unittest

from zcf.core.models import Architecture, BinaryFormat
from zcf.inspector.inspector import ApplicationInspector
from zcf.inspector.macho import MachOParser


class TestMachOParser(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "synthetic"))

    def test_parse_macho64(self):
        macho_path = os.path.join(self.fixtures_dir, "valid_macho64")
        with open(macho_path, "rb") as f:
            data = f.read()

        parser = MachOParser(data)
        res = parser.parse()

        self.assertEqual(res["format"], BinaryFormat.MACHO)
        self.assertEqual(res["architecture"], Architecture.X86_64)
        self.assertTrue(res["is_64bit"])

    def test_inspector_macho(self):
        macho_path = os.path.join(self.fixtures_dir, "valid_macho64")
        app = ApplicationInspector().inspect(macho_path)

        self.assertEqual(app.format, BinaryFormat.MACHO)
        self.assertEqual(app.architecture, Architecture.X86_64)


if __name__ == "__main__":
    unittest.main()
