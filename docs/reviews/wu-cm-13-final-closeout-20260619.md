# WU-CM-13 Final Closeout

## Scope

- Work unit: `WU-CM-13` — Unified conversation compact pipeline convergence
- Coupled prior work unit on the same branch: `WU-CM-14` — Recent final answer preservation for ordinal follow-ups
- Draft PR: https://github.com/noho/dayu-agent-r/pull/152
- Branch: `wu-cm-14-final-answer-preservation` -> `main`

## Completed Gates

- WU-CM-14 plan, implementation, code review, aggregate deepreview, and accepted slice commit completed.
- WU-CM-13 plan, plan review, four implementation slices, code reviews, aggregate deepreview, final smoke hard gate, draft PR creation, and PR review completed.
- Draft PR #152 remains open as a draft. Mark-ready, reviewer requests, merge, and issue closure were not performed.

## Accepted Commits

- WU-CM-14 accepted implementation commit: `921c6219`
- WU-CM-14 aggregate accepted commit: `be6fcbd6`
- WU-CM-13 accepted plan commit: `222ba5b1`
- WU-CM-13 Slice 1 accepted commit: `0390c9ad`
- WU-CM-13 Slice 2a accepted commit: `b180a510`
- WU-CM-13 Slice 2b accepted commit: `7b0367ab`
- WU-CM-13 Slice 2c accepted commit: `7aab0f94`
- WU-CM-13 aggregate accepted commit: `00da03a3`
- PR #152 review accepted commit: `f2970512`

## Validation

- WU-CM-14 focused validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` passed with 220 tests.
- WU-CM-13 aggregate validation: `pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` passed with 305 tests.
- Type check: `python -m pyright dayu/ tests/ utils/` passed with 0 errors, 0 warnings, 0 informations.
- Final smoke hard gate: `python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact --pressure-mode auto` passed with `SMOKE COMPACT_ACCEPTANCE status=pass requested_proactive=4 compacted_proactive=4 failed_total=0 artifact_files=12`.
- `git diff --check` passed before each accepted commit.

## Residual Reconciliation

- `WU-CM-12-S4-R1` closed by WU-CM-13: proactive and reactive compact semantic construction now share Host-internal compact pipeline helpers.
- `WU-CM-12-PR-R1` closed by WU-CM-13 Slice 1: `dayu/host/compaction_evidence.py` was deleted and useful tests migrated.
- `WU-CM-13-S1-R1` closed by aggregate review: the old malformed compacted payload fact-ref edge is covered by the typed `ConversationCompactOutputVNext` helper boundary, operation-level candidate rejection tests, and compact payload/material provenance coverage.
- `WU-CM-14-RR-1` and `WU-CM-14-RR-3` closed by WU-CM-13 Slice 2c: WU-CM-14 preservation is now audited through shared compact pipeline helpers and pipeline-owned ordinary raw-tail selection.

## Remaining External Actions

- PR #152 is intentionally left as draft.
- Mark-ready, reviewer requests, merge, branch deletion, and issue closure require separate user authorization.

## Conclusion

WU-CM-13 is locally complete at `draft-PR-pass`. WU-CM-14 remains completed, and its preservation logic is covered by the WU-CM-13 shared compact pipeline convergence.
