# ZCF Security & Isolation Model

**Document:** `docs/SECURITY_MODEL.md`  
**Framework Version:** `v0.2.0`  
**Milestone:** 2 (Prefix Data Safety, Process Lifecycle & Trust Integrity)

---

## 1. Principles of Security

1. **Non-Root Execution:** Running compatibility layers as root is strictly prohibited and rejected by `SecurityController`.
2. **Credential Minimization:** Host environment variables are scrubbed. Secrets, API keys, tokens, and SSH agent sockets are never inherited by untrusted child processes. `XAUTHORITY` is preserved only for legitimate X11 authentication.
3. **Read-Only System Boundaries:** Host operating system roots (`/usr`, `/lib`, `/bin`, `/etc`) are mounted read-only via Bubblewrap.
4. **App-Specific Writable Isolation:** Each Windows application receives an isolated WINEPREFIX. Applications cannot modify system files or other application prefixes.
5. **Deterministic Argument Integrity:** Structured command arrays prevent shell injection vulnerabilities.
6. **Fail-Closed Container Isolation:** If sandboxing is requested but unavailable, execution aborts with `SecurityViolationError` unless unconfined mode is explicitly authorized.
7. **Durable User Data Safety:** Prefix persistence defaults to `True`. Prefixes with missing, unreadable, or corrupted metadata are strictly preserved and never automatically purged.

---

## 2. Desktop Environment Allowlist & Authentication

ZCF preserves only legitimate desktop session variables required for graphics, audio, and display servers:

- **Display:** `DISPLAY`, `XAUTHORITY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`
- **Audio & D-Bus:** `DBUS_SESSION_BUS_ADDRESS`, `PULSE_SERVER`, `PIPEWIRE_RUNTIME_DIR`
- **Vulkan / GPU:** `VK_ICD_FILENAMES`, `VK_LAYER_PATH`, `DRI_PRIME`, `__NV_PRIME_RENDER_OFFLOAD`
- **Compatibility Layer:** `WINEPREFIX`, `WINEDEBUG`, `WINEDLLOVERRIDES`, `WINEARCH`

All environment variables matching sensitive patterns (`TOKEN`, `KEY`, `SECRET`, `PASSWORD`, `AUTHORIZATION`, `AUTH_TOKEN`, `CREDENTIAL`, `SSH_`, `AWS_`, `GITHUB_`) are automatically stripped, while legitimate display authentication files (`XAUTHORITY`) are mounted read-only into the sandbox.

---

## 3. Bubblewrap Sandbox Policy & Fail-Closed Enforcement

ZCF adheres to strict fail-closed container isolation:
1. **Fail-Closed Default:** If `use_sandbox=True` is configured and Bubblewrap is not installed or available, execution halts immediately with a `SecurityViolationError`. Unconfined execution is never silently permitted; callers must explicitly pass `allow_unconfined=True` to execute without a sandbox.
2. **Read-Only System & App Filesystems:** Operating system directories (`/usr`, `/lib`, `/bin`, `/etc`) and the application directory (`<app_dir>`) are mounted strictly read-only (`--ro-bind`). Untrusted binaries cannot mutate host binaries or their own source directory.
3. **Restricted Writable Scope:** Writable access is confined exclusively to the isolated application prefix (`<prefix_path>`). Root system paths and `/run` are strictly prohibited from writable bind mounts.
4. **Selective Display Sockets:** GUI applications access the display server via selective socket binding (`/tmp/.X11-unix` and `$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY`), completely avoiding exposing host runtime directories or system daemons.
5. **Desktop Entry Protection:** All launcher generation paths strictly reject newlines (`\r`, `\n`) and non-printable control characters (`ord(c) < 32`), neutralizing `.desktop` key injection attacks. Field codes (`%`) are escaped to `%%`, quotes to `\"`, backslashes to `\\`, and dollar signs to `\$`.
6. **POSIX Resource Limits (`rlimit`):** On Linux systems, memory and CPU constraints are enforced at process creation via `preexec_fn` (`RLIMIT_AS` and `RLIMIT_CPU`).
7. **Process Group & Descendant Reaping:** Processes that exceed execution deadlines are terminated at the process-group level (`child_pgid = process.pid`). After a 0.4s grace period, `os.killpg(child_pgid, signal.SIGKILL)` is executed unconditionally to prevent surviving orphan descendants.
8. **Bounded Queue & Output Protection:** Real-time subprocess output streaming uses a bounded queue (`maxsize=1000`) and a strict 512 KB capture buffer cap to prevent memory exhaustion attacks from stdout spam.

```bash
bwrap \
  --ro-bind /usr /usr \
  --ro-bind /lib /lib \
  --ro-bind /bin /bin \
  --ro-bind /etc /etc \
  --proc /proc \
  --dev /dev \
  --unshare-user \
  --unshare-pid \
  --unshare-ipc \
  --unshare-uts \
  --ro-bind <app_dir> <app_dir> \
  --bind <prefix_path> <prefix_path> \
  --chdir <app_dir> \
  -- <command>
```

For offline applications, `--unshare-net` completely disables network namespace access.
