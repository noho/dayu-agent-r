# PR 68 P12.6 Draft Fix — Codex

## Gate

- Gate: P12.6 draft PR fix gate
- PR: https://github.com/noho/dayu-agent-r/pull/68
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Source adjudication: `docs/reviews/pr-68-p12-6-draft-review-controller-adjudication-20260524.md`
- Assigned scope: Fix or directly disprove accepted findings A1-A8

## Changed Files

- `dayu/host/durable/schema.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/run_input.py`
- `dayu/host/dispatch.py`
- `dayu/host/compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/README.md`
- `tests/host/test_memory_projection.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_toolruntime_accept_barrier.py`

Existing controller dirty files were not reverted or edited by this fix pass.

## Finding Resolution

### A1 — 已修复 — Memory diagnostic reason schema mismatch

- Schema CHECK now includes `evidence_backed_fact_superseded` and `minimum_preserve_item_covered`.
- Added direct durable-store tests proving both reasons can be inserted and read back from `host_memory_diagnostics`.

### A2 — 已修复 — LLM compaction timeout/cancellation handling

- `LLMContextCompactor.compact()` now catches runner timeout, signals writable Host cancellation tokens via `request_cancel("compactor_proposal_timeout")`, and raises `LLMCompactionProposalError("compactor proposal timed out")`.
- Added test proving timeout is wrapped and cancellation token state is updated.

### A3 — 已修复 — Range endpoint labels must resolve to exactly one canonical ref

- Range parsing now rejects start/end labels unless they resolve to exactly one canonical source ref.
- Added tests for zero-ref and multi-ref endpoint labels.

### A4 — 已修复 — Compact material provenance must preserve locator/artifact refs

- `RunInputMaterialBlock` now carries `artifact_refs` and `source_locator_refs`.
- Run input accepted evidence blocks propagate these refs from `InitialEvidenceMaterial`.
- Second-pass compact material provenance copies refs from selected evidence blocks instead of dropping them.
- Added provenance test with non-empty payload, artifact, and source locator refs.

### A5 — 已修复 — Dispatch lag repair failure must not leave records permanently running

- If lag rebuild retry still raises `SNAPSHOT_LAG_OVER_THRESHOLD`, worker startup now performs terminal startup closeout and releases the lane token instead of returning `skipped`.
- Added scheduler test proving persistent lag repair failure leaves Run / Attempt failed and dispatch record cancelled, with no worker accepted.

### A6 — 已修复 — Evidence-backed facts must not be starved by lower-value stable blocks

- Stable memory block priority now renders evidence-backed facts before confirmed subjects.
- Added budget-pressure test proving facts are retained while oversized subjects are skipped under stable budget pressure.

### A7 — 已修复 — Empty evidence labels must not disable evidence-backed guard rails

- Quality check now emits `CompactQualityIssue.EVIDENCE_LABELS_MISSING` when `evidence_backed_fact_refs` are non-empty but material evidence labels are empty.
- Added fail-closed quality test for that premise.

### A8 — 已修复 — Accept barrier payload descriptor existence

- `DefaultHostToolFactAcceptPort` has direct durable transaction access, so the accept path now rejects candidates whose `payload_ref` descriptor is missing before writing any accepted events.
- Added test proving the result is `PAYLOAD_REFERENCE_INVALID` and no tool events are written.

## Validation

- `source .venv/bin/activate && python -m pytest tests/host/test_memory_projection.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_compaction_contract.py tests/host/test_dispatch_scheduler.py tests/host/test_toolruntime_accept_barrier.py --tb=short -q`
  - Result: `220 passed in 3.97s`
- `source .venv/bin/activate && python -m pytest tests/host/test_compaction_operation.py tests/host/test_memory_projection.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compact_material.py tests/service/test_host_assembly.py tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_accept_barrier.py tests/runtime/test_config_loader.py --tb=short -q`
  - Result: `315 passed in 4.79s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## README Updates

- Updated `dayu/host/README.md` for Host-scoped stable behavior:
  - persistent post-rebuild memory lag repair failure closes out worker startup instead of hanging;
  - stable budget prioritizes evidence-backed facts over confirmed subjects;
  - compact provenance map preserves locator and artifact refs;
  - compactor timeout signals writable cancellation tokens and reports stable proposal failure.

## Residual Risks

- A6 fix prevents starvation by lower-priority stable blocks. If the evidence-backed fact block itself exceeds the configured stable budget, it may still be skipped by budget policy and emit the existing budget diagnostic.
- No old-database compatibility migration was added; this follows the project rule for schema changes in this task.

## Stop Status

Fix artifact written. No commit, push, PR state change, merge, reviewer request, or later-gate action was performed.
