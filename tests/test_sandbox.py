"""
Unit tests for ZCF Sandbox Manager.
Verifies secure writable mounts, canonicalization, symlink escape prevention,
fail-closed semantics, and display socket confinement.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from zcf.core.exceptions import SecurityViolationError
from zcf.security.sandbox import SandboxManager, SandboxPolicy, validate_writable_mount


class TestSandboxManager(unittest.TestCase):
    def setUp(self):
        self.mgr = SandboxManager()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sandbox_policy_wrapping_with_bwrap(self):
        base_cmd = ["/bin/echo", "hello"]
        valid_prefix = os.path.join(self.test_dir, "wine_prefix")
        os.makedirs(valid_prefix, exist_ok=True)
        policy = SandboxPolicy(
            isolate_network=True,
            read_only_root=True,
            read_only_app=True,
            prefix_path=valid_prefix,
            allowed_prefix_roots=[self.test_dir],
            bind_mounts=[valid_prefix],
            ro_bind_mounts=["/tmp/.X11-unix"],
        )

        with patch.object(self.mgr, "has_bwrap", True), patch.object(self.mgr, "bwrap_bin", "/usr/bin/bwrap"):
            wrapped = self.mgr.wrap_command(base_cmd, "/tmp", policy)
            self.assertGreaterEqual(len(wrapped), len(base_cmd))
            self.assertEqual(wrapped[0], "/usr/bin/bwrap")
            self.assertIn("--unshare-net", wrapped)
            self.assertIn("--ro-bind", wrapped)
            # Ensure working dir is mounted read-only
            ro_idx = [i for i, v in enumerate(wrapped) if v == "--ro-bind"]
            self.assertTrue(any(wrapped[i + 1] == "/tmp" for i in ro_idx))
            # Critical: Ensure /run is NEVER mounted writable
            bind_idx = [i for i, v in enumerate(wrapped) if v == "--bind"]
            self.assertFalse(any(wrapped[i + 1] == "/run" for i in bind_idx))
            # Critical: Ensure valid prefix IS mounted writable
            real_prefix = os.path.realpath(valid_prefix)
            self.assertTrue(any(wrapped[i + 1] == real_prefix for i in bind_idx))

    def test_sandbox_fail_closed_when_bwrap_missing(self):
        base_cmd = ["/bin/echo", "hello"]
        policy = SandboxPolicy()

        with patch.object(self.mgr, "has_bwrap", False), patch.object(self.mgr, "bwrap_bin", None):
            # Default allow_unconfined=False MUST raise SecurityViolationError
            with self.assertRaises(SecurityViolationError):
                self.mgr.wrap_command(base_cmd, "/tmp", policy, allow_unconfined=False)

            # Explicit allow_unconfined=True returns original command
            unconfined = self.mgr.wrap_command(base_cmd, "/tmp", policy, allow_unconfined=True)
            self.assertEqual(unconfined, base_cmd)

    def test_sandbox_status_report(self):
        status = self.mgr.get_sandbox_status()
        self.assertIn("backend", status)
        self.assertIn("available", status)
        self.assertIn("resource_enforcement", status)

    def test_validate_writable_mount_rejects_sensitive_roots_and_traversal(self):
        """Rejects root, system directories, and traversal aliases."""
        allowed = [self.test_dir]
        for sensitive in ["/", "/etc", "/usr", "/run", "/var", "/boot", "/root", "/sys", "/proc"]:
            with self.assertRaises(SecurityViolationError) as ctx:
                validate_writable_mount(sensitive, allowed)
            # Error message must be actionable and safe (no raw path leak)
            self.assertIn("Writable sandbox mount rejected", str(ctx.exception))

        # Traversal alias (/tmp/../etc)
        traversal = os.path.join(tempfile.gettempdir(), "..", "etc")
        with self.assertRaises(SecurityViolationError):
            validate_writable_mount(traversal, allowed)

    def test_validate_writable_mount_rejects_symlink_escape(self):
        """Symlinks pointing to outside the approved root must be rejected."""
        symlink_path = os.path.join(self.test_dir, "symlink_escape")
        target_dir = os.path.join(tempfile.gettempdir(), "outside_target")
        os.makedirs(target_dir, exist_ok=True)
        try:
            try:
                os.symlink(target_dir, symlink_path)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported in current environment")

            # Approved root only includes self.test_dir, but symlink points to target_dir outside it
            with self.assertRaises(SecurityViolationError):
                validate_writable_mount(symlink_path, [self.test_dir])
        finally:
            shutil.rmtree(target_dir, ignore_errors=True)

    def test_validate_writable_mount_allows_valid_isolated_prefix(self):
        """Legitimate directory within approved prefix roots is permitted."""
        valid_prefix = os.path.join(self.test_dir, "prefixes", "app_123")
        os.makedirs(valid_prefix, exist_ok=True)
        resolved = validate_writable_mount(valid_prefix, [self.test_dir])
        self.assertEqual(resolved, os.path.realpath(valid_prefix))

    def test_validate_writable_mount_rejects_prefix_outside_allowed_roots(self):
        """Directory outside approved roots is rejected even if not in forbidden list."""
        other_dir = tempfile.mkdtemp()
        try:
            with self.assertRaises(SecurityViolationError):
                validate_writable_mount(other_dir, [self.test_dir])
        finally:
            shutil.rmtree(other_dir, ignore_errors=True)

    def test_wrap_command_binds_wayland_socket_narrowly(self):
        """Wayland display socket is narrowly bound when available without exposing entire XDG runtime dir."""
        base_cmd = ["/bin/true"]
        xdg_dir = os.path.join(self.test_dir, "run_user")
        os.makedirs(xdg_dir, exist_ok=True)
        sock_path = os.path.join(xdg_dir, "wayland-0")
        with open(sock_path, "w") as f:
            f.write("")

        valid_prefix = os.path.join(self.test_dir, "prefix")
        os.makedirs(valid_prefix, exist_ok=True)

        policy = SandboxPolicy(
            enable_wayland=True,
            prefix_path=valid_prefix,
            allowed_prefix_roots=[self.test_dir],
        )

        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": xdg_dir, "WAYLAND_DISPLAY": "wayland-0"}), \
             patch.object(self.mgr, "has_bwrap", True), \
             patch.object(self.mgr, "bwrap_bin", "/usr/bin/bwrap"):
            wrapped = self.mgr.wrap_command(base_cmd, "/tmp", policy)
            bind_idx = [i for i, v in enumerate(wrapped) if v == "--bind"]
            # Socket file itself must be bound specifically
            self.assertTrue(any(wrapped[i + 1] == sock_path for i in bind_idx))
            # The entire runtime dir must NOT be mounted writable
            self.assertFalse(any(wrapped[i + 1] == xdg_dir for i in bind_idx))

    def test_symlink_pointing_to_sensitive_location_rejected(self):
        """Symlink inside approved directory pointing to /etc or sensitive root is rejected."""
        symlink_to_sys = os.path.join(self.test_dir, "evil_sys_link")
        target_sys = "/etc" if os.name != "nt" else os.environ.get("SystemRoot", "C:\\Windows")
        try:
            try:
                os.symlink(target_sys, symlink_to_sys)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported in current environment")

            # Symlink itself is inside self.test_dir, but targets sensitive root
            with self.assertRaises(SecurityViolationError):
                validate_writable_mount(symlink_to_sys, [self.test_dir])

            # Nonexistent child under the symlink must also be safely rejected
            nonexistent_child = os.path.join(symlink_to_sys, "nonexistent_leaf.conf")
            with self.assertRaises(SecurityViolationError):
                validate_writable_mount(nonexistent_child, [self.test_dir])
        finally:
            if os.path.islink(symlink_to_sys) or os.path.exists(symlink_to_sys):
                try:
                    os.unlink(symlink_to_sys)
                except Exception:
                    pass

    def test_conflicting_read_only_and_writable_mount_rejected(self):
        """Attempting to mount a read-only directory as writable raises SecurityViolationError."""
        base_cmd = ["/bin/true"]
        ro_dir = os.path.join(self.test_dir, "ro_shared")
        os.makedirs(ro_dir, exist_ok=True)

        policy = SandboxPolicy(
            read_only_root=True,
            allowed_prefix_roots=[self.test_dir],
            ro_bind_mounts=[ro_dir],
            bind_mounts=[ro_dir],  # Conflict! Same directory declared both ro and writable
        )

        with patch.object(self.mgr, "has_bwrap", True), patch.object(self.mgr, "bwrap_bin", "/usr/bin/bwrap"):
            with self.assertRaises(SecurityViolationError) as ctx:
                self.mgr.wrap_command(base_cmd, "/tmp", policy)
            self.assertIn("Conflicting mount configuration", str(ctx.exception))

    def test_alternate_spellings_and_redundant_separators(self):
        """Alternate path spellings (/./ and redundant separators) resolve correctly within containment."""
        valid_prefix = os.path.join(self.test_dir, "prefixes", ".", "sub_prefix", "..", "sub_prefix")
        os.makedirs(valid_prefix, exist_ok=True)
        # Traversal '..' is rejected by 1b
        with self.assertRaises(SecurityViolationError):
            validate_writable_mount(valid_prefix, [self.test_dir])

        # Redundant separators and dot-slash without '..' are accepted within root
        safe_spelling = os.path.join(self.test_dir, "prefixes", ".", "sub_prefix")
        resolved = validate_writable_mount(safe_spelling, [self.test_dir])
        self.assertEqual(resolved, os.path.realpath(safe_spelling))


if __name__ == "__main__":
    unittest.main()
