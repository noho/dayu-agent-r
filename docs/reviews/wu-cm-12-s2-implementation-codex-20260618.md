# WU-CM-12 S2 Implementation Artifact

## Gate

- Work unit: WU-CM-12 Conversation Memory Drift Repair
- Slice: S2 - Turn-Group Selected Recent Window And Fallback Selection
- Agent: AgentCodex
- Date: 2026-06-18
- Scope source: `docs/host/design.md` chapter 24/25 and `docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md` S2

## Motivation Judgment

S2 motivation is real. The S1 code had `turn_group_id` on material blocks, but the selectors still protected recent material by raw item/block count:

- memory projection selected recent window protected the newest user/assistant items, not Host admitted Run groups.
- compact segment protection selected newest raw blocks.
- fallback selection selected raw blocks and did not apply fallback selected recent window caps when a memory policy is supplied.

The correct root cause is selector drift from Host Run group semantics, not missing retrieval or ranking. No public API, EventLog type, durable schema, retrieval, ranking or Engine change was needed.

## Changed Files

- `dayu/host/memory.py`
  - Replaced item-count floor with newest non-null `run_id` group floor for selected recent window.
  - Floor now includes user, assistant and recent evidence items for the protected Host Run groups.
  - Eligible item missing `run_id` while floor is required raises a source-path error instead of being silently skipped.

- `dayu/host/compact_material.py`
  - Replaced protected recent raw block helper with turn-group based protection.
  - Protected groups include user input, assistant final answer and accepted tool evidence blocks sharing the same `turn_group_id`.
  - Eligible material block missing `turn_group_id` while floor is required raises a source-path error.
  - S2 review fix: `RunInputMaterialBlock` turn-group helper is now the single Host-internal source used by compact segment and fallback selection. The helper uses non-underscore names for cross-module internal reuse and is intentionally not added to `__all__`.
  - S2 review fix: removed dead `_is_raw_turn_block`.

- `dayu/host/context_fallback.py`
  - Fallback selection now computes floor by newest `turn_group_id` groups and keeps all eligible blocks in the protected groups.
  - Added optional `MemoryProjectionPolicy` input so fallback selection can enforce `fallback_selected_recent_window_item_cap` and `fallback_selected_recent_window_char_cap` for non-floor appends.
  - Fallback floor is built before caps, is not trimmed by caps, and hard-budget failure of floor-only material is surfaced through the existing budget result for fail-closed handling.
  - Non-floor appends are whole-block only; cap rejection or hard-budget rejection records the blocked block and stops without later backfill.
  - S2 review fix: removed duplicate local turn-group helper implementation and now reuses the non-underscore Host-internal helper in `compact_material.py`.

- `dayu/host/dispatch.py`
  - Proactive production fallback selection now passes the existing `HostLocalExecutionOptions.memory_projection_policy` into `build_recent_window_fallback_selection`.

- `dayu/host/engine_ingest.py`
  - Reactive compact pending state now carries the existing ingestor `MemoryProjectionPolicy`.
  - Reactive production fallback decision now passes that policy into `build_recent_window_fallback_selection`.

- `tests/host/test_memory_projection.py`
  - Added multi-run-group selected recent window coverage with multiple blocks per group.
  - Added missing `run_id` source-path failure coverage.

- `tests/host/test_compact_material.py`
  - Added compact segment group-floor coverage for multiple blocks per group, including evidence.
  - Added missing `turn_group_id` source-path failure coverage.

- `tests/host/test_run_input_builder.py`
  - Added fallback floor-over-caps coverage.
  - Added fallback cap stop/no later backfill coverage.
  - Added hard-budget rollback coverage.
  - Added floor-only over-hard-budget coverage.
  - Added missing `turn_group_id` fallback source-path failure coverage.

- `tests/host/test_dispatch_scheduler.py`
  - Added proactive production fallback assertion proving fallback caps drop an older non-floor material block.
  - Added focused reactive fallback helper coverage proving `engine_ingest` production fallback decision uses `MemoryProjectionPolicy` caps.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q
```

Result: `127 passed in 0.80s`
Controller cleanup rerun after removing formatting-only churn: `127 passed in 1.01s`

Controller pyright fix rerun with affected dispatch tests included:

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view tests/host/test_dispatch_scheduler.py::test_reactive_fallback_decision_uses_memory_policy_caps -q
```

Result: `130 passed in 0.95s`
S2 review fix rerun after F1/F2 fixes: `130 passed in 1.21s`
S2 follow-up rerun after replacing cross-module underscored helper imports: `130 passed in 0.92s`

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view tests/host/test_dispatch_scheduler.py::test_reactive_fallback_decision_uses_memory_policy_caps -q
```

Result: `3 passed in 0.33s`
Controller cleanup rerun after removing formatting-only churn: `3 passed in 0.45s`

Passed:

```bash
source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/compact_material.py dayu/host/context_fallback.py dayu/host/run_input.py dayu/host/dispatch.py dayu/host/engine_ingest.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py
```

Result: `0 errors, 0 warnings, 0 informations`

Passed:

```bash
git diff --check
```

Result: no whitespace errors.

## README Decision

- `dayu/host/README.md` was checked because Host files changed. No update made: this slice changes internal selector semantics and tests, without adding or changing Host public API, stable package boundary, command path, user workflow or developer-facing extension point.
- `tests/README.md` was checked because tests changed. It has no `Agent更新约束` section, and this slice only extends existing host test files without changing test organization or entry points. No update made.

## Residual Risks

- Fixed in current slice: production fallback call-site wiring for `MemoryProjectionPolicy` fallback caps is closed. Direct code evidence: `dayu/host/dispatch.py` proactive fallback passes `self._local_execution.memory_projection_policy`, and `dayu/host/engine_ingest.py` reactive pending carries `self._memory_projection_policy` into `_reactive_fallback_decision`. Tests prove proactive and reactive production paths no longer rely on the no-policy compatibility path when a policy exists.
- Fixed in current slice: accepted code review F1 is closed. `context_fallback.py` no longer carries its own `_protected_recent_turn_group_ids` / `_is_turn_group_material_block` implementation and imports the internal shared helper from `compact_material.py`.
- Fixed in current slice: accepted code review F2 is closed. The unused `_is_raw_turn_block` helper was deleted.
- Deferred with owner: this slice did not implement tier 1-3 compact recovery fallback or S3 selected-id provenance rendering guards; those remain in later approved slices.

## Completion Status

S2 implementation, including controller-requested production fallback policy wiring, is complete and verified. The controller-requested cleanup restored formatting-only churn and reapplied scoped logic patches only; production diff is now limited to real selector / policy wiring changes plus tests. No files were staged, committed or pushed.
