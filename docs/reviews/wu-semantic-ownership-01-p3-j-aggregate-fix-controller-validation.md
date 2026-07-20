# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Fix Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub work unit: `P3-J - Host durable schema and weak-contract hardening backlog`
- Gate: aggregate deepreview fix validation
- Accepted finding: `P3-J-AGG-F01`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-codex.md`

## Fix Summary

- `RunRow.queue_policy` is now typed as `RunQueuePolicy`.
- `_decode_run_queue_policy(...)` now returns `RunQueuePolicy`.
- `insert_run(...)` serializes `run.queue_policy.value` at the SQLite write boundary.
- Low-level `CreateAcceptedRunInput`, `CreateQueuedRunInput`, and `CreateRunningRunInput` now carry `RunQueuePolicy`, preserving the typed durable row contract at the direct upstream owner boundary.
- `RunResultRow.terminal_status` validation now uses `_validate_run_result_terminal_status(...)`; `serialize_run_result_terminal_status(...)` remains the SQLite/public text serialization helper.

## Controller Validation

- `source .venv/bin/activate && pytest tests/host/test_state_schema.py::test_run_row_queue_policy_decodes_to_owner_type tests/host/test_durable_schema.py::test_host_runs_queue_policy_check_uses_owner_values tests/host/test_projection_read_model.py::test_read_model_python_validation_rejects_unknown_terminal_status tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py -q`
  - Result: `81 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- Source scan:
  - `rg -n 'serialize_run_queue_policy\(parse_run_queue_policy|parse_run_queue_policy\(run\.queue_policy|serialize_run_result_terminal_status\(row\.terminal_status\)|queue_policy: str|def _decode_run_queue_policy\(.*\) -> str' dayu/host/durable`
  - Result: only `dayu/host/durable/read_model.py:181` remains, which is the legitimate `insert_run_result_if_absent` SQLite serialization boundary.

## Broader Changed-Test Probe

- `source .venv/bin/activate && pytest` over the modified Host test files produced `597 passed, 2 failed`.
- The two failures were:
  - `tests/host/test_dispatch_scheduler.py::test_proactive_compaction_recovery_tier2_degrades_previous_view`
  - `tests/host/test_dispatch_scheduler.py::test_reactive_compact_request_uses_latest_previous_view`
- Controller ran the same two tests in a detached baseline worktree at pre-fix commit `0bc75a5b`; both failed there with the same assertions.
- Decision: these two failures are pre-existing compaction / previous-view verification failures, not introduced by `P3-J-AGG-F01`. They remain outside this aggregate fix scope and are recorded as validation residual risk.

## Propagation Audit

- Fact: Host run queue policy.
- Producer owner: `dayu.host.queue_policy.RunQueuePolicy`.
- Direct upstream creation boundary: `CreateAcceptedRunInput`, `CreateQueuedRunInput`, and `CreateRunningRunInput` accept `RunQueuePolicy`.
- Durable row: `RunRow.queue_policy: RunQueuePolicy`.
- SQLite write: `insert_run(...)` writes `run.queue_policy.value`.
- SQLite read: `_decode_run_queue_policy(...)` parses stored text through the owner and returns `RunQueuePolicy`.
- Public text boundary: public request/admission entry points still accept user text and parse through `RunQueuePolicy`; this remains intentional and is not durable weak-contract leakage.

## Residual Risk

- Existing `test_dispatch_scheduler.py` compaction previous-view failures predate this fix. They are not accepted as P3-J aggregate fix findings because they do not share the `queue_policy` or `RunResultRow.terminal_status` data path.
- No blocking residual risk remains for `P3-J-AGG-F01`.

## Next Gate

Dispatch AgentMiMo and AgentDS for aggregate fix re-review.
