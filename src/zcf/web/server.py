"""
ZCF Web Console Server.
Zero-dependency, local browser-based control center and REST API for ZCF.
Provides live system telemetry, compatibility database browsing, prefix storage management,
binary inspection, test execution, and diagnostic troubleshooting over a secure loopback interface.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

from zcf import __version__
from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.diagnostics.analyzer import DiagnosticEngine
from zcf.diagnostics.remediator import AutomatedRemediator
from zcf.environment.inspector import EnvironmentInspector
from zcf.execution.history import ExecutionHistoryManager
from zcf.inspector.inspector import ApplicationInspector
from zcf.planner.engine import CompatibilityPlanner
from zcf.runtimes.prefix_manager import WinePrefixManager
from zcf.runtimes.registry import RuntimeRegistry
from zcf.security.controller import SecurityController


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
      overflow-x: auto;
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
      white-space: nowrap;
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
    input:focus, textarea:focus, select:focus {{
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
    .btn-danger {{
      background: rgba(255, 82, 82, 0.2);
      color: var(--accent-red);
      border: 1px solid rgba(255, 82, 82, 0.4);
    }}
    .btn-danger:hover {{
      background: rgba(255, 82, 82, 0.35);
    }}
    .btn-sm {{
      padding: 4px 10px;
      font-size: 12px;
      margin-top: 0;
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
    .modal-overlay {{
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }}
    .modal-overlay.active {{
      display: flex;
    }}
    .modal {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      max-width: 800px;
      width: 100%;
      max-height: 85vh;
      overflow-y: auto;
      padding: 24px;
    }}
    .modal-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 12px;
    }}
    .close-btn {{
      background: none;
      border: none;
      color: var(--fg-subtle);
      font-size: 20px;
      cursor: pointer;
    }}
    .close-btn:hover {{ color: var(--fg); }}
    .alert-banner {{
      padding: 12px 16px;
      border-radius: 6px;
      margin-bottom: 16px;
      font-size: 14px;
      display: none;
    }}
    .alert-error {{
      background: rgba(255, 82, 82, 0.15);
      border: 1px solid rgba(255, 82, 82, 0.3);
      color: var(--accent-red);
    }}
    .alert-success {{
      background: rgba(0, 230, 118, 0.15);
      border: 1px solid rgba(0, 230, 118, 0.3);
      color: var(--accent-green);
    }}
  </style>
</head>
<body>
  <header>
    <div class="logo">
      <span>ZCF Web Console</span>
      <span class="logo-badge">v{__version__}</span>
    </div>
    <div class="header-meta" id="header-platform">Loading host telemetry...</div>
  </header>

  <nav>
    <button class="nav-btn active" onclick="switchTab('dashboard', event)">System Health</button>
    <button class="nav-btn" onclick="switchTab('inspector', event)">Binary Inspector & Plan</button>
    <button class="nav-btn" onclick="switchTab('test', event)">Execution Test Runner</button>
    <button class="nav-btn" onclick="switchTab('history', event)">Execution History</button>
    <button class="nav-btn" onclick="switchTab('database', event)">Compatibility Knowledge Base</button>
    <button class="nav-btn" onclick="switchTab('prefixes', event)">Isolated Storage</button>
    <button class="nav-btn" onclick="switchTab('diagnostics', event)">Crash Troubleshooter</button>
  </nav>

  <main>
    <div id="global-alert" class="alert-banner"></div>

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
        <input type="text" id="inspect-path" placeholder="/path/to/application.exe or fixtures/synthetic/valid_pe32plus.exe">
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

    <!-- TAB 3: EXECUTION TEST RUNNER -->
    <section id="tab-test" class="tab-content">
      <div class="card">
        <div class="card-title">Live Execution & Dry-Run Test Runner</div>
        <label for="test-path">Target Executable Path:</label>
        <input type="text" id="test-path" placeholder="/path/to/application.exe or valid_script.sh">
        
        <div style="display: flex; gap: 20px; margin-top: 12px; align-items: center;">
          <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
            <input type="checkbox" id="test-dry-run" checked style="width: auto; margin: 0;">
            Dry Run (Validate orchestration path without process execution)
          </label>
          <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
            <input type="checkbox" id="test-record" style="width: auto; margin: 0;">
            Record Outcome to Compatibility Knowledge Base
          </label>
        </div>

        <button class="btn" onclick="runTest()">Execute Compatibility Test</button>
      </div>

      <div class="card" id="test-result-card" style="display: none;">
        <div class="card-title" id="test-title">Test Results</div>
        <div id="test-summary" style="margin-bottom: 12px;"></div>
        <pre id="test-output"></pre>
      </div>
    </section>

    <!-- TAB: EXECUTION HISTORY -->
    <section id="tab-history" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Execution & Test Run History</span>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-secondary btn-sm" onclick="compareSelectedRuns()">Compare Selected (2)</button>
            <button class="btn btn-secondary btn-sm" onclick="loadHistory()">Refresh</button>
            <button class="btn btn-danger btn-sm" onclick="clearHistory()">Clear All</button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width: 36px;">Select</th>
              <th>Run ID</th>
              <th>Timestamp</th>
              <th>Application</th>
              <th>Runtime</th>
              <th>Mode</th>
              <th>Status</th>
              <th>Exit Code</th>
              <th>Duration</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="history-table-body">
            <tr><td colspan="10" style="color: var(--fg-subtle);">Loading execution history...</td></tr>
          </tbody>
        </table>
      </div>

      <div class="card" id="history-compare-card" style="display: none;">
        <div class="card-title">
          <span>Run Comparison Findings</span>
          <button class="close-btn" onclick="document.getElementById('history-compare-card').style.display='none'">&times;</button>
        </div>
        <div id="history-compare-content"></div>
      </div>
    </section>

    <!-- TAB 4: DATABASE -->
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
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="db-table-body">
            <tr><td colspan="8">Loading compatibility database...</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- TAB 5: PREFIXES -->
    <section id="tab-prefixes" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Managed Storage Containers & Prefixes</span>
          <button class="btn btn-secondary btn-sm" onclick="cleanupPrefixes()">Clean Stale Prefixes</button>
        </div>
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

    <!-- TAB 6: DIAGNOSTICS -->
    <section id="tab-diagnostics" class="tab-content">
      <div class="card">
        <div class="card-title">Automated Crash Troubleshooter & Root-Cause Remediation</div>
        <p style="color: var(--fg-subtle); margin-bottom: 10px;">Paste runtime stderr, Wine logs, or dynamic loader errors below for automated failure signature classification and package install instructions:</p>
        <textarea id="diag-log" rows="6" placeholder="err:module:import_dll Library D3DX9_43.dll not found&#10;error while loading shared libraries: libvulkan.so.1: cannot open shared object file"></textarea>
        <button class="btn" onclick="analyzeLog()">Diagnose Failure Signatures</button>
      </div>

      <div class="card" id="diag-result-card" style="display: none;">
        <div class="card-title">Diagnostic Findings & Remediations</div>
        <div id="diag-findings"></div>
      </div>
    </section>
  </main>

  <!-- DETAIL MODAL FOR PROFILE EVIDENCE -->
  <div id="profile-modal" class="modal-overlay">
    <div class="modal">
      <div class="modal-header">
        <h3 id="modal-title">Compatibility Profile Evidence</h3>
        <button class="close-btn" onclick="closeModal()">&times;</button>
      </div>
      <pre id="modal-content"></pre>
    </div>
  </div>

  <script>
    let dbEntries = [];

    function escapeHtml(str) {{
      if (str === null || str === undefined) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}

    function showAlert(msg, isError = true) {{
      const b = document.getElementById('global-alert');
      b.className = 'alert-banner ' + (isError ? 'alert-error' : 'alert-success');
      b.textContent = msg;
      b.style.display = 'block';
      setTimeout(() => {{ b.style.display = 'none'; }}, 5000);
    }}

    function switchTab(tabId, ev) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
      const activeTab = document.getElementById('tab-' + tabId);
      if (activeTab) activeTab.classList.add('active');
      if (ev && ev.target) ev.target.classList.add('active');
    }}

    function closeModal() {{
      document.getElementById('profile-modal').classList.remove('active');
    }}

    async function viewProfile(entryId) {{
      try {{
        const res = await fetch('/api/db/profile?id=' + encodeURIComponent(entryId));
        if (!res.ok) throw new Error('Failed to fetch profile details');
        const data = await res.json();
        document.getElementById('modal-title').textContent = 'Profile Evidence: ' + (data.application_name || entryId);
        document.getElementById('modal-content').textContent = JSON.stringify(data, null, 2);
        document.getElementById('profile-modal').classList.add('active');
      }} catch (err) {{
        showAlert('Error loading profile: ' + err.message, true);
      }}
    }}

    async function deleteProfile(entryId) {{
      if (!confirm('Are you sure you want to delete profile "' + entryId + '"?')) return;
      try {{
        const res = await fetch('/api/db/delete', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ id: entryId }})
        }});
        if (!res.ok) throw new Error('Deletion request failed');
        showAlert('Successfully deleted profile ' + entryId, false);
        loadTelemetry();
      }} catch (err) {{
        showAlert('Failed to delete profile: ' + err.message, true);
      }}
    }}

    async function loadTelemetry() {{
      try {{
        const [envRes, dbRes, prefRes] = await Promise.all([
          fetch('/api/env').then(r => r.json()),
          fetch('/api/db').then(r => r.json()),
          fetch('/api/prefixes').then(r => r.json())
        ]);

        // Platform & Meta
        document.getElementById('header-platform').textContent = 
          escapeHtml(envRes.os_name).toUpperCase() + ' (' + escapeHtml(envRes.architecture) + ') • Kernel ' + escapeHtml((envRes.kernel_version || '').substring(0, 32));
        document.getElementById('stat-os').textContent = escapeHtml(envRes.os_name).toUpperCase();
        document.getElementById('stat-arch').textContent = escapeHtml(envRes.architecture);
        document.getElementById('env-display').textContent = escapeHtml(envRes.display_server).toUpperCase();
        document.getElementById('env-cores').textContent = escapeHtml(envRes.logical_cores) + ' Logical CPUs';
        document.getElementById('env-mem').textContent = Number(envRes.total_memory_mb || 0).toLocaleString() + ' MB';
        document.getElementById('env-kernel').textContent = escapeHtml(envRes.kernel_version);
        document.getElementById('env-vulkan').textContent = envRes.graphics_capabilities && envRes.graphics_capabilities.vulkan_supported ? "Active / Supported" : "Missing / Fallback";
        document.getElementById('env-sandbox').textContent = envRes.isolation_features && envRes.isolation_features.can_sandbox ? "Active (Bubblewrap Confined)" : "Unavailable (Unconfined)";

        // Runtimes Table
        const runtimes = envRes.available_runtimes || [];
        const installedCount = runtimes.filter(r => r.installed).length;
        document.getElementById('stat-runtimes').textContent = installedCount + ' / ' + runtimes.length + ' Active';

        const rTable = document.getElementById('runtimes-table-body');
        rTable.innerHTML = '';
        runtimes.forEach(r => {{
          const row = document.createElement('tr');
          const isInst = Boolean(r.installed);
          row.innerHTML = 
            '<td><code>' + escapeHtml(r.runtime_id) + '</code></td>' +
            '<td><strong>' + escapeHtml(r.name) + '</strong></td>' +
            '<td><span class="badge ' + (isInst ? 'badge-green' : 'badge-red') + '">' + (isInst ? 'Active' : 'Missing') + '</span></td>' +
            '<td>' + escapeHtml(r.version || 'N/A') + '</td>' +
            '<td>' + escapeHtml((r.supported_architectures || []).join(', ')) + '</td>';
          rTable.appendChild(row);
        }});

        // Database Table
        dbEntries = dbRes || [];
        document.getElementById('stat-profiles').textContent = dbEntries.length + ' Profiles';
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
            const isLock = Boolean(p.is_locked);
            const isPersist = Boolean(p.is_persistent);
            row.innerHTML = 
              '<td><strong>' + escapeHtml(p.runtime_type || '').toUpperCase() + '</strong></td>' +
              '<td>' + escapeHtml(p.app_name) + '</td>' +
              '<td><code>' + escapeHtml(p.architecture) + '</code></td>' +
              '<td>' + escapeHtml(p.size_mb) + ' MB</td>' +
              '<td><span class="badge ' + (isPersist ? 'badge-cyan' : 'badge-amber') + '">' + (isPersist ? 'Durable' : 'Disposable') + '</span></td>' +
              '<td><span class="badge ' + (isLock ? 'badge-amber' : 'badge-green') + '">' + (isLock ? 'Locked' : 'Ready') + '</span></td>' +
              '<td><code>' + escapeHtml(p.prefix_path) + '</code></td>';
            pTable.appendChild(row);
          }});
        }}

        loadHistory();

      }} catch (err) {{
        console.error("Failed to load telemetry:", err);
      }}
    }}

    function renderDatabaseTable(entries) {{
      const dTable = document.getElementById('db-table-body');
      dTable.innerHTML = '';
      if (!entries || entries.length === 0) {{
        dTable.innerHTML = '<tr><td colspan="8" style="color: var(--fg-subtle);">No matching compatibility entries found.</td></tr>';
        return;
      }}
      entries.forEach(e => {{
        const row = document.createElement('tr');
        const st = String(e.status || '');
        const statusBadgeClass = st.includes('compatible') ? 'badge-green' : 'badge-amber';
        row.innerHTML = 
          '<td><code>' + escapeHtml(e.entry_id) + '</code></td>' +
          '<td><strong>' + escapeHtml(e.application_name) + '</strong></td>' +
          '<td><code>' + escapeHtml(String(e.target_format || '').toUpperCase()) + '</code></td>' +
          '<td>' + escapeHtml(e.target_architecture) + '</td>' +
          '<td><span class="badge ' + statusBadgeClass + '">' + escapeHtml(st) + '</span></td>' +
          '<td><code>' + escapeHtml(e.recommended_runtime) + '</code></td>' +
          '<td><span class="badge badge-cyan">' + escapeHtml(e.provenance_tier) + '</span></td>' +
          '<td><div style="display: flex; gap: 6px;">' +
            '<button class="btn btn-secondary btn-sm" onclick="viewProfile(\'' + escapeHtml(e.entry_id) + '\')">Details</button>' +
            '<button class="btn btn-danger btn-sm" onclick="deleteProfile(\'' + escapeHtml(e.entry_id) + '\')">Delete</button>' +
          '</div></td>';
        dTable.appendChild(row);
      }});
    }}

    function filterDatabase() {{
      const query = document.getElementById('db-filter').value.toLowerCase().trim();
      if (!query) return renderDatabaseTable(dbEntries);
      const filtered = dbEntries.filter(e => 
        String(e.application_name || '').toLowerCase().includes(query) ||
        String(e.recommended_runtime || '').toLowerCase().includes(query) ||
        String(e.entry_id || '').toLowerCase().includes(query)
      );
      renderDatabaseTable(filtered);
    }}

    async function inspectBinary() {{
      const path = document.getElementById('inspect-path').value.trim();
      if (!path) return showAlert('Please enter a target executable path.');
      try {{
        const res = await fetch('/api/inspect', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ path }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Inspection failed');
        document.getElementById('inspect-title').textContent = 'Binary Inspection: ' + path;
        document.getElementById('inspect-json').textContent = JSON.stringify(data, null, 2);
        document.getElementById('inspect-result-card').style.display = 'block';
      }} catch (err) {{
        showAlert('Inspection error: ' + err.message, true);
      }}
    }}

    async function generatePlan() {{
      const path = document.getElementById('inspect-path').value.trim();
      if (!path) return showAlert('Please enter a target executable path.');
      try {{
        const res = await fetch('/api/plan', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ path }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Planning failed');

        document.getElementById('inspect-title').textContent = 'Compatibility Plan: ' + path;
        
        let evBadge = '<span class="badge badge-cyan">Static Analysis</span>';
        if (data.evidence_type === 'exact_measured') {{
          evBadge = '<span class="badge badge-green">Exact Measured Evidence</span>';
        }} else if (data.evidence_type === 'heuristic_prediction') {{
          evBadge = '<span class="badge badge-amber">Heuristic Prediction</span>';
        }}

        let summaryHtml = '<div style="margin-bottom: 16px; padding: 12px; background: var(--code-bg); border-radius: 6px; border: 1px solid var(--card-border);">' +
          '<div style="display: flex; gap: 12px; align-items: center; margin-bottom: 8px;">' +
            '<strong>Evidence Type:</strong> ' + evBadge +
            '<span style="margin-left: auto;"><strong>Confidence:</strong> ' + Math.round((data.confidence_score || 0) * 100) + '%</span>' +
          '</div>' +
          '<div><strong>Selected Runtime:</strong> <code>' + escapeHtml(data.selected_runtime_name || 'None') + '</code> (' + escapeHtml(data.execution_mode || '').toUpperCase() + ')</div>' +
          '<div style="color: var(--fg-subtle); margin-top: 4px;">' + escapeHtml(data.reasoning || '') + '</div>';

        if (data.similar_profiles && data.similar_profiles.length > 0) {{
          summaryHtml += '<div style="margin-top: 10px; border-top: 1px solid var(--card-border); padding-top: 8px;">' +
            '<strong style="color: var(--accent-amber);">Similar Cataloged Profiles:</strong>' +
            '<ul style="margin-left: 20px; margin-top: 4px; font-size: 13px;">';
          data.similar_profiles.forEach(sp => {{
            summaryHtml += '<li><strong>' + escapeHtml(sp.application_name) + '</strong> (' + escapeHtml(sp.entry_id) + ') &rarr; ' +
              escapeHtml(sp.recommended_runtime) + ' <span class="badge badge-cyan" style="font-size: 10px;">' + escapeHtml(sp.status) + '</span></li>';
          }});
          summaryHtml += '</ul></div>';
        }}

        if (data.applied_workarounds && data.applied_workarounds.length > 0) {{
          summaryHtml += '<div style="margin-top: 10px; border-top: 1px solid var(--card-border); padding-top: 8px;">' +
            '<strong style="color: var(--primary);">Known Workarounds:</strong>' +
            '<ul style="margin-left: 20px; margin-top: 4px; font-size: 13px;">';
          data.applied_workarounds.forEach(w => {{
            summaryHtml += '<li><strong>' + escapeHtml(w.issue || 'Issue') + ':</strong> ' + escapeHtml(w.solution || '') + '</li>';
          }});
          summaryHtml += '</ul></div>';
        }}

        summaryHtml += '</div>';

        const jsonPre = document.getElementById('inspect-json');
        jsonPre.innerHTML = summaryHtml + '<pre style="background: transparent; border: none; padding: 0;">' + escapeHtml(JSON.stringify(data, null, 2)) + '</pre>';
        document.getElementById('inspect-result-card').style.display = 'block';
      }} catch (err) {{
        showAlert('Planning error: ' + err.message, true);
      }}
    }}

    async function runTest() {{
      const path = document.getElementById('test-path').value.trim();
      if (!path) return showAlert('Please enter a target path to test.');
      const dryRun = document.getElementById('test-dry-run').checked;
      const record = document.getElementById('test-record').checked;

      try {{
        const res = await fetch('/api/test', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ path, dry_run: dryRun, record }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Test request failed');

        const card = document.getElementById('test-result-card');
        const summary = document.getElementById('test-summary');
        const outPre = document.getElementById('test-output');

        document.getElementById('test-title').textContent = 'Test Result: ' + path;
        const statusBadge = data.success 
          ? '<span class="badge badge-green">SUCCESS</span>' 
          : '<span class="badge badge-red">BLOCKED / FAILED</span>';

        summary.innerHTML = 
          '<div>Status: ' + statusBadge + ' | Exit Code: <code>' + escapeHtml(data.exit_code) + '</code> | Runtime: <strong>' + escapeHtml(data.runtime || 'None') + '</strong></div>' +
          '<div style="font-size: 13px; color: var(--fg-subtle); margin-top: 4px;">Mode: ' + escapeHtml(data.execution_mode) + ' • Duration: ' + escapeHtml(data.execution_time_seconds) + 's</div>';

        outPre.textContent = (data.stdout || '') + (data.stderr ? '\nError:\n' + data.stderr : '') + (data.reasoning ? '\nReason:\n' + data.reasoning : '');
        card.style.display = 'block';
        if (record) loadTelemetry();
        loadHistory();
      }} catch (err) {{
        showAlert('Test execution error: ' + err.message, true);
      }}
    }}

    async function loadHistory() {{
      try {{
        const res = await fetch('/api/history');
        if (!res.ok) return;
        const runs = await res.json();
        renderHistoryTable(runs);
      }} catch (err) {{
        console.error('Failed to load history:', err);
      }}
    }}

    function renderHistoryTable(runs) {{
      const hTable = document.getElementById('history-table-body');
      hTable.innerHTML = '';
      if (!runs || runs.length === 0) {{
        hTable.innerHTML = '<tr><td colspan="10" style="color: var(--fg-subtle);">No execution or test runs recorded yet. Run a test to view history.</td></tr>';
        return;
      }}
      runs.forEach(r => {{
        const row = document.createElement('tr');
        const isSuccess = Boolean(r.success);
        const isDry = Boolean(r.dry_run);
        row.innerHTML = 
          '<td><input type="checkbox" class="history-select" value="' + escapeHtml(r.run_id) + '"></td>' +
          '<td><code>' + escapeHtml(r.run_id) + '</code></td>' +
          '<td>' + escapeHtml((r.timestamp || '').substring(0, 19).replace('T', ' ')) + '</td>' +
          '<td><strong>' + escapeHtml(r.application_name) + '</strong></td>' +
          '<td><code>' + escapeHtml(r.runtime_name || r.runtime_id) + '</code></td>' +
          '<td><span class="badge ' + (isDry ? 'badge-amber' : 'badge-cyan') + '">' + (isDry ? 'Dry Run' : 'Live') + '</span></td>' +
          '<td><span class="badge ' + (isSuccess ? 'badge-green' : 'badge-red') + '">' + (isSuccess ? 'SUCCESS' : 'FAILED') + '</span></td>' +
          '<td><code>' + escapeHtml(r.exit_code) + '</code></td>' +
          '<td>' + Number(r.execution_time_seconds || 0).toFixed(4) + 's</td>' +
          '<td><div style="display: flex; gap: 6px;">' +
            '<button class="btn btn-secondary btn-sm" onclick="viewRun(\'' + escapeHtml(r.run_id) + '\')">Details</button>' +
            '<button class="btn btn-danger btn-sm" onclick="deleteRun(\'' + escapeHtml(r.run_id) + '\')">Delete</button>' +
          '</div></td>';
        hTable.appendChild(row);
      }});
    }}

    async function viewRun(runId) {{
      try {{
        const res = await fetch('/api/history/detail?id=' + encodeURIComponent(runId));
        if (!res.ok) throw new Error('Failed to load run details');
        const data = await res.json();
        document.getElementById('modal-title').textContent = 'Execution Run: ' + runId;
        document.getElementById('modal-content').textContent = JSON.stringify(data, null, 2);
        document.getElementById('profile-modal').classList.add('active');
      }} catch (err) {{
        showAlert('Error loading run: ' + err.message, true);
      }}
    }}

    async function deleteRun(runId) {{
      if (!confirm('Delete execution run record "' + runId + '"?')) return;
      try {{
        const res = await fetch('/api/history/delete', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ id: runId }})
        }});
        if (!res.ok) throw new Error('Deletion request failed');
        showAlert('Deleted run record ' + runId, false);
        loadHistory();
      }} catch (err) {{
        showAlert('Error deleting run: ' + err.message, true);
      }}
    }}

    async function clearHistory() {{
      if (!confirm('Clear all execution run records?')) return;
      try {{
        const res = await fetch('/api/history/clear', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{}})
        }});
        if (!res.ok) throw new Error('Clear request failed');
        const data = await res.json();
        showAlert('Cleared ' + (data.cleared_count || 0) + ' run records.', false);
        loadHistory();
      }} catch (err) {{
        showAlert('Error clearing history: ' + err.message, true);
      }}
    }}

    async function compareSelectedRuns() {{
      const checkboxes = Array.from(document.querySelectorAll('.history-select:checked'));
      if (checkboxes.length !== 2) {{
        return showAlert('Please select exactly 2 runs using the checkboxes to compare side-by-side.');
      }}
      const runA = checkboxes[0].value;
      const runB = checkboxes[1].value;
      try {{
        const res = await fetch('/api/history/compare', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ run_a: runA, run_b: runB }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Comparison failed');

        const card = document.getElementById('history-compare-card');
        const content = document.getElementById('history-compare-content');
        
        content.innerHTML = 
          '<div class="grid-2" style="margin-bottom: 16px;">' +
            '<div style="background: var(--code-bg); padding: 14px; border-radius: 6px; border: 1px solid var(--card-border);">' +
              '<h4 style="color: var(--primary); margin-bottom: 8px;">Run A: ' + escapeHtml(data.run_a.run_id) + '</h4>' +
              '<div><strong>Application:</strong> ' + escapeHtml(data.run_a.application) + '</div>' +
              '<div><strong>Runtime:</strong> ' + escapeHtml(data.run_a.runtime) + '</div>' +
              '<div><strong>Mode:</strong> ' + (data.run_a.dry_run ? 'Dry Run' : 'Live') + '</div>' +
              '<div><strong>Exit Code:</strong> <code>' + escapeHtml(data.run_a.exit_code) + '</code></div>' +
              '<div><strong>Duration:</strong> ' + Number(data.run_a.execution_time_seconds || 0).toFixed(4) + 's</div>' +
              '<div><strong>Sandbox:</strong> ' + (data.run_a.sandbox_active ? 'Active' : 'Unconfined') + '</div>' +
            '</div>' +
            '<div style="background: var(--code-bg); padding: 14px; border-radius: 6px; border: 1px solid var(--card-border);">' +
              '<h4 style="color: var(--primary); margin-bottom: 8px;">Run B: ' + escapeHtml(data.run_b.run_id) + '</h4>' +
              '<div><strong>Application:</strong> ' + escapeHtml(data.run_b.application) + '</div>' +
              '<div><strong>Runtime:</strong> ' + escapeHtml(data.run_b.runtime) + '</div>' +
              '<div><strong>Mode:</strong> ' + (data.run_b.dry_run ? 'Dry Run' : 'Live') + '</div>' +
              '<div><strong>Exit Code:</strong> <code>' + escapeHtml(data.run_b.exit_code) + '</code></div>' +
              '<div><strong>Duration:</strong> ' + Number(data.run_b.execution_time_seconds || 0).toFixed(4) + 's</div>' +
              '<div><strong>Sandbox:</strong> ' + (data.run_b.sandbox_active ? 'Active' : 'Unconfined') + '</div>' +
            '</div>' +
          '</div>' +
          '<div style="background: var(--code-bg); padding: 14px; border-radius: 6px; border: 1px solid var(--card-border);">' +
            '<h4 style="margin-bottom: 8px;">Comparison Analysis</h4>' +
            '<div><strong>Runtime Changed:</strong> ' + (data.differences.runtime_changed ? 'Yes' : 'No') + '</div>' +
            '<div><strong>Exit Code Changed:</strong> ' + (data.differences.exit_code_changed ? 'Yes' : 'No') + '</div>' +
            '<div><strong>Execution Time Delta:</strong> ' + Number(data.differences.execution_time_delta_seconds || 0).toFixed(4) + 's</div>' +
            '<div><strong>Outcome Improved:</strong> ' + (data.differences.outcome_improved ? '<span style="color: var(--accent-green);">YES</span>' : 'No') + '</div>' +
          '</div>';

        card.style.display = 'block';
      }} catch (err) {{
        showAlert('Comparison error: ' + err.message, true);
      }}
    }}

    async function cleanupPrefixes() {{
      if (!confirm('Clean all unpinned/stale prefix directories older than 14 days?')) return;
      try {{
        const res = await fetch('/api/prefixes/cleanup', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ max_age_days: 14 }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Cleanup failed');
        showAlert('Cleaned ' + (data.total || 0) + ' stale prefix directories.', false);
        loadTelemetry();
      }} catch (err) {{
        showAlert('Cleanup error: ' + err.message, true);
      }}
    }}

    async function analyzeLog() {{
      const log = document.getElementById('diag-log').value.trim();
      if (!log) return showAlert('Please enter an error log to diagnose.');
      try {{
        const res = await fetch('/api/diag', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ log }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Diagnostic analysis failed');

        const card = document.getElementById('diag-result-card');
        const container = document.getElementById('diag-findings');
        container.innerHTML = '';
        if (!data.events || data.events.length === 0) {{
          container.innerHTML = '<p style="color: var(--accent-green);">No known fatal crash signatures detected. Application log appears clean.</p>';
        }} else {{
          data.events.forEach((ev, i) => {{
            const item = document.createElement('div');
            item.style.marginBottom = '16px';
            item.innerHTML = 
              '<div style="font-weight: 700; color: var(--accent-red); margin-bottom: 4px;">[' + (i + 1) + '] ' + escapeHtml(ev.signature) + ' (Confidence: ' + Math.round(ev.confidence * 100) + '%)</div>' +
              '<p style="margin-left: 12px; color: var(--fg-subtle);">Root Cause: ' + escapeHtml(ev.root_cause) + '</p>' +
              '<p style="margin-left: 12px; color: var(--primary); margin-top: 2px;">Fix: ' + escapeHtml(ev.remediation) + '</p>';
            container.appendChild(item);
          }});
        }}
        card.style.display = 'block';
      }} catch (err) {{
        showAlert('Diagnostic error: ' + err.message, true);
      }}
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
        self.registry = RuntimeRegistry()
        self.planner = CompatibilityPlanner(self.registry)
        self.db = CompatibilityDatabase()
        self.diag_engine = DiagnosticEngine()
        self.remediator = AutomatedRemediator()
        self.wine_prefix_mgr = WinePrefixManager()
        self.proton_prefix_mgr = WinePrefixManager(base_dir=os.path.expanduser("~/.zcf/proton_prefixes"))
        self.security = SecurityController()
        self.history_mgr = ExecutionHistoryManager()
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args):
        if os.environ.get("ZCF_WEB_QUIET") == "1":
            return
        sys.stderr.write(f"[ZCF Web Console] {self.address_string()} - {format % args}\n")

    def _validate_host_header(self) -> bool:
        """Validates Host header to protect against DNS rebinding and remote injection."""
        host_header = self.headers.get("Host", "").strip()
        if not host_header:
            return False
        # Strip port if present
        host_name = host_header.split(":")[0].lower()
        allowed_hosts = {"127.0.0.1", "localhost", "::1"}
        server_host = getattr(self.server, "server_address", (None,))[0]
        if server_host:
            allowed_hosts.add(str(server_host).lower())
        return host_name in allowed_hosts

    def _validate_origin(self) -> bool:
        """Validates Origin and Sec-Fetch-Site headers to protect against CSRF attacks."""
        sec_fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if sec_fetch_site in ("cross-site",):
            return False

        origin = self.headers.get("Origin")
        if not origin:
            return True  # Direct non-browser requests or same-origin without Origin header
        try:
            parsed = urllib.parse.urlparse(origin)
            host_name = parsed.hostname.lower() if parsed.hostname else ""
            allowed = {"127.0.0.1", "localhost", "::1"}
            server_host = getattr(self.server, "server_address", (None,))[0]
            if server_host:
                allowed.add(str(server_host).lower())
            return host_name in allowed
        except Exception:
            return False

    def _send_security_headers(self, content_type: str = "text/html; charset=utf-8"):
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self';",
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

    def _validate_target_path(self, target: Any) -> Optional[str]:
        """Validates that a path is safe, exists on disk, and is a regular file."""
        if not target or not isinstance(target, str):
            return None
        if "\x00" in target:
            return None
        canonical = os.path.realpath(os.path.abspath(target))
        if not os.path.isfile(canonical):
            return None
        return canonical

    def do_GET(self):
        if not self._validate_host_header():
            self._send_error_json("Forbidden: Invalid Host header", status=403)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

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

        if path == "/api/db/profile":
            entry_id = query.get("id", [""])[0].strip()
            if not entry_id:
                self._send_error_json("Missing 'id' query parameter", status=400)
                return
            entry = self.db.get_by_id(entry_id)
            if not entry:
                self._send_error_json(f"Profile '{entry_id}' not found", status=404)
                return
            self._send_json(entry.to_dict())
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

        if path == "/api/history":
            sha = query.get("sha256", [""])[0].strip() or None
            try:
                limit = int(query.get("limit", [50])[0])
            except ValueError:
                limit = 50
            runs = self.history_mgr.list_runs(sha256=sha, limit=limit)
            self._send_json(runs)
            return

        if path == "/api/history/detail":
            run_id = query.get("id", [""])[0].strip()
            if not run_id:
                self._send_error_json("Missing 'id' query parameter", status=400)
                return
            run = self.history_mgr.get_run(run_id)
            if not run:
                self._send_error_json(f"Run '{run_id}' not found", status=404)
                return
            self._send_json(run)
            return

        self._send_error_json(f"Endpoint '{path}' not found", status=404)

    def do_POST(self):
        if not self._validate_host_header():
            self._send_error_json("Forbidden: Invalid Host header", status=403)
            return

        if not self._validate_origin():
            self._send_error_json("Forbidden: Cross-origin request rejected", status=403)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            content_len = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_error_json("Invalid Content-Length header", status=400)
            return

        if content_len < 0:
            self._send_error_json("Invalid negative Content-Length", status=400)
            return

        if content_len > 2 * 1024 * 1024:  # 2MB request body cap
            self._send_error_json("Payload too large (exceeds 2MB limit)", status=413)
            return

        try:
            raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
            payload = json.loads(raw_body) if raw_body else {}
        except Exception as e:
            self._send_error_json(f"Malformed JSON payload: {e}", status=400)
            return

        if path == "/api/inspect":
            raw_target = payload.get("path")
            canonical = self._validate_target_path(raw_target)
            if not canonical:
                self._send_error_json(f"File not found or not a valid regular file: {raw_target}", status=404)
                return
            try:
                app = self.inspector.inspect(canonical)
                self._send_json(app.to_dict())
            except Exception as e:
                self._send_error_json(f"Inspection error: {e}", status=500)
            return

        if path == "/api/plan":
            raw_target = payload.get("path")
            canonical = self._validate_target_path(raw_target)
            if not canonical:
                self._send_error_json(f"File not found or not a valid regular file: {raw_target}", status=404)
                return
            try:
                app = self.inspector.inspect(canonical)
                env = self.env_inspector.inspect()
                db_ev = self.db.get_by_sha256(app.sha256)
                similar_ev = None
                if not db_ev:
                    similar_ev = self.db.find_similar_profiles(
                        name=app.file_name, format_type=app.format.value, arch=app.architecture.value
                    )
                plan = self.planner.plan(app, env, db_evidence=db_ev, similar_evidence=similar_ev)
                self._send_json(plan.to_dict())
            except Exception as e:
                self._send_error_json(f"Planning error: {e}", status=500)
            return

        if path == "/api/test":
            raw_target = payload.get("path")
            canonical = self._validate_target_path(raw_target)
            if not canonical:
                self._send_error_json(f"File not found or not a valid regular file: {raw_target}", status=404)
                return

            dry_run = bool(payload.get("dry_run", True))
            should_record = bool(payload.get("record", False))

            try:
                self.security.validate_execution_safety(canonical)
                app = self.inspector.inspect(canonical)
                env = self.env_inspector.inspect()
                db_ev = self.db.get_by_sha256(app.sha256)
                similar_ev = None
                if not db_ev:
                    similar_ev = self.db.find_similar_profiles(
                        name=app.file_name, format_type=app.format.value, arch=app.architecture.value
                    )
                plan = self.planner.plan(app, env, db_evidence=db_ev, similar_evidence=similar_ev)

                if not plan.selected_runtime_id:
                    self.history_mgr.record_run(
                        artifact_path=canonical,
                        artifact_sha256=app.sha256,
                        application_name=app.file_name,
                        target_format=app.format.value,
                        target_architecture=app.architecture.value,
                        runtime_id="none",
                        runtime_name="None",
                        execution_mode="blocked",
                        dry_run=dry_run,
                        success=False,
                        exit_code=2,
                        execution_time_seconds=0.0,
                        sandbox_active=False,
                        network_isolated=True,
                        stdout="",
                        stderr=plan.reasoning,
                        environment={"os": env.os_name, "arch": env.architecture, "kernel": env.kernel_version},
                    )
                    self._send_json({
                        "success": False,
                        "exit_code": 2,
                        "runtime": None,
                        "execution_mode": "blocked",
                        "is_blocked": True,
                        "reasoning": plan.reasoning,
                        "stdout": "",
                        "stderr": plan.reasoning,
                        "execution_time_seconds": 0.0,
                    })
                    return

                # If live execution requested but blocked by prerequisites
                if not dry_run and plan.execution_mode.value == "blocked":
                    self.history_mgr.record_run(
                        artifact_path=canonical,
                        artifact_sha256=app.sha256,
                        application_name=app.file_name,
                        target_format=app.format.value,
                        target_architecture=app.architecture.value,
                        runtime_id=plan.selected_runtime_id,
                        runtime_name=plan.selected_runtime_name or "None",
                        execution_mode="blocked",
                        dry_run=dry_run,
                        success=False,
                        exit_code=2,
                        execution_time_seconds=0.0,
                        sandbox_active=False,
                        network_isolated=True,
                        stdout="",
                        stderr=f"Live execution blocked: {plan.reasoning}",
                        environment={"os": env.os_name, "arch": env.architecture, "kernel": env.kernel_version},
                    )
                    self._send_json({
                        "success": False,
                        "exit_code": 2,
                        "runtime": plan.selected_runtime_name,
                        "execution_mode": "blocked",
                        "is_blocked": True,
                        "reasoning": plan.reasoning,
                        "stdout": "",
                        "stderr": f"Live execution blocked: {plan.reasoning}",
                        "execution_time_seconds": 0.0,
                    })
                    return

                adapter = self.registry.get_adapter(plan.selected_runtime_id)
                if not adapter:
                    self._send_error_json(f"Adapter '{plan.selected_runtime_id}' not found", status=500)
                    return

                context = adapter.prepare_environment(app, config={"dry_run": dry_run})
                result = adapter.execute(app, context, dry_run=dry_run)

                self.history_mgr.record_run(
                    artifact_path=canonical,
                    artifact_sha256=app.sha256,
                    application_name=app.file_name,
                    target_format=app.format.value,
                    target_architecture=app.architecture.value,
                    runtime_id=plan.selected_runtime_id,
                    runtime_name=plan.selected_runtime_name or "None",
                    execution_mode=plan.execution_mode.value,
                    dry_run=dry_run,
                    success=result.success if not dry_run else True,
                    exit_code=0 if dry_run else result.exit_code,
                    execution_time_seconds=0.0 if dry_run else result.execution_time_seconds,
                    sandbox_active=False,
                    network_isolated=True,
                    command=getattr(result, "command", []),
                    stdout=result.stdout,
                    stderr=getattr(result, "stderr", ""),
                    environment={"os": env.os_name, "arch": env.architecture, "kernel": env.kernel_version},
                )

                if should_record:
                    from zcf.core.models import CompatibilityStatus
                    if dry_run:
                        status = CompatibilityStatus.UNTESTED
                        procedure = f"Dry-run orchestration validation via {plan.selected_runtime_name} (unexecuted)"
                    elif result.success:
                        status = CompatibilityStatus.VERIFIED_COMPATIBLE
                        procedure = f"Live execution test passed via {plan.selected_runtime_name} (exit code: 0)"
                    else:
                        status = CompatibilityStatus.INCOMPATIBLE
                        procedure = f"Live execution test failed via {plan.selected_runtime_name} (exit code: {result.exit_code})"

                    self.db.submit_profile(
                        app=app,
                        recommended_runtime=plan.selected_runtime_id,
                        status=status,
                        contributor_name="Web Console Tester",
                        test_procedure=procedure,
                        env=env,
                    )

                self._send_json({
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "runtime": plan.selected_runtime_name,
                    "execution_mode": plan.execution_mode.value,
                    "is_blocked": plan.is_blocked,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "execution_time_seconds": result.execution_time_seconds,
                    "dry_run": dry_run,
                })
            except Exception as e:
                self._send_error_json(f"Test execution error: {e}", status=500)
            return

        if path == "/api/db/delete":
            entry_id = payload.get("id")
            if not entry_id or not isinstance(entry_id, str):
                self._send_error_json("Missing 'id' string in JSON body", status=400)
                return
            try:
                deleted = self.db.delete_entry(entry_id)
                if not deleted:
                    self._send_error_json(f"Profile '{entry_id}' not found", status=404)
                    return
                self._send_json({"success": True, "deleted_id": entry_id})
            except Exception as e:
                self._send_error_json(f"Database deletion error: {e}", status=500)
            return

        if path == "/api/prefixes/cleanup":
            max_age_days = int(payload.get("max_age_days", 14))
            cleaned_wine = self.wine_prefix_mgr.cleanup_stale_prefixes(max_age_days=max_age_days)
            cleaned_proton = self.proton_prefix_mgr.cleanup_stale_prefixes(max_age_days=max_age_days)
            self._send_json({
                "success": True,
                "cleaned_wine": cleaned_wine,
                "cleaned_proton": cleaned_proton,
                "total": cleaned_wine + cleaned_proton,
            })
            return

        if path == "/api/history/compare":
            run_a = payload.get("run_a")
            run_b = payload.get("run_b")
            if not run_a or not run_b:
                self._send_error_json("Missing 'run_a' or 'run_b' in JSON body", status=400)
                return
            try:
                diff = self.history_mgr.compare_runs(run_a, run_b)
                self._send_json(diff)
            except Exception as e:
                self._send_error_json(f"Comparison error: {e}", status=400)
            return

        if path == "/api/history/delete":
            run_id = payload.get("id")
            if not run_id or not isinstance(run_id, str):
                self._send_error_json("Missing 'id' string in JSON body", status=400)
                return
            deleted = self.history_mgr.delete_run(run_id)
            if not deleted:
                self._send_error_json(f"Run '{run_id}' not found", status=404)
                return
            self._send_json({"success": True, "deleted_id": run_id})
            return

        if path == "/api/history/clear":
            count = self.history_mgr.clear_runs()
            self._send_json({"success": True, "cleared_count": count})
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
    """Manages the local HTTP server lifecycle with multi-threading and security controls."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, allow_remote: bool = False):
        self.host = host
        self.port = port
        self.allow_remote = allow_remote

        # Security check: Non-loopback binding requires explicit allow_remote confirmation
        is_loopback = self.host in ("127.0.0.1", "localhost", "::1")
        if not is_loopback and not self.allow_remote:
            raise ValueError(
                f"Binding to non-loopback address '{self.host}' is blocked for security. "
                "Specify --allow-remote to explicitly authorize remote network exposure."
            )

        self.server: Optional[ThreadingHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None

    def start(self, blocking: bool = True):
        self.server = ThreadingHTTPServer((self.host, self.port), ZCFWebConsoleRequestHandler)
        url = f"http://{self.host}:{self.port}"
        print(f"\n=======================================================")
        print(f"  [ZCF] Web Console Active")
        print(f"  URL: {url}")
        print(f"  Host: {self.host} ({'Loopback Only' if self.host in ('127.0.0.1', 'localhost') else 'REMOTE NETWORK ACTIVE'}) | Port: {self.port}")
        print(f"  Press Ctrl+C to terminate the console server")
        print(f"=======================================================\n")

        if blocking:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                print("\n[ZCF Web Console] Terminating server...")
                self.stop()
        else:
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def run_console(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True, allow_remote: bool = False):
    console = ZCFWebConsole(host=host, port=port, allow_remote=allow_remote)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    console.start(blocking=True)


def main():
    parser = argparse.ArgumentParser(description="Launch ZCF Web Console (Browser Control Center)")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (defaults to loopback 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    parser.add_argument("--allow-remote", action="store_true", help="Explicitly permit binding to remote/non-loopback network interfaces")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")
    args = parser.parse_args()

    run_console(host=args.host, port=args.port, open_browser=not args.no_browser, allow_remote=args.allow_remote)


if __name__ == "__main__":
    main()
