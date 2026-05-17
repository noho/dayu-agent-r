# P9-S1 Code Review Controller Adjudication

- **Controller**: Codex
- **Date**: 2026-05-17
- **Branch**: `feat/host-p9-conversation-memory`
- **Scope**: P9-S1 `Durable Memory Contracts and Schema`
- **Design truth**: `docs/host/design.md` §23 / §24 / §26
- **Control truth**: `docs/host/implementation-control.md` Phase 9
- **Plan truth**: `docs/host/phase9-conversation-memory-plan.md` Slice 1

## Review Artifacts

- Initial review: `docs/reviews/p9-s1-code-review-mimo-20260517.md`
- Initial review: `docs/reviews/p9-s1-code-review-ds-20260517.md`
- Re-review: `docs/reviews/p9-s1-code-rereview-mimo-20260517.md`
- Re-review: `docs/reviews/p9-s1-code-rereview-ds-20260517.md`

## Verdict

P9-S1 is accepted for slice commit.

- AgentMiMo re-review verdict: PASS, remaining blocking findings 0.
- AgentDS re-review verdict: PASS, remaining blocking findings 0.
- Controller verdict: PASS.

The implemented scope stays within Slice 1: typed memory contracts, schema v6 memory projection tables, transaction-scoped durable read/write helpers, and focused tests. It does not introduce projection consumer, RunInputBuilder memory provider, repair / catch-up service, long-term retrieval, business evidence store, or Engine changes.

## Accepted Findings

### MiMo B1 / DS C2: snapshot digest used non-deterministic diagnostic fields

Decision: accepted and fixed.

Reasoning: P9 requires deterministic memory snapshot digest for the same EventLog and policy. Including `diagnostic_id` or `recorded_at` would make rebuild output depend on write-time metadata, violating the design invariant and weakening projection auditability.

Resolution:

- `_snapshot_digest_json_value` now uses a digest-only diagnostic projection.
- Digest input excludes `diagnostic_id` and `recorded_at`.
- Durable JSON serialization still keeps full diagnostic identity and timestamp.
- `test_snapshot_digest_ignores_nondeterministic_diagnostic_fields` covers the regression case.

### MiMo N2: reserved claim status rejection coverage was partial

Decision: accepted and fixed.

Reasoning: P9 may reserve `CONFLICTED`, `STALE`, and `SUPERSEDED` for future issue 39 / long-term retrieval work, but must not synthesize them in working assumptions or continuity views.

Resolution:

- `test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` now covers all three reserved statuses across both `WorkingAssumptionView` and `ConversationContinuityItem`.

## Deferred Non-blocking Findings

### DS C1: non-TOOL `producer_name` semantic precision

Decision: defer to Slice 2.

Reasoning: Slice 1 only establishes contracts and durable primitives. Actual event-to-memory projection in Slice 2 is the right place to map user / assistant / host projection producer identity consistently. Current fallback to `producer_kind.value` is explicit, Host-neutral, and does not create false tool provenance.

Owner: P9-S2 stable layer / projection consumer.

### MiMo N1: included / excluded reason naming divergence from plan

Decision: defer until downstream rendering / trace consumers stabilize.

Reasoning: The current enum values are Host-neutral and semantically valid. Renaming before any consumer exists is lower priority than preserving the accepted anti-hallucination and provenance boundaries.

Owner: P9-S2 before stable layer output becomes a downstream contract.

### MiMo N3: `MemoryDiagnostic.recorded_at` optional type surface

Decision: defer.

Reasoning: Snapshot diagnostics can exist before durable persistence assigns a recorded timestamp, while standalone durable diagnostic writes require a concrete timestamp. This is acceptable for Slice 1. Error message polish is not blocking.

Owner: later P9 hardening if the optional surface proves confusing.

### DS C3 / S3 / A1 / T1: JSON optional helper wording, empty snapshot construction, upsert concurrency guard, cast comment

Decision: defer.

Reasoning: These are maintainability or edge-path hardening items. Current tests and pyright pass, and none undermine P9-S1 correctness, Host layering, or schema truth. Concurrency guard behavior should be revisited when Slice 2 / Slice 4 define projection writer concurrency and repair semantics.

Owner: P9-S2 / P9-S4 as relevant, otherwise later Host hardening.

## Controller Checks

- Verified facts remain restricted to tool provenance.
- User / assistant / host projection items remain assumptions or continuity, not verified facts.
- Reserved issue 39 statuses are present as Host-neutral enum values but rejected by P9 active views.
- Snapshot digest excludes non-deterministic snapshot and diagnostic identity / time fields.
- Durable schema remains Host-neutral and does not import or encode `dayu.fins` business semantics.
- Memory projection lag remains a diagnostic / repair concern and does not touch Run recovery state.

## Validation

Latest validation after accepted fixes:

- `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py` passed, 21 tests.
- `pytest tests/host/test_weak_typing_guard.py` passed, 1 test.
- `pyright dayu/host tests/host` passed, 0 errors.
- `git diff --check` passed in reviewer verification; controller reruns verification before accepted slice commit.

## Remaining Risk

No blocking P9-S1 risk remains. Deferred items are tracked in `docs/host/implementation-control.md` with explicit P9 slice or hardening owners.
