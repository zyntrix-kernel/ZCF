# Zyntrix Compatibility Fabric (ZCF) Governance

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Status:** Open-Source Community Project  
**Founding Organization:** Zyntrix Labs  

---

## 1. Core Principles

1. **Ecosystem Independence:** ZCF is designed for the broader Linux ecosystem. While Zyntrix OS serves as the flagship desktop showcase, ZCF must run identically on Ubuntu, Arch Linux, Fedora, Debian, Alpine, and other distributions. No core feature may be locked to Zyntrix OS.
2. **Community Parity:** All core code, tests, documentation, compatibility entries, and schemas are developed publicly in the open-source repository under Apache-2.0.
3. **No Commercial Paywalls in Core:** ZCF core tools, CLI, planning engines, and databases shall never require paid licenses, product keys, cloud activation, or telemetry. Zyntrix Labs may offer value-added enterprise services (managed fleet testing, private lab infrastructure), but the open-source core remains self-sufficient.

---

## 2. Decision Making and RFC Process

- **Architectural Changes:** Major additions (new runtime adapters, schema revisions, new planning algorithms) require a written Architecture Decision Record (ADR) or Request for Comments (RFC) submitted as an issue/PR.
- **Maintainership:** Maintainers are selected based on technical merit, consistency of contributions, and adherence to security and verification principles.
- **Fail-Closed Verification:** Proposals that reduce test rigor or encourage speculative compatibility ratings without empirical evidence are rejected.
