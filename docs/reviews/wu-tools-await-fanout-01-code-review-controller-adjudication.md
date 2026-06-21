# WU-TOOLS-AWAIT-FANOUT-01 Code Review Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-AWAIT-FANOUT-01` / GitHub Issue #111
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-tools-await-fanout-01-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-await-fanout-01-code-review-mimo.md`
  - `docs/reviews/wu-tools-await-fanout-01-code-review-ds.md`

## Verdict

CHANGES_REQUESTED.

AgentMiMo reported PASS with 0 blocking findings. AgentDS reported PASS with 0 blocking findings but identified one medium structural correctness risk and two low-severity issues. Controller accepts DS-F01 as a required fix because the accepted plan explicitly says `record_awaiting_accepted` failure must follow the existing best-effort cleanup style and must not overwrite the owner accepted-awaiting return path. Controller accepts DS-F03 as a low-cost required regression test for the protective `AWAITING_ACCEPTED` guard. Controller defers DS-F02 because it is diagnostic visibility for a defensive path and does not affect the core accepted-awaiting cleanup correctness.

## Finding Decisions

| Finding | Source | Controller decision | Required action |
|---|---|---|---|
| DS-F01: `_record_duplicate_awaiting_accepted` exception can propagate and let `finally` record `GOVERNED_BEFORE_ACCEPT` after Host accepted awaiting | AgentDS | accepted / must fix | Make awaiting accepted marker recording best-effort. If marker recording fails after Host awaiting accept ack, return the owner awaiting outcome and suppress durable-missing cleanup. Emit/log a diagnostic using the existing ToolRuntime diagnostic style where practical. Add focused test coverage by injecting `record_awaiting_accepted` failure. |
| DS-F02: `AWAITING_FANOUT` diagnostic refs are not attached to the returned record | AgentDS | deferred | No implementation change in this WU. `AWAITING_FANOUT` remains defensive Host-internal/unit-level behavior, not current production e2e path. Do not expand record schema or public diagnostics for this WU. |
| DS-F03: `record_durable_missing` guard for `AWAITING_ACCEPTED` lacks a direct unit test | AgentDS | accepted / must fix | Add a direct duplicate-governance unit test: owner records `AWAITING_ACCEPTED`, then `record_durable_missing(...)`, then a subsequent duplicate decision must still be `AWAITING_FANOUT` and keep the same owner wait. |

## Fix Scope

The fix gate is intentionally narrow:

- Allowed production files:
  - `dayu/host/tool_runtime.py`
  - `dayu/host/tool_duplicate_governance.py` only if needed for diagnostics or testability
- Allowed tests:
  - `tests/host/test_toolruntime_executor.py`
  - `tests/host/test_toolruntime_duplicate_governance.py`
- Do not modify `engine_ingest.py`, durable schema/state, public API/contracts, wait adapter activation contract, or issue-129 behavior.
- Do not add durable follower ledger, wait alias schema, cross-Attempt duplicate table, or new public await lifecycle contract.
- Preserve current batch behavior: first awaiting outcome suspends remaining batch calls with `run_suspended_by_tool_awaiting`.

## Required Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/host/test_wait_awaiting_accept.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_public_resolve_wait_resume.py -q`
- `source .venv/bin/activate && pyright`

