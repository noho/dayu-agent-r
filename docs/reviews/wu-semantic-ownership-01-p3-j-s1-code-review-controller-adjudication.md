# WU-SEMANTIC-OWNERSHIP-01 P3-J S1 Code Review Controller Adjudication

## Inputs

- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-s1-controller-validation.md`
- MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-j-s1-code-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-p3-j-s1-code-review-ds.md`

## Findings Merge

Both reviewers reported:

- `Findings`: 未发现实质性问题。
- `Open Questions`: 无。

Therefore there are no accepted S1 code-review findings to fix.

## Controller Decision

S1 is accepted.

Evidence:

- EventLog `event_type` legal set is owned by `dayu.host.lifecycle_events`.
- Append validation rejects unknown `event_type` before durable write.
- Row decoder rejects externally mutated unknown `event_type` before downstream projection/read consumers see it.
- Fresh schema DDL CHECK derives its values from `all_host_event_type_values()`.
- Controller and reviewers confirmed production append event types are covered; transient `CONTENT_DELTA` and `TOOL_CALL_DELTA` are not persisted.
- Tests and pyright passed in controller validation.

## Non-Blocking Observations

- Production modules still define local `_EVENT_TYPE_*` string constants. This is acceptable for S1 because S1 closes the durable owner boundary; later slices may migrate producers to typed owner constants if they touch those modules.
- `serialize_host_event_type()` and `host_event_type_values()` currently have test coverage and no production caller. This is acceptable owner surface for follow-on use.
- Exhaustive category tests duplicate expected owner ordering. This is intentional to catch accidental owner set drift.

## Residual Risk

- Future Host durable event types must be added to `dayu.host.lifecycle_events` before append paths write them.
- Existing schema-21 SQLite databases are out of scope; this WU follows fresh-schema policy.

## Next Gate

Proceed to commit S1 and update `docs/host/issues-implementation-control.md`, then continue P3-J S2: Queue Policy Owner And RunResult Terminal Row Surface.
