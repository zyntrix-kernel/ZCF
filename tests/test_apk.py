"""
Unit tests for ZCF Android APK parser.
"""

import os
import unittest

from zcf.core.models import Architecture, BinaryFormat
from zcf.inspector.apk import APKParser
from zcf.inspector.inspector import ApplicationInspector


class TestAPKParser(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "synthetic"))

    def test_parse_apk(self):
        apk_path = os.path.join(self.fixtures_dir, "valid_app.apk")
        with open(apk_path, "rb") as f:
            data = f.read()

        parser = APKParser(data, "valid_app.apk")
        res = parser.parse()

        self.assertEqual(res["format"], BinaryFormat.ARCHIVE)
        self.assertEqual(res["runtime_family"], "android-art")
        self.assertEqual(res["dex_file_count"], 1)
        self.assertIn("arm64", res["supported_abis"])
        self.assertIn("x86_64", res["supported_abis"])

    def test_inspector_apk(self):
        apk_path = os.path.join(self.fixtures_dir, "valid_app.apk")
        app = ApplicationInspector().inspect(apk_path)

        self.assertEqual(app.format, BinaryFormat.ARCHIVE)
        self.assertEqual(app.runtime_family, "android-art")
        self.assertTrue(app.is_managed)


if __name__ == "__main__":
    unittest.main()
