# ZCF Software Compatibility Taxonomy and Problem Model

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Document:** `docs/COMPATIBILITY_MODEL.md`  
**Date:** October 24, 2026  
**Auditor:** Antigravity Autonomous Engineering Agent  

---

## 1. Multi-Dimensional Compatibility Model

Software incompatibility on modern operating systems cannot be reduced to a single missing function. It spans multiple orthogonal layers of the computing stack. ZCF models compatibility as a 7-dimensional constraint problem:

```
+--------------------------------------------------------------------+
| 7. Protected & Security Boundaries (DRM, Anti-Cheat, Signatures)   |
+--------------------------------------------------------------------+
| 6. Distribution, Filesystem & Sandboxing Assumptions (FHS, Flatpak)|
+--------------------------------------------------------------------+
| 5. Graphics, Multimedia & Hardware (Vulkan, DXVK, Wayland, Audio)  |
+--------------------------------------------------------------------+
| 4. Runtime & Language Frameworks (.NET, Java, Electron, Libc)      |
+--------------------------------------------------------------------+
| 3. Operating System API Semantics (Win32, POSIX, NT Kernel, IPC)   |
+--------------------------------------------------------------------+
| 2. ABI & Calling Conventions (System V AMD64 vs MS x64 vs AAPCS64) |
+--------------------------------------------------------------------+
| 1. Instruction Set Architecture (x86_64, AArch64, RISC-V, ARMv7)   |
+--------------------------------------------------------------------+
```

---

## 2. Dimension Breakdown

### 2.1 Dimension 1: Instruction-Set Architecture (ISA)
- **Problem:** Target binary compiled for CPU architecture $A$ executing on host CPU architecture $B$.
- **Compatibility Matrix:**
  - $A == B$: Native execution (overhead ~0%).
  - $A == \text{x86\_64}$ and $B == \text{AArch64}$: High-performance thunking via Box64 / FEX or full emulation via QEMU TCG.
  - $A \neq B$ (arbitrary): User-mode instruction translation via QEMU User.
- **Key Indicators:** ELF `e_machine`, PE Machine header (`0x8664`, `0x014c`, `0xaa64`).

### 2.2 Dimension 2: Application Binary Interface (ABI)
- **Problem:** Differences in calling conventions, register usage, struct packing, stack alignment, and syscall numbers.
- **Examples:**
  - Microsoft x64 ABI (`RCX, RDX, R8, R9` + 32-byte shadow space) vs System V AMD64 ABI (`RDI, RSI, RDX, RCX, R8, R9`).
  - Linux syscall numbering vs Windows NT syscall indices (dynamic per Windows build).
- **Resolution Strategy:** Handled by runtime adapters (Wine for Windows-to-Linux ABI; QEMU for cross-Linux ABI).

### 2.3 Dimension 3: Operating System API Semantics
- **Problem:** Target software assumes operating system services that do not exist natively on the host:
  - Windows: Registry hives (`HKEY_LOCAL_MACHINE`), named pipes, Windows Service Control Manager, COM/OLE, WinRT.
  - Linux: POSIX filesystem permissions, `/proc`, `/sys`, D-Bus, systemd.
- **Resolution Strategy:** API translation layers (Wine, Proton) or containerized guest kernels (Waydroid, VM).

### 2.4 Dimension 4: Framework and Runtime Dependencies
- **Problem:** Applications rely on managed runtimes or specific library ABIs:
  - C Runtime: GLIBC symbol versioning (`GLIBC_2.38`, `GLIBC_2.42`), Musl vs Glibc incompatibilities.
  - Managed Runtimes: .NET CLR versions (.NET 8, .NET Framework 4.8), Java JRE/JDK, Node.js/Electron versions.
- **Resolution Strategy:** Static inspection detects runtime signatures; ZCF recommends required dependency packages or sidecar containers.

### 2.5 Dimension 5: Graphics, Multimedia, and Hardware
- **Problem:** Graphics rendering, display protocols, and audio/input pipelines:
  - Graphics APIs: Direct3D 9/11/12 translated to Vulkan via DXVK and VKD3D.
  - Display Servers: X11 vs Wayland (requires `Xwayland` for legacy applications).
  - Audio: PulseAudio / ALSA translated through modern PipeWire backends.
- **Resolution Strategy:** Dynamic GPU capability probing; verify Vulkan extensions and driver capabilities before launching graphics workloads.

### 2.6 Dimension 6: Packaging, Filesystem, and Sandboxing
- **Problem:** Distribution assumptions:
  - Path hardcoding (`/usr/lib64` vs `/usr/lib/x86_64-linux-gnu`).
  - Sandboxing constraints: Flatpak bubblewrap restrictions, read-only root filesystems, lack of host device nodes.
- **Resolution Strategy:** ZCF uses isolated directory overlays and controlled environment variables (`LD_LIBRARY_PATH`, `WINEPREFIX`).

### 2.7 Dimension 7: Protected and Proprietary Functionality
- **Problem:** Digital Rights Management (DRM), anti-cheat drivers (EasyAntiCheat, BattlEye, Vanguard), proprietary kernel modules.
- **Ethical and Technical Policy:**
  - ZCF **never** bypasses authentication, DRM, or security mechanisms.
  - When anti-cheat requires Windows kernel-level ring 0 drivers, ZCF reports `unsupported_kernel_protection` and explains the limitation clearly to the user.
