# WU-CM-01 Deferred Risk Cleanup Implementation

## Gate

- Work unit: WU-CM-01 PR deferred risk cleanup
- Scope: D1 / D2 / D4 / D5
- Implementation agent: AgentCodex
- Status: implemented; commit / push intentionally skipped per user instruction.

## Changed Files

- `dayu/host/memory.py`
- `dayu/host/context_fallback.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compact_material.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_durable_concurrency_matrix.py`
- `tests/README.md`

## Implementation Notes

- D1: added explicit module-level `__all__` to `memory.py` and `context_fallback.py`. The lists include stable typed contracts, constants and public helpers only; private helpers remain excluded.
- D2: added `CompactionFailureCategory` and `CompactionNextPolicyDecision` as `StrEnum` types. `CompactionAttemptRejected` now stores enum fields; EventLog reason and payload write boundaries use `.value`, preserving JSON strings.
- D4: renamed initial compact material diagnostic constants from implementation slice names to semantic initial material names and cleaned related docstrings.
- D5: added focused tests for module exports, typed/schema missing source label boundary, real durable memory catch-up integration, and memory snapshot / checkpoint same-transaction commit.

## Review Findings

- Finding D5-F1: The originally planned direct quality checker missing-source-label test is not reachable through normal typed candidate construction because `SessionSummaryCandidateVNext` already rejects empty required `source_labels`.
  - Decision: rejected-with-reason for direct checker bypass; accepted equivalent schema boundary coverage.
  - Fix status: 已修复 by testing the typed boundary without constructing invalid objects through private bypass.
- Finding MiMo-F1: `tests/host/test_compaction_operation.py` retained three raw string assertions for `CompactionAttemptRejected.failure_category` after D2 introduced `CompactionFailureCategory`.
  - Decision: accepted.
  - Fix status: 已修复 by replacing the remaining raw string comparisons with enum `isinstance` and identity assertions.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compaction_contract.py tests/host/test_memory_repair.py tests/host/test_durable_concurrency_matrix.py -q`
  - Result: passed, 104 tests.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: passed, 0 errors.
- `git diff --check`
  - Result: passed after README / artifact sync.

## README Decision

- `dayu/host/README.md`: checked; no update needed because existing stable Host memory / context governance / compaction descriptions already cover the implemented behavior.
- `tests/README.md`: updated package export and durable concurrency matrix descriptions to match the new tests.

## Residual Risks

- Long-term conversation memory evaluation remains outside this cleanup and stays with GitHub Issue #80.
- No package root public contract was added; Service-facing imports remain unchanged.
