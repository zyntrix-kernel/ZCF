"""
Unit tests for ZCF Web Console Server and REST API.
Verifies loopback interface, security headers, endpoints, and JSON models.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from zcf.web.server import ZCFWebConsole


class TestWebConsole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ZCF_WEB_QUIET"] = "1"
        # Pick a non-default test port to avoid conflicting with active servers
        cls.port = 8789
        cls.host = "127.0.0.1"
        cls.base_url = f"http://{cls.host}:{cls.port}"
        cls.console = ZCFWebConsole(host=cls.host, port=cls.port)
        cls.console.start(blocking=False)
        # Allow thread to bind socket
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        cls.console.stop()

    def setUp(self):
        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "synthetic"))
        self.pe_fixture = os.path.join(self.fixtures_dir, "valid_pe32plus.exe")

    def _http_get(self, path: str):
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = resp.read()
            return resp.status, resp.headers, data

    def _http_post(self, path: str, payload: dict):
        url = f"{self.base_url}{path}"
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = resp.read()
            return resp.status, resp.headers, data

    def test_get_root_serves_html_and_security_headers(self):
        """Verifies GET / returns HTML5 web dashboard and strict security headers."""
        status, headers, body = self._http_get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertIn("Content-Security-Policy", headers)
        html_str = body.decode("utf-8")
        self.assertIn("ZCF Web Console", html_str)
        self.assertIn("System Health", html_str)
        self.assertIn("Binary Inspector", html_str)

    def test_get_api_env(self):
        """Verifies GET /api/env returns host environment report JSON."""
        status, headers, body = self._http_get("/api/env")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        data = json.loads(body.decode("utf-8"))
        self.assertIn("os_name", data)
        self.assertIn("architecture", data)
        self.assertIn("available_runtimes", data)
        self.assertIsInstance(data["available_runtimes"], list)

    def test_get_api_db(self):
        """Verifies GET /api/db returns list of compatibility profiles."""
        status, headers, body = self._http_get("/api/db")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        first = data[0]
        self.assertIn("entry_id", first)
        self.assertIn("target_sha256", first)

    def test_get_api_prefixes(self):
        """Verifies GET /api/prefixes returns Wine and Proton prefix containers."""
        status, headers, body = self._http_get("/api/prefixes")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("wine", data)
        self.assertIn("proton", data)

    def test_get_api_dashboard(self):
        """Verifies GET /api/dashboard returns aggregated summary telemetry."""
        status, headers, body = self._http_get("/api/dashboard")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("os", data)
        self.assertIn("architecture", data)
        self.assertIn("total_profiles", data)
        self.assertIn("active_runtimes", data)

    def test_post_api_inspect(self):
        """Verifies POST /api/inspect returns parsed binary metadata."""
        if not os.path.exists(self.pe_fixture):
            self.skipTest("Synthetic PE fixture not generated")
        status, headers, body = self._http_post("/api/inspect", {"path": self.pe_fixture})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("format"), "pe")
        self.assertEqual(data.get("architecture"), "x86_64")
        self.assertIn("sha256", data)

    def test_post_api_plan(self):
        """Verifies POST /api/plan returns compatibility plan JSON."""
        if not os.path.exists(self.pe_fixture):
            self.skipTest("Synthetic PE fixture not generated")
        status, headers, body = self._http_post("/api/plan", {"path": self.pe_fixture})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("plan_id", data)
        self.assertIn("selected_runtime_name", data)
        self.assertIn("confidence_score", data)

    def test_post_api_diag(self):
        """Verifies POST /api/diag analyzes error log text."""
        log_sample = "err:module:import_dll Library D3DX9_43.dll not found\nerror while loading shared libraries: libvulkan.so.1: cannot open shared object file"
        status, headers, body = self._http_post("/api/diag", {"log": log_sample})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("events", data)
        events = data["events"]
        self.assertGreaterEqual(len(events), 2)
        signatures = [e["signature"] for e in events]
        self.assertIn("wine_dll_not_found", signatures)
        self.assertIn("missing_shared_library", signatures)

    def test_not_found_endpoint(self):
        """Verifies nonexistent routes return 404 JSON error."""
        url = f"{self.base_url}/api/nonexistent"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
