# WU-DUR-P01 Slice 3 Code Review Controller Adjudication

## Verdict

fix-required

## Inputs

- `docs/reviews/wu-dur-obs-cm-closeout-slice3-implementation-retry-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-code-review-mimo.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-code-review-ds.md`
- `docs/host/design.md`
- `docs/host/wu-dur-obs-cm-closeout-plan.md`
- Current workspace diff for Slice 3 retry

## Accepted Fix Scope

### F1. Reactive compaction does not carry proposal manifest refs

- Source: AgentDS F1, AgentMiMo remaining risk 3
- Severity: medium
- Decision: accepted
- Rationale: `CONTEXT_COMPACTED` and `CONTEXT_COMPACTION_ATTEMPT_REJECTED` are the same compact event contracts for proactive and reactive governance. The design requires accepted compact events to reference the accepted proposal manifest and rejected attempts to reference their proposal manifest. The current retry connected the recorder only through `dispatch.py`; `engine_ingest.py` still calls `run_compaction_operation()` without `proposal_manifest_recorder`, so reactive accepted/rejected payloads keep default null proposal manifest refs. This is not just analyzer convenience; it is a missing durable cross-reference on a canonical compact event path.
- Required fix: wire the same durable compactor proposal manifest recorder into reactive compaction, or extract a shared Host helper if needed to avoid duplicating recorder semantics. Reactive accepted compact events must include `accepted_proposal_manifest_ref` and `accepted_proposal_manifest_digest`; reactive rejected attempts must include `proposal_manifest_ref` and `proposal_manifest_digest` when a prepared compactor path records a manifest. Generic non-prepared fake compactors may remain without proposal manifests.

### F2. Accepted compaction missing proposal manifest fail-closed path lacks a direct test

- Source: AgentMiMo F2
- Severity: low
- Decision: accepted
- Rationale: the production proactive accepted path deliberately raises if an accepted result lacks proposal manifest ref/digest. Because this is the fail-closed guard preventing a compacted fact from being written without durable runner-call input truth, it deserves a focused regression test.
- Required fix: add a direct test for the accepted missing manifest ref/digest guard. The test may target the narrow helper or the smallest production path that exercises the same guard.

## Deferred Findings

### D1. Initial compactor proposal trigger reason lacks a precise enum value

- Source: AgentMiMo F1, AgentDS F2
- Decision: deferred-with-owner
- Owner / destination: WU-DUR-P01 design contract hardening before WU-OBS-P00 analyzer consumes trigger reason semantics.
- Rationale: the implementation currently uses an existing legal trigger reason for attempt 1 because the design enum lacks an initial compactor proposal value. Fixing this correctly requires a design contract update and enum propagation, which is outside the narrow Slice 3 implementation fix. The manifest remains structurally valid and analyzable; the semantic label is imprecise but not a durable ref/digest correctness break.

### D2. Outcome-dependent `CompactorRunnerCallIdentity` fields cannot be filled at proposal-time manifest write

- Source: AgentMiMo F3, AgentDS F3
- Decision: deferred-with-owner
- Owner / destination: WU-OBS-P00 / WU-DUR-P01 design contract cleanup.
- Rationale: the manifest is intentionally written before the proposal runner call, so accepted/rejected event refs do not exist yet. Current event payloads provide reverse refs from accepted/rejected compact facts to the proposal manifest. The design should clarify that outcome refs are event-payload cross-references unless a later explicit manifest update contract is introduced.

### D3. Artifact write inside SQLite transaction can leave orphan files on rollback

- Source: AgentDS F4
- Decision: deferred-with-owner
- Owner / destination: storage lifecycle / retention owner, not Slice 3.
- Rationale: this is a pre-existing artifact-store transaction boundary pattern shared by existing compact artifacts. It is not introduced by Slice 3 and does not affect the runner-call manifest contract being implemented here.

## Fix Gate Constraints

- Agent: AgentCodex
- Allowed production files:
  - `dayu/host/engine_ingest.py`
  - `dayu/host/dispatch.py`
  - `dayu/host/compaction_operation.py`
  - `dayu/host/context_events.py`
  - `dayu/host/durable/schema.py`
- Allowed tests:
  - `tests/host/test_engine_ingest_mapping.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_public_compact_smoke.py`
- Allowed docs:
  - `dayu/host/README.md`
  - `tests/README.md`
  - `docs/reviews/wu-dur-obs-cm-closeout-slice3-fix-codex.md`
- Do not change `ConversationCompactOutputVNext`.
- Do not make compactor proposal a Host admitted Run.
- Do not save full provider request/messages in hot EventLog payload.
- Do not implement Tool Trace analyzer consumption in this fix.
- Do not update `docs/host/design.md` in this fix gate; record trigger reason and outcome identity wording as residual risks.

## Required Validation

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_public_compact_smoke.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`

