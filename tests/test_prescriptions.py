"""Unit tests for ZCF Autonomous Healing Prescription Engine."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from zcf.diagnostics.analyzer import DiagnosticEvent
from zcf.diagnostics.prescriptions import HealingPrescription, PrescriptionEngine


class TestPrescriptions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.prefix_dir = os.path.join(self.temp_dir, "prefix")
        os.makedirs(self.prefix_dir, exist_ok=True)
        self.rx_engine = PrescriptionEngine()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_synthesize_directx_prescription(self):
        events = [
            DiagnosticEvent(
                signature="wine_directx_missing",
                severity="error",
                matched_text="d3dcompiler_47.dll not found",
                root_cause="DirectX runtime component missing in Wine prefix.",
                remediation="Install DirectX components",
                confidence=0.96,
            )
        ]
        rx = self.rx_engine.synthesize(events, app_name="EldenRing.exe", prefix_path=self.prefix_dir)
        self.assertTrue(rx.id.startswith("rx_"))
        self.assertEqual(rx.target_app, "EldenRing.exe")
        self.assertIn("d3dcompiler_47", rx.components_to_install)
        self.assertIn("d3d11", rx.dll_overrides_to_set)
        self.assertEqual(rx.recommended_runner, "runtime.proton")

    def test_synthesize_vcrun_and_dotnet_prescription(self):
        events = [
            DiagnosticEvent(
                signature="wine_dll_not_found",
                severity="error",
                matched_text="Library MSVCR100.dll not found",
                root_cause="Visual C++ runtime missing",
                remediation="Install vcrun2010",
                confidence=0.95,
            ),
            DiagnosticEvent(
                signature="wine_dll_not_found",
                severity="error",
                matched_text="Library mscoree.dll not found",
                root_cause=".NET Framework runtime missing",
                remediation="Install dotnet48",
                confidence=0.95,
            ),
        ]
        rx = self.rx_engine.synthesize(events, app_name="Tool.exe")
        self.assertIn("vcrun2010", rx.components_to_install)
        self.assertIn("dotnet48", rx.components_to_install)

    def test_apply_prescription_creates_snapshot_and_applies_overrides(self):
        # Create baseline prefix
        with open(os.path.join(self.prefix_dir, "system.reg"), "w") as f:
            f.write("[Software\\\\Wine]\n")

        rx = HealingPrescription(
            id="rx_test_1",
            target_app="Game.exe",
            target_prefix=self.prefix_dir,
            created_at="2024-10-26T00:00:00Z",
            root_causes=["Missing DirectX and VC runtimes"],
            recommended_runner="runtime.proton",
            components_to_install=["corefonts"],  # corefonts is fast and doesn't require download
            dll_overrides_to_set={"d3d11": "native,builtin"},
            env_vars_to_set={"WINE_LARGE_ADDRESS_AWARE": "1"},
        )

        result = self.rx_engine.apply(rx, self.prefix_dir)
        self.assertEqual(result.get("status"), "applied")
        self.assertIsNotNone(result.get("snapshot_id"))

        # Verify DLL override written to prefix_meta.json
        meta_file = os.path.join(self.prefix_dir, "prefix_meta.json")
        self.assertTrue(os.path.isfile(meta_file))
        with open(meta_file, "r") as f:
            data = json.load(f)
            self.assertEqual(data.get("dll_overrides", {}).get("d3d11"), "native,builtin")
