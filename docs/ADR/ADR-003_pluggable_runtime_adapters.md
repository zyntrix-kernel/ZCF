# ADR-003: Pluggable Runtime Adapter Interface

**Status:** Accepted  
**Date:** October 24, 2026  
**Deciders:** ZCF Core Engineering Team  

## Context
Compatibility technologies operate with vastly different primitives:
- Wine requires prefix paths, wineserver lifecycle management, and Windows registry initialization.
- QEMU User requires target sysroot directory flags (`-L`) and system call translation.
- Box64 requires wrapped library search paths and custom dynarec tuning.
- Native Linux execution requires standard process spawning with environment filtering.

Forcing all compatibility mechanisms into a generic "runner" interface without considering their specific lifecycle leads to leaky abstractions or lowest-common-denominator limitations.

## Decision
ZCF establishes a **Pluggable Runtime Adapter Interface** (`RuntimeAdapterInterface`) with distinct lifecycle phases:
1. `is_available(env)`: Detects whether host dependencies and binaries are installed.
2. `validate(app, env)`: Evaluates whether the adapter can execute the specific application artifact on this host.
3. `prepare_environment(app, config)`: Creates isolated prefixes, sets up temporary overlays, and mounts necessary libraries.
4. `execute(app, context)`: Spawns the process under security controller constraints, streaming diagnostics.
5. `cleanup(context)`: Tear down disposable state, ensuring zero persistent pollution.

## Consequences
- Clean separation between core planning logic and runtime mechanics.
- New runtimes (e.g. FEX, Waydroid, Proton GE) can be integrated without modifying the core compatibility planner.
