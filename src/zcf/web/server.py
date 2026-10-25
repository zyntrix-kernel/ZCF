"""
ZCF Web Console Server.
Zero-dependency, local browser-based control center and REST API for ZCF.
Provides live system telemetry, compatibility database browsing, prefix storage management,
binary inspection, and diagnostic troubleshooting over a secure loopback interface.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional

from zcf import __version__
from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.diagnostics.analyzer import DiagnosticEngine
from zcf.diagnostics.remediator import AutomatedRemediator
from zcf.environment.inspector import EnvironmentInspector
from zcf.inspector.inspector import ApplicationInspector
from zcf.planner.engine import CompatibilityPlanner
from zcf.runtimes.prefix_manager import WinePrefixManager


def get_web_dashboard_html() -> str:
    """Returns the standalone HTML5/CSS3 single-page application for the ZCF Web Console."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ZCF Web Console (v{__version__})</title>
  <style>
    :root {{
      --bg: #121214;
      --card-bg: #1a1a1e;
      --card-border: #2a2a30;
      --primary: #00e5ff;
      --primary-hover: #00b8cc;
      --accent-green: #00e676;
      --accent-red: #ff5252;
      --accent-amber: #ffd740;
      --fg: #f0f0f4;
      --fg-subtle: #9e9ea8;
      --code-bg: #0d0d0f;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      background-color: var(--bg);
      color: var(--fg);
      line-height: 1.5;
      padding: 0;
    }}
    header {{
      background-color: var(--card-bg);
      border-bottom: 1px solid var(--card-border);
      padding: 16px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .logo {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 20px;
      font-weight: 700;
      color: var(--fg);
      letter-spacing: -0.5px;
    }}
    .logo-badge {{
      background: linear-gradient(135deg, #00e5ff, #0077ff);
      color: #000;
      font-size: 13px;
      font-weight: 800;
      padding: 3px 8px;
      border-radius: 4px;
    }}
    .header-meta {{
      font-size: 13px;
      color: var(--fg-subtle);
    }}
    nav {{
      background-color: var(--card-bg);
      border-bottom: 1px solid var(--card-border);
      display: flex;
      padding: 0 28px;
      gap: 6px;
    }}
    .nav-btn {{
      background: none;
      border: none;
      color: var(--fg-subtle);
      font-size: 14px;
      font-weight: 600;
      padding: 14px 18px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s ease;
    }}
    .nav-btn:hover {{
      color: var(--fg);
    }}
    .nav-btn.active {{
      color: var(--primary);
      border-bottom-color: var(--primary);
    }}
    main {{
      max-width: 1240px;
      margin: 24px auto;
      padding: 0 24px;
    }}
    .tab-content {{
      display: none;
    }}
    .tab-content.active {{
      display: block;
    }}
    .card {{
      background-color: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    .card-title {{
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    .grid-4 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .stat-box {{
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 16px;
    }}
    .stat-label {{
      font-size: 12px;
      color: var(--fg-subtle);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .stat-value {{
      font-size: 22px;
      font-weight: 700;
      color: var(--primary);
      margin-top: 4px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }}
    th {{
      color: var(--fg-subtle);
      font-weight: 600;
      padding: 10px 12px;
      border-bottom: 1px solid var(--card-border);
    }}
    td {{
      padding: 12px;
      border-bottom: 1px solid var(--card-border);
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .badge-green {{ background: rgba(0, 230, 118, 0.15); color: var(--accent-green); border: 1px solid rgba(0, 230, 118, 0.3); }}
    .badge-red {{ background: rgba(255, 82, 82, 0.15); color: var(--accent-red); border: 1px solid rgba(255, 82, 82, 0.3); }}
    .badge-amber {{ background: rgba(255, 215, 64, 0.15); color: var(--accent-amber); border: 1px solid rgba(255, 215, 64, 0.3); }}
    .badge-cyan {{ background: rgba(0, 229, 255, 0.15); color: var(--primary); border: 1px solid rgba(0, 229, 255, 0.3); }}
    input, textarea, select {{
      width: 100%;
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      color: var(--fg);
      padding: 10px 14px;
      font-size: 14px;
      margin-top: 6px;
      outline: none;
      font-family: inherit;
    }}
    input:focus, textarea:focus {{
      border-color: var(--primary);
    }}
    textarea {{
      resize: vertical;
      font-family: Consolas, Monaco, "Courier New", monospace;
      font-size: 13px;
    }}
    .btn {{
      background: var(--primary);
      color: #000;
      border: none;
      border-radius: 6px;
      padding: 10px 18px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 12px;
      transition: background 0.15s ease;
    }}
    .btn:hover {{
      background: var(--primary-hover);
    }}
    .btn-secondary {{
      background: #2a2a32;
      color: var(--fg);
    }}
    .btn-secondary:hover {{
      background: #3a3a44;
    }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 14px;
      font-family: Consolas, Monaco, monospace;
      font-size: 13px;
      overflow-x: auto;
      color: var(--fg);
    }}
  </style>
</head>
<body>
  <header>
    <div class="logo">
      <span>⚡ ZCF Web Console</span>
      <span class="logo-badge">v{__version__}</span>
    </div>
    <div class="header-meta" id="header-platform">Loading host telemetry...</div>
  </header>

  <nav>
    <button class="nav-btn active" onclick="switchTab('dashboard')">📊 System Health</button>
    <button class="nav-btn" onclick="switchTab('inspector')">🔍 Binary Inspector & Plan</button>
    <button class="nav-btn" onclick="switchTab('database')">📚 Compatibility Knowledge Base</button>
    <button class="nav-btn" onclick="switchTab('prefixes')">💾 Isolated Storage</button>
    <button class="nav-btn" onclick="switchTab('diagnostics')">🛠️ Crash Troubleshooter</button>
  </nav>

  <main>
    <!-- TAB 1: SYSTEM HEALTH -->
    <section id="tab-dashboard" class="tab-content active">
      <div class="grid-4" id="stats-grid">
        <div class="stat-box">
          <div class="stat-label">Operating System</div>
          <div class="stat-value" id="stat-os">-</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Architecture</div>
          <div class="stat-value" id="stat-arch">-</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Discovered Runtimes</div>
          <div class="stat-value" id="stat-runtimes">-</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Compatibility Profiles</div>
          <div class="stat-value" id="stat-profiles">-</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Discovered Compatibility Engines & Isolation Health</div>
        <table>
          <thead>
            <tr>
              <th>Runtime Identifier</th>
              <th>Display Name</th>
              <th>Status</th>
              <th>Discovered Version</th>
              <th>Supported Architecture</th>
            </tr>
          </thead>
          <tbody id="runtimes-table-body">
            <tr><td colspan="5">Scanning compatibility runtimes...</td></tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <div class="card-title">Host Subsystem Capabilities</div>
        <div class="grid-2">
          <div>
            <p><strong>Display Server:</strong> <span id="env-display">-</span></p>
            <p style="margin-top: 6px;"><strong>CPU Cores:</strong> <span id="env-cores">-</span></p>
            <p style="margin-top: 6px;"><strong>Total Memory:</strong> <span id="env-mem">-</span></p>
          </div>
          <div>
            <p><strong>Bubblewrap Sandboxing:</strong> <span id="env-sandbox">-</span></p>
            <p style="margin-top: 6px;"><strong>Vulkan 3D Graphics:</strong> <span id="env-vulkan">-</span></p>
            <p style="margin-top: 6px;"><strong>Kernel Release:</strong> <span id="env-kernel">-</span></p>
          </div>
        </div>
      </div>
    </section>

    <!-- TAB 2: INSPECTOR & PLANNER -->
    <section id="tab-inspector" class="tab-content">
      <div class="card">
        <div class="card-title">Inspect Application & Generate Compatibility Plan</div>
        <label for="inspect-path">Target Executable Path (PE, ELF, APK, or Script):</label>
        <input type="text" id="inspect-path" placeholder="/path/to/application.exe or valid_pe32plus.exe">
        <div style="display: flex; gap: 10px; margin-top: 10px;">
          <button class="btn" onclick="inspectBinary()">Inspect Headers</button>
          <button class="btn btn-secondary" onclick="generatePlan()">Generate Execution Plan</button>
        </div>
      </div>

      <div class="card" id="inspect-result-card" style="display: none;">
        <div class="card-title" id="inspect-title">Inspection Results</div>
        <pre id="inspect-json"></pre>
      </div>
    </section>

    <!-- TAB 3: DATABASE -->
    <section id="tab-database" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Cataloged Compatibility Profiles</span>
          <input type="text" id="db-filter" placeholder="Filter by application or runtime..." style="max-width: 280px; margin-top: 0;" oninput="filterDatabase()">
        </div>
        <table>
          <thead>
            <tr>
              <th>Profile ID</th>
              <th>Application</th>
              <th>Target Format</th>
              <th>Architecture</th>
              <th>Compatibility Status</th>
              <th>Recommended Runtime</th>
              <th>Provenance Tier</th>
            </tr>
          </thead>
          <tbody id="db-table-body">
            <tr><td colspan="7">Loading compatibility database...</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- TAB 4: PREFIXES -->
    <section id="tab-prefixes" class="tab-content">
      <div class="card">
        <div class="card-title">Managed Storage Containers & Prefixes</div>
        <table>
          <thead>
            <tr>
              <th>Runtime</th>
              <th>Application / ID</th>
              <th>Architecture</th>
              <th>Disk Size</th>
              <th>Persistence</th>
              <th>Active Lock</th>
              <th>Filesystem Path</th>
            </tr>
          </thead>
          <tbody id="prefixes-table-body">
            <tr><td colspan="7">Loading prefix storage status...</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- TAB 5: DIAGNOSTICS -->
    <section id="tab-diagnostics" class="tab-content">
      <div class="card">
        <div class="card-title">Automated Crash Troubleshooter & Root-Cause Remediation</div>
        <p style="color: var(--fg-subtle); margin-bottom: 10px;">Paste runtime stderr, Wine logs, or dynamic loader errors below for automated failure signature classification and package install instructions:</p>
        <textarea id="diag-log" rows="6" placeholder="err:module:import_dll Library D3DX9_43.dll not found\nerror while loading shared libraries: libvulkan.so.1: cannot open shared object file"></textarea>
        <button class="btn" onclick="analyzeLog()">Diagnose Failure Signatures</button>
      </div>

      <div class="card" id="diag-result-card" style="display: none;">
        <div class="card-title">Diagnostic Findings & Remediations</div>
        <div id="diag-findings"></div>
      </div>
    </section>
  </main>

  <script>
    let dbEntries = [];

    function switchTab(tabId) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
      const activeTab = document.getElementById('tab-' + tabId);
      if (activeTab) activeTab.classList.add('active');
      event.target.classList.add('active');
    }}

    async function loadTelemetry() {{
      try {{
        const [envRes, dbRes, prefRes] = await Promise.all([
          fetch('/api/env').then(r => r.json()),
          fetch('/api/db').then(r => r.json()),
          fetch('/api/prefixes').then(r => r.json())
        ]);

        // Platform & Meta
        document.getElementById('header-platform').textContent = `${{envRes.os_name.toUpperCase()}} (${{envRes.architecture}}) • Kernel ${{envRes.kernel_version.substring(0, 32)}}`;
        document.getElementById('stat-os').textContent = envRes.os_name.toUpperCase();
        document.getElementById('stat-arch').textContent = envRes.architecture;
        document.getElementById('env-display').textContent = envRes.display_server.toUpperCase();
        document.getElementById('env-cores').textContent = `${{envRes.logical_cores}} Logical CPUs`;
        document.getElementById('env-mem').textContent = `${{envRes.total_memory_mb.toLocaleString()}} MB`;
        document.getElementById('env-kernel').textContent = envRes.kernel_version;
        document.getElementById('env-vulkan').textContent = envRes.graphics_capabilities.vulkan_supported ? "Active / Supported" : "Missing / Fallback";
        document.getElementById('env-sandbox').textContent = envRes.isolation_features.can_sandbox ? "Active (Bubblewrap Confined)" : "Unavailable (Unconfined)";

        // Runtimes Table
        const runtimes = envRes.available_runtimes || [];
        const installedCount = runtimes.filter(r => r.installed).length;
        document.getElementById('stat-runtimes').textContent = `${{installedCount}} / ${{runtimes.length}} Active`;

        const rTable = document.getElementById('runtimes-table-body');
        rTable.innerHTML = '';
        runtimes.forEach(r => {{
          const row = document.createElement('tr');
          const statusBadge = r.installed 
            ? '<span class="badge badge-green">🟢 Active</span>' 
            : '<span class="badge badge-red">🔴 Missing</span>';
          row.innerHTML = `
            <td><code>${{r.runtime_id}}</code></td>
            <td><strong>${{r.name}}</strong></td>
            <td>${{statusBadge}}</td>
            <td>${{r.version || 'N/A'}}</td>
            <td>${{r.supported_architectures.join(', ')}}</td>
          `;
          rTable.appendChild(row);
        }});

        // Database Table
        dbEntries = dbRes || [];
        document.getElementById('stat-profiles').textContent = `${{dbEntries.length}} Profiles`;
        renderDatabaseTable(dbEntries);

        // Prefixes Table
        const pTable = document.getElementById('prefixes-table-body');
        pTable.innerHTML = '';
        const allPrefixes = (prefRes.wine || []).concat(prefRes.proton || []);
        if (allPrefixes.length === 0) {{
          pTable.innerHTML = '<tr><td colspan="7" style="color: var(--fg-subtle);">No compatibility prefixes created yet.</td></tr>';
        }} else {{
          allPrefixes.forEach(p => {{
            const row = document.createElement('tr');
            const lockBadge = p.is_locked ? '<span class="badge badge-amber">🔒 Locked</span>' : '<span class="badge badge-green">Ready</span>';
            const persistBadge = p.is_persistent ? '<span class="badge badge-cyan">Durable</span>' : '<span class="badge badge-amber">Disposable</span>';
            row.innerHTML = `
              <td><strong>${{p.runtime_type.toUpperCase()}}</strong></td>
              <td>${{p.app_name}}</td>
              <td><code>${{p.architecture}}</code></td>
              <td>${{p.size_mb}} MB</td>
              <td>${{persistBadge}}</td>
              <td>${{lockBadge}}</td>
              <td><code>${{p.prefix_path}}</code></td>
            `;
            pTable.appendChild(row);
          }});
        }}

      }} catch (err) {{
        console.error("Failed to load telemetry:", err);
      }}
    }}

    function renderDatabaseTable(entries) {{
      const dTable = document.getElementById('db-table-body');
      dTable.innerHTML = '';
      if (entries.length === 0) {{
        dTable.innerHTML = '<tr><td colspan="7">No matching entries found.</td></tr>';
        return;
      }}
      entries.forEach(e => {{
        const row = document.createElement('tr');
        const statusBadge = e.status.includes('compatible')
          ? '<span class="badge badge-green">' + e.status + '</span>'
          : '<span class="badge badge-amber">' + e.status + '</span>';
        row.innerHTML = `
          <td><code>${{e.entry_id}}</code></td>
          <td><strong>${{e.application_name}}</strong></td>
          <td><code>${{e.target_format.toUpperCase()}}</code></td>
          <td>${{e.target_architecture}}</td>
          <td>${{statusBadge}}</td>
          <td><code>${{e.recommended_runtime}}</code></td>
          <td><span class="badge badge-cyan">${{e.provenance_tier}}</span></td>
        `;
        dTable.appendChild(row);
      }});
    }}

    function filterDatabase() {{
      const query = document.getElementById('db-filter').value.toLowerCase();
      const filtered = dbEntries.filter(e => 
        e.application_name.toLowerCase().includes(query) ||
        e.recommended_runtime.toLowerCase().includes(query) ||
        e.entry_id.toLowerCase().includes(query)
      );
      renderDatabaseTable(filtered);
    }}

    async function inspectBinary() {{
      const path = document.getElementById('inspect-path').value.trim();
      if (!path) return alert('Please enter a target path.');
      const res = await fetch('/api/inspect', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ path }})
      }});
      const data = await res.json();
      document.getElementById('inspect-title').textContent = `Binary Inspection: ${{path}}`;
      document.getElementById('inspect-json').textContent = JSON.stringify(data, null, 2);
      document.getElementById('inspect-result-card').style.display = 'block';
    }}

    async function generatePlan() {{
      const path = document.getElementById('inspect-path').value.trim();
      if (!path) return alert('Please enter a target path.');
      const res = await fetch('/api/plan', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ path }})
      }});
      const data = await res.json();
      document.getElementById('inspect-title').textContent = `Compatibility Plan: ${{path}}`;
      document.getElementById('inspect-json').textContent = JSON.stringify(data, null, 2);
      document.getElementById('inspect-result-card').style.display = 'block';
    }}

    async function analyzeLog() {{
      const log = document.getElementById('diag-log').value.trim();
      if (!log) return alert('Please enter an error log.');
      const res = await fetch('/api/diag', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ log }})
      }});
      const data = await res.json();
      const card = document.getElementById('diag-result-card');
      const container = document.getElementById('diag-findings');
      container.innerHTML = '';
      if (!data.events || data.events.length === 0) {{
        container.innerHTML = '<p style="color: var(--accent-green);">No known fatal crash signatures detected. Application log appears clean.</p>';
      }} else {{
        data.events.forEach((ev, i) => {{
          const item = document.createElement('div');
          item.style.marginBottom = '16px';
          item.innerHTML = `
            <div style="font-weight: 700; color: var(--accent-red); margin-bottom: 4px;">[${{i + 1}}] ${{ev.signature}} (Confidence: ${{Math.round(ev.confidence * 100)}}%)</div>
            <p style="margin-left: 12px; color: var(--fg-subtle);">Root Cause: ${{ev.root_cause}}</p>
            <p style="margin-left: 12px; color: var(--primary); margin-top: 2px;">Fix: ${{ev.remediation}}</p>
          `;
          container.appendChild(item);
        }});
      }}
      card.style.display = 'block';
    }}

    window.addEventListener('DOMContentLoaded', loadTelemetry);
  </script>
