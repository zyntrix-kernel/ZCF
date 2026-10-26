"""
Unit tests for ZCF Web Console Server and REST API.
Verifies loopback interface, security headers, endpoints, and JSON models.
Includes comprehensive tests for DNS rebinding, CSRF protection, payload limits,
path validation, profile querying, test execution, and remote binding restrictions.
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
        cls.port = 8789
        cls.host = "127.0.0.1"
        cls.base_url = f"http://{cls.host}:{cls.port}"
        cls.console = ZCFWebConsole(host=cls.host, port=cls.port)
        cls.console.start(blocking=False)
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        cls.console.stop()

    def setUp(self):
        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "synthetic"))
        self.pe_fixture = os.path.join(self.fixtures_dir, "valid_pe32plus.exe")

    def _http_get(self, path: str, headers: dict = None):
        url = f"{self.base_url}{path}"
        req_headers = {"Host": f"{self.host}:{self.port}"}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = resp.read()
            return resp.status, resp.headers, data

    def _http_post(self, path: str, payload: dict, headers: dict = None):
        url = f"{self.base_url}{path}"
        data_bytes = json.dumps(payload).encode("utf-8")
        req_headers = {
            "Content-Type": "application/json",
            "Host": f"{self.host}:{self.port}",
        }
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers=req_headers,
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

    def test_get_api_db_profile_detail(self):
        """Verifies GET /api/db/profile?id=<id> returns complete evidence bundle."""
        status, _, body = self._http_get("/api/db")
        data = json.loads(body.decode("utf-8"))
        entry_id = data[0]["entry_id"]

        status, _, body = self._http_get(f"/api/db/profile?id={entry_id}")
        self.assertEqual(status, 200)
        detail = json.loads(body.decode("utf-8"))
        self.assertEqual(detail["entry_id"], entry_id)
        self.assertIn("provenance_tier", detail)
        self.assertIn("target_sha256", detail)

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

    def test_post_api_test_execution_dry_run(self):
        """Verifies POST /api/test executes dry-run validation."""
        if not os.path.exists(self.pe_fixture):
            self.skipTest("Synthetic PE fixture not generated")
        status, _, body = self._http_post("/api/test", {"path": self.pe_fixture, "dry_run": True})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("dry_run"))
        self.assertIn("exit_code", data)
        self.assertIn("runtime", data)

    def test_post_api_prefixes_cleanup(self):
        """Verifies POST /api/prefixes/cleanup safely cleans stale prefixes."""
        status, _, body = self._http_post("/api/prefixes/cleanup", {"max_age_days": 14})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("success"))
        self.assertIn("total", data)

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

    # -------------------------------------------------------------
    # SECURITY & REJECTION TESTS
    # -------------------------------------------------------------

    def test_security_rejects_invalid_host_header(self):
        """Verifies that requests with an unauthorized Host header (DNS rebinding) are rejected with 403."""
        url = f"{self.base_url}/api/env"
        req = urllib.request.Request(url, headers={"Host": "attacker.evil.com"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 403)

    def test_security_rejects_cross_site_fetch(self):
        """Verifies that cross-site POST requests (Sec-Fetch-Site: cross-site) are rejected with 403."""
        url = f"{self.base_url}/api/diag"
        data_bytes = json.dumps({"log": "sample"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Host": f"{self.host}:{self.port}",
                "Sec-Fetch-Site": "cross-site",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 403)

    def test_security_rejects_external_origin(self):
        """Verifies that POST requests from external browser origins are rejected with 403."""
        url = f"{self.base_url}/api/diag"
        data_bytes = json.dumps({"log": "sample"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Host": f"{self.host}:{self.port}",
                "Origin": "http://evil-website.com",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 403)

    def test_security_rejects_directory_for_binary_inspection(self):
        """Verifies that passing a directory instead of a regular file returns 404."""
        temp_dir = tempfile.mkdtemp()
        try:
            url = f"{self.base_url}/api/inspect"
            data_bytes = json.dumps({"path": temp_dir}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={
                    "Content-Type": "application/json",
                    "Host": f"{self.host}:{self.port}",
                },
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=3)
            self.assertEqual(ctx.exception.code, 404)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_security_rejects_oversized_payload(self):
        """Verifies that requests exceeding the 2MB payload cap are rejected with 413."""
        url = f"{self.base_url}/api/diag"
        oversized = "x" * (2 * 1024 * 1024 + 100)
        data_bytes = json.dumps({"log": oversized}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Host": f"{self.host}:{self.port}",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 413)

    def test_security_rejects_non_loopback_without_allow_remote(self):
        """Verifies that attempting to bind to non-loopback interface raises ValueError unless allow_remote=True."""
        with self.assertRaises(ValueError):
            ZCFWebConsole(host="192.168.1.100", port=9999, allow_remote=False)

        # But succeeds when explicitly authorized
        allowed_console = ZCFWebConsole(host="192.168.1.100", port=9999, allow_remote=True)
        self.assertEqual(allowed_console.host, "192.168.1.100")

    def test_not_found_endpoint(self):
        """Verifies nonexistent routes return 404 JSON error."""
        url = f"{self.base_url}/api/nonexistent"
        req = urllib.request.Request(url, headers={"Host": f"{self.host}:{self.port}"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 404)

    def test_api_history_workflow(self):
        """Verifies history listing, detail, compare, delete, and clear REST endpoints."""
        # Execute test to generate a run
        status, _, test_bytes = self._http_post("/api/test", {"path": self.pe_fixture, "dry_run": True})
        self.assertEqual(status, 200)

        # GET /api/history
        status, _, hist_bytes = self._http_get("/api/history")
        self.assertEqual(status, 200)
        runs = json.loads(hist_bytes.decode("utf-8"))
        self.assertIsInstance(runs, list)
        self.assertGreaterEqual(len(runs), 1)

        run_id = runs[0]["run_id"]
        # GET /api/history/detail
        status, _, detail_bytes = self._http_get(f"/api/history/detail?id={run_id}")
        self.assertEqual(status, 200)
        detail = json.loads(detail_bytes.decode("utf-8"))
        self.assertEqual(detail["run_id"], run_id)
        self.assertTrue(detail["dry_run"])

        # Execute second test to compare
        self._http_post("/api/test", {"path": self.pe_fixture, "dry_run": True})
        status, _, hist2_bytes = self._http_get("/api/history")
        runs2 = json.loads(hist2_bytes.decode("utf-8"))
        self.assertGreaterEqual(len(runs2), 2)

        # POST /api/history/compare
        status, _, comp_bytes = self._http_post("/api/history/compare", {"run_a": runs2[0]["run_id"], "run_b": runs2[1]["run_id"]})
        self.assertEqual(status, 200)
        comp = json.loads(comp_bytes.decode("utf-8"))
        self.assertIn("differences", comp)

        # POST /api/history/delete
        status, _, del_bytes = self._http_post("/api/history/delete", {"id": run_id})
        self.assertEqual(status, 200)
        del_res = json.loads(del_bytes.decode("utf-8"))
        self.assertTrue(del_res["success"])

        # POST /api/history/clear
        status, _, clear_bytes = self._http_post("/api/history/clear", {})
        self.assertEqual(status, 200)
        clear_res = json.loads(clear_bytes.decode("utf-8"))
        self.assertTrue(clear_res["success"])

    def test_api_plan_returns_evidence_type(self):
        """Verifies POST /api/plan returns explicit evidence_type categorization."""
        status, _, body = self._http_post("/api/plan", {"path": self.pe_fixture})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("evidence_type", data)
        self.assertIn(data["evidence_type"], ("exact_measured", "heuristic_prediction", "static_analysis"))

    def test_get_api_readiness(self):
        """Verifies GET /api/readiness returns system readiness index, grade, and 7 checks."""
        status, _, body = self._http_get("/api/readiness")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("score", data)
        self.assertIn("grade", data)
        self.assertIn("checks", data)
        self.assertEqual(len(data["checks"]), 7)

    def test_get_api_components(self):
        """Verifies GET /api/components returns all registered Windows components."""
        status, _, body = self._http_get("/api/components")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 6)
        keys = [c["key"] for c in data]
        self.assertIn("vcrun2022", keys)
        self.assertIn("corefonts", keys)
        self.assertIn("dotnet48", keys)

    def test_api_prefixes_overrides_crud(self):
        """Verifies configuring, reading, and removing prefix DLL overrides via REST API."""
        with tempfile.TemporaryDirectory() as temp_prefix:
            # Set override
            status, _, body = self._http_post(
                "/api/prefixes/overrides",
                {"prefix_path": temp_prefix, "dll_name": "d3d11", "mode": "native,builtin"},
            )
            self.assertEqual(status, 200)
            data = json.loads(body.decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("overrides", {}).get("d3d11"), "native,builtin")

            # Get overrides
            status, _, get_body = self._http_get(f"/api/prefixes/overrides?prefix_path={urllib.request.quote(temp_prefix)}")
            self.assertEqual(status, 200)
            get_data = json.loads(get_body.decode("utf-8"))
            self.assertEqual(get_data.get("overrides", {}).get("d3d11"), "native,builtin")

            # Remove override
            status, _, rem_body = self._http_post(
                "/api/prefixes/overrides",
                {"prefix_path": temp_prefix, "dll_name": "d3d11", "action": "remove"},
            )
            self.assertEqual(status, 200)
            rem_data = json.loads(rem_body.decode("utf-8"))
            self.assertTrue(rem_data.get("success"))
            self.assertNotIn("d3d11", rem_data.get("overrides", {}))

    def test_get_root_contains_interactive_visualizations(self):
        """Verifies Web Console single-page app HTML contains pipeline topology and readiness matrix."""
        status, _, body = self._http_get("/")
        self.assertEqual(status, 200)
        html_str = body.decode("utf-8")
        self.assertIn("Pre-Flight System Readiness", html_str)
        self.assertIn("readiness-gauge-circle", html_str)
        self.assertIn("pipeline-topology-card", html_str)
        self.assertIn("prefix-surgery-card", html_str)
        self.assertIn("log-filter-bar", html_str)
        self.assertIn("tab-tuning", html_str)
        self.assertIn("tab-runners", html_str)
        self.assertIn("tab-vault", html_str)
        self.assertIn("healing-rx-card", html_str)

    def test_api_tuning_tools_and_presets(self):
        """Verifies GET /api/tuning/tools returns accelerator binary status and esports presets."""
        status, _, body = self._http_get("/api/tuning/tools")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("tools", data)
        self.assertIn("presets", data)
        self.assertIn("gamescope", data["tools"])
        self.assertIn("esports", data["presets"])
        self.assertEqual(data["presets"]["esports"]["fps_limit"], 144)

    def test_api_tuning_preview(self):
        """Verifies POST /api/tuning/preview generates full wrapped command pipeline."""
        payload = {
            "tuning": {"enabled": True, "use_gamemode": True, "use_gamescope": True, "upscaling_filter": "fsr"},
            "command": ["wine", "test.exe"],
        }
        status, _, body = self._http_post("/api/tuning/preview", payload)
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("command", data)
        cmd = data["command"]
        self.assertEqual(cmd[0], "gamemoderun")
        self.assertEqual(cmd[1], "gamescope")

    def test_api_runners_and_available(self):
        """Verifies GET /api/runners and GET /api/runners/available."""
        status, _, body = self._http_get("/api/runners")
        self.assertEqual(status, 200)
        runners = json.loads(body.decode("utf-8"))
        self.assertIsInstance(runners, list)

        status, _, body = self._http_get("/api/runners/available?limit=3")
        self.assertEqual(status, 200)
        available = json.loads(body.decode("utf-8"))
        self.assertIsInstance(available, list)
        self.assertGreaterEqual(len(available), 1)

    def test_api_snapshots_lifecycle(self):
        """Verifies Time-Machine snapshots creation and listing via REST API."""
        with tempfile.TemporaryDirectory() as temp_prefix:
            with open(os.path.join(temp_prefix, "system.reg"), "w") as f:
                f.write("[Software\\\\Wine]\n")

            # Create snapshot
            status, _, body = self._http_post(
                "/api/snapshots/create",
                {"prefix_path": temp_prefix, "label": "Web Test Snap"},
            )
            self.assertEqual(status, 200)
            data = json.loads(body.decode("utf-8"))
            self.assertTrue(data.get("success"))
            snap_id = data["snapshot"]["id"]

            # List snapshots
            status, _, list_body = self._http_get(f"/api/snapshots?prefix_path={urllib.request.quote(temp_prefix)}")
            self.assertEqual(status, 200)
            snaps = json.loads(list_body.decode("utf-8"))
            self.assertEqual(len(snaps), 1)
            self.assertEqual(snaps[0]["id"], snap_id)

    def test_api_prescriptions_generate(self):
        """Verifies POST /api/prescriptions/generate synthesizes actionable prescription."""
        log = "err:module:import_dll Library d3dx9_43.dll not found\nerror loading d3dcompiler_47.dll"
        status, _, body = self._http_post("/api/prescriptions/generate", {"log": log, "app_name": "game.exe"})
        self.assertEqual(status, 200)
        rx = json.loads(body.decode("utf-8"))
        self.assertIn("d3dcompiler_47", rx.get("components_to_install", []))
        self.assertEqual(rx.get("recommended_runner"), "runtime.proton")


if __name__ == "__main__":
    unittest.main()
