# P9-S2 Code Review Controller Adjudication

- **Controller**: Codex
- **Date**: 2026-05-17
- **Branch**: `feat/host-p9-conversation-memory`
- **Scope**: P9-S2 `Projection Consumer and Stable Layer Builder`
- **Design truth**: `docs/host/design.md` §23 / §24 / §26
- **Control truth**: `docs/host/implementation-control.md` Phase 9
- **Plan truth**: `docs/host/phase9-conversation-memory-plan.md` Slice 2

## Review Artifacts

- Initial review: `docs/reviews/p9-s2-code-review-mimo-20260517-0905.md`
- Initial review: `docs/reviews/p9-s2-code-review-ds-20260517.md`
- Re-review: `docs/reviews/p9-s2-code-rereview-mimo-20260517.md`
- Re-review: `docs/reviews/p9-s2-code-rereview-ds-20260517.md`

## Verdict

P9-S2 is accepted for slice commit.

- AgentMiMo re-review verdict: PASS, remaining blocking findings 0.
- AgentDS re-review verdict: PASS, remaining blocking findings 0.
- Controller verdict: PASS.

The implementation remains inside Slice 2. It adds the EventLog-to-memory projection builder, `ConversationMemoryProjectionConsumer`, verified fact extraction, assumption / continuity classification, history pool budget selection, deterministic snapshot rebuild tests, and ProjectionRunner integration tests. It does not connect RunInputBuilder, implement repair / catch-up orchestration, change schema, modify Engine, or write EventLog from memory.

## Accepted Findings And Fixes

### Continuity items bypassed history pool budget

Decision: accepted and fixed.

Reasoning: Assistant conclusions are continuity material. Letting them enter `always_items` without a size or count cap would turn conversation continuity into an unbounded channel and violate P9's memory budget discipline.

Resolution:

- Non-raw, non-episode continuity items now compete in the history pool with older raw turns.
- Recent raw turn floor is still preserved.
- Episode summaries use remaining budget after older raw turns / assistant conclusions.
- Tests cover assistant conclusion budget limiting and episode summary priority.

### `recent_raw_turns_floor=0` kept all raw turns

Decision: accepted and fixed.

Reasoning: Python `items[-0:]` returns all items. A configured zero floor must mean no raw-turn floor, not unlimited retention.

Resolution:

- `_limit_continuity_items` handles zero floor explicitly.
- Tests cover zero floor behavior.

### Missing `tool_name` used `host_projection` as TOOL producer name

Decision: accepted and fixed.

Reasoning: `producer_kind=TOOL` with `producer_name=host_projection` confuses missing tool identity with Host-authored projection. That weakens provenance clarity.

Resolution:

- Missing tool name now uses the neutral producer name `unknown_tool`.
- Tests cover the fallback and neutral summary.

### Malformed `source_refs` could drop a verified fact

Decision: accepted and fixed.

Reasoning: A malformed optional source ref should not cause the whole `TOOL_RESULT_ACCEPTED` fact to fail projection when the accepted tool fact itself is otherwise usable.

Resolution:

- Invalid `HostNeutralRefKind` values in explicit `source_refs` are skipped.
- Tests cover preserving the fact and valid refs.

### Unknown event type advanced cursor silently

Decision: accepted and fixed.

Reasoning: The configured consumer filter should normally prevent unknown types, but the pure builder must not silently advance without an observable signal if called defensively or by a future adapter.

Resolution:

- Unknown event type records a diagnostic while advancing the snapshot cursor.
- Tests cover non-silent behavior.

## Deferred Non-blocking Items

- Stable layer `MemorySnapshotProvider` and RunInputBuilder message rendering remain Slice 3.
- Memory repair / after-commit catch-up orchestration remains Slice 4.
- The unsupported event diagnostic currently uses an existing durable diagnostic reason and records the unsupported code in the message because Slice 2 is not a schema-change slice. A dedicated diagnostic reason can be considered in a later schema hardening work unit if needed.
- `stable_layer_size_units` is still not consumed by RunInputBuilder rendering in Slice 2; it becomes relevant when Slice 3 materializes memory messages.

## Validation

Controller and reviewers verified:

- `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py` passed, 35 tests.
- `pytest tests/host/test_weak_typing_guard.py` passed, 1 test.
- `pyright dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py` passed, 0 errors.
- `git diff --check` passed.

## Remaining Risk

No blocking P9-S2 risk remains. The next architectural risk is Slice 3: ensuring RunInputBuilder consumes memory messages in the fixed P9 order without letting legacy `SessionContinuityProvider` inject unbudgeted raw history.
