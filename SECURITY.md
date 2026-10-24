# Security and Research Policy

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Security Model:** Least-Privilege Static Inspection & Isolated Sandboxing  

---

## 1. Responsible Research Boundaries

1. **Authorization and Compliance:**
   - ZCF is designed to analyze software you have legitimate permission, licenses, or rights to examine.
   - Do not use ZCF to circumvent anti-tamper mechanisms, extract cryptographic keys, or violate software licensing terms.
2. **Never Blindly Execute Untrusted Binaries:**
   - Always run static inspection (`zcf inspect`) first.
   - Dynamic execution must only occur inside isolated containers, disposable prefixes, or non-root sandboxes.
3. **Privacy and Secret Scrubbing:**
   - ZCF automated reports scrub private paths, user tokens, and environment secrets before publishing evidence bundles.

---

## 2. Vulnerability Reporting

If you identify a security vulnerability (such as a path traversal vulnerability in an artifact unpacker or command injection in a runtime adapter):
- Please report it confidentially to `security@zyntrixlabs.org` (or via private GitHub Security Advisory).
- Do not disclose zero-day vulnerabilities in public issue trackers.
- The ZCF team will acknowledge receipt within 48 hours and work with you on a coordinated disclosure timeline.
