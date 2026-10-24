"""
Tests for ZCF Execution Runner, Virtual Display Manager, and Package Installer Bridge.
"""

import unittest
from unittest.mock import MagicMock, patch

from zcf.desktop.notifier import DesktopNotifier
from zcf.execution.display import VirtualDisplayManager
from zcf.execution.installer import PackageInstallerBridge
from zcf.execution.runner import ExecutionOrchestrator


class TestExecutionSubsystem(unittest.TestCase):

    def test_package_installer_bridge_commands(self):
        bridge_deb = PackageInstallerBridge(distro="ubuntu")
        cmd_wine = bridge_deb.get_install_command("wine")
        self.assertIsNotNone(cmd_wine)
        self.assertTrue(any("wine" in arg for arg in cmd_wine))

        bridge_arch = PackageInstallerBridge(distro="arch")
        cmd_qemu = bridge_arch.get_install_command("qemu-user")
        self.assertIsNotNone(cmd_qemu)

        bridge_fedora = PackageInstallerBridge(distro="fedora")
        cmd_xvfb = bridge_fedora.get_install_command("xvfb")
        self.assertIsNotNone(cmd_xvfb)

    def test_virtual_display_manager_support(self):
        vdm = VirtualDisplayManager()
        self.assertIsInstance(vdm.is_supported(), bool)
        wrapped = vdm.wrap_command(["echo", "hello"])
        self.assertTrue(len(wrapped) >= 2)

    def test_desktop_notifier_fallback(self):
        notifier = DesktopNotifier()
        # Should not crash even in headless or Windows environment
        res = notifier.notify("Test Title", "Test message")
        self.assertIsInstance(res, bool)
        notifier.notify_starting("app.exe", "Wine")
        notifier.notify_failure("app.exe", "Missing DLL")

    @patch("zcf.execution.runner.ApplicationInspector")
    @patch("zcf.execution.runner.EnvironmentInspector")
    def test_execution_orchestrator_initialization(self, mock_env, mock_insp):
        runner = ExecutionOrchestrator()
        self.assertIsNotNone(runner.inspector)
        self.assertIsNotNone(runner.planner)
        self.assertIsNotNone(runner.sandbox_manager)
        self.assertIsNotNone(runner.installer_bridge)


if __name__ == "__main__":
    unittest.main()
