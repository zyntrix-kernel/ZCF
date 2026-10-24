"""
Unit tests for ZCF Runtime Adapters.
"""

import unittest

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    EnvironmentReport,
    RuntimeInfo,
    Subsystem,
)
from zcf.runtimes.native import NativeAdapter
from zcf.runtimes.qemu import QemuUserAdapter
from zcf.runtimes.wine import WineAdapter


class TestRuntimeAdapters(unittest.TestCase):
    def test_native_adapter_validation(self):
        adapter = NativeAdapter()
        app = ApplicationDescription(
            artifact_path="/bin/ls",
            file_name="ls",
            sha256="a" * 64,
            byte_size=1000,
            format=BinaryFormat.ELF,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.POSIX,
        )
        env = EnvironmentReport(os_name="linux", architecture="x86_64", kernel_version="6.18")

        res = adapter.validate(app, env)
        self.assertTrue(res.valid)

        # Dry run execution test
        ctx = adapter.prepare_environment(app)
        exec_res = adapter.execute(app, ctx, dry_run=True)
        self.assertTrue(exec_res.success)
        self.assertEqual(exec_res.exit_code, 0)
        self.assertIn("[Dry Run]", exec_res.stdout)

    def test_wine_adapter_prefix_preparation(self):
        adapter = WineAdapter(base_prefix_dir="/tmp/test_zcf_prefixes")
        app = ApplicationDescription(
            artifact_path="/tmp/test.exe",
            file_name="test.exe",
            sha256="1234567890abcdef" * 4,
            byte_size=2048,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.CONSOLE,
        )

        ctx = adapter.prepare_environment(app)
        self.assertIn("WINEPREFIX", ctx["environment_variables"])
        self.assertIn("WINEDEBUG", ctx["environment_variables"])

        exec_res = adapter.execute(app, ctx, dry_run=True)
        self.assertTrue(exec_res.success)
        self.assertIn("[Dry Run]", exec_res.stdout)

    def test_qemu_adapter_validation(self):
        adapter = QemuUserAdapter()
        app = ApplicationDescription(
            artifact_path="/tmp/arm_app",
            file_name="arm_app",
            sha256="f" * 64,
            byte_size=4096,
            format=BinaryFormat.ELF,
            architecture=Architecture.ARM64,
            subsystem=Subsystem.POSIX,
        )
        env = EnvironmentReport(os_name="linux", architecture="x86_64", kernel_version="6.18")

        ctx = adapter.prepare_environment(app)
        exec_res = adapter.execute(app, ctx, dry_run=True)
        self.assertTrue(exec_res.success)
        self.assertIn("[Dry Run]", exec_res.stdout)


if __name__ == "__main__":
    unittest.main()
