"""Unit tests for ZCF Runner Fleet & ProtonUp Manager."""

from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import tempfile
import unittest

from zcf.runtimes.fleet import AvailableRemoteRelease, DiscoveredRunner, RunnerFleetManager
from zcf.runtimes.registry import RuntimeRegistry


class TestRunnerFleet(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fleet = RunnerFleetManager(runners_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_discover_local_runners_in_fleet_dir(self):
        # Create a mock Proton runner inside runners_dir
        runner_dir = os.path.join(self.temp_dir, "GE-Proton9-25")
        os.makedirs(runner_dir, exist_ok=True)
        proton_file = os.path.join(runner_dir, "proton")
        with open(proton_file, "w") as f:
            f.write("#!/bin/sh\necho mock proton\n")
        with open(os.path.join(runner_dir, "version"), "w") as f:
            f.write("GE-Proton9-25\n")

        runners = self.fleet.discover_local_runners()
        match = next((r for r in runners if "GE-Proton9-25" in r.name), None)
        self.assertIsNotNone(match)
        self.assertEqual(match.runner_type, "ge-proton")
        self.assertIn("dxvk", match.capabilities)

    def test_verify_archive_checksum(self):
        sample_file = os.path.join(self.temp_dir, "sample.tar.gz")
        with open(sample_file, "wb") as f:
            f.write(b"mock runner archive binary contents 123456789")

        real_sha512 = hashlib.sha512(b"mock runner archive binary contents 123456789").hexdigest()

        # Exact match
        self.assertTrue(self.fleet.verify_archive_checksum(sample_file, real_sha512))
        # Formatted with filename as in sha512sum output
        self.assertTrue(self.fleet.verify_archive_checksum(sample_file, f"{real_sha512}  sample.tar.gz"))
        # Invalid hash
        self.assertFalse(self.fleet.verify_archive_checksum(sample_file, "bad_hash_value"))

    def test_install_runner_archive(self):
        # Create a valid test tar.gz archive
        archive_path = os.path.join(self.temp_dir, "Custom-Runner.tar.gz")
        payload_dir = os.path.join(self.temp_dir, "payload")
        os.makedirs(os.path.join(payload_dir, "bin"), exist_ok=True)
        with open(os.path.join(payload_dir, "bin", "wine"), "w") as f:
            f.write("#!/bin/sh\n")
        with open(os.path.join(payload_dir, "version"), "w") as f:
            f.write("Custom-1.0\n")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(payload_dir, arcname="Custom-Runner")

        runner = self.fleet.install_runner(archive_path, symlink_to_steam=False)
        self.assertIsNotNone(runner)
        self.assertEqual(runner.name, "Custom-Runner")
        self.assertTrue(os.path.isdir(runner.path))

    def test_fetch_available_releases_fallback(self):
        releases = self.fleet.fetch_available_releases(limit=5)
        self.assertIsInstance(releases, list)
        self.assertGreaterEqual(len(releases), 1)
        first = releases[0]
        self.assertIn("GE-Proton", first.name)
        self.assertTrue(first.download_url.startswith("http"))

    def test_register_fleet_with_registry(self):
        # Create a mock GE-Proton runner
        r_dir = os.path.join(self.temp_dir, "GE-Proton9-20")
        os.makedirs(r_dir, exist_ok=True)
        with open(os.path.join(r_dir, "proton"), "w") as f:
            f.write("#!/bin/sh\n")

        registry = RuntimeRegistry()
        initial_count = len(registry.list_adapters())
        added = self.fleet.register_fleet_with_registry(registry)
        self.assertGreaterEqual(added, 1)
        self.assertGreater(len(registry.list_adapters()), initial_count)
