"""
Unit tests for ZCF Compatibility Planner.
"""

import os
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
    WorkloadType,
)
from zcf.planner.engine import CompatibilityPlanner
from zcf.runtimes.android import AndroidContainerAdapter
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

    def test_plan_proton_vulkan_mandatory_prerequisite(self):
        """Proton requires Vulkan when DXVK is active. Missing Vulkan must block Proton selection."""
        app = ApplicationDescription(
            artifact_path="/tmp/game.exe",
            file_name="game.exe",
            sha256="e" * 64,
            byte_size=500000,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.GUI,
            workload_type=WorkloadType.GAME,
        )
        # Environment with Proton installed, but Vulkan absent
        env = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            graphics_capabilities={"vulkan_available": False},
            available_runtimes=[
                RuntimeInfo(runtime_id="runtime.native", name="Native", installed=True),
                RuntimeInfo(runtime_id="runtime.proton", name="Proton", installed=True, version="Proton-9.0"),
            ],
        )

        plan = self.planner.plan(app, env)
        # Proton must NOT be selected without Vulkan for DXVK
        self.assertNotEqual(plan.selected_runtime_id, "runtime.proton")

        # Candidate evaluation for Proton must be marked ineligible and blocked
        proton_eval = next((c for c in plan.candidate_evaluations if c.runtime_id == "runtime.proton"), None)
        self.assertIsNotNone(proton_eval)
        self.assertFalse(proton_eval.eligible)
        self.assertTrue(proton_eval.blocked)
        self.assertIn("Vulkan", proton_eval.notes)

    def test_plan_waydroid_mandatory_prerequisites(self):
        """Waydroid requires Wayland compositor and /dev/binder. Missing either blocks execution."""
        app = ApplicationDescription(
            artifact_path="/tmp/app.apk",
            file_name="app.apk",
            sha256="f" * 64,
            byte_size=1000000,
            format=BinaryFormat.ARCHIVE,
            runtime_family="android-art",
            architecture=Architecture.ARM64,
            subsystem=Subsystem.GUI,
        )
        # Environment with Waydroid installed, but running on X11 display server without /dev/binder
        env = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            display_server=DisplayServer.X11,
            available_runtimes=[
                RuntimeInfo(runtime_id="runtime.native", name="Native", installed=True),
                RuntimeInfo(runtime_id="runtime.android", name="Waydroid", installed=True, version="1.4.2"),
            ],
        )

        plan = self.planner.plan(app, env)
        self.assertEqual(plan.execution_mode, ExecutionMode.BLOCKED)

    def test_android_adapter_distinct_actions(self):
        """Android adapter must distinguish between installation, application launch, and combined."""
        adapter = AndroidContainerAdapter()
        app = ApplicationDescription(
            artifact_path="/tmp/sample.apk",
            file_name="sample.apk",
            sha256="0" * 64,
            byte_size=50000,
            format=BinaryFormat.ARCHIVE,
            runtime_family="android-art",
            architecture=Architecture.ALL,
            subsystem=Subsystem.GUI,
        )

        # 1. Action = install
        ctx_install = adapter.prepare_environment(app, {"action": "install"})
        cmd_install = adapter.build_command(app, ctx_install)
        self.assertEqual(cmd_install, ["waydroid", "app", "install", os.path.abspath(app.artifact_path)])

        # 2. Action = launch (requires package_name)
        ctx_launch = adapter.prepare_environment(app, {"action": "launch", "package_name": "org.example.app"})
        cmd_launch = adapter.build_command(app, ctx_launch)
        self.assertEqual(cmd_launch, ["waydroid", "app", "launch", "org.example.app"])


if __name__ == "__main__":
    unittest.main()
