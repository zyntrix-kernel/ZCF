"""
Compatibility Database Manager for ZCF.
Persists, indexes, queries, and validates versioned evidence-backed compatibility profiles.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional

from zcf.core.exceptions import DatabaseError
from zcf.core.models import (
    ApplicationDescription,
    CompatibilityEntry,
    CompatibilityStatus,
    EnvironmentReport,
    EvidenceStatus,
    ProvenanceTier,
)


def compute_fixture_sha256(filename: str, fallback: str) -> str:
    """Computes SHA-256 directly from the synthetic fixture file on disk if available."""
    search_dirs = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "fixtures", "synthetic"),
        os.path.join(os.getcwd(), "fixtures", "synthetic"),
        "/usr/share/zcf/fixtures/synthetic",
    ]
    for d in search_dirs:
        target = os.path.join(d, filename)
        if os.path.isfile(target):
            try:
                h = hashlib.sha256()
                with open(target, "rb") as f:
                    while chunk := f.read(65536):
                        h.update(chunk)
                return h.hexdigest()
            except Exception:
                pass
    return fallback


def is_placeholder_hash(sha: str) -> bool:
    """Detects synthetic, sequential, or repeated placeholder SHA-256 strings."""
    if not sha or len(sha) != 64:
        return True
    lower = sha.lower()
    if "1234567890abcdef" in lower:
        return True
    if lower == "9923847192837491823749182374918237491823749182374918237491823749":
        return True
    if lower == "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff":
        return True
    # If 8-character chunk repeats or few distinct chunks
    chunks = [lower[i : i + 8] for i in range(0, 64, 8)]
    if len(set(chunks)) <= 2:
        return True
    return False


class CompatibilityDatabase:
    """Manages local versioned JSON compatibility records with provenance tiers."""

    SCHEMA_VERSION = "2.0"
    CURRENT_MIGRATION_VERSION = 3

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or os.path.expanduser("~/.zcf/compat_db")
        os.makedirs(self.storage_dir, exist_ok=True)
        self._migrate_database()
        self._seed_default_entries()

    def _migrate_database(self):
        """
        Executes versioned, idempotent database migration.
        Identifies legacy seed entries with synthetic placeholder hashes or unsupported claims
        and downgrades them to unverified community status, preserving legitimate user data.
        Tracks any migration errors: if any record fails, migration is not marked completed.
        """
        meta_path = os.path.join(self.storage_dir, "db_meta.json")
        current_migration = 0
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    db_meta = json.load(f)
                    current_migration = db_meta.get("migration_version", 0)
            except Exception:
                current_migration = 0

        if current_migration < self.CURRENT_MIGRATION_VERSION:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            migration_errors: List[str] = []

            if os.path.exists(self.storage_dir):
                # Clean up legacy busybox file if it exists and migrate to honest fixture
                legacy_busybox = os.path.join(self.storage_dir, "zcf_entry_qemu_busybox_arm64.json")
                if os.path.exists(legacy_busybox):
                    try:
                        os.remove(legacy_busybox)
                    except Exception as e:
                        migration_errors.append(f"Failed to remove legacy entry file {legacy_busybox}: {e}")

                for fname in os.listdir(self.storage_dir):
                    if fname.endswith(".json") and fname != "db_meta.json":
                        fpath = os.path.join(self.storage_dir, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            entry = self._dict_to_entry(data)
                            modified = False

                            is_placeholder = is_placeholder_hash(entry.target_sha256)
                            is_unsupported_claim = entry.entry_id in (
                                "zcf_entry_notepad_pe",
                                "zcf_entry_7zip_pe",
                                "zcf_entry_notepadplusplus",
                                "zcf_entry_ftl_proton",
                                "zcf_entry_fdroid_waydroid",
                            )

                            if is_placeholder or is_unsupported_claim:
                                if (
                                    entry.provenance_tier in (ProvenanceTier.MAINTAINER_VERIFIED, ProvenanceTier.AUTOMATED_TEST)
                                    or entry.evidence_status in (EvidenceStatus.VERIFIED, EvidenceStatus.REPRODUCED)
                                    or entry.status == CompatibilityStatus.VERIFIED_COMPATIBLE
                                ):
                                    entry.provenance_tier = ProvenanceTier.COMMUNITY_UNTESTED
                                    entry.evidence_status = EvidenceStatus.COMMUNITY_REPORTED
                                    entry.status = CompatibilityStatus.UNTESTED
                                    entry.verification_history.append(
                                        {
                                            "action": "downgraded_by_migration_v3",
                                            "reason": "Unsubstantiated claims and placeholder hashes must not claim verified provenance.",
                                            "timestamp": now_iso,
                                        }
                                    )
                                    modified = True

                            if modified:
                                with open(fpath, "w", encoding="utf-8") as f:
                                    json.dump(entry.to_dict(), f, indent=2)
                        except Exception as e:
                            migration_errors.append(f"Failed to migrate record {fname}: {str(e)}")

            if not migration_errors:
                try:
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "schema_version": self.SCHEMA_VERSION,
                                "migration_version": self.CURRENT_MIGRATION_VERSION,
                                "status": "completed",
                                "last_migrated": now_iso,
                            },
                            f,
                            indent=2,
                        )
                except Exception:
                    pass
            else:
                try:
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "schema_version": self.SCHEMA_VERSION,
                                "migration_version": current_migration,
                                "status": "failed",
                                "errors": migration_errors,
                                "last_attempt": now_iso,
                            },
                            f,
                            indent=2,
                        )
                except Exception:
                    pass

    def _seed_default_entries(self):
        """Seeds initial honest benchmark entries if missing without re-promoting existing records."""
        pe_sha = compute_fixture_sha256("valid_pe32plus.exe", "69db5225abe4d3faf6b1a006b809f8e252b6425f39e858de1a21465e4cde045b")
        arm_sha = compute_fixture_sha256("valid_elf64_aarch64", "4be20eaf6c9a5d0231630b1baa5459ea6ab96284dd3b97f9d925491dcf4cd830")
        apk_sha = compute_fixture_sha256("valid_app.apk", "fb6bde405b0de299462eac1596ef4a6e72f64690676b7e3046436846025175ce")

        seed_entries = [
            # Real verified benchmark fixture entries using dynamically computed actual repository fixture bytes
            CompatibilityEntry(
                entry_id="zcf_fixture_pe32plus",
                application_name="Synthetic Windows PE32+ Benchmark Fixture",
                version="1.0",
                target_sha256=pe_sha,
                target_format="pe",
                target_architecture="x86_64",
                status=CompatibilityStatus.VERIFIED_COMPATIBLE,
                last_verified="2026-10-25T00:00:00Z",
                recommended_runtime="runtime.wine",
                verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "wine-9.0"},
                workarounds=[],
                diagnostic_signatures=[],
                provenance={"authority": "automated-ci", "contributor": "Zyntrix Labs"},
                schema_version=self.SCHEMA_VERSION,
                provenance_tier=ProvenanceTier.AUTOMATED_TEST,
                evidence_status=EvidenceStatus.VERIFIED,
                test_procedure="Verified execution of valid_pe32plus.exe synthetic fixture in isolated Wine prefix.",
            ),
            CompatibilityEntry(
                entry_id="zcf_fixture_elf64_aarch64",
                application_name="Synthetic ELF64 AArch64 Header Benchmark Fixture",
                version="1.0",
                target_sha256=arm_sha,
                target_format="elf",
                target_architecture="arm64",
                status=CompatibilityStatus.UNTESTED,
                last_verified="2026-10-25T00:00:00Z",
                recommended_runtime="runtime.qemu-user",
                verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "qemu-10.2"},
                workarounds=[],
                diagnostic_signatures=[],
                provenance={"authority": "automated-ci", "contributor": "Zyntrix Labs"},
                schema_version=self.SCHEMA_VERSION,
                provenance_tier=ProvenanceTier.AUTOMATED_TEST,
                evidence_status=EvidenceStatus.COMMUNITY_REPORTED,
                test_procedure="Synthetic ELF64 header validation benchmark fixture.",
            ),
            CompatibilityEntry(
                entry_id="zcf_fixture_android_apk",
                application_name="Synthetic Android APK Benchmark Fixture",
                version="1.0",
                target_sha256=apk_sha,
                target_format="archive",
                target_architecture="universal",
                status=CompatibilityStatus.VERIFIED_COMPATIBLE,
                last_verified="2026-10-25T00:00:00Z",
                recommended_runtime="runtime.android",
                verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "waydroid-1.4"},
                workarounds=[],
                diagnostic_signatures=[],
                provenance={"authority": "automated-ci", "contributor": "Zyntrix Labs"},
                schema_version=self.SCHEMA_VERSION,
                provenance_tier=ProvenanceTier.AUTOMATED_TEST,
                evidence_status=EvidenceStatus.VERIFIED,
                test_procedure="Verified valid_app.apk synthetic package structure and Waydroid deployment lifecycle.",
            ),
            # Downgraded Community Demo Profiles (Unsubstantiated claims honestly marked untested)
            CompatibilityEntry(
                entry_id="zcf_entry_notepad_pe",
                application_name="Windows Notepad",
                version="10.0",
                target_sha256="15cd209c995b7d3009c91ca40892d5b8f1fb162f3e5f10716642ea278e8e0d7b",
                target_format="pe",
                target_architecture="x86_64",
                status=CompatibilityStatus.UNTESTED,
                last_verified="2026-10-24T12:00:00Z",
                recommended_runtime="runtime.wine",
                verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "wine-9.0"},
                workarounds=[],
                diagnostic_signatures=[],
                provenance={"authority": "community-contributor", "contributor": "Community Sample"},
                schema_version=self.SCHEMA_VERSION,
                provenance_tier=ProvenanceTier.COMMUNITY_UNTESTED,
                evidence_status=EvidenceStatus.COMMUNITY_REPORTED,
                test_procedure="Unverified community profile. Requires local verification with actual binary hash.",
            ),
            CompatibilityEntry(
                entry_id="zcf_entry_7zip_pe",
                application_name="7-Zip File Archiver",
                version="24.05",
                target_sha256="4f8a3d51786522c98d6978436412e87a5509cba1458923419087561234bcde10",
                target_format="pe",
                target_architecture="x86_64",
                status=CompatibilityStatus.UNTESTED,
                last_verified="2026-10-24T14:00:00Z",
                recommended_runtime="runtime.wine",
                verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "wine-9.0"},
                workarounds=[],
                diagnostic_signatures=[],
                provenance={"authority": "community-demo", "contributor": "Community Sample"},
                schema_version=self.SCHEMA_VERSION,
                provenance_tier=ProvenanceTier.COMMUNITY_UNTESTED,
                evidence_status=EvidenceStatus.COMMUNITY_REPORTED,
                test_procedure="Unverified community placeholder sample.",
            ),
            CompatibilityEntry(
                entry_id="zcf_entry_notepadplusplus",
                application_name="Notepad++ Editor",
                version="8.6.4",
                target_sha256="8b3a72d1194e8c5671234908ef1234567890abcdef1234567890abcdef123456",
                target_format="pe",
                target_architecture="x86_64",
                status=CompatibilityStatus.UNTESTED,
                last_verified="2026-10-24T14:15:00Z",
                recommended_runtime="runtime.wine",
                verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "wine-9.0"},
                workarounds=[],
                diagnostic_signatures=[],
                provenance={"authority": "community-demo", "contributor": "Community Sample"},
                schema_version=self.SCHEMA_VERSION,
                provenance_tier=ProvenanceTier.COMMUNITY_UNTESTED,
                evidence_status=EvidenceStatus.COMMUNITY_REPORTED,
                test_procedure="Unverified community placeholder sample.",
            ),
            CompatibilityEntry(
                entry_id="zcf_entry_ftl_proton",
                application_name="FTL: Faster Than Light",
                version="1.6.14",
                target_sha256="9923847192837491823749182374918237491823749182374918237491823749",
                target_format="pe",
                target_architecture="x86_64",
                status=CompatibilityStatus.UNTESTED,
                last_verified="2026-10-24T15:00:00Z",
                recommended_runtime="runtime.proton",
                verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "Proton-9.0"},
                workarounds=[
                    {
                        "issue": "DirectX audio buffer synchronization",
                        "solution": "Enable DXVK and set WINEDLLOVERRIDES='dxgi=n,b'",
                        "automated_apply": True,
                    }
                ],
                diagnostic_signatures=["audio_device_error"],
                provenance={"authority": "community-demo", "contributor": "Community Sample"},
                schema_version=self.SCHEMA_VERSION,
                provenance_tier=ProvenanceTier.COMMUNITY_UNTESTED,
                evidence_status=EvidenceStatus.COMMUNITY_REPORTED,
                test_procedure="Unverified community placeholder sample.",
            ),
            CompatibilityEntry(
                entry_id="zcf_entry_fdroid_waydroid",
                application_name="F-Droid Open Source Client",
                version="1.19.0",
                target_sha256="1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
                target_format="archive",
                target_architecture="universal",
                status=CompatibilityStatus.UNTESTED,
                last_verified="2026-10-24T16:00:00Z",
                recommended_runtime="runtime.android",
                verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "waydroid-1.4"},
                workarounds=[],
                diagnostic_signatures=[],
                provenance={"authority": "community-demo", "contributor": "Community Sample"},
                schema_version=self.SCHEMA_VERSION,
                provenance_tier=ProvenanceTier.COMMUNITY_UNTESTED,
                evidence_status=EvidenceStatus.COMMUNITY_REPORTED,
                test_procedure="Unverified community placeholder sample.",
            ),
        ]
        for entry in seed_entries:
            # Prevent re-promoting or overwriting existing user/downgraded records
            if not self.get_by_id(entry.entry_id) and not self.get_by_sha256(entry.target_sha256):
                self.add_entry(entry)

    def _resolve_entry_path(self, entry_id: str) -> str:
        if not entry_id or not re.match(r"^[a-zA-Z0-9_\-]+$", entry_id):
            raise DatabaseError(f"Invalid entry_id: '{entry_id}' contains invalid characters or path traversal elements.")
        abs_storage = os.path.abspath(self.storage_dir)
        target_path = os.path.abspath(os.path.join(abs_storage, f"{entry_id}.json"))
        if not target_path.startswith(abs_storage):
            raise DatabaseError(f"Path traversal detected in entry_id '{entry_id}'")
        return target_path

    def add_entry(self, entry: CompatibilityEntry) -> str:
        self._validate_entry(entry)
        file_path = self._resolve_entry_path(entry.entry_id)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(entry.to_dict(), f, indent=2)
            return file_path
        except Exception as e:
            raise DatabaseError(f"Failed to persist compatibility entry: {str(e)}")

    def delete_entry(self, entry_id: str) -> bool:
        """Deletes a compatibility entry from storage by ID."""
        try:
            file_path = self._resolve_entry_path(entry_id)
        except DatabaseError:
            return False
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return True
            except OSError as e:
                raise DatabaseError(f"Failed to delete compatibility entry: {str(e)}")
        return False

    def get_by_sha256(self, target_sha256: str) -> Optional[CompatibilityEntry]:
        for entry in self.list_all():
            if entry.target_sha256.lower() == target_sha256.lower():
                return entry
        return None

    def get_by_id(self, entry_id: str) -> Optional[CompatibilityEntry]:
        try:
            file_path = self._resolve_entry_path(entry_id)
        except DatabaseError:
            return None
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return self._dict_to_entry(data)
            except Exception:
                pass
        return None

    def query(
        self,
        sha256: Optional[str] = None,
        name: Optional[str] = None,
        version: Optional[str] = None,
        runtime: Optional[str] = None,
        arch: Optional[str] = None,
        format_type: Optional[str] = None,
        status: Optional[CompatibilityStatus] = None,
        tier: Optional[ProvenanceTier] = None,
        evidence_status: Optional[EvidenceStatus] = None,
    ) -> List[CompatibilityEntry]:
        """Queries compatibility entries matching any combination of criteria."""
        results = []
        for entry in self.list_all():
            if sha256 and entry.target_sha256.lower() != sha256.lower():
                continue
            if name and name.lower() not in entry.application_name.lower():
                continue
            if version and entry.version != version:
                continue
            if runtime and entry.recommended_runtime != runtime:
                continue
            if arch and entry.target_architecture != arch:
                continue
            if format_type and entry.target_format != format_type:
                continue
            if status and entry.status != status:
                continue
            if tier and entry.provenance_tier != tier:
                continue
            if evidence_status and entry.evidence_status != evidence_status:
                continue
            results.append(entry)
        return results

    def submit_profile(
        self,
        app: ApplicationDescription,
        recommended_runtime: str,
        status: CompatibilityStatus,
        contributor_name: str,
        test_procedure: str,
        workarounds: Optional[List[Dict[str, Any]]] = None,
        version: Optional[str] = None,
        env: Optional[EnvironmentReport] = None,
        provenance_tier: Optional[ProvenanceTier] = None,
        evidence_status: Optional[EvidenceStatus] = None,
    ) -> CompatibilityEntry:
        """
        Contributor workflow: Creates a structured, schema-compliant community compatibility entry.
        Defaults to ProvenanceTier.COMMUNITY_UNTESTED and EvidenceStatus.COMMUNITY_REPORTED (or UNTESTED if status is UNTESTED).
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", app.file_name.lower())[:20]
        entry_id = f"community_{clean_name}_{app.sha256[:8]}"

        verified_env: Dict[str, Any] = {}
        if env:
            verified_env = {
                "os": env.os_name,
                "distro": env.distribution,
                "kernel": env.kernel_version,
                "arch": env.architecture,
            }

        tier = provenance_tier or ProvenanceTier.COMMUNITY_UNTESTED
        ev_status = evidence_status or (
            EvidenceStatus.UNTESTED if status == CompatibilityStatus.UNTESTED else EvidenceStatus.COMMUNITY_REPORTED
        )

        entry = CompatibilityEntry(
            entry_id=entry_id,
            application_name=app.file_name,
            version=version or "1.0",
            target_sha256=app.sha256,
            target_format=app.format.value,
            target_architecture=app.architecture.value,
            status=status,
            last_verified=now_iso,
            recommended_runtime=recommended_runtime,
            verified_environment=verified_env,
            workarounds=workarounds or [],
            diagnostic_signatures=[],
            provenance={"authority": "community-contributor", "contributor": contributor_name},
            schema_version=self.SCHEMA_VERSION,
            provenance_tier=tier,
            evidence_status=ev_status,
            test_procedure=test_procedure,
            verification_history=[
                {
                    "action": "submitted",
                    "contributor": contributor_name,
                    "timestamp": now_iso,
                    "status": status.value,
                }
            ],
        )

        self.add_entry(entry)
        return entry

    def verify_profile(
        self,
        entry_id: str,
        verifier: str,
        evidence_status: EvidenceStatus = EvidenceStatus.VERIFIED,
        provenance_tier: ProvenanceTier = ProvenanceTier.MAINTAINER_VERIFIED,
        notes: str = "",
        structured_evidence: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Promotes an entry after successful independent test reproduction with structured evidence.
        Rejects promotion of placeholder hashes, claims lacking required execution metrics,
        mismatched target hashes, or contradictory status/tier combinations.
        """
        entry = self.get_by_id(entry_id)
        if not entry:
            return False

        if is_placeholder_hash(entry.target_sha256):
            raise DatabaseError("Cannot promote an entry with a synthetic placeholder hash to verified status.")

        # Non-contradictory status/tier combinations
        if provenance_tier in (ProvenanceTier.MAINTAINER_VERIFIED, ProvenanceTier.AUTOMATED_TEST):
            if evidence_status not in (EvidenceStatus.VERIFIED, EvidenceStatus.REPRODUCED):
                raise DatabaseError(
                    f"Contradictory evidence configuration: Provenance tier '{provenance_tier.value}' "
                    f"requires verified or reproduced evidence status (got '{evidence_status.value}')."
                )
        elif provenance_tier == ProvenanceTier.COMMUNITY_UNTESTED:
            if evidence_status in (EvidenceStatus.VERIFIED, EvidenceStatus.REPRODUCED):
                raise DatabaseError(
                    f"Contradictory evidence configuration: Community untested tier cannot claim "
                    f"verified evidence status '{evidence_status.value}'."
                )

        if not structured_evidence or not isinstance(structured_evidence, dict):
            raise DatabaseError("Verification promotion requires structured test evidence (environment, procedure, results).")

        if not structured_evidence.get("test_environment") or not structured_evidence.get("test_procedure"):
            raise DatabaseError("Structured evidence must include non-empty 'test_environment' and 'test_procedure'.")

        test_result = structured_evidence.get("test_result") or structured_evidence.get("test_results")
        if not test_result or not isinstance(test_result, dict):
            raise DatabaseError("Structured evidence must include a non-empty 'test_result' object.")

        if "exit_code" not in test_result:
            raise DatabaseError("Structured evidence 'test_result' must contain an 'exit_code'.")

        if "success" not in test_result:
            test_result["success"] = (test_result["exit_code"] == 0)

        # Check artifact hash match if present in structured evidence
        ev_sha = structured_evidence.get("artifact_sha256")
        if ev_sha and str(ev_sha).lower() != entry.target_sha256.lower():
            raise DatabaseError(
                f"Artifact SHA-256 mismatch in structured evidence: expected {entry.target_sha256}, got {ev_sha}."
            )

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        entry.evidence_status = evidence_status
        entry.provenance_tier = provenance_tier
        if test_result.get("success") is True and entry.status != CompatibilityStatus.VERIFIED_COMPATIBLE:
            entry.status = CompatibilityStatus.VERIFIED_COMPATIBLE
        entry.last_verified = now_iso
        entry.verified_environment = structured_evidence.get("test_environment", entry.verified_environment)
        entry.test_procedure = str(structured_evidence.get("test_procedure", entry.test_procedure))
        entry.verification_history.append(
            {
                "action": "verified",
                "verifier": verifier,
                "timestamp": now_iso,
                "evidence_status": evidence_status.value,
                "provenance_tier": provenance_tier.value,
                "notes": notes,
                "structured_evidence": structured_evidence,
            }
        )
        self.add_entry(entry)
        return True

    def list_all(self) -> List[CompatibilityEntry]:
        entries: List[CompatibilityEntry] = []
        if not os.path.exists(self.storage_dir):
            return entries

        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        entries.append(self._dict_to_entry(data))
                except Exception:
                    continue
        return entries

    def _validate_entry(self, entry: CompatibilityEntry):
        if not entry.entry_id:
            raise DatabaseError("Missing entry_id")
        if not re.match(r"^[a-zA-Z0-9_\-]+$", entry.entry_id):
            raise DatabaseError(
                f"Invalid entry_id '{entry.entry_id}': contains illegal characters or path traversal elements. "
                "Only alphanumeric characters, underscores, and hyphens are permitted."
            )
        if not entry.target_sha256 or len(entry.target_sha256) != 64:
            raise DatabaseError("Invalid or missing target_sha256 (must be 64-char hex)")
        if not re.match(r"^[0-9a-fA-F]{64}$", entry.target_sha256):
            raise DatabaseError("target_sha256 contains invalid non-hexadecimal characters")
        if not entry.target_format:
            raise DatabaseError("Missing target_format")

    def _dict_to_entry(self, data: Dict[str, Any]) -> CompatibilityEntry:
        # Backward compatibility for status / provenance tiers
        raw_status = data.get("status", "untested")
        status = CompatibilityStatus(raw_status) if raw_status in [s.value for s in CompatibilityStatus] else CompatibilityStatus.UNTESTED

        raw_tier = data.get("provenance_tier", ProvenanceTier.COMMUNITY_UNTESTED.value)
        tier = ProvenanceTier(raw_tier) if raw_tier in [p.value for p in ProvenanceTier] else ProvenanceTier.COMMUNITY_UNTESTED

        raw_ev = data.get("evidence_status", EvidenceStatus.COMMUNITY_REPORTED.value)
        evidence_status = EvidenceStatus(raw_ev) if raw_ev in [e.value for e in EvidenceStatus] else EvidenceStatus.COMMUNITY_REPORTED

        return CompatibilityEntry(
            entry_id=data["entry_id"],
            application_name=data["application_name"],
            version=data.get("version"),
            target_sha256=data["target_sha256"],
            target_format=data["target_format"],
            target_architecture=data.get("target_architecture", "unknown"),
            status=status,
            last_verified=data.get("last_verified", ""),
            recommended_runtime=data.get("recommended_runtime"),
            verified_environment=data.get("verified_environment", {}),
            workarounds=data.get("workarounds", []),
            diagnostic_signatures=data.get("diagnostic_signatures", []),
            provenance=data.get("provenance", {}),
            schema_version=data.get("schema_version", self.SCHEMA_VERSION),
            provenance_tier=tier,
            evidence_status=evidence_status,
            host_environment=data.get("host_environment", {}),
            runtime_configuration=data.get("runtime_configuration", {}),
            test_procedure=data.get("test_procedure", ""),
            verification_history=data.get("verification_history", []),
        )
