# WU-SEMANTIC-OWNERSHIP-01 P3-F Plan Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-F - Fins source document, blob, provenance, citation, and wait timeout ownership`
- Gate: plan review
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-f-fins-source-provenance-plan.md`
- MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-review-ds.md`

## Review Results

| Reviewer | Conclusion | Material findings | Open questions |
| --- | --- | ---: | ---: |
| AgentMiMo | pass-with-risks | 5 | 4 |
| AgentDS | pass-with-risks | 6 | 3 |

Both reviewers accepted the P3-F motivation and owner-boundary direction. The plan is not yet accepted because multiple findings identify underspecified contracts that would force the implementation agent to design core behavior during implementation.

## Merged Finding Adjudication

### P3-F-PF-01 - Define staging source idempotency and retry semantics

- Sources: MiMo 01; DS-F02; DS OQ-03
- Decision: accepted
- Required plan fix:
  - Define `stage_source_document` behavior for first call, repeated call with existing `ingest_complete=False`, existing completed source meta, and mismatched request fields.
  - Specify SEC staging insertion point in concrete function(s): after the target `SourceHandle` is known and before any downloader `store_file` callback can run.
  - Specify staging placeholder requirements for SEC before files are known: `ingest_complete=False`, valid source kind/provider/ingest method, no completed file membership claim, and read/list exclusion.
  - Add tests for first staging, repeated staging, staging-to-complete commit, failed/retried SEC download, and completed-source conflict.

### P3-F-PF-02 - Resolve provenance lookup signature versus citation caller context

- Sources: MiMo 02; MiMo OQ-04
- Decision: accepted
- Required plan fix:
  - State exactly how `_build_citation` obtains the routing `source_kind` without using it as provenance truth.
  - Decide whether `get_source_document_provenance(...)` takes `source_kind` or searches across source kinds; justify the choice.
  - Preserve meta reads only for citation business fields such as form type, filing date, accession number, fiscal year, and heading; source classification must come from provenance projection.
  - Add validation that all citation call sites still route through one helper.

### P3-F-PF-03 - Name LLM-facing SourceType and source_provider values explicitly

- Sources: MiMo 03; MiMo 04; DS-F01
- Decision: accepted
- Required plan fix:
  - Explicitly name any new `SourceType` enum values and their output strings.
  - Define `Citation.source_provider` output format, whether it appears in `Citation.to_dict()`, whether `None` is allowed, and what it means.
  - Ensure LLM-facing values are self-explanatory and not internal implementation names.
  - Add tests asserting exact citation `source_type` and `source_provider` values for SEC, CNINFO, HKEXNEWS, upload, and material.

### P3-F-PF-04 - Tighten company metadata freshness mechanism

- Sources: DS-F03; MiMo residual 3
- Decision: accepted
- Required plan fix:
  - Define who owns `RESOLVER_VERSION`, when it changes, and why resolver-version mismatch is a current freshness boundary.
  - If resolver-version mismatch is retained, add tests that create older-version metadata and prove upload refreshes it.
  - If the simpler current rule is better, update the plan to refresh company meta from explicit upload fields without inventing a never-triggered freshness mechanism.
  - Keep time-based TTL out of P3-F unless the plan provides current production evidence and owner boundary.

### P3-F-PF-05 - Specify blob/source validation boundary and ProcessedHandle scope

- Sources: MiMo 05; DS-F04; DS OQ-01
- Decision: accepted
- Required plan fix:
  - State whether source acknowledgement is enforced inside blob repository, source repository, or pipeline/workflow layer.
  - If blob repository enforces it, specify dependency injection / shared repository core mechanism without reverse imports or concrete cross-layer coupling.
  - State that validation applies only to `SourceHandle` unless ProcessedHandle evidence proves current scope should widen.
  - Classify TOCTOU risk as accepted residual or require a file-lock/atomic strategy; do not leave it implicit.

### P3-F-PF-06 - Clarify slice dependency and shared protocol ownership

- Sources: DS-F05; DS OQ-02
- Decision: accepted
- Required plan fix:
  - State which slice introduces shared protocol methods and which later slices consume them.
  - Clarify whether CN staging migrates to the new `stage_source_document` method or remains a legacy-shaped caller of the same repository invariant.
  - Avoid two independent staging semantics.

### P3-F-PF-07 - Make fixture and migration impact explicit

- Sources: DS-F06; MiMo residual 1
- Decision: accepted
- Required plan fix:
  - Add a required fixture/source-meta scan before Slice 1 implementation.
  - List the fixture classes or directories likely to need `source_provider`.
  - State that completed source meta missing provider fails closed in new-schema behavior, while tests must be migrated rather than production code adding prefix fallback.

### P3-F-PF-08 - Verify wait boundary availability and no-boundary behavior

- Sources: MiMo OQ-01
- Decision: accepted
- Required plan fix:
  - Require inspection of Host wait record creation for Fins awaiting tools to determine whether `deadline_at` or `expires_at` is normally present.
  - If no-boundary waits are valid, explicitly justify `WaitPollNotReady` for transient unavailable and identify which Host poller policy prevents unbounded practical waiting.
  - Add tests for deadline, expires, invalid boundary, and no-boundary behavior.

## Rejected / Deferred Items

- No reviewer finding is rejected as invalid.
- Physical cleanup of stale staging directories remains deferred unless implementation evidence shows current repository operations cannot tolerate incomplete staging meta.
- Full company metadata time-based TTL remains out of P3-F unless plan fix supplies current production evidence and owner boundary.

## Controller Decision

- Current plan status: not accepted.
- Required next gate: plan fix by AgentCodex.
- Re-review required after plan fix: yes, AgentMiMo and AgentDS.

## Residual Risk

- P3-F may touch a wide Fins storage surface. The plan fix must keep slices owner-aligned and avoid bundling all Fins storage concerns into one implementation slice.
- New `SourceType` / `source_provider` values are LLM-facing. Exact strings must be reviewed before implementation.
