# WU-SEMANTIC-OWNERSHIP-01 P2-B S1 Implementation Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-B`
- Slice: `S1`
- Gate: implementation review adjudication
- Accepted plan commit: `823ee002`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-s1-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-s1-implementation-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-b-s1-implementation-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-b-s1-implementation-review-ds.md`

## Verdict

Accepted with no required fix gate.

Both AgentMiMo and AgentDS returned `pass` and reported no blocking finding.

## Findings Adjudication

No accepted blocking findings.

Non-blocking observations:

- AgentMiMo noted `_call_name_lines(...)` does not chase indirect wrapper patterns such as `a = some_func(ConversationMemorySnapshotVNext)`. Controller adjudication: not accepted as required fix. Current S1 owner boundary is direct constructor / common alias detection in compact and run-input business tests; deliberately indirect reflection or wrapper construction would be a new testing anti-pattern and can be handled if it appears.
- AgentMiMo noted `test_memory_projection.py` is not included in direct constructor source-scan scope. Controller adjudication: not accepted as required fix for S1. `test_memory_projection.py` owns schema and digest invariant assertions, currently has no direct `ConversationMemorySnapshotVNext(...)` call, and is already included in pending digest source-scan. S2 must reuse the S1 factory for cross-path equivalence tests.
- AgentDS noted `_required_memory_cursor(...)` still constructs `MemorySnapshotCursor(...)` directly. Controller adjudication: not accepted as required fix. P2-B S1 targeted `ConversationMemorySnapshotVNext` construction and snapshot digest sentinel ownership; cursor construction from durable database rows remains local test setup and does not duplicate snapshot materialization semantics.

## Controller Decision

S1 satisfies the accepted P2-B plan slice:

- Import boundary scanner now resolves relative imports into absolute module names and fails loudly on invalid package roots or relative import levels.
- Compact / run-input memory snapshot construction is centralized through `tests/host/memory_snapshot_factories.py`.
- Snapshot digest recomputation uses production memory dataclasses and production digest helper.
- Business tests no longer scatter pending digest sentinels or directly construct `ConversationMemorySnapshotVNext(...)`.
- AST source-scan tests guard the S1 ownership boundary without fragile literal matching.
- No production Host semantic owner was changed; P2-B S2 remains pending.

## Validation Evidence

Controller validation before review:

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py`: `23 passed`
- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_memory_projection.py`: `203 passed`
- `source .venv/bin/activate && pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed

Reviewer validation:

- AgentMiMo reran the affected pytest set, pyright, diff check, and source scans.
- AgentDS reran the affected pytest set, pyright, diff check, and rollback source scans.

## Residual Risk

- P2-B S2 terminal answer continuity projection contract is not implemented in S1 and remains the next implementation slice.
- Future tests could deliberately hide direct snapshot construction behind reflection or higher-order wrappers. This is not a current S1 blocker; if it appears, the test owner should either move the construction into `tests/host/memory_snapshot_factories.py` or extend the AST guardrail with direct evidence.

## Next Gate

Commit accepted S1, then enter P2-B S2 implementation. S2 must not reintroduce local pending digest or direct snapshot construction in its real durable-store cross-path tests.
