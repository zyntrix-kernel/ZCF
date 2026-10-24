# ADR-002: Evidence-Backed Knowledge Representation and Schemas

**Status:** Accepted  
**Date:** October 24, 2026  
**Deciders:** ZCF Core Engineering Team  

## Context
Compatibility reports and databases in legacy ecosystems (e.g., Wine AppDB, ProtonDB) often suffer from subjective, anecdotal claims (e.g. "Game works great, Platinum rating" followed by reports of immediate crashes). ZCF requires reproducible, machine-verifiable data structures that can be consumed by automated orchestrators, CI pipelines, and agents.

## Decision
ZCF adopts an **Evidence-Backed Knowledge Schema** directly aligned with REA's provenance architecture. Every compatibility assertion, test result, or workaround profile must include:
1. **Target Identity:** Cryptographic hash (SHA-256), exact byte length, and parsed format headers.
2. **Environment Fingerprint:** Linux distribution, kernel release, host architecture, driver versions, and active display server.
3. **Execution Context:** Command line arguments, environment overrides (`WINEDLLOVERRIDES`, `VK_ICD_FILENAMES`), runner version.
4. **Observed Signals:** Return exit codes, normalized diagnostic signatures, and stderr/stdout logs.
5. **Authority Tag:** Tagged as `shipped-artifact`, `automated-test-run`, `manual-verification`, or `ai-hypothesis`.

## Consequences
- Subjective rating drift is eliminated.
- Automated regression test suites can validate database entries against reproducible test fixtures.
- Schemas are defined in standard JSON Schema Draft 2020-12, enabling cross-language validation.
