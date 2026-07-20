# WU-SEMANTIC-OWNERSHIP-01 P3-J S2 Code Review Controller Adjudication

## Inputs

- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-s2-controller-validation.md`
- MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-j-s2-code-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-p3-j-s2-code-review-ds.md`

## Findings Merge

Both reviews concluded:

- `Findings`: 未发现实质性问题。
- `Open Questions`: 无。

Therefore there are no accepted S2 code-review findings to fix.

## Controller Decision

S2 is accepted with no fix gate.

Evidence:

- `dayu.host.queue_policy` owns the three-value queue policy closed set.
- Public request validation, admission branching, durable transition validation, durable state insert/decode validation, EventLog payload serialization, semantic digest, and fresh-schema DDL all consume the owner helper.
- `AdmissionPolicy` is deleted and residual scans show no compatibility alias, wrapper, re-export, or import.
- `host_runs.queue_policy` CHECK is derived from the queue-policy owner and `HOST_SCHEMA_VERSION` is bumped to 23.
- `RunResultRow.terminal_status` is typed as `RunStatus`; SQLite text boundaries use a single serializer/parser path.
- `execution_target` remains deployment-resolved non-empty text, with no invented closed set.
- Tests, pyright, source scans, README decision, and propagation audit passed in controller validation.

## Non-Blocking Residual Notes

- `RunRow.queue_policy` remains normalized text. This is accepted because S2 closes the owner boundary through public input, admission, durable insert/decode validation, EventLog payload serialization, and DDL. Typing the run row snapshot itself would broaden the slice beyond the accepted plan.
- There is no dedicated test for `RunResultRow.terminal_status=RunStatus.ACCEPTED`. The serializer already rejects non-terminal `RunStatus` values via `is_terminal_run_status`; the current unknown-value fail-closed test and terminal mapping tests are sufficient for S2.
- Existing schema-22 databases remain out of scope under the fresh-schema policy.

## Next Gate

Proceed to commit S2 and update `docs/host/issues-implementation-control.md`, then continue P3-J S3: Idempotency And Descriptor Kind Weak-Contract Closure.
