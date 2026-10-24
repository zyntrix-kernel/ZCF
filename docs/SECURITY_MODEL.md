# ZCF Security & Isolation Model

**Document:** `docs/SECURITY_MODEL.md`  
**Framework Version:** `v0.2.0`  

---

## 1. Principles of Security

1. **Non-Root Execution:** Running compatibility layers as root is strictly prohibited and rejected by `SecurityController`.
2. **Credential Minimization:** Host environment variables are scrubbed. Secrets, API keys, tokens, and SSH agent sockets are never inherited by untrusted child processes.
3. **Read-Only System Boundaries:** Host operating system roots (`/usr`, `/lib`, `/bin`, `/etc`) are mounted read-only via Bubblewrap.
4. **App-Specific Writable Isolation:** Each Windows application receives an isolated WINEPREFIX. Applications cannot modify system files or other application prefixes.
5. **Deterministic Argument Integrity:** Structured command arrays prevent shell injection vulnerabilities.

---

## 2. Desktop Environment Allowlist

ZCF preserves only legitimate desktop session variables required for graphics, audio, and display servers:

- **Display:** `DISPLAY`, `XAUTHORITY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`
- **Audio & D-Bus:** `DBUS_SESSION_BUS_ADDRESS`, `PULSE_SERVER`, `PIPEWIRE_RUNTIME_DIR`
- **Vulkan / GPU:** `VK_ICD_FILENAMES`, `VK_LAYER_PATH`, `DRI_PRIME`, `__NV_PRIME_RENDER_OFFLOAD`
- **Compatibility Layer:** `WINEPREFIX`, `WINEDEBUG`, `WINEDLLOVERRIDES`, `WINEARCH`

All environment variables matching sensitive patterns (`TOKEN`, `KEY`, `SECRET`, `PASSWORD`, `AUTH`, `CREDENTIAL`, `SSH_`, `AWS_`, `GITHUB_`) are automatically stripped.

---

## 3. Bubblewrap Sandbox Policy

When sandboxing is active, `SandboxManager` wraps the target invocation:

```
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
  --bind <app_dir> <app_dir> \
  --bind <prefix_path> <prefix_path> \
  --chdir <app_dir> \
  -- <command>
```

For offline applications, `--unshare-net` completely disables network namespace access.
