# ADR-001: Selection of Core Implementation Language and Runtime

**Status:** Accepted  
**Date:** October 24, 2026  
**Deciders:** ZCF Core Engineering Team  

## Context
ZCF must be cross-distribution and cross-platform, capable of running seamlessly on Linux distributions (Ubuntu, Fedora, Arch, Debian, Alpine), BSD systems, and dual Windows/WSL environments. It requires rich standard library support for raw byte parsing (struct unpacking), subprocess orchestration, JSON schema validation, and system inspection.

We evaluated three potential primary implementation stacks:
1. **Rust:** High performance, memory safety, single static binary. However, compile times for rapid autonomous evolution and scripting flexibility are slower during early foundation milestones.
2. **TypeScript / Node.js:** Strong agent ecosystem (aligns with REA MCP server), but requires Node.js runtime everywhere, which is heavier on minimal Linux installations.
3. **Python 3 (3.10+):** Universally pre-installed on virtually all Linux distributions (`/usr/bin/python3`), excellent native binary struct unpacking (`struct`), rich process management (`subprocess`), native dataclasses, and zero external build toolchain prerequisites for basic runtime orchestration.

## Decision
We select **Python 3 (3.10+) with strict static typing (`typing`, `dataclasses`, `enum`)** as the primary implementation language for the ZCF core framework, accompanied by the Python standard library. External dependencies are minimized to ensure zero-install portability across distributions.

## Consequences
- **Positive:**
  - Runs out of the box on Windows host, WSL2 Ubuntu 26.04, and any modern Linux distribution without compilation.
  - Zero-dependency core means ZCF can inspect systems even in minimal rescue or container environments.
  - Type annotations and strict schema validation prevent runtime type errors.
- **Negative:**
  - Compute-heavy JIT or decompiler components must be implemented in native C/Rust and invoked via CLI or FFI rather than written in pure Python.
