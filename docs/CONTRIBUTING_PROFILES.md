# Compatibility Profile Contribution Guidelines for ZCF

**Document:** `docs/CONTRIBUTING_PROFILES.md`  
**Schema Version:** `2.0`  
**License:** CC-BY-4.0  

---

## 1. Overview

ZCF's compatibility intelligence database records empirical, reproducible compatibility evidence across distributions, hardware, and runtimes. Every profile is backed by cryptographic SHA-256 binary digests and verification logs.

Contributors can submit profiles without writing Python code or modifying ZCF's core codebase.

---

## 2. Provenance Tiers & Evidence Statuses

| Tier (`provenance_tier`) | Description |
| :--- | :--- |
| `demo_fixture` | Synthetic demonstration records bundled for unit tests. |
| `community_untested` | Community submissions awaiting independent verification. |
| `automated_test` | Automatically verified and tested by automated CI test runners. |
| `maintainer_verified` | Core maintainer validated with complete hardware and log reproduction. |

| Status (`evidence_status`) | Description |
| :--- | :--- |
| `untested` | Profile declared but not yet executed in a verified test pass. |
| `community_reported` | User-submitted report with empirical test notes. |
| `reproduced` | Re-tested on at least one secondary hardware/distribution setup. |
| `verified` | Fully functional; passed all interactive or automated tests. |
| `incompatible` | Known fatal blocker (e.g. anti-cheat driver requirement). |

---

## 3. Submitting a Profile via CLI

Contributors can submit a compatibility profile directly from the terminal or Control Center:

```bash
# Submit a verified test outcome
zcf db submit \
  --app /path/to/app.exe \
  --runtime runtime.wine \
  --status verified_compatible \
  --contributor "Jane Doe <jane@example.com>" \
  --test-procedure "Launched app, tested file save, audio playback 100% functional."
```

Or programmatically in Python:

```python
from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.inspector.inspector import ApplicationInspector
from zcf.core.models import CompatibilityStatus

inspector = ApplicationInspector()
app = inspector.inspect("/path/to/app.exe")

db = CompatibilityDatabase()
entry = db.submit_profile(
    app=app,
    recommended_runtime="runtime.wine",
    status=CompatibilityStatus.VERIFIED_COMPATIBLE,
    contributor_name="Jane Doe",
    test_procedure="Clean prefix run; zero graphical glitches.",
)
print(f"Profile created: {entry.entry_id}")
```

---

## 4. Exporting and Sharing Evidence Bundles

Evidence bundles can be shared with other nodes or submitted via pull request:

```bash
# Export local verified records
zcf db export --output my_evidence_bundle.json

# Import community evidence bundle
zcf db import --file community_bundle.json
```
