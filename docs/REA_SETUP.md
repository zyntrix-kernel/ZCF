# REA Installation, Integration, and Diagnostic Report

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Document:** `docs/REA_SETUP.md`  
**Date:** October 24, 2026  
**REA Version:** `rea-agents@6.7.0` (npm-published, MIT License)  
**Official Repository:** `https://github.com/morluto/rea`  
**Local Inspection Source Tree:** `research/targets/rea`  
**Integration Status:** **FULLY CONFIGURED & VERIFIED LIVE (MCP & CLI)**

---

## 1. Project Background and Architecture

REA (Reverse Engineer Anything), authored by morluto, is a unified reverse engineering and static/dynamic binary analysis platform designed specifically for autonomous AI agents and developer terminals. It exposes a unified command-line interface (`rea`), an MCP (Model Context Protocol) stdio server, and specialized agent skills.

Key architectural concepts implemented by REA:
1. **Evidence-Based Analysis:** REA does not treat decompilation or reconstruction as ground truth. Instead, every result is packaged into an immutable Evidence JSON object containing an `evidence_id`, cryptographic digests (`sha256`), authority tiers (`shipped-artifact`, `managed-static-analysis`, `native-analysis-provider`), observations, hypotheses, and unexplored branches.
2. **Layered Analysis Providers:**
   - *Tier 0 (Safe Built-in Graphs):* `rea-artifact-graph` performs recursive archive and container walks without process execution.
   - *Tier 1 (Safe Static Deconstructors):* `rea-dotnet-static` parses PE/CLI structures, CLR tables, and P/Invoke declarations directly from raw bytes.
   - *Tier 2 (Deep Native Engines):* Pluggable native engines (Ghidra, Hopper, IDA, Kuna, Rizin, GDB) for disassembly, control-flow reconstruction, and decompilation.
3. **Fail-Closed Verification:** Strict typing and integrity policies ensure that damaged or tampered binaries produce explicit contradiction records rather than silently corrupted symbol graphs.

---

## 2. Installation and Registration Procedure

### 2.1 Package Verification
The official package was resolved against the npm registry:
```powershell
npm view rea-agents
# Result: rea-agents@6.7.0 | MIT | deps: 40 | unpackedSize: 28.6 MB
```

### 2.2 Integration Setup Command
To register REA with the Antigravity agent without disrupting existing tools, the automated setup was executed:
```powershell
npx -y rea-agents@6.7.0 setup --client antigravity -y
```

### 2.3 Actions Applied
1. **MCP Configuration Registered:**
   - Target configuration: `C:\Users\USER\.gemini\config\mcp_config.json`
   - Entry created:
     ```json
     "rea": {
       "command": "cmd.exe",
       "args": [
         "/d",
         "/c",
         "npx",
         "-y",
         "rea-agents@6.7.0",
         "mcp"
       ]
     }
     ```
   - Automated backup retained at `C:\Users\USER\.gemini\config\mcp_config.json.rea.backup`.
2. **Skill Installed:**
   - Target path: `C:\Users\USER\.gemini\config\skills\reverse-engineer-anything`
   - Installed Skill Version: 42 (207 MCP tools cataloged).

---

## 3. Diagnostic Audit (`rea doctor`)

Executing `npx -y rea-agents@6.7.0 doctor` revealed the exact state of providers and environment capabilities:

```yaml
healthy: true
environment_healthy: false
scope:
  mode: audit-wide
  clients: [antigravity]
server_identity:
  package: rea-agents@6.7.0
  catalog:
    cli_commands: 153
    mcp_tools: 207
    mcp_prompts: 6
scope_checks:
  - node: healthy (v24.18.0)
  - host: healthy (win32 x64)
  - registration:antigravity: aligned (C:\Users\USER\.gemini\config\mcp_config.json)
  - hopper: missing_analysis_engine (Hopper requires macOS; unsupported on win32)
  - ghidra: not_configured (GHIDRA_INSTALL_DIR unset, but JDK 17.0.20.1 is detected)
  - ida-registration: not_configured (requires commercial IDA MCP configuration)
  - kuna-installation: not_configured (requires local kuna binary)
```

