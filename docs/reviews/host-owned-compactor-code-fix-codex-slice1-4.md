# Host-Owned Compactor Code Fix - Slice 1-4

## Gate

- Gate: code review fix for implementation Slice 1-4
- Work unit: Host-owned LLM context compactor public opener contract
- Accepted plan commit: `cab7ad0`
- Source review artifacts:
  - `docs/reviews/host-owned-compactor-code-review-mimo-slice1-4.md`
  - `docs/reviews/host-owned-compactor-code-review-ds-slice1-4.md`

## Accepted Findings And Status

| Finding | Status |
| --- | --- |
| ACCEPTED-FIX-1 / MiMo F-1 / DS F1 duplicated compaction operation logic | fixed |
| ACCEPTED-FIX-2 / MiMo F-2 / DS test gap for HostEvent projection | fixed |
| ACCEPTED-FIX-3 / DS F4 operation_id diagnostic risk | fixed |

## Changed Files

- `dayu/host/compaction_operation.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `docs/reviews/host-owned-compactor-code-fix-codex-slice1-4.md`

## Per-Finding Fix Description

### ACCEPTED-FIX-1

Extracted the shared bounded semantic compaction operation loop into `dayu/host/compaction_operation.py`.

The new Host-internal helper owns only:

- proposal attempt execution through `ContextCompactor.compact`;
- proposal failure capture;
- `check_compaction_candidate` quality validation;
- hard-threshold validation;
- structured `CompactionOperationResult` and `CompactionAttemptRejected` results.

`dispatch.py` and `engine_ingest.py` still own request fact writes, attempt rejected event writes, failed/compacted event writes, artifact writes, state rechecks, recovery/start transitions, and returned Host/ingest behavior.

### ACCEPTED-FIX-2

Added `test_attempt_rejected_projects_to_progress_host_event` in `tests/host/test_context_compact_events.py`.

The test directly exercises the HostEvent projection path and proves a `CONTEXT_COMPACTION_ATTEMPT_REJECTED` EventLog row maps to `HostEventKind.PROGRESS`.

Runner/provider retry HostEvent emission was not given a separate new HostEvent test in this fix. Direct code structure keeps provider retry inside `LLMContextCompactor` / runner execution, while HostEvent projection only reads EventLog rows. Existing `tests/host/test_llm_compaction.py::test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair` covers that runner retry is passthrough and does not create a Host-owned semantic repair loop. The new shared helper also emits no EventLog rows itself, so provider retry cannot emit HostEvent through this helper.

### ACCEPTED-FIX-3

Changed attempt rejected `operation_id` from `estimate.estimator_digest` to the stable `CONTEXT_COMPACTION_REQUESTED` event id.

- Proactive path: `_append_compaction_requested_event` now returns the request row, and `_GovernanceCompactPending.operation_id` carries `requested.event_id`.
- Reactive path: `_ReactiveCompactPending.operation_id` carries the already-written reactive request row id.
- Attempt rejected payload builders now receive that operation id from dispatch/ingest event-writing code.

Added focused assertions:

- proactive rejected attempt payload operation id equals the request event id in `tests/host/test_dispatch_scheduler.py`;
- reactive rejected attempt payload operation id equals the request event id and differs from estimator digest in `tests/host/test_engine_ingest_mapping.py`.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q
```

Result: `93 passed in 1.03s`

Command:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: `0 errors, 0 warnings, 0 informations`

Command:

```bash
git diff --check
```

Result: passed with no output.

## Rejected And Deferred Findings

| Finding | Status | Owner / Destination |
| --- | --- | --- |
| DEFERRED-1 / MiMo F-3 dead `_RealLLMContextCompactor` in `test_public_compact_smoke.py` | deferred, unchanged | Slice 5 smoke migration |
| REJECTED/DEFERRED-2 / DS F2 daemon thread bridge | unchanged per controller decision | Current sync `ContextCompactor` constraint |
| DEFERRED-3 / DS F3 `_input_range` ordering assumption | deferred, unchanged | Later touch to `llm_compaction.py` if needed |

## Residual Risks And Open Questions

- No public contract, schema, EventLog ownership, artifact ownership, or memory projection ownership was moved.
- No Slice 5/6 files were edited.
- README files were not edited because the handoff explicitly excluded README changes.
- Residual risk: the operation helper is intentionally Host-internal and shared by proactive/reactive paths; future semantic compaction policy changes should update the helper rather than reintroducing path-local loops.

## Stop Status

Stop status: fix artifact complete; ready for Gateflow controller re-review. No commit, push, PR creation, or re-review was performed.
