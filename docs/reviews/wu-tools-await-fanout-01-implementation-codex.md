# WU-TOOLS-AWAIT-FANOUT-01 Implementation - Codex

## Gate / Slice / Work Unit

- Work unit: `WU-TOOLS-AWAIT-FANOUT-01` / GitHub issue-111
- Gate: `implementation`
- Slice: `S1 轻量 awaiting cleanup terminal marker`
- Accepted plan: `docs/host/wu-tools-await-fanout-01-plan.md`
- Accepted plan commit: `29b211d7`

## Changed Files

- `dayu/host/tool_duplicate_governance.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/run_input.py`
- `dayu/host/README.md`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_run_input_builder.py`

## Exact Behavior Implemented

- Added attempt-local `AWAITING_ACCEPTED` duplicate terminal marker via `DuplicateAwaitingAcceptedEntry` and `record_awaiting_accepted(...)`.
- Added defensive Host-internal `AWAITING_FANOUT` duplicate decision. It returns the owner awaiting outcome, keeps `prior_outcome=None`, sets `prior_awaiting_outcome` / `prior_wait_id`, and does not use the ordinary accepted-result index.
- Updated ToolRuntime awaiting accepted path so Host accepted awaiting ack records the duplicate terminal marker and suppresses `_execute_one` durable-missing cleanup.
- Updated awaiting accept rejected / timeout paths so they still return governed failures and record `HOST_ACCEPT_REJECTED` / `HOST_ACCEPT_TIMEOUT` durable-missing reasons.
- Preserved current batch behavior: after the first `ToolAwaitingOutcome`, remaining calls return `run_suspended_by_tool_awaiting` governed failure and do not start a second business job or second awaiting accept candidate.
- Updated resume wait material to append shared duplicate result guidance after the existing accepted wait result projection, without exposing wait id, tool call id, EventLog id, payload ref, digest, Attempt id, or execution id.

## Tests Added / Updated

- Added duplicate governance tests for awaiting accepted marker, multiple fanout waiters, and durable-missing owner handoff.
- Updated ToolRuntime awaiting tests to assert accepted awaiting does not call `record_durable_missing`, rejected / timeout still do, and defensive concurrent fanout does not start a second job or awaiting accept candidate.
- Updated batch awaiting test to assert only one awaiting accept candidate.
- Added RunInputBuilder resume wait message test for shared duplicate result guidance and internal ref non-leakage.

## README / Docs Decision

- Read `dayu/host/README.md` Agent update constraints before modifying Host.
- Updated `dayu/host/README.md` because the duplicate governance section enumerates current duplicate decisions and now needs to describe the implemented Host-internal `AWAITING_FANOUT` and awaiting terminal marker.
- Did not update durable schema docs, Engine docs, public API docs, or control doc because no schema, Engine contract, public contract, or gate-control change was made.

## Validation Commands And Results

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/host/test_wait_awaiting_accept.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_public_resolve_wait_resume.py -q`
  - Result: `182 passed in 1.35s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## Residual Risks / Uncovered Areas

- `AWAITING_FANOUT` is covered as Host internal / unit-level defensive behavior; this artifact does not claim current production end-to-end batch flow must hit it.
- Engine ingest alias awaiting confirmation was not modified or tested because no direct evidence showed current Host ToolRuntime sends alias awaiting records to Engine ingest.
- No durable follower ledger, cross-Attempt duplicate ledger, or two-phase activation behavior was added.

## Stop Conditions

- None encountered.
- Did not modify `dayu/host/engine_ingest.py`.
- Did not modify durable schema / state.
- Did not modify Host public API, Engine contract, or wait adapter activation contract.
- Did not implement issue-129 two-phase activation.

## Completion Status

Implementation gate for S1 is complete. No commit, push, PR, merge, issue mutation, review gate, or fix gate was performed.