### 3.1 Provider Capabilities Summary
- **Available immediately without external binaries:**
  - `rea-artifact-graph` (v1): Safe container, PE/ELF/Mach-O inspection, SHA-256 digesting.
  - `rea-dotnet-static` (v1): Complete .NET / CLI metadata analysis and P/Invoke boundary extraction.
  - `sqlite`: Database schema and table inspector using Node.js DatabaseSync.
- **Requiring external dependencies:**
  - `ghidra`: Requires setting `GHIDRA_INSTALL_DIR` to Ghidra 12.1.x.
  - `hopper`: Unavailable on Windows host (macOS exclusive).

---

## 4. Verification and Live Evidence Collection

### 4.1 CLI Verification
We verified REA's CLI static analysis on `C:\Windows\System32\cmd.exe`:

#### Test 1: Artifact Graph Inspection
```powershell
npx -y rea-agents@6.7.0 inspect-artifact "C:\Windows\System32\cmd.exe" --format json
```
**Observed Result:**
- `evidence_id`: `ev_023eddb2272dd06ec13475f068b38ed5112a472ea190a196fc3b7516a3a78a75`
- `subject.digest.sha256`: `15cd209c995b7d3009c91ca40892d5b8f1fb162f3e5f10716642ea278e8e0d7b`
- `subject.format`: `pe`
- `declared_size`: 339,968 bytes
- Derived hypothesis: PE artifact may contain native code or managed CLI metadata.

#### Test 2: Managed CLI Inspection
```powershell
npx -y rea-agents@6.7.0 inspect-managed-artifact "C:\Windows\System32\cmd.exe" --format json
```
**Observed Result:**
- `evidence_id`: `ev_ec38de54e14d3f39155f3d588129a4f07fb91ca0f21a147f62e78f3037797277`
- Machine: `0x8664` (`x86_64`)
- Optional Header: `pe32-plus`
- Section Count: 8
- Classification: `not-managed` (`cli-directory-absent`)

### 4.2 Live Agent Model Context Protocol (MCP) Verification
Following the server restart, REA's MCP stdio server loaded directly into the Antigravity session. We performed live tool invocations using `call_mcp_tool`:

1. **`open_binary` Invocation:**
   - Tool: `open_binary`
   - Arguments: `{"path": "C:\\Windows\\System32\\cmd.exe"}`
   - Result:
     ```json
     {
       "result": {
         "path": "C:\\Windows\\System32\\cmd.exe",
         "format": "pe",
         "kind": "executable",
         "sha256": "15cd209c995b7d3009c91ca40892d5b8f1fb162f3e5f10716642ea278e8e0d7b",
         "architecture": "x86_64"
       }
     }
     ```
2. **`inspect_artifact` Invocation:**
   - Tool: `inspect_artifact`
   - Arguments: `{}`
   - Result: Successfully returned full content-addressed artifact graph Evidence JSON.
3. **`close_binary` Invocation:**
   - Tool: `close_binary`
   - Result: Session cleanly closed (`{"result": null}`).

---

## 5. Architectural Lessons for ZCF

1. **Evidence Containers vs Heuristic Guessing:** REA structures all analysis as verifiable `Evidence` objects with explicit authority tags (`shipped-artifact`, `derived-observation`, `hypothesis`). ZCF adopts this directly into its `CompatibilityEvidence` and `CompatibilityReport` schemas.
2. **Fail-Closed Safety:** Unrecognized formats or damaged headers must produce structured diagnostic errors rather than unhandled exceptions or speculative claims.
3. **Stateless Tooling with Session Caching:** Tools should operate cleanly on file paths or lightweight sessions that can be opened, queried, and cleanly closed without leaking background processes.
