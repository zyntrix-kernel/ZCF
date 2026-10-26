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
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

from zcf import __version__
from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.diagnostics.analyzer import DiagnosticEngine
from zcf.diagnostics.prescriptions import PrescriptionEngine
from zcf.diagnostics.remediator import AutomatedRemediator
from zcf.environment.inspector import EnvironmentInspector
from zcf.execution.history import ExecutionHistoryManager
from zcf.execution.tuning import (
    GamingTuningConfig,
    build_tuning_pipeline,
    check_tuning_tools_availability,
    get_tuning_preset,
)
from zcf.inspector.inspector import ApplicationInspector
from zcf.planner.engine import CompatibilityPlanner
from zcf.runtimes.components import WindowsComponentManager
from zcf.runtimes.fleet import RunnerFleetManager
from zcf.runtimes.prefix_manager import WinePrefixManager
from zcf.runtimes.registry import RuntimeRegistry
from zcf.runtimes.snapshots import PrefixSnapshotManager
from zcf.runtimes.tasks import PrefixTaskManager
from zcf.runtimes.vault import GameSaveVault
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
    .topology-node {{
      background: #181b22;
      border: 1px solid #2a3142;
      border-radius: 8px;
      padding: 14px;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .topology-node:hover {{
      border-color: var(--primary);
      background: #202533;
    }}
    .topology-node.active-node {{
      border-color: var(--primary);
      box-shadow: 0 0 14px rgba(0, 229, 255, 0.25);
    }}
    .component-row {{
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 10px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }}
    .filter-btn {{
      background: none;
      border: 1px solid var(--card-border);
      color: var(--fg-subtle);
      border-radius: 4px;
      padding: 4px 10px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .filter-btn:hover {{
      color: var(--fg);
      border-color: var(--fg-subtle);
    }}
    .filter-btn.active {{
      background: var(--primary);
      color: #000;
      border-color: var(--primary);
      font-weight: 700;
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
    <button class="nav-btn" onclick="switchTab('tuning', event)">Gaming & Tuning</button>
    <button class="nav-btn" onclick="switchTab('runners', event)">Runner Fleet</button>
    <button class="nav-btn" onclick="switchTab('inspector', event)">Binary Inspector & Plan</button>
    <button class="nav-btn" onclick="switchTab('test', event)">Execution Test Runner</button>
    <button class="nav-btn" onclick="switchTab('history', event)">Execution History</button>
    <button class="nav-btn" onclick="switchTab('database', event)">Compatibility Knowledge Base</button>
    <button class="nav-btn" onclick="switchTab('prefixes', event)">Isolated Storage & Tools</button>
    <button class="nav-btn" onclick="switchTab('vault', event)">Save Game Vault</button>
    <button class="nav-btn" onclick="switchTab('diagnostics', event)">Crash Troubleshooter</button>
  </nav>

  <main>
    <div id="global-alert" class="alert-banner"></div>

    <!-- TAB 1: SYSTEM HEALTH -->
    <section id="tab-dashboard" class="tab-content active">
      <div class="card" id="readiness-card" style="border-left: 4px solid var(--primary); margin-bottom: 24px;">
        <div class="card-title">
          <span>Pre-Flight System Readiness & Gaming Optimization Matrix</span>
          <button class="btn btn-secondary btn-sm" onclick="loadReadinessAudit()">Run Diagnostic Audit</button>
        </div>
        <div style="display: flex; gap: 24px; align-items: center; flex-wrap: wrap; margin-bottom: 20px;">
          <!-- Circular SVG Gauge -->
          <div style="position: relative; width: 110px; height: 110px; flex-shrink: 0;">
            <svg viewBox="0 0 36 36" style="width: 100%; height: 100%; transform: rotate(-90deg);">
              <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#25252c" stroke-width="3.2" />
              <path id="readiness-gauge-circle" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--primary)" stroke-width="3.2" stroke-dasharray="0, 100" style="transition: stroke-dasharray 0.6s ease;" />
            </svg>
            <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;">
              <span id="readiness-gauge-val" style="font-size: 20px; font-weight: 800; color: var(--primary);">0%</span>
              <span id="readiness-grade-badge" class="badge badge-cyan" style="font-size: 9px; margin-top: 2px;">AUDITING</span>
            </div>
          </div>
          <!-- Summary Info -->
          <div style="flex: 1; min-width: 260px;">
            <div style="font-size: 15px; font-weight: 700; margin-bottom: 4px;" id="readiness-summary-title">System Status: Evaluating Subsystems...</div>
            <p style="color: var(--fg-subtle); font-size: 13px;" id="readiness-summary-desc">Auditing kernel capabilities, Vulkan drivers, user namespaces, and thread synchronization limits.</p>
          </div>
        </div>
        <!-- Checks Table -->
        <table>
          <thead>
            <tr>
              <th style="width: 75px;">Status</th>
              <th>Subsystem Check</th>
              <th style="width: 80px;">Points</th>
              <th>Diagnostic Telemetry & Host Findings</th>
              <th>Actionable Remediation</th>
            </tr>
          </thead>
          <tbody id="readiness-table-body">
            <tr><td colspan="5" style="color: var(--fg-subtle);">Running readiness audit...</td></tr>
          </tbody>
        </table>
      </div>

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

    <!-- TAB: GAMING & TUNING -->
    <section id="tab-tuning" class="tab-content">
      <div class="card" style="border-left: 4px solid var(--accent-green);">
        <div class="card-title">
          <span>Esports & Gaming Performance Accelerators</span>
          <span class="badge badge-green" id="tuning-status-badge">Gaming Pipeline Active</span>
        </div>
        <p style="color: var(--fg-subtle); margin-bottom: 16px; font-size: 13px;">
          Hardware-accelerated execution wrapper combining Gamescope nested micro-compositor, AMD FSR / NIS spatial upscaling, Feral GameMode governor boosting, and MangoHud frame telemetry.
        </p>

        <!-- Presets -->
        <div style="margin-bottom: 20px;">
          <label style="font-weight: 700; font-size: 13px; margin-bottom: 6px; display: block;">Quick Performance Profiles:</label>
          <div style="display: flex; gap: 8px; flex-wrap: wrap;">
            <button class="btn btn-sm" onclick="applyTuningPreset('esports')">Esports Competitive (144Hz FSR)</button>
            <button class="btn btn-secondary btn-sm" onclick="applyTuningPreset('4k_fidelity')">4K Fidelity Upscale</button>
            <button class="btn btn-secondary btn-sm" onclick="applyTuningPreset('power_saver')">Power Saver (60Hz)</button>
            <button class="btn btn-secondary btn-sm" onclick="applyTuningPreset('minimal_overlay')">Minimal HUD Only</button>
          </div>
        </div>

        <div class="grid-2">
          <!-- Left Column: Micro-Compositor & Upscaling -->
          <div style="background: rgba(255,255,255,0.02); padding: 16px; border-radius: 6px; border: 1px solid var(--card-border);">
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 12px; color: var(--primary);">
              Gamescope Micro-Compositor & Upscaling
            </div>

            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
              <input type="checkbox" id="tune-gamescope" checked onchange="updateTuningPreview()">
              <label for="tune-gamescope" style="margin: 0; font-weight: 600;">Enable Gamescope Nested Compositor</label>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px;">
              <div>
                <label style="font-size: 12px; color: var(--fg-subtle);">Internal Render Res:</label>
                <select id="tune-render-res" onchange="updateTuningPreview()" style="margin-top: 4px; padding: 6px 8px; font-size: 13px;">
                  <option value="1280x720">1280 x 720 (720p)</option>
                  <option value="1920x1080" selected>1920 x 1080 (1080p)</option>
                  <option value="2560x1440">2560 x 1440 (1440p)</option>
                </select>
              </div>
              <div>
                <label style="font-size: 12px; color: var(--fg-subtle);">Display Output Res:</label>
                <select id="tune-output-res" onchange="updateTuningPreview()" style="margin-top: 4px; padding: 6px 8px; font-size: 13px;">
                  <option value="1920x1080" selected>1920 x 1080 (1080p)</option>
                  <option value="2560x1440">2560 x 1440 (1440p)</option>
                  <option value="3840x2160">3840 x 2160 (4K UHD)</option>
                </select>
              </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px;">
              <div>
                <label style="font-size: 12px; color: var(--fg-subtle);">Spatial Filter:</label>
                <select id="tune-upscale" onchange="updateTuningPreview()" style="margin-top: 4px; padding: 6px 8px; font-size: 13px;">
                  <option value="fsr" selected>AMD FSR (FidelityFX)</option>
                  <option value="nis">NVIDIA Image Scaling (NIS)</option>
                  <option value="pixel">Integer Pixel Scaling</option>
                  <option value="linear">Bilinear Filtering</option>
                </select>
              </div>
              <div>
                <label style="font-size: 12px; color: var(--fg-subtle);">FSR Sharpness (0-10):</label>
                <input type="number" id="tune-sharpness" min="0" max="10" value="5" onchange="updateTuningPreview()" style="margin-top: 4px; padding: 6px 8px; font-size: 13px;">
              </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
              <div>
                <label style="font-size: 12px; color: var(--fg-subtle);">FPS Cap / Refresh Rate:</label>
                <select id="tune-fps" onchange="updateTuningPreview()" style="margin-top: 4px; padding: 6px 8px; font-size: 13px;">
                  <option value="0">Unlimited (Display Max)</option>
                  <option value="60">60 FPS (V-Sync Standard)</option>
                  <option value="120">120 FPS</option>
                  <option value="144" selected>144 FPS (Esports)</option>
                  <option value="240">240 FPS</option>
                </select>
              </div>
              <div style="display: flex; flex-direction: column; justify-content: center; margin-top: 14px;">
                <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; margin: 0;">
                  <input type="checkbox" id="tune-fullscreen" checked onchange="updateTuningPreview()"> Fullscreen Display
                </label>
              </div>
            </div>
          </div>

          <!-- Right Column: GameMode, MangoHud & Audio -->
          <div style="background: rgba(255,255,255,0.02); padding: 16px; border-radius: 6px; border: 1px solid var(--card-border);">
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 12px; color: var(--primary);">
              System Prioritization & Telemetry
            </div>

            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
              <input type="checkbox" id="tune-gamemode" checked onchange="updateTuningPreview()">
              <div>
                <label for="tune-gamemode" style="margin: 0; font-weight: 600;">Feral GameMode (gamemoderun)</label>
                <p style="font-size: 11px; color: var(--fg-subtle); margin-top: 2px;">Boosts CPU governor to performance, elevates process scheduling priority and GPU power states.</p>
              </div>
            </div>

            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
              <input type="checkbox" id="tune-mangohud" checked onchange="updateTuningPreview()">
              <div>
                <label for="tune-mangohud" style="margin: 0; font-weight: 600;">MangoHud Real-Time Overlay</label>
                <p style="font-size: 11px; color: var(--fg-subtle); margin-top: 2px;">Injected via --mangoapp inside Gamescope or MANGOHUD=1 wrapper outside.</p>
              </div>
            </div>

            <div style="margin-bottom: 12px; padding-left: 24px;">
              <label style="font-size: 12px; color: var(--fg-subtle);">MangoHud Preset Layout:</label>
              <select id="tune-mangohud-preset" onchange="updateTuningPreview()" style="margin-top: 4px; padding: 6px 8px; font-size: 13px;">
                <option value="fps_only">FPS & Frametime Only (Minimal)</option>
                <option value="compact" selected>Compact (FPS, Frametime, CPU, GPU, VRAM)</option>
                <option value="full">Full Extended Diagnostics</option>
              </select>
            </div>

            <div style="display: flex; align-items: center; gap: 10px;">
              <input type="checkbox" id="tune-audio" checked onchange="updateTuningPreview()">
              <div>
                <label for="tune-audio" style="margin: 0; font-weight: 600;">Low-Latency Audio Fast-Path</label>
                <p style="font-size: 11px; color: var(--fg-subtle); margin-top: 2px;">Configures PIPEWIRE_LATENCY="128/48000" and PULSE_LATENCY_MSEC=15 for zero-lag spatial sound.</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Live Command Preview Box -->
        <div style="margin-top: 20px;">
          <div style="font-size: 13px; font-weight: 700; margin-bottom: 6px; display: flex; justify-content: space-between;">
            <span>Generated Acceleration Execution Pipeline:</span>
            <span style="color: var(--primary); font-size: 12px; cursor: pointer;" onclick="navigator.clipboard.writeText(document.getElementById('tuning-cmd-preview').innerText); showAlert('Copied command pipeline to clipboard!', false);">Copy Pipeline Command</span>
          </div>
          <pre id="tuning-cmd-preview" style="background: var(--code-bg); padding: 14px; border-radius: 6px; font-size: 12px; color: var(--accent-green); overflow-x: auto;">gamemoderun gamescope -w 1920 -h 1080 -W 1920 -H 1080 -F fsr -S 5 -U -r 144 -f --mangoapp -- bwrap ... wine app.exe</pre>
        </div>
      </div>
    </section>

    <!-- TAB: RUNNER FLEET -->
    <section id="tab-runners" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Compatibility Runner Fleet & ProtonUp Manager</span>
          <button class="btn btn-secondary btn-sm" onclick="loadRunners()">Refresh Runners</button>
        </div>
        <p style="color: var(--fg-subtle); font-size: 13px; margin-bottom: 16px;">
          Discovers installed Proton and Wine runners across Steam, Lutris, Bottles, and ~/.zcf/runners/, and provides automated installation for upstream GE-Proton releases with cryptographic verification.
        </p>

        <!-- Installed Runners Table -->
        <div style="font-size: 14px; font-weight: 700; margin-bottom: 8px;">Installed Compatibility Runners</div>
        <table style="margin-bottom: 24px;">
          <thead>
            <tr>
              <th>Status</th>
              <th>Runner Name</th>
              <th>Type</th>
              <th>Version</th>
              <th>Capabilities</th>
              <th>Filesystem Path</th>
            </tr>
          </thead>
          <tbody id="runners-local-body">
            <tr><td colspan="6" style="color: var(--fg-subtle);">Scanning local runners...</td></tr>
          </tbody>
        </table>

        <!-- Available Upstream Releases -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <div style="font-size: 14px; font-weight: 700;">Upstream Custom Releases (GE-Proton Feed)</div>
          <button class="btn btn-secondary btn-sm" onclick="loadAvailableRunners()">Check for Updates</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Release Tag</th>
              <th>Size</th>
              <th>Published</th>
              <th>Integrity</th>
              <th style="width: 140px;">Action</th>
            </tr>
          </thead>
          <tbody id="runners-remote-body">
            <tr><td colspan="5" style="color: var(--fg-subtle);">Click "Check for Updates" to fetch available GE-Proton releases...</td></tr>
          </tbody>
        </table>
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

      <div class="card" id="pipeline-topology-card" style="display: none; border-left: 4px solid var(--accent-green);">
        <div class="card-title">
          <span>Compatibility Pipeline Topology & Execution Perimeter</span>
          <span class="badge badge-cyan" id="pipeline-confidence-badge">Confidence: 100%</span>
        </div>
        <p style="color: var(--fg-subtle); font-size: 13px; margin-bottom: 16px;">
          Multi-layer runtime abstraction pipeline for this binary across isolation, binary translation, and host graphics passthrough:
        </p>
        <div style="display: flex; gap: 10px; align-items: stretch; justify-content: space-between; overflow-x: auto; padding: 10px 0;">
          <!-- Node 1 -->
          <div class="topology-node active-node" id="top-node-binary" onclick="selectTopologyNode('binary')" style="flex: 1; min-width: 170px;">
            <div style="font-size: 11px; font-weight: 700; color: var(--fg-subtle); text-transform: uppercase;">1. Target Binary</div>
            <div style="font-size: 14px; font-weight: 800; color: #fff; margin-top: 4px;" id="top-binary-name">Binary</div>
            <div style="font-size: 12px; color: var(--primary); margin-top: 3px;" id="top-binary-format">PE32+ (x86_64)</div>
            <div style="font-size: 11px; color: var(--fg-subtle); margin-top: 5px;" id="top-binary-auth">Header: Authenticode OK</div>
          </div>
          <div style="display: flex; align-items: center; color: var(--primary); font-size: 18px; font-weight: bold;">&rarr;</div>
          <!-- Node 2 -->
          <div class="topology-node" id="top-node-security" onclick="selectTopologyNode('security')" style="flex: 1; min-width: 170px;">
            <div style="font-size: 11px; font-weight: 700; color: var(--fg-subtle); text-transform: uppercase;">2. Security Perimeter</div>
            <div style="font-size: 14px; font-weight: 800; color: #00e676; margin-top: 4px;" id="top-security-status">Bubblewrap Active</div>
            <div style="font-size: 12px; color: var(--fg-subtle); margin-top: 3px;" id="top-security-ns">Namespaces Isolated</div>
            <div style="font-size: 11px; color: var(--fg-subtle); margin-top: 5px;" id="top-security-fs">Strict RO Rootfs</div>
          </div>
          <div style="display: flex; align-items: center; color: var(--primary); font-size: 18px; font-weight: bold;">&rarr;</div>
          <!-- Node 3 -->
          <div class="topology-node" id="top-node-runtime" onclick="selectTopologyNode('runtime')" style="flex: 1; min-width: 170px;">
            <div style="font-size: 11px; font-weight: 700; color: var(--fg-subtle); text-transform: uppercase;">3. Translation Engine</div>
            <div style="font-size: 14px; font-weight: 800; color: var(--primary); margin-top: 4px;" id="top-runtime-name">Proton / Wine</div>
            <div style="font-size: 12px; color: var(--accent-amber); margin-top: 3px;" id="top-runtime-gfx">Direct3D &rarr; Vulkan DXVK</div>
            <div style="font-size: 11px; color: var(--fg-subtle); margin-top: 5px;" id="top-runtime-audio">Audio: PipeWire Fast-Path</div>
          </div>
          <div style="display: flex; align-items: center; color: var(--primary); font-size: 18px; font-weight: bold;">&rarr;</div>
          <!-- Node 4 -->
          <div class="topology-node" id="top-node-host" onclick="selectTopologyNode('host')" style="flex: 1; min-width: 170px;">
            <div style="font-size: 11px; font-weight: 700; color: var(--fg-subtle); text-transform: uppercase;">4. Host Acceleration</div>
            <div style="font-size: 14px; font-weight: 800; color: #fff; margin-top: 4px;" id="top-host-kernel">Linux Kernel</div>
            <div style="font-size: 12px; color: var(--accent-green); margin-top: 3px;" id="top-host-gpu">DRM /renderD128</div>
            <div style="font-size: 11px; color: var(--fg-subtle); margin-top: 5px;" id="top-host-display">Wayland / X11 Session</div>
          </div>
        </div>
        <div id="topology-node-detail" style="margin-top: 14px; padding: 12px; background: var(--code-bg); border: 1px solid var(--card-border); border-radius: 6px; font-size: 13px;">
          Select any pipeline node above to inspect its configuration details.
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
        <div style="display: flex; gap: 6px; margin-bottom: 10px; align-items: center;" id="log-filter-bar">
          <span style="font-size: 12px; font-weight: 600; color: var(--fg-subtle); margin-right: 6px;">Filter Output:</span>
          <button class="filter-btn active" id="filter-all" onclick="filterLogs('ALL')">All Lines</button>
          <button class="filter-btn" id="filter-errors" onclick="filterLogs('ERRORS')">Errors Only</button>
          <button class="filter-btn" id="filter-warnings" onclick="filterLogs('WARNINGS')">Warnings</button>
          <button class="filter-btn" id="filter-wine" onclick="filterLogs('WINE')">Wine/Proton Channels</button>
        </div>
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

      <div class="card" id="prefix-surgery-card" style="display: none; border-top: 3px solid var(--primary); margin-top: 24px;">
        <div class="card-title">
          <span>Prefix Surgery & Component Control: <code id="surgery-prefix-name">prefix</code></span>
          <button class="close-btn" onclick="document.getElementById('prefix-surgery-card').style.display='none'">&times;</button>
        </div>
        <p style="color: var(--fg-subtle); font-size: 13px; margin-bottom: 16px;">
          Storage Path: <code id="surgery-prefix-path">-</code> &bull; Architecture: <strong id="surgery-prefix-arch">-</strong>
        </p>

        <div class="grid-2">
          <!-- Windows Components -->
          <div>
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
              <span>Windows Runtimes & Components</span>
              <button class="btn btn-secondary btn-sm" onclick="refreshPrefixComponents()">Refresh Components</button>
            </div>
            <div id="surgery-components-list" style="display: flex; flex-direction: column; gap: 8px; max-height: 440px; overflow-y: auto; padding-right: 4px;">
              <p style="color: var(--fg-subtle); font-size: 13px;">Loading components...</p>
            </div>
          </div>

          <!-- DLL Overrides -->
          <div>
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 10px;">
              <span>Wine DLL Overrides (WINEDLLOVERRIDES)</span>
            </div>
            <div style="display: flex; gap: 6px; margin-bottom: 12px; align-items: center;">
              <input type="text" id="override-dll-input" placeholder="e.g. d3d11, dxgi" style="flex: 2; margin-top: 0; padding: 7px 10px; font-size: 13px;">
              <select id="override-mode-select" style="flex: 2; margin-top: 0; padding: 7px 10px; font-size: 13px;">
                <option value="native,builtin">native, builtin</option>
                <option value="builtin,native">builtin, native</option>
                <option value="native">native only</option>
                <option value="builtin">builtin only</option>
                <option value="disabled">disabled</option>
              </select>
              <button class="btn btn-sm" onclick="saveDllOverride()" style="margin-top: 0; white-space: nowrap;">Set Override</button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>DLL Library</th>
                  <th>Override Mode</th>
                  <th style="width: 70px;">Action</th>
                </tr>
              </thead>
              <tbody id="surgery-overrides-body">
                <tr><td colspan="3" style="color: var(--fg-subtle);">No custom DLL overrides configured.</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- TIME-MACHINE SNAPSHOTS -->
        <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--card-border);">
          <div style="font-size: 15px; font-weight: 700; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
            <span>Prefix Time-Machine & Rollback Points</span>
            <div style="display: flex; gap: 8px;">
              <input type="text" id="snapshot-label-input" placeholder="Snapshot label (e.g. Pre-Patch v1.2)" style="margin: 0; padding: 6px 10px; font-size: 13px;">
              <button class="btn btn-sm" onclick="createPrefixSnapshot()">Take Snapshot</button>
            </div>
          </div>
          <p style="color: var(--fg-subtle); font-size: 12px; margin-bottom: 12px;">
            Captures atomic registry hives, system configuration, and DLL states for instant zero-loss rollbacks.
          </p>
          <table>
            <thead>
              <tr>
                <th>Snapshot ID</th>
                <th>Label</th>
                <th>Trigger</th>
                <th>Created</th>
                <th>Size</th>
                <th style="width: 140px;">Action</th>
              </tr>
            </thead>
            <tbody id="surgery-snapshots-body">
              <tr><td colspan="6" style="color: var(--fg-subtle);">Select a prefix to load Time-Machine restore points.</td></tr>
            </tbody>
          </table>
        </div>

        <!-- PROCESS MONITOR & SYSTEM TOOLS -->
        <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--card-border);">
          <div style="font-size: 15px; font-weight: 700; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
            <span>Prefix Process Task Manager & Wine Utilities</span>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-secondary btn-sm" onclick="refreshPrefixProcesses()">Refresh Processes</button>
              <button class="btn btn-sm btn-error" onclick="killPrefixProcesses()">Kill wineserver (-k)</button>
              <button class="btn btn-secondary btn-sm" onclick="resetPrefixLocks()">Reset Locks</button>
            </div>
          </div>
          <div style="display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap;">
            <button class="btn btn-secondary btn-sm" onclick="launchWineUtility('winecfg')">Launch winecfg</button>
            <button class="btn btn-secondary btn-sm" onclick="launchWineUtility('regedit')">Launch regedit</button>
            <button class="btn btn-secondary btn-sm" onclick="launchWineUtility('taskmgr')">Launch taskmgr</button>
            <button class="btn btn-secondary btn-sm" onclick="launchWineUtility('control')">Launch control</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>PID</th>
                <th>Process Name</th>
                <th>Memory (RSS)</th>
                <th>Command Line</th>
              </tr>
            </thead>
            <tbody id="surgery-processes-body">
              <tr><td colspan="4" style="color: var(--fg-subtle);">No active processes detected in this prefix.</td></tr>
            </tbody>
          </table>
        </div>

      </div>
    </section>

    <!-- TAB: SAVE GAME VAULT -->
    <section id="tab-vault" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Universal Game Save Vault</span>
          <button class="btn btn-secondary btn-sm" onclick="loadVaultBackups()">Refresh Vault</button>
        </div>
        <p style="color: var(--fg-subtle); font-size: 13px; margin-bottom: 16px;">
          Automatically discovers save directories across Windows user profiles in Wine/Proton prefixes, stores compressed archives with SHA-256 integrity, and allows safe prefix resets and cross-runner save migration.
        </p>

        <!-- Discovery & Backup -->
        <div class="grid-2" style="margin-bottom: 24px;">
          <div style="background: rgba(255,255,255,0.02); padding: 16px; border-radius: 6px; border: 1px solid var(--card-border);">
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 10px;">Discover & Backup Prefix Saves</div>
            <label style="font-size: 12px; color: var(--fg-subtle);">Source Prefix Path:</label>
            <input type="text" id="vault-prefix-input" placeholder="/path/to/prefix or select above" style="margin-top: 4px; padding: 7px 10px; font-size: 13px;">
            <label style="font-size: 12px; color: var(--fg-subtle); margin-top: 8px; display: block;">Game / App Name Filter:</label>
            <input type="text" id="vault-app-input" placeholder="e.g. EldenRing or Cyberpunk2077" style="margin-top: 4px; padding: 7px 10px; font-size: 13px;">
            <div style="display: flex; gap: 8px; margin-top: 12px;">
              <button class="btn btn-secondary btn-sm" onclick="discoverPrefixSaves()">Scan for Saves</button>
              <button class="btn btn-sm" onclick="backupPrefixSaves()">Backup to Vault</button>
            </div>
            <div id="vault-discovery-results" style="margin-top: 12px; font-size: 12px; color: var(--fg-subtle);"></div>
          </div>

          <!-- Stored Backups -->
          <div>
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 10px;">Vault Save Backups</div>
            <table>
              <thead>
                <tr>
                  <th>Vault ID</th>
                  <th>Game Name</th>
                  <th>Size</th>
                  <th>Archived</th>
                  <th style="width: 140px;">Action</th>
                </tr>
              </thead>
              <tbody id="vault-backups-body">
                <tr><td colspan="5" style="color: var(--fg-subtle);">Loading archived saves...</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <!-- TAB 6: DIAGNOSTICS -->
    <section id="tab-diagnostics" class="tab-content">
      <div class="card">
        <div class="card-title">Automated Crash Troubleshooter & Root-Cause Remediation</div>
        <p style="color: var(--fg-subtle); margin-bottom: 10px;">Paste runtime stderr, Wine logs, or dynamic loader errors below for automated failure signature classification and package install instructions:</p>
        <textarea id="diag-log" rows="6" placeholder="err:module:import_dll Library D3DX9_43.dll not found&#10;error while loading shared libraries: libvulkan.so.1: cannot open shared object file"></textarea>
        <div style="display: flex; gap: 10px; margin-top: 10px;">
          <button class="btn" onclick="analyzeLog()">Diagnose Failure Signatures</button>
          <button class="btn btn-secondary" onclick="generateHealingPrescription()">Synthesize Healing Prescription</button>
        </div>
      </div>

      <!-- HEALING PRESCRIPTION CARD -->
      <div class="card" id="healing-rx-card" style="display: none; border-left: 4px solid var(--accent-green);">
        <div class="card-title">
          <span>Autonomous Healing Prescription</span>
          <span class="badge badge-green" id="rx-status-badge">Prescription Synthesized</span>
        </div>
        <div id="rx-content" style="margin-bottom: 16px; font-size: 13px;"></div>
        <div style="display: flex; gap: 10px; align-items: center;">
          <input type="text" id="rx-prefix-input" placeholder="Target prefix path to apply fix" style="flex: 2; margin: 0; padding: 7px 10px; font-size: 13px;">
          <button class="btn btn-sm" onclick="applyHealingPrescription(false)">Apply Prescription & Auto-Heal</button>
          <button class="btn btn-secondary btn-sm" onclick="applyHealingPrescription(true)">Dry-Run Simulation</button>
        </div>
      </div>

      <div class="card" id="diag-result-card" style="display: none;">
        <div class="card-title">
          <span>Diagnostic Findings & Root-Cause Remediations</span>
          <span id="diag-summary-badge" class="badge badge-amber">Analysis Ready</span>
        </div>
        <div class="grid-4" id="diag-stats-grid" style="margin-bottom: 16px;">
          <div class="stat-box">
            <div class="stat-label">Critical Faults</div>
            <div class="stat-value" id="diag-stat-critical" style="color: var(--accent-red);">0</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Missing DLLs</div>
            <div class="stat-value" id="diag-stat-dlls" style="color: var(--accent-amber);">0</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Graphics/Vulkan</div>
            <div class="stat-value" id="diag-stat-vulkan" style="color: var(--primary);">0</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Remediations Available</div>
            <div class="stat-value" id="diag-stat-remediations" style="color: var(--accent-green);">0</div>
          </div>
        </div>
        <div id="diag-timeline" style="margin-bottom: 16px;"></div>
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

        window.currentHostKernel = envRes.kernel_version || '';
        window.currentHostDisplay = envRes.display_server || '';

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
              '<td><code>' + escapeHtml(p.prefix_path) + '</code> ' +
              '<button class="btn btn-secondary btn-sm" style="margin-left: 8px;" onclick="selectPrefixForSurgery(\'' + escapeHtml(p.prefix_path).replace(/\\/g, '\\\\') + '\', \'' + escapeHtml(p.app_name) + '\', \'' + escapeHtml(p.architecture) + '\')">Surgery / Components</button></td>';
            pTable.appendChild(row);
          }});
        }}

        loadHistory();
        loadReadinessAudit();

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

    let lastInspectedApp = null;
    let currentPipelineData = null;
    let currentRawLogLines = [];
    let selectedPrefixPath = '';

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
        lastInspectedApp = data;
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

        renderPipelineTopology(data, lastInspectedApp);
      }} catch (err) {{
        showAlert('Planning error: ' + err.message, true);
      }}
    }}

    function renderPipelineTopology(planData, appData) {{
      currentPipelineData = {{ plan: planData, app: appData }};
      const card = document.getElementById('pipeline-topology-card');
      if (!card) return;

      const confBadge = document.getElementById('pipeline-confidence-badge');
      if (confBadge) confBadge.textContent = 'Confidence: ' + Math.round((planData.confidence_score || 0) * 100) + '%';

      const binaryName = (appData && appData.file_name) || (planData && planData.target_application) || 'Target Binary';
      const formatStr = ((appData && appData.format) || (planData && planData.target_format) || 'PE').toUpperCase() + ' (' + ((appData && appData.architecture) || (planData && planData.target_architecture) || 'x86_64') + ')';
      document.getElementById('top-binary-name').textContent = binaryName;
      document.getElementById('top-binary-format').textContent = formatStr;
      const isSigned = appData && appData.authenticode && appData.authenticode.is_signed;
      document.getElementById('top-binary-auth').textContent = isSigned ? 'Authenticode: Signed' : 'Authenticode: Unsigned';

      const isSandbox = Boolean(planData.sandbox_active !== false);
      const secStatus = document.getElementById('top-security-status');
      if (secStatus) {{
        secStatus.textContent = isSandbox ? 'Bubblewrap Active' : 'Unconfined Process';
        secStatus.style.color = isSandbox ? '#00e676' : 'var(--accent-amber)';
      }}
      document.getElementById('top-security-ns').textContent = isSandbox ? 'Namespaces Isolated' : 'Host Direct Execution';
      document.getElementById('top-security-fs').textContent = isSandbox ? 'Strict RO Rootfs' : 'Unrestricted Host Root';

      const runtimeName = planData.selected_runtime_name || 'Direct Native';
      document.getElementById('top-runtime-name').textContent = runtimeName;
      const isPE = (appData && appData.format === 'pe') || (planData && planData.target_format === 'pe');
      document.getElementById('top-runtime-gfx').textContent = isPE ? 'Direct3D \u2192 Vulkan DXVK' : 'Native Host Syscalls';
      document.getElementById('top-runtime-audio').textContent = 'Audio: PipeWire Fast-Path';

      document.getElementById('top-host-kernel').textContent = window.currentHostKernel || 'Host Kernel';
      document.getElementById('top-host-gpu').textContent = 'DRM /renderD128 Node';
      document.getElementById('top-host-display').textContent = 'Display: ' + (window.currentHostDisplay || 'Wayland / X11');

      card.style.display = 'block';
      selectTopologyNode('binary');
    }}

    function selectTopologyNode(nodeKey) {{
      document.querySelectorAll('.topology-node').forEach(n => n.classList.remove('active-node'));
      const activeEl = document.getElementById('top-node-' + nodeKey);
      if (activeEl) activeEl.classList.add('active-node');

      const detail = document.getElementById('topology-node-detail');
      if (!detail) return;

      const p = currentPipelineData ? currentPipelineData.plan : null;
      const a = currentPipelineData ? currentPipelineData.app : null;

      if (nodeKey === 'binary') {{
        detail.innerHTML = 
          '<strong>[Stage 1: Target Executable Binary]</strong>' +
          '<div style="margin-top: 6px; color: var(--fg-subtle);">' +
            'File: <code>' + escapeHtml(a ? a.file_name : 'Target') + '</code> &bull; ' +
            'Format: <strong>' + escapeHtml(a ? a.format : 'PE') + '</strong> &bull; ' +
            'Architecture: <strong>' + escapeHtml(a ? a.architecture : 'x86_64') + '</strong> &bull; ' +
            'Subsystem: <strong>' + escapeHtml(a ? (a.subsystem || 'Windows GUI') : 'N/A') + '</strong>' +
          '</div>';
      }} else if (nodeKey === 'security') {{
        detail.innerHTML = 
          '<strong>[Stage 2: Bubblewrap Security Perimeter]</strong>' +
          '<div style="margin-top: 6px; color: var(--fg-subtle);">' +
            'Containment: <strong>Unprivileged Linux User Namespaces (bwrap)</strong> &bull; ' +
            'Network Policy: <strong>' + (p && p.network_isolated ? 'BLOCKED (Air-Gapped Sandbox)' : 'Permitted') + '</strong> &bull; ' +
            'Mount Policy: <strong>Strict read-only host bindings with ephemeral disposable tmpfs</strong>' +
          '</div>';
      }} else if (nodeKey === 'runtime') {{
        detail.innerHTML = 
          '<strong>[Stage 3: Translation & Compatibility Engine]</strong>' +
          '<div style="margin-top: 6px; color: var(--fg-subtle);">' +
            'Selected Runtime: <strong>' + escapeHtml(p ? p.selected_runtime_name : 'N/A') + '</strong> &bull; ' +
            'Execution Mode: <strong>' + escapeHtml((p ? p.execution_mode : '').toUpperCase()) + '</strong> &bull; ' +
            'Graphics Translation: <strong>DXVK / VKD3D (Direct3D \u2192 Vulkan 1.3 SPIR-V bytecode)</strong>' +
          '</div>';
      }} else if (nodeKey === 'host') {{
        detail.innerHTML = 
          '<strong>[Stage 4: Native Host Kernel & GPU Passthrough]</strong>' +
          '<div style="margin-top: 6px; color: var(--fg-subtle);">' +
            'Kernel: <strong>' + escapeHtml(window.currentHostKernel || 'Linux Kernel') + '</strong> &bull; ' +
            'Display Session: <strong>' + escapeHtml(window.currentHostDisplay || 'Wayland / X11') + '</strong> &bull; ' +
            'GPU Acceleration: <strong>Direct Rendering Infrastructure (/dev/dri/renderD128)</strong>' +
          '</div>';
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

        const fullLog = (data.stdout || '') + (data.stderr ? '\nError:\n' + data.stderr : '') + (data.reasoning ? '\nReason:\n' + data.reasoning : '');
        currentRawLogLines = fullLog.split('\n');
        filterLogs('ALL');

        card.style.display = 'block';
        if (record) loadTelemetry();
        loadHistory();
      }} catch (err) {{
        showAlert('Test execution error: ' + err.message, true);
      }}
    }}

    function filterLogs(mode) {{
      document.querySelectorAll('#log-filter-bar .filter-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.getElementById('filter-' + mode.toLowerCase());
      if (activeBtn) activeBtn.classList.add('active');

      const outPre = document.getElementById('test-output');
      if (!outPre) return;

      if (mode === 'ALL') {{
        outPre.textContent = currentRawLogLines.join('\n');
      }} else if (mode === 'ERRORS') {{
        const filtered = currentRawLogLines.filter(l => {{
          const s = l.toLowerCase();
          return s.includes('err:') || s.includes('error') || s.includes('fatal') || s.includes('failed') || s.includes('exception');
        }});
        outPre.textContent = filtered.length > 0 ? filtered.join('\n') : '(No error lines detected in output)';
      }} else if (mode === 'WARNINGS') {{
        const filtered = currentRawLogLines.filter(l => {{
          const s = l.toLowerCase();
          return s.includes('warn:') || s.includes('warning') || s.includes('fixme:');
        }});
        outPre.textContent = filtered.length > 0 ? filtered.join('\n') : '(No warning lines detected in output)';
      }} else if (mode === 'WINE') {{
        const filtered = currentRawLogLines.filter(l => {{
          const s = l.toLowerCase();
          return s.includes('wine:') || s.includes('proton:') || s.includes('err:') || s.includes('fixme:') || s.includes('trace:');
        }});
        outPre.textContent = filtered.length > 0 ? filtered.join('\n') : '(No Wine/Proton log lines detected in output)';
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

    async function loadReadinessAudit() {{
      try {{
        const res = await fetch('/api/readiness');
        if (!res.ok) return;
        const audit = await res.json();
        const score = Number(audit.score || 0);
        const grade = audit.grade || 'UNKNOWN';

        const circle = document.getElementById('readiness-gauge-circle');
        if (circle) circle.setAttribute('stroke-dasharray', score + ', 100');
        const valElem = document.getElementById('readiness-gauge-val');
        if (valElem) valElem.textContent = score + '%';
        const badgeElem = document.getElementById('readiness-grade-badge');
        if (badgeElem) {{
          badgeElem.textContent = grade;
          badgeElem.className = 'badge ' + (score >= 90 ? 'badge-green' : (score >= 70 ? 'badge-cyan' : (score >= 45 ? 'badge-amber' : 'badge-red')));
        }}

        const titleElem = document.getElementById('readiness-summary-title');
        if (titleElem) titleElem.textContent = 'System Status: ' + grade + ' (' + score + '% Readiness Index)';
        const descElem = document.getElementById('readiness-summary-desc');
        if (descElem) descElem.textContent = audit.summary || '';

        const tbody = document.getElementById('readiness-table-body');
        if (tbody && audit.checks) {{
          tbody.innerHTML = '';
          audit.checks.forEach(c => {{
            const row = document.createElement('tr');
            let badgeClass = 'badge-red';
            if (c.status === 'PASS') badgeClass = 'badge-green';
            else if (c.status === 'WARN') badgeClass = 'badge-amber';

            let fixHtml = '<span style="color: var(--fg-subtle);">&mdash;</span>';
            if (c.remediation) {{
              fixHtml = '<code style="background: rgba(0,229,255,0.1); padding: 2px 6px; border-radius: 4px; color: var(--primary); cursor: pointer;" title="Click to copy" onclick="navigator.clipboard.writeText(this.innerText); showAlert(\'Copied remediation fix to clipboard!\', false);">' + escapeHtml(c.remediation) + '</code>';
            }}

            row.innerHTML = 
              '<td><span class="badge ' + badgeClass + '">' + escapeHtml(c.status) + '</span></td>' +
              '<td><strong>' + escapeHtml(c.name) + '</strong></td>' +
              '<td>' + escapeHtml(c.score_points) + '/' + escapeHtml(c.max_points) + '</td>' +
              '<td style="color: var(--fg-subtle); font-size: 12px;">' + escapeHtml(c.details) + '</td>' +
              '<td>' + fixHtml + '</td>';
            tbody.appendChild(row);
          }});
        }}
      }} catch (err) {{
        console.error('Failed to load readiness audit:', err);
      }}
    }}

    async function selectPrefixForSurgery(prefixPath, appName, arch) {{
      selectedPrefixPath = prefixPath;
      document.getElementById('surgery-prefix-name').textContent = appName;
      document.getElementById('surgery-prefix-path').textContent = prefixPath;
      document.getElementById('surgery-prefix-arch').textContent = arch;
      document.getElementById('prefix-surgery-card').style.display = 'block';
      document.getElementById('prefix-surgery-card').scrollIntoView({{ behavior: 'smooth' }});

      await Promise.all([
        refreshPrefixComponents(),
        refreshPrefixOverrides(),
        refreshPrefixSnapshots(),
        refreshPrefixProcesses()
      ]);
    }}

    async function refreshPrefixComponents() {{
      if (!selectedPrefixPath) return;
      const listContainer = document.getElementById('surgery-components-list');
      listContainer.innerHTML = '<p style="color: var(--fg-subtle); font-size: 13px;">Scanning prefix components...</p>';

      try {{
        const res = await fetch('/api/components?prefix_path=' + encodeURIComponent(selectedPrefixPath));
        if (!res.ok) throw new Error('Failed to fetch components');
        const comps = await res.json();
        listContainer.innerHTML = '';

        comps.forEach(c => {{
          const item = document.createElement('div');
          item.className = 'component-row';
          const isInst = Boolean(c.installed);
          
          let actionBtn = isInst 
            ? '<span class="badge badge-green">Installed (Verified)</span>'
            : '<button class="btn btn-sm" onclick="installPrefixComponent(\'' + escapeHtml(c.key) + '\', this)">Install into Prefix</button>';

          item.innerHTML = 
            '<div>' +
              '<div style="font-weight: 700; font-size: 13px; color: #fff;">' + escapeHtml(c.name) + ' (<code>' + escapeHtml(c.key) + '</code>)</div>' +
              '<div style="color: var(--fg-subtle); font-size: 12px; margin-top: 2px;">' + escapeHtml(c.description) + '</div>' +
            '</div>' +
            '<div style="flex-shrink: 0;">' + actionBtn + '</div>';
          listContainer.appendChild(item);
        }});
      }} catch (err) {{
        listContainer.innerHTML = '<p style="color: var(--accent-red); font-size: 13px;">Error loading components: ' + escapeHtml(err.message) + '</p>';
      }}
    }}

    async function installPrefixComponent(compKey, btnElem) {{
      if (!selectedPrefixPath) return showAlert('No prefix selected.');
      if (btnElem) {{
        btnElem.disabled = true;
        btnElem.textContent = 'Installing...';
      }}
      try {{
        const res = await fetch('/api/components/install', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath, component_key: compKey }})
        }});
        const data = await res.json();
        if (!res.ok || !data.success) {{
          throw new Error(data.error || 'Component installation failed');
        }}
        showAlert('Successfully installed component: ' + data.component_name, false);
        refreshPrefixComponents();
      }} catch (err) {{
        showAlert('Component install error: ' + err.message, true);
        if (btnElem) {{
          btnElem.disabled = false;
          btnElem.textContent = 'Install into Prefix';
        }}
      }}
    }}

    async function refreshPrefixOverrides() {{
      if (!selectedPrefixPath) return;
      const tbody = document.getElementById('surgery-overrides-body');
      tbody.innerHTML = '<tr><td colspan="3" style="color: var(--fg-subtle);">Reading DLL overrides...</td></tr>';

      try {{
        const res = await fetch('/api/prefixes/overrides?prefix_path=' + encodeURIComponent(selectedPrefixPath));
        if (!res.ok) throw new Error('Failed to fetch overrides');
        const data = await res.json();
        const overrides = data.overrides || {{}};
        const keys = Object.keys(overrides);

        tbody.innerHTML = '';
        if (keys.length === 0) {{
          tbody.innerHTML = '<tr><td colspan="3" style="color: var(--fg-subtle);">No custom DLL overrides configured for this prefix.</td></tr>';
          return;
        }}

        keys.forEach(dll => {{
          const row = document.createElement('tr');
          row.innerHTML = 
            '<td><code>' + escapeHtml(dll) + '.dll</code></td>' +
            '<td><span class="badge badge-cyan">' + escapeHtml(overrides[dll]) + '</span></td>' +
            '<td><button class="btn btn-danger btn-sm" onclick="removeDllOverride(\'' + escapeHtml(dll) + '\')">Remove</button></td>';
          tbody.appendChild(row);
        }});
      }} catch (err) {{
        tbody.innerHTML = '<tr><td colspan="3" style="color: var(--accent-red);">Error: ' + escapeHtml(err.message) + '</td></tr>';
      }}
    }}

    async function saveDllOverride() {{
      if (!selectedPrefixPath) return showAlert('No prefix selected.');
      const dll = document.getElementById('override-dll-input').value.trim();
      const mode = document.getElementById('override-mode-select').value;
      if (!dll) return showAlert('Please enter a DLL name (e.g. d3d11).');

      try {{
        const res = await fetch('/api/prefixes/overrides', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath, dll_name: dll, mode: mode, action: 'set' }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to set override');
        document.getElementById('override-dll-input').value = '';
        showAlert('Configured DLL override for ' + dll + ': ' + mode, false);
        refreshPrefixOverrides();
      }} catch (err) {{
        showAlert('Override error: ' + err.message, true);
      }}
    }}

    async function removeDllOverride(dll) {{
      if (!selectedPrefixPath) return showAlert('No prefix selected.');
      try {{
        const res = await fetch('/api/prefixes/overrides', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath, dll_name: dll, action: 'remove' }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to remove override');
        showAlert('Removed DLL override for ' + dll, false);
        refreshPrefixOverrides();
      }} catch (err) {{
        showAlert('Override removal error: ' + err.message, true);
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
        const timeline = document.getElementById('diag-timeline');
        const summaryBadge = document.getElementById('diag-summary-badge');
        container.innerHTML = '';
        timeline.innerHTML = '';

        const events = data.events || [];
        let critCount = 0;
        let dllCount = 0;
        let vulkanCount = 0;

        events.forEach(ev => {{
          const sig = (ev.signature || '').toLowerCase();
          if (sig.includes('crash') || sig.includes('fault') || sig.includes('abort') || sig.includes('segv')) critCount++;
          if (sig.includes('dll') || sig.includes('library') || sig.includes('module')) dllCount++;
          if (sig.includes('vulkan') || sig.includes('dxvk') || sig.includes('d3d') || sig.includes('gpu')) vulkanCount++;
        }});

        document.getElementById('diag-stat-critical').textContent = critCount;
        document.getElementById('diag-stat-dlls').textContent = dllCount;
        document.getElementById('diag-stat-vulkan').textContent = vulkanCount;
        document.getElementById('diag-stat-remediations').textContent = events.length;

        if (events.length === 0) {{
          summaryBadge.className = 'badge badge-green';
          summaryBadge.textContent = 'Clean Log (No Signatures)';
          container.innerHTML = '<p style="color: var(--accent-green);">No known fatal crash signatures detected. Application log appears clean.</p>';
        }} else {{
          summaryBadge.className = 'badge badge-red';
          summaryBadge.textContent = events.length + ' Fault Signatures Detected';

          let tlHtml = '<div style="font-size: 13px; font-weight: 700; margin-bottom: 10px; color: var(--fg-subtle);">DIAGNOSTIC EVENT SEQUENCE & ROOT-CAUSE TIMELINE:</div>';
          events.forEach((ev, idx) => {{
            const isCrit = (ev.confidence || 0) >= 0.8;
            const dotColor = isCrit ? 'var(--accent-red)' : 'var(--accent-amber)';
            tlHtml += 
              '<div class="timeline-step" style="display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-start;">' +
                '<div style="width: 10px; height: 10px; border-radius: 50%; background: ' + dotColor + '; margin-top: 6px; flex-shrink: 0;"></div>' +
                '<div style="background: var(--code-bg); border: 1px solid var(--card-border); border-radius: 6px; padding: 12px; flex: 1;">' +
                  '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">' +
                    '<strong style="color: ' + dotColor + ';">[' + (idx + 1) + '] ' + escapeHtml(ev.signature) + '</strong>' +
                    '<span class="badge ' + (isCrit ? 'badge-red' : 'badge-amber') + '">Confidence: ' + Math.round((ev.confidence || 0) * 100) + '%</span>' +
                  '</div>' +
                  '<p style="color: var(--fg-subtle); font-size: 13px;">' + escapeHtml(ev.root_cause) + '</p>' +
                  '<div style="margin-top: 8px; font-size: 13px; color: var(--primary);">' +
                    '<strong>Remediation:</strong> <code style="background: rgba(0,229,255,0.1); padding: 2px 6px; border-radius: 4px; cursor: pointer;" title="Click to copy" onclick="navigator.clipboard.writeText(this.innerText); showAlert(\'Copied remediation to clipboard!\', false);">' + escapeHtml(ev.remediation) + '</code>' +
                  '</div>' +
                '</div>' +
              '</div>';
          }});
          timeline.innerHTML = tlHtml;
        }}

        card.style.display = 'block';
      }} catch (err) {{
        showAlert('Diagnostic error: ' + err.message, true);
      }}
    }}

    function applyTuningPreset(presetName) {{
      if (presetName === 'esports') {{
        document.getElementById('tune-gamescope').checked = true;
        document.getElementById('tune-render-res').value = '1920x1080';
        document.getElementById('tune-output-res').value = '1920x1080';
        document.getElementById('tune-upscale').value = 'fsr';
        document.getElementById('tune-sharpness').value = 5;
        document.getElementById('tune-fps').value = '144';
        document.getElementById('tune-gamemode').checked = true;
        document.getElementById('tune-mangohud').checked = true;
        document.getElementById('tune-mangohud-preset').value = 'compact';
      }} else if (presetName === '4k_fidelity') {{
        document.getElementById('tune-gamescope').checked = true;
        document.getElementById('tune-render-res').value = '1920x1080';
        document.getElementById('tune-output-res').value = '3840x2160';
        document.getElementById('tune-upscale').value = 'fsr';
        document.getElementById('tune-sharpness').value = 7;
        document.getElementById('tune-fps').value = '0';
        document.getElementById('tune-gamemode').checked = true;
        document.getElementById('tune-mangohud').checked = false;
      }} else if (presetName === 'power_saver') {{
        document.getElementById('tune-gamescope').checked = true;
        document.getElementById('tune-render-res').value = '1280x720';
        document.getElementById('tune-output-res').value = '1920x1080';
        document.getElementById('tune-upscale').value = 'fsr';
        document.getElementById('tune-sharpness').value = 4;
        document.getElementById('tune-fps').value = '60';
        document.getElementById('tune-gamemode').checked = false;
        document.getElementById('tune-mangohud').checked = false;
      }} else if (presetName === 'minimal_overlay') {{
        document.getElementById('tune-gamescope').checked = false;
        document.getElementById('tune-gamemode').checked = false;
        document.getElementById('tune-mangohud').checked = true;
        document.getElementById('tune-mangohud-preset').value = 'fps_only';
      }}
      updateTuningPreview();
      showAlert('Applied ' + presetName + ' tuning profile', false);
    }}

    async function updateTuningPreview() {{
      const gs = document.getElementById('tune-gamescope').checked;
      const gm = document.getElementById('tune-gamemode').checked;
      const mh = document.getElementById('tune-mangohud').checked;
      const [rw, rh] = document.getElementById('tune-render-res').value.split('x').map(Number);
      const [ow, oh] = document.getElementById('tune-output-res').value.split('x').map(Number);
      const up = document.getElementById('tune-upscale').value;
      const sh = Number(document.getElementById('tune-sharpness').value);
      const fps = Number(document.getElementById('tune-fps').value);
      const fs = document.getElementById('tune-fullscreen').checked;
      const mPreset = document.getElementById('tune-mangohud-preset').value;

      const tuningObj = {{
        enabled: gs || gm || mh,
        use_gamescope: gs,
        use_gamemode: gm,
        use_mangohud: mh,
        gamescope_render_res: [rw, rh],
        gamescope_output_res: [ow, oh],
        upscaling_filter: up,
        fsr_sharpness: sh,
        fps_limit: fps > 0 ? fps : null,
        fullscreen: fs,
        mangohud_preset: mPreset
      }};

      try {{
        const res = await fetch('/api/tuning/preview', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ tuning: tuningObj, command: ['bwrap', '...', 'wine', 'app.exe'] }})
        }});
        if (res.ok) {{
          const data = await res.json();
          document.getElementById('tuning-cmd-preview').textContent = data.command.join(' ');
        }}
      }} catch (e) {{
        console.error('Preview error', e);
      }}
    }}

    async function loadRunners() {{
      try {{
        const res = await fetch('/api/runners');
        if (!res.ok) throw new Error('Failed to load local runners');
        const runners = await res.json();
        const tbody = document.getElementById('runners-local-body');
        tbody.innerHTML = '';
        if (!runners.length) {{
          tbody.innerHTML = '<tr><td colspan="6" style="color: var(--fg-subtle);">No runners found.</td></tr>';
          return;
        }}
        runners.forEach(r => {{
          const row = document.createElement('tr');
          const isSys = r.is_system;
          row.innerHTML =
            '<td><span class="badge ' + (isSys ? 'badge-amber' : 'badge-green') + '">' + (isSys ? 'SYSTEM' : 'CUSTOM') + '</span></td>' +
            '<td><strong>' + escapeHtml(r.name) + '</strong></td>' +
            '<td>' + escapeHtml(r.runner_type) + '</td>' +
            '<td><code>' + escapeHtml(r.version) + '</code></td>' +
            '<td>' + (r.capabilities || []).map(c => '<span class="badge badge-cyan" style="font-size: 10px; margin-right: 4px;">' + escapeHtml(c) + '</span>').join('') + '</td>' +
            '<td style="font-size: 11px; color: var(--fg-subtle);">' + escapeHtml(r.path) + '</td>';
          tbody.appendChild(row);
        }});
      }} catch (e) {{
        showAlert('Error loading runners: ' + e.message, true);
      }}
    }}

    async function loadAvailableRunners() {{
      const tbody = document.getElementById('runners-remote-body');
      tbody.innerHTML = '<tr><td colspan="5" style="color: var(--fg-subtle);">Fetching latest GE-Proton releases...</td></tr>';
      try {{
        const res = await fetch('/api/runners/available');
        if (!res.ok) throw new Error('Failed to fetch remote releases');
        const releases = await res.json();
        tbody.innerHTML = '';
        releases.forEach(rel => {{
          const row = document.createElement('tr');
          const szMb = rel.size_bytes ? (rel.size_bytes / (1024 * 1024)).toFixed(1) + ' MB' : '-';
          const pubDate = (rel.published_at || '').substring(0, 10);
          row.innerHTML =
            '<td><strong>' + escapeHtml(rel.tag_name) + '</strong></td>' +
            '<td>' + szMb + '</td>' +
            '<td>' + pubDate + '</td>' +
            '<td><span class="badge badge-green">SHA-512 Signed</span></td>' +
            '<td><button class="btn btn-sm" onclick="installRemoteRunner(\'' + escapeHtml(rel.tag_name) + '\', this)">Install Runner</button></td>';
          tbody.appendChild(row);
        }});
      }} catch (e) {{
        tbody.innerHTML = '<tr><td colspan="5" style="color: var(--accent-red);">Failed to fetch upstream releases: ' + escapeHtml(e.message) + '</td></tr>';
      }}
    }}

    async function installRemoteRunner(tagName, btnElem) {{
      if (btnElem) {{
        btnElem.disabled = true;
        btnElem.textContent = 'Installing...';
      }}
      try {{
        const res = await fetch('/api/runners/install', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ archive_or_tag: tagName }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Install failed');
        showAlert('Runner ' + tagName + ' installed successfully!', false);
        loadRunners();
      }} catch (e) {{
        showAlert('Runner install failed: ' + e.message, true);
      }} finally {{
        if (btnElem) {{
          btnElem.disabled = false;
          btnElem.textContent = 'Install Runner';
        }}
      }}
    }}

    async function refreshPrefixSnapshots() {{
      if (!selectedPrefixPath) return;
      const tbody = document.getElementById('surgery-snapshots-body');
      tbody.innerHTML = '<tr><td colspan="6" style="color: var(--fg-subtle);">Loading snapshots...</td></tr>';
      try {{
        const res = await fetch('/api/snapshots?prefix_path=' + encodeURIComponent(selectedPrefixPath));
        if (!res.ok) throw new Error('Failed to fetch snapshots');
        const snaps = await res.json();
        tbody.innerHTML = '';
        if (!snaps.length) {{
          tbody.innerHTML = '<tr><td colspan="6" style="color: var(--fg-subtle);">No restore points created for this prefix.</td></tr>';
          return;
        }}
        snaps.forEach(s => {{
          const row = document.createElement('tr');
          const szKb = (s.size_bytes / 1024).toFixed(1) + ' KB';
          const dt = (s.created_at || '').substring(0, 19).replace('T', ' ');
          row.innerHTML =
            '<td><code>' + escapeHtml(s.id) + '</code></td>' +
            '<td><strong>' + escapeHtml(s.label) + '</strong></td>' +
            '<td><span class="badge badge-cyan">' + escapeHtml(s.trigger) + '</span></td>' +
            '<td>' + dt + '</td>' +
            '<td>' + szKb + '</td>' +
            '<td>' +
              '<button class="btn btn-sm btn-secondary" onclick="restorePrefixSnapshot(\'' + escapeHtml(s.id) + '\')">Rollback</button> ' +
              '<button class="btn btn-sm btn-error" onclick="deletePrefixSnapshot(\'' + escapeHtml(s.id) + '\')">&times;</button>' +
            '</td>';
          tbody.appendChild(row);
        }});
      }} catch (e) {{
        tbody.innerHTML = '<tr><td colspan="6" style="color: var(--accent-red);">' + escapeHtml(e.message) + '</td></tr>';
      }}
    }}

    async function createPrefixSnapshot() {{
      if (!selectedPrefixPath) return showAlert('No prefix selected.', true);
      const label = document.getElementById('snapshot-label-input').value.trim() || 'Manual Snapshot';
      try {{
        const res = await fetch('/api/snapshots/create', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath, label: label }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Snapshot failed');
        showAlert('Snapshot ' + data.snapshot.id + ' captured!', false);
        document.getElementById('snapshot-label-input').value = '';
        refreshPrefixSnapshots();
      }} catch (e) {{
        showAlert('Failed to create snapshot: ' + e.message, true);
      }}
    }}

    async function restorePrefixSnapshot(snapId) {{
      if (!confirm('Rollback prefix to snapshot ' + snapId + '? Current modifications will be reverted.')) return;
      try {{
        const res = await fetch('/api/snapshots/restore', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath, snapshot_id: snapId }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Restore failed');
        showAlert('Successfully rolled back to snapshot ' + snapId, false);
        refreshPrefixComponents();
        refreshPrefixOverrides();
        refreshPrefixSnapshots();
      }} catch (e) {{
        showAlert('Rollback failed: ' + e.message, true);
      }}
    }}

    async function deletePrefixSnapshot(snapId) {{
      if (!confirm('Delete snapshot ' + snapId + '?')) return;
      try {{
        const res = await fetch('/api/snapshots/delete', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath, snapshot_id: snapId }})
        }});
        if (!res.ok) throw new Error('Deletion failed');
        showAlert('Deleted snapshot ' + snapId, false);
        refreshPrefixSnapshots();
      }} catch (e) {{
        showAlert('Failed to delete snapshot: ' + e.message, true);
      }}
    }}

    async function refreshPrefixProcesses() {{
      if (!selectedPrefixPath) return;
      const tbody = document.getElementById('surgery-processes-body');
      tbody.innerHTML = '<tr><td colspan="4" style="color: var(--fg-subtle);">Querying active prefix processes...</td></tr>';
      try {{
        const res = await fetch('/api/taskmgr/processes?prefix_path=' + encodeURIComponent(selectedPrefixPath));
        if (!res.ok) throw new Error('Failed to query processes');
        const procs = await res.json();
        tbody.innerHTML = '';
        if (!procs.length) {{
          tbody.innerHTML = '<tr><td colspan="4" style="color: var(--fg-subtle);">No active processes running in this prefix.</td></tr>';
          return;
        }}
        procs.forEach(p => {{
          const row = document.createElement('tr');
          row.innerHTML =
            '<td><code>' + p.pid + '</code></td>' +
            '<td><strong>' + escapeHtml(p.name) + '</strong></td>' +
            '<td>' + p.rss_mb + ' MB</td>' +
            '<td style="font-size: 11px; color: var(--fg-subtle);">' + escapeHtml(p.cmdline) + '</td>';
          tbody.appendChild(row);
        }});
      }} catch (e) {{
        tbody.innerHTML = '<tr><td colspan="4" style="color: var(--accent-red);">' + escapeHtml(e.message) + '</td></tr>';
      }}
    }}

    async function killPrefixProcesses() {{
      if (!selectedPrefixPath) return showAlert('No prefix selected.', true);
      try {{
        const res = await fetch('/api/taskmgr/kill', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Kill failed');
        showAlert('Terminated wineserver and prefix processes.', false);
        refreshPrefixProcesses();
      }} catch (e) {{
        showAlert('Failed to kill processes: ' + e.message, true);
      }}
    }}

    async function resetPrefixLocks() {{
      if (!selectedPrefixPath) return showAlert('No prefix selected.', true);
      try {{
        const res = await fetch('/api/taskmgr/reset-locks', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Reset locks failed');
        showAlert('Reset prefix locks: removed ' + (data.removed_locks ? data.removed_locks.length : 0) + ' locks', false);
      }} catch (e) {{
        showAlert('Failed to reset locks: ' + e.message, true);
      }}
    }}

    async function launchWineUtility(tool) {{
      if (!selectedPrefixPath) return showAlert('No prefix selected.', true);
      try {{
        const res = await fetch('/api/taskmgr/launch', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: selectedPrefixPath, tool: tool }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Launch failed');
        showAlert('Launched ' + tool + ' in prefix (PID: ' + (data.result ? data.result.pid : '-') + ')', false);
      }} catch (e) {{
        showAlert('Failed to launch ' + tool + ': ' + e.message, true);
      }}
    }}

    async function loadVaultBackups() {{
      const tbody = document.getElementById('vault-backups-body');
      tbody.innerHTML = '<tr><td colspan="5" style="color: var(--fg-subtle);">Loading Vault backups...</td></tr>';
      try {{
        const res = await fetch('/api/vault/backups');
        if (!res.ok) throw new Error('Failed to load vault');
        const backups = await res.json();
        tbody.innerHTML = '';
        if (!backups.length) {{
          tbody.innerHTML = '<tr><td colspan="5" style="color: var(--fg-subtle);">No save archives in Vault.</td></tr>';
          return;
        }}
        backups.forEach(b => {{
          const row = document.createElement('tr');
          const szKb = (b.size_bytes / 1024).toFixed(1) + ' KB';
          const dt = (b.created_at || '').substring(0, 19).replace('T', ' ');
          row.innerHTML =
            '<td><code>' + escapeHtml(b.vault_id) + '</code></td>' +
            '<td><strong>' + escapeHtml(b.app_name) + '</strong></td>' +
            '<td>' + szKb + '</td>' +
            '<td>' + dt + '</td>' +
            '<td>' +
              '<button class="btn btn-sm btn-secondary" onclick="restoreVaultBackup(\'' + escapeHtml(b.vault_id) + '\')">Restore</button> ' +
              '<button class="btn btn-sm btn-error" onclick="deleteVaultBackup(\'' + escapeHtml(b.vault_id) + '\')">&times;</button>' +
            '</td>';
          tbody.appendChild(row);
        }});
      }} catch (e) {{
        tbody.innerHTML = '<tr><td colspan="5" style="color: var(--accent-red);">' + escapeHtml(e.message) + '</td></tr>';
      }}
    }}

    async function discoverPrefixSaves() {{
      const pPath = document.getElementById('vault-prefix-input').value.trim() || selectedPrefixPath;
      const appName = document.getElementById('vault-app-input').value.trim();
      const div = document.getElementById('vault-discovery-results');
      if (!pPath) return showAlert('Please specify a prefix path to scan.', true);
      div.textContent = 'Scanning prefix user directories...';
      try {{
        const res = await fetch('/api/vault/saves?prefix_path=' + encodeURIComponent(pPath) + (appName ? '&app=' + encodeURIComponent(appName) : ''));
        if (!res.ok) throw new Error('Discovery failed');
        const saves = await res.json();
        if (!saves.length) {{
          div.textContent = 'No save folders matching criteria found in this prefix.';
          return;
        }}
        div.innerHTML = '<strong>Found ' + saves.length + ' save location(s):</strong><br>' +
          saves.map(s => '&bull; ' + escapeHtml(s.folder_name) + ' (' + escapeHtml(s.category) + ') - ' + (s.size_bytes / 1024).toFixed(1) + ' KB, ' + s.files_count + ' files').join('<br>');
      }} catch (e) {{
        div.textContent = 'Discovery error: ' + e.message;
      }}
    }}

    async function backupPrefixSaves() {{
      const pPath = document.getElementById('vault-prefix-input').value.trim() || selectedPrefixPath;
      const appName = document.getElementById('vault-app-input').value.trim();
      if (!pPath || !appName) return showAlert('Prefix path and app name are required for backup.', true);
      try {{
        const res = await fetch('/api/vault/backup', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prefix_path: pPath, app_name: appName }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Backup failed');
        showAlert('Backed up saves for ' + appName + ' to Vault!', false);
        loadVaultBackups();
      }} catch (e) {{
        showAlert('Backup failed: ' + e.message, true);
      }}
    }}

    async function restoreVaultBackup(vaultId) {{
      const targetPrefix = prompt('Enter target prefix path to restore save into:', selectedPrefixPath || '');
      if (!targetPrefix) return;
      try {{
        const res = await fetch('/api/vault/restore', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ vault_id: vaultId, prefix_path: targetPrefix }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Restore failed');
        showAlert('Save ' + vaultId + ' successfully restored into prefix!', false);
      }} catch (e) {{
        showAlert('Restore failed: ' + e.message, true);
      }}
    }}

    async function deleteVaultBackup(vaultId) {{
      if (!confirm('Permanently delete backup ' + vaultId + '?')) return;
      try {{
        const res = await fetch('/api/vault/delete', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ vault_id: vaultId }})
        }});
        if (!res.ok) throw new Error('Deletion failed');
        showAlert('Deleted backup ' + vaultId, false);
        loadVaultBackups();
      }} catch (e) {{
        showAlert('Failed to delete backup: ' + e.message, true);
      }}
    }}

    let currentPrescription = null;

    async function generateHealingPrescription() {{
      const logText = document.getElementById('diag-log').value.trim();
      if (!logText) return showAlert('Please paste error log or terminal output.', true);
      try {{
        const res = await fetch('/api/prescriptions/generate', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ log: logText, app_name: 'target_app.exe', prefix_path: selectedPrefixPath }})
        }});
        const rx = await res.json();
        if (!res.ok) throw new Error(rx.error || 'Failed to generate prescription');
        currentPrescription = rx;

        const card = document.getElementById('healing-rx-card');
        const content = document.getElementById('rx-content');
        let html = '<p><strong>Root Causes Detected:</strong></p><ul style="padding-left: 20px; margin-bottom: 10px;">';
        rx.root_causes.forEach(rc => {{ html += '<li>' + escapeHtml(rc) + '</li>'; }});
        html += '</ul>';

        if (rx.recommended_runner) {{
          html += '<p><strong>Recommended Runner:</strong> <code style="color: var(--primary);">' + escapeHtml(rx.recommended_runner) + '</code></p>';
        }}
        if (rx.components_to_install && rx.components_to_install.length) {{
          html += '<p style="margin-top: 6px;"><strong>Components to Install:</strong> ' + rx.components_to_install.map(c => '<span class="badge badge-cyan">' + escapeHtml(c) + '</span>').join(' ') + '</p>';
        }}
        if (rx.dll_overrides_to_set && Object.keys(rx.dll_overrides_to_set).length) {{
          html += '<p style="margin-top: 6px;"><strong>DLL Overrides:</strong> <code>' + escapeHtml(JSON.stringify(rx.dll_overrides_to_set)) + '</code></p>';
        }}
        if (rx.env_vars_to_set && Object.keys(rx.env_vars_to_set).length) {{
          html += '<p style="margin-top: 6px;"><strong>Environment Variables:</strong> <code>' + escapeHtml(JSON.stringify(rx.env_vars_to_set)) + '</code></p>';
        }}

        content.innerHTML = html;
        if (selectedPrefixPath) document.getElementById('rx-prefix-input').value = selectedPrefixPath;
        card.style.display = 'block';
        card.scrollIntoView({{ behavior: 'smooth' }});
      }} catch (e) {{
        showAlert('Prescription error: ' + e.message, true);
      }}
    }}

    async function applyHealingPrescription(dryRun = false) {{
      if (!currentPrescription) return showAlert('No prescription generated.', true);
      const targetPrefix = document.getElementById('rx-prefix-input').value.trim() || selectedPrefixPath;
      if (!targetPrefix) return showAlert('Please specify the target prefix path to heal.', true);

      try {{
        const res = await fetch('/api/prescriptions/apply', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ prescription: currentPrescription, prefix_path: targetPrefix, dry_run: dryRun }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Apply failed');
        showAlert((dryRun ? '[Dry-Run] ' : '') + 'Applied prescription ' + currentPrescription.id + ' successfully!', false);
        if (selectedPrefixPath === targetPrefix) {{
          refreshPrefixComponents();
          refreshPrefixOverrides();
          refreshPrefixSnapshots();
        }}
      }} catch (e) {{
        showAlert('Failed to apply prescription: ' + e.message, true);
      }}
    }}

    window.addEventListener('DOMContentLoaded', () => {{
      loadTelemetry();
      loadRunners();
      loadVaultBackups();
    }});
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
        self.component_mgr = WindowsComponentManager()
        self.fleet_mgr = RunnerFleetManager()
        self.snapshot_mgr = PrefixSnapshotManager()
        self.vault_mgr = GameSaveVault()
        self.task_mgr = PrefixTaskManager()
        self.prescription_engine = PrescriptionEngine()
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

        if path == "/api/readiness":
            audit = self.env_inspector.get_readiness_audit()
            self._send_json(audit)
            return

        if path == "/api/components":
            prefix_path = query.get("prefix_path", [""])[0].strip()
            all_comps = self.component_mgr.list_components()
            res = []
            for c in all_comps:
                is_inst = False
                if prefix_path and os.path.isdir(prefix_path):
                    is_inst = self.component_mgr.is_installed_in_prefix(prefix_path, c.key)
                res.append({
                    "key": c.key,
                    "name": c.name,
                    "description": c.description,
                    "winetricks_verb": c.winetricks_verb,
                    "verification_files": c.verification_files,
                    "installed": is_inst,
                })
            self._send_json(res)
            return

        if path == "/api/prefixes/overrides":
            prefix_path = query.get("prefix_path", [""])[0].strip()
            if not prefix_path:
                self._send_error_json("Missing 'prefix_path' query parameter", status=400)
                return
            overrides = self.component_mgr.get_dll_overrides(prefix_path)
            self._send_json({"prefix_path": prefix_path, "overrides": overrides})
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

        if path == "/api/tuning/tools":
            tools = check_tuning_tools_availability()
            presets = {
                "esports": get_tuning_preset("esports").to_dict(),
                "4k_fidelity": get_tuning_preset("4k_fidelity").to_dict(),
                "power_saver": get_tuning_preset("power_saver").to_dict(),
                "minimal_overlay": get_tuning_preset("minimal_overlay").to_dict(),
            }
            self._send_json({"tools": tools, "presets": presets})
            return

        if path == "/api/runners":
            runners = self.fleet_mgr.discover_local_runners()
            self._send_json([r.to_dict() for r in runners])
            return

        if path == "/api/runners/available":
            limit = int(query.get("limit", [10])[0]) if query.get("limit") else 10
            releases = self.fleet_mgr.fetch_available_releases(limit=limit)
            self._send_json([rel.to_dict() for rel in releases])
            return

        if path == "/api/snapshots":
            prefix_path = query.get("prefix_path", [""])[0].strip()
            if not prefix_path:
                self._send_error_json("Missing 'prefix_path' query parameter", status=400)
                return
            snaps = self.snapshot_mgr.list_snapshots(prefix_path)
            self._send_json([s.to_dict() for s in snaps])
            return

        if path == "/api/vault/saves":
            prefix_path = query.get("prefix_path", [""])[0].strip()
            app_filter = query.get("app", [""])[0].strip() or None
            if not prefix_path:
                self._send_error_json("Missing 'prefix_path' query parameter", status=400)
                return
            saves = self.vault_mgr.discover_save_locations(prefix_path, app_name_filter=app_filter)
            self._send_json([s.to_dict() for s in saves])
            return

        if path == "/api/vault/backups":
            app_filter = query.get("app", [""])[0].strip() or None
            backups = self.vault_mgr.list_backups(app_name_filter=app_filter)
            self._send_json([b.to_dict() for b in backups])
            return

        if path == "/api/taskmgr/processes":
            prefix_path = query.get("prefix_path", [""])[0].strip() or None
            procs = self.task_mgr.list_prefix_processes(prefix_path)
            self._send_json([p.to_dict() for p in procs])
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

        if path == "/api/components/install":
            prefix_path = payload.get("prefix_path", "").strip()
            comp_key = payload.get("component_key", "").strip()
            if not prefix_path or not comp_key:
                self._send_error_json("Missing 'prefix_path' or 'component_key' in JSON body", status=400)
                return
            res = self.component_mgr.install(prefix_path, comp_key)
            self._send_json({
                "success": res.success,
                "component_key": res.component_key,
                "component_name": res.component_name,
                "verified": res.verified,
                "output": res.output,
                "error": res.error,
                "assurance_level": res.assurance_level,
            })
            return

        if path == "/api/prefixes/overrides":
            prefix_path = payload.get("prefix_path", "").strip()
            dll_name = payload.get("dll_name", "").strip()
            mode = payload.get("mode", "native,builtin").strip()
            action = payload.get("action", "set").strip()
            if not prefix_path or not dll_name:
                self._send_error_json("Missing 'prefix_path' or 'dll_name' in JSON body", status=400)
                return
            if action == "remove":
                success = self.component_mgr.remove_dll_override(prefix_path, dll_name)
            else:
                success = self.component_mgr.set_dll_override(prefix_path, dll_name, mode)
            overrides = self.component_mgr.get_dll_overrides(prefix_path)
            self._send_json({"success": success, "overrides": overrides})
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

        if path == "/api/tuning/preview":
            tuning_data = payload.get("tuning", {})
            config = GamingTuningConfig.from_dict(tuning_data)
            base_cmd = payload.get("command", ["wine", "app.exe"])
            cmd, env = build_tuning_pipeline(base_cmd, tuning=config)
            self._send_json({"command": cmd, "env": env})
            return

        if path == "/api/runners/install":
            tag = payload.get("archive_or_tag", "").strip()
            if not tag:
                self._send_error_json("Missing 'archive_or_tag' in JSON body", status=400)
                return
            try:
                if os.path.isfile(tag):
                    installed = self.fleet_mgr.install_runner(tag)
                    self._send_json({"success": True, "runner": installed.to_dict()})
                    return
                releases = self.fleet_mgr.fetch_available_releases(limit=20)
                target = next((r for r in releases if r.tag_name == tag or r.name == tag), None)
                if not target:
                    self._send_error_json(f"Runner '{tag}' not found in releases", status=404)
                    return
                dest_tar = os.path.join(self.fleet_mgr.runners_dir, f"{target.tag_name}.tar.gz")
                urllib.request.urlretrieve(target.download_url, dest_tar)
                installed = self.fleet_mgr.install_runner(dest_tar)
                self._send_json({"success": True, "runner": installed.to_dict()})
            except Exception as e:
                self._send_error_json(f"Runner install error: {e}", status=500)
            return

        if path == "/api/snapshots/create":
            prefix_path = payload.get("prefix_path", "").strip()
            label = payload.get("label", "").strip() or "Manual Snapshot"
            if not prefix_path or not os.path.isdir(prefix_path):
                self._send_error_json("Missing or invalid 'prefix_path'", status=400)
                return
            try:
                snap = self.snapshot_mgr.create_snapshot(prefix_path, label=label, trigger="manual")
                self._send_json({"success": True, "snapshot": snap.to_dict()})
            except Exception as e:
                self._send_error_json(f"Snapshot creation error: {e}", status=500)
            return

        if path == "/api/snapshots/restore":
            prefix_path = payload.get("prefix_path", "").strip()
            snapshot_id = payload.get("snapshot_id", "").strip()
            if not prefix_path or not snapshot_id:
                self._send_error_json("Missing 'prefix_path' or 'snapshot_id'", status=400)
                return
            try:
                self.snapshot_mgr.restore_snapshot(prefix_path, snapshot_id)
                self._send_json({"success": True, "restored_id": snapshot_id})
            except Exception as e:
                self._send_error_json(f"Snapshot restore error: {e}", status=500)
            return

        if path == "/api/snapshots/delete":
            prefix_path = payload.get("prefix_path", "").strip()
            snapshot_id = payload.get("snapshot_id", "").strip()
            if not prefix_path or not snapshot_id:
                self._send_error_json("Missing 'prefix_path' or 'snapshot_id'", status=400)
                return
            deleted = self.snapshot_mgr.delete_snapshot(prefix_path, snapshot_id)
            if not deleted:
                self._send_error_json(f"Snapshot '{snapshot_id}' not found", status=404)
                return
            self._send_json({"success": True, "deleted_id": snapshot_id})
            return

        if path == "/api/vault/backup":
            prefix_path = payload.get("prefix_path", "").strip()
            app_name = payload.get("app_name", "").strip()
            notes = payload.get("notes", "").strip()
            if not prefix_path or not app_name:
                self._send_error_json("Missing 'prefix_path' or 'app_name'", status=400)
                return
            try:
                entry = self.vault_mgr.backup_save(prefix_path, app_name, notes=notes)
                self._send_json({"success": True, "vault_entry": entry.to_dict()})
            except Exception as e:
                self._send_error_json(f"Save backup error: {e}", status=500)
            return

        if path == "/api/vault/restore":
            vault_id = payload.get("vault_id", "").strip()
            prefix_path = payload.get("prefix_path", "").strip()
            if not vault_id or not prefix_path:
                self._send_error_json("Missing 'vault_id' or 'prefix_path'", status=400)
                return
            try:
                self.vault_mgr.restore_save(vault_id, prefix_path)
                self._send_json({"success": True, "restored_id": vault_id})
            except Exception as e:
                self._send_error_json(f"Save restore error: {e}", status=500)
            return

        if path == "/api/vault/delete":
            vault_id = payload.get("vault_id", "").strip()
            if not vault_id:
                self._send_error_json("Missing 'vault_id'", status=400)
                return
            deleted = self.vault_mgr.delete_backup(vault_id)
            if not deleted:
                self._send_error_json(f"Vault entry '{vault_id}' not found", status=404)
                return
            self._send_json({"success": True, "deleted_id": vault_id})
            return

        if path == "/api/taskmgr/kill":
            prefix_path = payload.get("prefix_path", "").strip()
            if not prefix_path:
                self._send_error_json("Missing 'prefix_path'", status=400)
                return
            res = self.task_mgr.kill_prefix_processes(prefix_path)
            self._send_json({"success": True, "result": res})
            return

        if path == "/api/taskmgr/reset-locks":
            prefix_path = payload.get("prefix_path", "").strip()
            if not prefix_path:
                self._send_error_json("Missing 'prefix_path'", status=400)
                return
            removed = self.task_mgr.reset_prefix_locks(prefix_path)
            self._send_json({"success": True, "removed_locks": removed})
            return

        if path == "/api/taskmgr/launch":
            prefix_path = payload.get("prefix_path", "").strip()
            tool = payload.get("tool", "").strip()
            if not prefix_path or not tool:
                self._send_error_json("Missing 'prefix_path' or 'tool'", status=400)
                return
            try:
                res = self.task_mgr.launch_wine_tool(prefix_path, tool)
                self._send_json({"success": True, "result": res})
            except Exception as e:
                self._send_error_json(f"Tool launch error: {e}", status=400)
            return

        if path == "/api/prescriptions/generate":
            log_text = payload.get("log", "")
            app_name = payload.get("app_name", "application.exe")
            prefix_path = payload.get("prefix_path")
            if not log_text:
                self._send_error_json("Missing 'log' in JSON body", status=400)
                return
            events = self.diag_engine.analyze_log(log_text)
            rx = self.prescription_engine.synthesize(events, app_name=app_name, prefix_path=prefix_path)
            self._send_json(rx.to_dict())
            return

        if path == "/api/prescriptions/apply":
            rx_data = payload.get("prescription", {})
            prefix_path = payload.get("prefix_path", "").strip()
            dry_run = bool(payload.get("dry_run", False))
            if not rx_data or not prefix_path:
                self._send_error_json("Missing 'prescription' or 'prefix_path'", status=400)
                return
            from zcf.diagnostics.prescriptions import HealingPrescription
            rx = HealingPrescription.from_dict(rx_data)
            try:
                res = self.prescription_engine.apply(rx, prefix_path=prefix_path, dry_run=dry_run)
                self._send_json({"success": True, "result": res})
            except Exception as e:
                self._send_error_json(f"Prescription apply error: {e}", status=500)
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
