# Research Report: CPU Architecture Emulation and Hybrid Library Thunking

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Document:** `research/02_architecture_emulation_and_thunking.md`  
**Targets:** QEMU User-Mode (`qemu-user`), Box64 (`ptitSeb/box64`), FEX-Emu  
**Auditor:** Antigravity Autonomous Engineering Agent  
**Focus:** Instruction Set Translation vs Library Forwarding / Thunking  

---

## 1. Research Objective

Investigate how cross-architecture compatibility is achieved on Linux, comparing:
1. Pure JIT/TCG instruction set translation and kernel syscall translation (QEMU User-Mode).
2. Hybrid execution with native library wrapping/thunking (Box64, FEX-Emu).
3. System call translation boundaries and ABI alignment.

---

## 2. Technical Findings

### 2.1 QEMU User-Mode Emulation (`qemu-user`)
QEMU User-Mode provides a target-to-host system call emulation layer:
- The target binary is loaded into the host process address space.
- CPU instructions are disassembled and translated into QEMU Intermediate Representation (IR), then compiled via the Tiny Code Generator (TCG) into host machine code.
- When the target binary executes a system call (e.g., `svc #0` on AArch64, `ecall` on RISC-V):
  1. QEMU intercepts the exception.
  2. The syscall number is mapped from target Linux ABI to host Linux ABI (`linux-user/syscall.c`).
  3. Arguments (including structs like `stat`, `timeval`, `iovec`) are unpacked, byte-swapped if endianness differs, and repackaged for the host kernel.
  4. The host kernel performs the syscall, and the return value is marshaled back.
- **Limitation:** Every shared library (`libc.so`, `libX11.so`, `libvulkan.so`) linked by the target binary must also be emulated in TCG, resulting in severe performance overhead for graphics and computing workloads.

### 2.2 Box64 and FEX-Emu: The Thunking Paradigm
Box64 and FEX take a fundamentally different approach for running x86_64 software on ARM64:
- Instead of emulating every library, Box64 maintains a directory of "wrapped libraries" (`wrappedgl.c`, `wrappedvulkan.c`, `wrappedlibc.c`).
- When an x86_64 program calls a function like `glDrawArrays` or `vkQueueSubmit`:
  1. Box64 traps the call.
  2. Arguments are copied across ABI calling conventions (System V AMD64 ABI -> ARM64 AAPCS64).
  3. The native ARM64 host library (`/usr/lib/aarch64-linux-gnu/libGL.so`) is invoked directly.
  4. Hardware GPU acceleration is executed natively on the host GPU driver without emulation.
- **Performance Impact:** Compute-heavy graphics and system calls achieve 80-95% of native speed, compared to 10-20% under pure QEMU TCG emulation.

---

## 3. Extracted ZCF Engineering Patterns

1. **Multi-Tiered ISA Planning:**
   - If `host_isa == binary_isa`: Route directly to native execution or OS compatibility layer.
   - If `host_isa != binary_isa`:
     - If targeting ARM64 host with x86_64 binary and hardware graphics: Prefer Box64 / FEX adapter with native library wrapping.
     - If generic cross-architecture execution or non-x86 target: Route to `QemuUserAdapter`.
2. **Library Dependency Resolution:**
   - For QEMU user execution, ZCF's `EnvironmentInspector` checks for multiarch rootfs libraries (`/usr/aarch64-linux-gnu` or `/usr/arm-linux-gnueabihf`).
3. **Structured Translation Diagnostics:**
   - Syscall mapping failures (e.g. unhandled ioctl or unimplemented syscall) must be tagged with `unsupported_syscall` in ZCF's DiagnosticEngine.
