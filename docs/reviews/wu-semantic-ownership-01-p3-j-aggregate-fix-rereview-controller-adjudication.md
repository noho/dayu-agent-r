# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Fix Re-review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub work unit: `P3-J - Host durable schema and weak-contract hardening backlog`
- Gate: aggregate fix re-review
- Accepted finding: `P3-J-AGG-F01`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-rereview-ds.md`

## Re-review Results

- AgentMiMo: PASS. Confirmed `RunRow.queue_policy`, `_decode_run_queue_policy`, `insert_run`, `Create*RunInput`, `_run_accepted_event_request`, and `_validate_run_result_terminal_status` close `P3-J-AGG-F01`; no masking; public request text boundary remains correct.
- AgentDS: PASS. Confirmed producer -> durable row -> SQLite write -> SQLite read -> tests propagation; no material findings.

## Controller Judgment

### P3-J-AGG-F01 - Durable queue policy typed row surface and adjacent validation clarity

- Decision: `accepted fixed`.
- Evidence:
  - `RunRow.queue_policy` now carries `RunQueuePolicy`.
  - Direct upstream create inputs now carry `RunQueuePolicy`.
  - SQLite write boundary serializes `.value` once.
  - SQLite read boundary parses stored text through `RunQueuePolicy` owner and returns the typed value.
  - `RunResultRow.terminal_status` validation now uses explicit `_validate_run_result_terminal_status(...)`.
  - Focused controller validation passed `81 passed`; pyright passed with `0 errors`; `git diff --check` passed.
  - Both independent re-reviews passed with zero material findings.
- Status: closed.

## Residual Risk

- Two `test_dispatch_scheduler.py` compaction previous-view tests fail in both current workspace and pre-fix baseline commit `0bc75a5b`. They are not on the queue-policy or run-result terminal-status data path and are not accepted as P3-J aggregate fix regressions.
- DS noted admission idempotency digest canonicalization still uses parse -> serialize on public request text. Controller accepts this as a valid public text-boundary normalization, not a durable row weak contract.

## Next Gate

Commit the accepted aggregate fix and re-review artifacts, then update `docs/host/issues-implementation-control.md` to record P3-J aggregate acceptance and the next umbrella sub work unit.
