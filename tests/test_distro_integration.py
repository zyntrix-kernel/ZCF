"""
Tests for ZCF Linux Distribution Integration Assets (binfmt, desktop, AppStream, man page, completions).
"""

import os
import unittest
import xml.etree.ElementTree as ET


class TestDistroIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def test_binfmt_configuration_exists(self):
        conf_path = os.path.join(self.root_dir, "data", "binfmt.d", "zcf.conf")
        self.assertTrue(os.path.isfile(conf_path), f"Missing {conf_path}")
        with open(conf_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(":zcf-pe:M::MZ::/usr/bin/zcf-runner:PC", content)
        self.assertIn(":zcf-elf-aarch64:", content)

    def test_desktop_entry_validity(self):
        desktop_path = os.path.join(self.root_dir, "data", "desktop", "org.zyntrix.zcf.desktop")
        self.assertTrue(os.path.isfile(desktop_path), f"Missing {desktop_path}")
        with open(desktop_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        has_exec = any(line.strip().startswith("Exec=zcf run") for line in lines)
        has_mime = any(line.strip().startswith("MimeType=") for line in lines)
        self.assertTrue(has_exec)
        self.assertTrue(has_mime)

    def test_appstream_metainfo_xml(self):
        metainfo_path = os.path.join(self.root_dir, "data", "metainfo", "org.zyntrix.zcf.metainfo.xml")
        self.assertTrue(os.path.isfile(metainfo_path), f"Missing {metainfo_path}")
        tree = ET.parse(metainfo_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "component")
        self.assertEqual(root.attrib.get("type"), "desktop-application")
        id_elem = root.find("id")
        self.assertIsNotNone(id_elem)
        self.assertEqual(id_elem.text, "org.zyntrix.zcf")

    def test_shell_completions_exist(self):
        bash_comp = os.path.join(self.root_dir, "data", "completions", "bash", "zcf")
        zsh_comp = os.path.join(self.root_dir, "data", "completions", "zsh", "_zcf")
        fish_comp = os.path.join(self.root_dir, "data", "completions", "fish", "zcf.fish")

        self.assertTrue(os.path.isfile(bash_comp))
        self.assertTrue(os.path.isfile(zsh_comp))
        self.assertTrue(os.path.isfile(fish_comp))

        with open(bash_comp, "r", encoding="utf-8") as f:
            self.assertIn("zcf-runner", f.read())

    def test_man_page_exists(self):
        man_path = os.path.join(self.root_dir, "docs", "man", "zcf.1")
        self.assertTrue(os.path.isfile(man_path))
        with open(man_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        self.assertTrue(first_line.startswith(".TH ZCF 1"))


if __name__ == "__main__":
    unittest.main()
