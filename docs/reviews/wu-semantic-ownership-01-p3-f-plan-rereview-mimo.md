# WU-SEMANTIC-OWNERSHIP-01 P3-F Plan Re-Review (AgentMiMo)

## Review Target

- Plan: `docs/host/wu-semantic-ownership-01-p3-f-fins-source-provenance-plan.md`
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-F - Fins source document, blob, provenance, citation, and wait timeout ownership`
- Fix report: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-fix-controller-validation.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-review-controller-adjudication.md`
- Original MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-review-mimo.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-review-ds.md`

## Review Scope

Re-review only: verify that all 8 accepted plan-fix requirements (P3-F-PF-01 through P3-F-PF-08) are closed in the updated plan. Do not re-review the full plan from scratch.

## Accepted Fix Verification

### P3-F-PF-01 - staging source idempotency/retry, SEC insertion point, placeholders, tests

**Status: closed**

Plan updates verified:

1. `stage_source_document(...)` semantics section defines: first call creates `ingest_complete=False` meta; repeated call with matching stable fields returns same `SourceHandle` idempotently; repeated call with mismatched fields fails closed; existing completed source meta fails with conflict exception. (Proposed Contracts / APIs)
2. SEC staging insertion point: "in `dayu/fins/pipelines/sec_download_filing_workflow.py`, after the target `SourceHandle` is known and before calling either downloader path that receives `store_file=host._build_store_file(source_handle=source_handle)`." Stream and non-stream branches both downstream of staging. (Slice 2)
3. Staging placeholder: `ingest_complete=False`, valid `source_kind=filing`, valid `source_provider=sec_edgar`, valid `ingest_method=download`, stable SEC identity/fingerprint fields when available, `primary_document=None`, empty/omitted `files`/`file_entries`. Must not be listable/readable as completed. (Slice 2)
4. Tests cover: first staging, repeated idempotent staging, mismatched-field failure, completed-source conflict, staging-to-complete commit, failed/retried SEC download reuses matching staging. (Slice 2)

Code fact confirmation: `_wait_record_row` at `waiting.py:2158-2161` confirms `deadline_at` derived from `await_spec.deadline` (can be `None`); `expires_at=None` hardcoded. No-boundary case is real.

### P3-F-PF-02 - provenance lookup signature vs citation routing context

**Status: closed**

Plan updates verified:

1. `_build_citation` obtains `source_kind` by reading source meta as a routing key, then calls `get_source_document_provenance(ticker, document_id, source_kind)`. (Owner Boundary, Slice 1)
2. `source_kind` kept in provenance method signature — matches existing repository addressing, avoids cross-kind search. (Proposed Contracts)
3. Meta reads for citation business fields only (form_type, filing_date, accession_no, fiscal period, heading); source classification from `SourceDocumentProvenance`. (Owner Boundary, Slice 1)
4. `_build_citation` removes all `document_id.startswith("fil_")` classification logic. (Slice 1)
5. Validation scans: `_build_citation` scan shows one helper definition and all call sites through it. (Slice 1)

Code fact confirmation: current `_build_citation` at `read_runtime.py:1695-1708` uses `document_id.startswith("fil_")` and `ingest_method` for classification — exactly the pattern the plan removes.

### P3-F-PF-03 - exact LLM-facing SourceType and Citation.source_provider values

**Status: closed**

Plan updates verified:

1. `SourceType` enum values explicitly listed: `SEC_EDGAR = "SEC_EDGAR"`, `CNINFO = "CNINFO"`, `HKEXNEWS = "HKEXNEWS"`, `UPLOADED = "UPLOADED"`, `SUPPLEMENTARY = "SUPPLEMENTARY"`. (Proposed Contracts)
2. `Citation.source_provider` output strings: uppercase self-explanatory business names derived from `FinsSourceProvider` — `SEC_EDGAR`, `CNINFO`, `HKEXNEWS`, `USER_UPLOAD`. (Proposed Contracts)
3. `source_provider` visible in `Citation.to_dict()` when non-`None`; omitted when `None`. `None` allowed only for non-source-backed transitional citations. (Proposed Contracts)
4. Complete mapping table: SEC → `source_type="SEC_EDGAR"`, `source_provider="SEC_EDGAR"`; CNINFO → `source_type="CNINFO"`, `source_provider="CNINFO"`; HKEXNEWS → `source_type="HKEXNEWS"`, `source_provider="HKEXNEWS"`; upload → `source_type="UPLOADED"`, `source_provider="USER_UPLOAD"`; supplementary → `source_type="SUPPLEMENTARY"`, `source_provider` from provenance. (Proposed Contracts)
5. Tests assert exact citation output strings for all five paths. (Slice 1)

### P3-F-PF-04 - company metadata freshness mechanism

**Status: closed**

Plan updates verified:

1. `RESOLVER_VERSION` owned by `dayu/fins/pipelines/upload_company_meta.py`; changes only when upload company identity normalization or required-field semantics change. Not a release version, schema version, market-data recency marker, or cache TTL. (Proposed Contracts)
2. Current-scope rule: upload preserves existing meta only when `resolver_version` matches; mismatch requires current company fields and upsert. No time-based TTL. (Proposed Contracts, Slice 4)
3. Tests: same-version meta preserved with existing warning; older-version meta (constructed explicitly in test) refreshed from current upload fields; stale meta plus missing `company_name` raises validation error. (Slice 4)
4. `RESOLVER_VERSION` ownership and change rule documented and tested. (Propagation Audit)

### P3-F-PF-05 - blob/source validation boundary, ProcessedHandle scope, TOCTOU classification

**Status: closed**

Plan updates verified:

1. Enforcement layer: blob repository performs final guard. (Proposed Contracts)
2. Dependency mechanism: filesystem implementation receives source-meta existence/provenance reader by constructor injection or shared lower-level storage core. Must not import concrete higher-layer repository, pipeline, service, Host, or UI object. (Proposed Contracts)
3. `ProcessedHandle` remains under processed artifact ownership, not widened in P3-F unless implementation evidence shows same orphan-source bug. (Proposed Contracts)
4. TOCTOU classification: accepted residual for single storage assembly; multi-worker writes must either use existing workspace file lock or record a follow-up owner. (Proposed Contracts, Risks)

### P3-F-PF-06 - slice dependency and shared staging/protocol ownership

**Status: closed**

Plan updates verified:

1. Slice 1 owns shared domain/protocol surface: `FinsSourceProvider`, `SourceDocumentProvenance`, `get_source_document_provenance(...)`, and `stage_source_document(...)` protocol signature plus filesystem repository core. (Slice 1)
2. Slice 2 consumes `stage_source_document(...)`; must not add parallel staging protocol. (Slice 2)
3. CN staging must align with same source repository invariant. `update_cn_staging_source_document(...)` may remain as workflow-shaped helper but must delegate to or be semantically backed by same `stage_source_document(...)` idempotency and conflict rules. (Slice 2)

### P3-F-PF-07 - fixture/source-meta migration impact

**Status: closed**

Plan updates verified:

1. Required fixture/source-meta scan before Slice 1: `rg` commands for completed source meta and meta.json fixtures. (Slice 1)
2. Likely affected fixtures listed: `tests/fins/fixtures/**/meta.json`, SEC/CN/HK downloaded filing fixtures, upload filing/material workspace fixtures, read-runtime fixtures. (Slice 1)
3. Rule: completed source meta loaded through new provenance contract must include valid `source_provider`; missing provider fails closed by design; tests migrated to new schema rather than adding production prefix fallback. (Slice 1, Risks)

### P3-F-PF-08 - wait boundary availability and no-boundary behavior

**Status: closed**

Plan updates verified:

1. Host wait creation evidence: `dayu/host/waiting.py:_wait_record_row` derives `deadline_at` from `candidate.await_spec.deadline` and writes `expires_at=None`. (Slice 3)
2. Boundary precedence: `deadline_at` first, then `expires_at`, matching `dayu/host/wait_callback.py:_stale_status_or_none`. (Slice 3)
3. No-boundary behavior: `WaitPollNotReady` for transient unavailable when no boundary present. Rationale: Fins adapter is not lifecycle owner; practical retry cadence bounded by Host poller policy (`WaitPollerRuntimePolicy.not_ready_observe_interval_seconds`, claim TTL, backoff, close/cancel lifecycle); true terminal loss is Host/user cancellation, explicit callback/poll loss, or Host-owned deadline/expires boundary. (Proposed Contracts, Slice 3)
4. Invalid boundary: fail closed as `WaitPollLost` only if boundary present but invalid. (Slice 3)
5. Tests: future `deadline_at` → `WaitPollNotReady`; past `deadline_at` → `WaitPollLost`; no `deadline_at` + past `expires_at` → `WaitPollLost`; invalid boundary → `WaitPollLost`; no boundary → `WaitPollNotReady`; `created_at` older than 300s no longer makes result lost when no boundary. (Slice 3)

## New Material Findings

None. The updated plan addresses all 8 accepted fixes with sufficient specificity for code generation. No new material issues identified during re-review.

## Open Questions

All original open questions are either resolved by plan updates or properly scoped as implementation-verification items:

1. **Host no-boundary frequency** (originally MiMo OQ-01): Plan now requires implementation to inspect Host wait creation for Fins awaiting tools. No-boundary behavior justified with Host poller policy reference. Acceptable for implementation gate.
2. **`_build_citation` routing vs provenance** (originally MiMo OQ-04): Plan explicitly distinguishes meta reads for routing key vs provenance projection for classification. Resolved.
3. **Staging cleanup** (originally MiMo OQ-03): Deferred with explicit acceptance criteria. Acceptable.
4. **`_build_citation` call sites** (originally MiMo residual 4): Plan validation scans confirm all call sites through one helper. Resolved.

## Residual Risks

1. Fixture/source-meta migration work: plan requires scan before Slice 1, but actual volume depends on existing fixture count. Mitigation: scan is mandatory, not optional.
2. `RESOLVER_VERSION` may never change in practice, making freshness check a no-op for existing data. Mitigation: test constructs older-version metadata explicitly; plan documents change rule.
3. TOCTOU residual in blob write: accepted with clear multi-worker escalation path. Low risk for current single-assembly Host.

## Conclusion

**pass**

All 8 accepted plan-fix requirements (P3-F-PF-01 through P3-F-PF-08) are closed in the updated plan. No new material plan findings. The plan is code-generation-ready for implementation agent handoff.
