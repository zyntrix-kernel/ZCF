"""
Unit tests for ZCF Compatibility Planner.
"""

import unittest

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    DisplayServer,
    EnvironmentReport,
    ExecutionMode,
    RuntimeInfo,
    Subsystem,
)
from zcf.planner.engine import CompatibilityPlanner
from zcf.runtimes.registry import RuntimeRegistry


class TestCompatibilityPlanner(unittest.TestCase):
    def setUp(self):
        self.registry = RuntimeRegistry()
        self.planner = CompatibilityPlanner(self.registry)

    def test_plan_native_linux_match(self):
        app = ApplicationDescription(
            artifact_path="/bin/ls",
            file_name="ls",
            sha256="a" * 64,
            byte_size=142000,
            format=BinaryFormat.ELF,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.POSIX,
        )
        env = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            available_runtimes=[
                RuntimeInfo(runtime_id="runtime.native", name="Native", installed=True),
            ],
        )

        plan = self.planner.plan(app, env)
        self.assertEqual(plan.selected_runtime_id, "runtime.native")
        self.assertEqual(plan.execution_mode, ExecutionMode.NATIVE)
        self.assertEqual(plan.confidence_score, 1.0)
        self.assertIn("Direct native execution", plan.reasoning)

    def test_plan_wine_installed(self):
        app = ApplicationDescription(
            artifact_path="/tmp/app.exe",
            file_name="app.exe",
            sha256="b" * 64,
            byte_size=500000,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.CONSOLE,
        )
        env = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            available_runtimes=[
                RuntimeInfo(runtime_id="runtime.native", name="Native", installed=True),
                RuntimeInfo(runtime_id="runtime.wine", name="Wine", installed=True, version="wine-9.0"),
            ],
        )

        plan = self.planner.plan(app, env)
        self.assertEqual(plan.selected_runtime_id, "runtime.wine")
        self.assertEqual(plan.execution_mode, ExecutionMode.TRANSLATION)
        self.assertEqual(plan.confidence_score, 0.90)

    def test_plan_wine_uninstalled(self):
        app = ApplicationDescription(
            artifact_path="/tmp/app.exe",
            file_name="app.exe",
            sha256="c" * 64,
            byte_size=500000,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.CONSOLE,
        )
        env = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            available_runtimes=[
                RuntimeInfo(runtime_id="runtime.native", name="Native", installed=True),
                RuntimeInfo(runtime_id="runtime.wine", name="Wine", installed=False),
            ],
        )

        plan = self.planner.plan(app, env)
        self.assertEqual(plan.execution_mode, ExecutionMode.BLOCKED)
        self.assertEqual(plan.confidence_score, 0.0)
        self.assertGreater(len(plan.missing_requirements), 0)

    def test_plan_qemu_user_emulation(self):
        app = ApplicationDescription(
            artifact_path="/tmp/arm_binary",
            file_name="arm_binary",
            sha256="d" * 64,
            byte_size=200000,
            format=BinaryFormat.ELF,
            architecture=Architecture.ARM64,
            subsystem=Subsystem.POSIX,
        )
        env = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            available_runtimes=[
                RuntimeInfo(runtime_id="runtime.native", name="Native", installed=True),
                RuntimeInfo(runtime_id="runtime.qemu-user", name="QEMU User", installed=True, version="10.2"),
            ],
        )

        plan = self.planner.plan(app, env)
        self.assertEqual(plan.selected_runtime_id, "runtime.qemu-user")
        self.assertEqual(plan.execution_mode, ExecutionMode.EMULATION)
        self.assertEqual(plan.confidence_score, 0.85)


if __name__ == "__main__":
    unittest.main()
