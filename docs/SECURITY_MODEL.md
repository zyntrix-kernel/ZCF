# ZCF Security & Isolation Model

**Document:** `docs/SECURITY_MODEL.md`  
**Framework Version:** `v0.2.0`  
**Milestone:** 3 (Close the Remaining Security and Evidence Gaps)

---

## 1. Principles of Security

1. **Non-Root Execution:** Running compatibility layers as root is strictly prohibited and rejected by `SecurityController`.
2. **Credential Minimization:** Host environment variables are scrubbed. Secrets, API keys, tokens, and SSH agent sockets are never inherited by untrusted child processes. `XAUTHORITY` is preserved only for legitimate X11 authentication.
3. **Read-Only System Boundaries:** Host operating system roots (`/usr`, `/lib`, `/bin`, `/etc`) are mounted strictly read-only via Bubblewrap (`--ro-bind`).
4. **Strict Writable Mount Policy:** All writable paths passed to the sandbox must be canonicalized (`os.path.realpath`), checked against sensitive system roots, symlink escapes, traversal attacks, and strictly confined within approved prefix roots (`allowed_prefix_roots`).
5. **Fail-Closed Network Isolation by Default:** Every workload defaults to complete network isolation (`isolate_network = True`, Bubblewrap `--unshare-net`). Outbound network access requires explicit caller authorization (`allow_network = True` or `--allow-network`).
6. **Deterministic Argument Integrity:** Structured command arrays prevent shell injection vulnerabilities.
7. **Fail-Closed Container Isolation:** If sandboxing is requested (`use_sandbox = True`) but Bubblewrap is unavailable, execution aborts immediately with `SecurityViolationError` unless unconfined mode is explicitly authorized (`allow_unconfined = True`).
8. **Durable User Data Safety:** Prefix persistence defaults to `True`. Prefixes with missing, unreadable, or corrupted metadata are strictly preserved and never automatically purged.
9. **Truthful Resource & Timeout Enforcement:** Workload-aware deadlines prevent runaway background processes. Interactive workloads default to unconstrained execution, while bounded workloads enforce strict timeouts. Resource limit mechanisms are truthfully reported, distinguishing per-process POSIX `RLIMIT_AS` virtual address space from physical RSS/cgroups.

---

## 2. Desktop Environment Allowlist & Authentication

ZCF preserves only legitimate desktop session variables required for graphics, audio, and display servers:

- **Display:** `DISPLAY`, `XAUTHORITY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`
- **Audio & D-Bus:** `DBUS_SESSION_BUS_ADDRESS`, `PULSE_SERVER`, `PIPEWIRE_RUNTIME_DIR`
- **Vulkan / GPU:** `VK_ICD_FILENAMES`, `VK_LAYER_PATH`, `DRI_PRIME`, `__NV_PRIME_RENDER_OFFLOAD`
- **Compatibility Layer:** `WINEPREFIX`, `WINEDEBUG`, `WINEDLLOVERRIDES`, `WINEARCH`

All environment variables matching sensitive patterns (`TOKEN`, `KEY`, `SECRET`, `PASSWORD`, `AUTHORIZATION`, `AUTH_TOKEN`, `CREDENTIAL`, `SSH_`, `AWS_`, `GITHUB_`) are automatically stripped, while legitimate display authentication files (`XAUTHORITY`) are mounted read-only into the sandbox.

---

## 3. Secure Writable Sandbox Mount Policy

Bubblewrap mount validation (`validate_writable_mount()`) enforces strict source path verification:

1. **Path Canonicalization & Symlink Resolution:** Mount sources are resolved via `os.path.realpath(os.path.abspath(path))` before evaluating security policies. Symlinks pointing to forbidden directories or outside approved prefix roots are identified and blocked immediately.
2. **Rejection of Root & Sensitive System Directories:** The filesystem root (`/`, `C:\`), and sensitive directories (`/etc`, `/usr`, `/run`, `/var`, `/boot`, `/root`, `/sys`, `/proc`, `/dev`, `/opt`, `/srv`) cannot be mounted writable under any circumstances.
3. **Rejection of Traversal Aliases:** Relative traversal patterns (such as `/tmp/../etc`) are resolved to canonical targets and evaluated against the policy rules.
4. **User Home Directory & Private Credentials:** Mounting the user's home directory root (`~`) directly as writable is forbidden. Sensitive credential directories (`~/.ssh`, `~/.gnupg`, `~/.pki`) are strictly blocked.
5. **Approved Prefix Root Confinement:** If `allowed_prefix_roots` is specified (e.g. `~/.local/share/zcf/wine_prefixes` and `~/.local/share/zcf/proton_prefixes`), writable paths must reside within those approved directories.
6. **Narrow Display Socket Confinement:** Wayland display sockets (`$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY`) are narrowly mounted specifically for the socket file itself, preventing exposure of the broader runtime directory or other session sockets.
7. **Actionable Sanitized Error Reporting:** Rejections generate clean, actionable error messages that identify the security violation without leaking full private host paths.

---

## 4. Execution Timeouts & Truthful Resource Enforcement

1. **Workload-Aware Defaults:**
   - **Installers (`WorkloadType.INSTALLER`):** 600 seconds default deadline; 3600 seconds maximum ceiling.
   - **CLI Tools (`WorkloadType.CLI_TOOL`):** 120 seconds default deadline; 1800 seconds maximum ceiling.
   - **Desktop GUI & Games (`WorkloadType.DESKTOP_GUI`, `WorkloadType.GAME`):** Default to unconstrained execution (`timeout = None`).
2. **Boundary Validation & Clamping:**
   - Negative timeouts (`timeout < 0`) raise `ValueError`.
   - `timeout = 0` provides an explicit, intentional unlimited execution mode.
   - User timeouts exceeding policy ceilings are safely clamped to `max_timeout_seconds` and recorded in `security_warnings`.
3. **Truthful Resource Accounting:**
   - Virtual memory limits are enforced on Linux via POSIX `RLIMIT_AS`. ZCF explicitly documents and reports that `RLIMIT_AS` restricts virtual address space per-process and does not measure physical memory (RSS) or aggregate process trees.
4. **Descendant Reaping & Stream Closure:**
   - Upon deadline expiration (exit code 124), the entire process group is signaled with `SIGTERM`, followed by unconditional `SIGKILL` to prevent lingering orphans.
   - Output pipes (`process.stdout`, `process.stderr`) are explicitly closed to avoid blocking reader threads if descendant processes attempt to hold file descriptors open.

---

## 5. Bubblewrap Sandbox Execution Model

```bash
bwrap \
  --ro-bind /usr /usr \
  --ro-bind /lib /lib \
  --ro-bind /bin /bin \
  --ro-bind /etc /etc \
  --proc /proc \
  --dev /dev \
  --tmpfs /tmp \
  --unshare-net \
  --unshare-user \
  --unshare-pid \
  --unshare-ipc \
  --unshare-uts \
  --ro-bind <app_dir> <app_dir> \
  --bind <validated_prefix_path> <validated_prefix_path> \
  --chdir <app_dir> \
  -- <command>
```

When network access is permitted via explicit opt-in (`allow_network=True`), `--unshare-net` is omitted and the policy records `network_mode: "bridged_host"`. Offline execution remains the absolute default.