</body>
</html>"""


class ZCFWebConsoleRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for ZCF Web Console and REST API."""

    def __init__(self, *args, **kwargs):
        self.inspector = ApplicationInspector()
        self.env_inspector = EnvironmentInspector()
        self.planner = CompatibilityPlanner()
        self.db = CompatibilityDatabase()
        self.diag_engine = DiagnosticEngine()
        self.remediator = AutomatedRemediator()
        self.wine_prefix_mgr = WinePrefixManager()
        self.proton_prefix_mgr = WinePrefixManager(base_dir=os.path.expanduser("~/.zcf/proton_prefixes"))
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args):
        # Clean terminal logging for web requests
        if os.environ.get("ZCF_WEB_QUIET") == "1":
            return
        sys.stderr.write(f"[ZCF Web Console] {self.address_string()} - {format % args}\n")

    def _send_security_headers(self, content_type: str = "text/html; charset=utf-8"):
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self' 'unsafe-inline'; img-src 'self' data:;",
        )

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self._send_security_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400):
        self._send_json({"error": message, "status": status}, status=status)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html", "/console"):
            html_content = get_web_dashboard_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self._send_security_headers("text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content)
            return

        if path == "/api/env":
            env = self.env_inspector.inspect()
            self._send_json(env.to_dict())
            return

        if path == "/api/db":
            entries = self.db.list_all()
            self._send_json([e.to_dict() for e in entries])
            return

        if path == "/api/prefixes":
            wine_p = [p.to_dict() for p in self.wine_prefix_mgr.list_prefixes()]
            proton_p = [p.to_dict() for p in self.proton_prefix_mgr.list_prefixes()]
            self._send_json({"wine": wine_p, "proton": proton_p})
            return

        if path == "/api/dashboard":
            env = self.env_inspector.inspect()
            entries = self.db.list_all()
            verified = sum(1 for e in entries if "compatible" in e.status.value)
            self._send_json({
                "os": env.os_name,
                "architecture": env.architecture,
                "kernel": env.kernel_version,
                "display": env.display_server.value,
                "total_profiles": len(entries),
                "verified_profiles": verified,
                "active_runtimes": [r.runtime_id for r in env.available_runtimes if r.installed],
            })
            return

        self._send_error_json(f"Endpoint '{path}' not found", status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 2 * 1024 * 1024:  # 2MB request body cap
            self._send_error_json("Payload too large", status=413)
            return

        try:
            raw_body = self.rfile.read(content_len).decode("utf-8")
            payload = json.loads(raw_body) if raw_body else {}
        except Exception as e:
            self._send_error_json(f"Malformed JSON payload: {e}", status=400)
            return

        if path == "/api/inspect":
            target = payload.get("path")
            if not target or not isinstance(target, str):
                self._send_error_json("Missing 'path' string in JSON body", status=400)
                return
            if not os.path.exists(target):
                self._send_error_json(f"File not found: {target}", status=404)
                return
            try:
                app = self.inspector.inspect(target)
                self._send_json(app.to_dict())
            except Exception as e:
                self._send_error_json(f"Inspection error: {e}", status=500)
            return

        if path == "/api/plan":
            target = payload.get("path")
            if not target or not isinstance(target, str):
                self._send_error_json("Missing 'path' string in JSON body", status=400)
                return
            if not os.path.exists(target):
                self._send_error_json(f"File not found: {target}", status=404)
                return
            try:
                app = self.inspector.inspect(target)
                env = self.env_inspector.inspect()
                db_ev = self.db.get_by_sha256(app.sha256)
                plan = self.planner.plan(app, env, db_evidence=db_ev)
                self._send_json(plan.to_dict())
            except Exception as e:
                self._send_error_json(f"Planning error: {e}", status=500)
            return

        if path == "/api/diag":
            log_text = payload.get("log", "")
            if not log_text or not isinstance(log_text, str):
                self._send_error_json("Missing 'log' string in JSON body", status=400)
                return
            events = self.diag_engine.analyze_log(log_text)
            self._send_json({"events": [ev.to_dict() for ev in events]})
            return

        self._send_error_json(f"Endpoint '{path}' not found", status=404)


class ZCFWebConsole:
    """Manages the local HTTP server lifecycle."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None

    def start(self, blocking: bool = True):
        self.server = HTTPServer((self.host, self.port), ZCFWebConsoleRequestHandler)
        url = f"http://{self.host}:{self.port}"
        print(f"\n=======================================================")
        print(f"  [ZCF] Web Console Active")
        print(f"  URL: {url}")
        print(f"  Host: {self.host} (Loopback Only) | Port: {self.port}")
        print(f"  Press Ctrl+C to terminate the console server")
        print(f"=======================================================\n")

        if blocking:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                print("\n[ZCF Web Console] Terminating server...")
                self.server.server_close()
        else:
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def run_console(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    console = ZCFWebConsole(host=host, port=port)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    console.start(blocking=True)


def main():
    parser = argparse.ArgumentParser(description="Launch ZCF Web Console (Browser Control Center)")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (defaults to loopback 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")
    args = parser.parse_args()

    run_console(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
