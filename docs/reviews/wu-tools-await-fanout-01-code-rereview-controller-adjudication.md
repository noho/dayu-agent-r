# WU-TOOLS-AWAIT-FANOUT-01 Code Re-review Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-AWAIT-FANOUT-01` / GitHub Issue #111
- Gate: code re-review adjudication
- Fix artifact: `docs/reviews/wu-tools-await-fanout-01-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-await-fanout-01-code-rereview-mimo.md`
  - `docs/reviews/wu-tools-await-fanout-01-code-rereview-ds.md`

## Verdict

PASS.

Both re-review lanes reported 0 unfixed accepted findings and 0 new blocking findings. DS-F01 and DS-F03 are closed. DS-F02 remains intentionally deferred under the prior controller decision because it concerns diagnostic visibility for a defensive Host-internal path and does not affect the core accepted-awaiting cleanup correctness.

## Accepted Finding Closure

| Finding | Closure status | Evidence |
|---|---|---|
| DS-F01: awaiting accepted marker failure could propagate and let `finally` record durable-missing | closed | `ToolRuntimeExecutor._record_duplicate_awaiting_accepted(...)` now records marker failure as best-effort diagnostic and returns terminal handled after Host awaiting accept ack. `test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup` verifies owner `ToolAwaitingOutcome` is returned and durable-missing cleanup is not called. |
| DS-F03: `AWAITING_ACCEPTED` guard lacked direct unit test | closed | `test_durable_missing_preserves_awaiting_accepted_marker` directly verifies `record_durable_missing(...)` preserves an `AWAITING_ACCEPTED` marker and subsequent duplicate decision remains `AWAITING_FANOUT`. |
| DS-F02: defensive `AWAITING_FANOUT` diagnostic refs not attached to returned record | deferred | No change required for this WU. The path remains Host-internal/unit-level defensive behavior; no record schema, durable schema, public diagnostics, or public contract expansion was introduced. |

## Scope Check

- No `dayu/host/engine_ingest.py` change.
- No durable schema/state change.
- No public API or contract change.
- No issue-129 two-phase activation behavior.
- No durable follower ledger, wait alias schema, cross-Attempt duplicate table, or new public await lifecycle contract.
- Current batch behavior remains: after the first `ToolAwaitingOutcome`, remaining batch calls return `run_suspended_by_tool_awaiting`.

## Residual Risks

- `AWAITING_FANOUT` remains a defensive Host-internal state and is not claimed as current production end-to-end batch behavior.
- DS-F02 remains deferred as diagnostic visibility for a defensive path.
- If future Engine or ToolRuntime concurrency work makes fanout a production reachable path, that future work must revisit diagnostic visibility and Engine ingest alias semantics.

