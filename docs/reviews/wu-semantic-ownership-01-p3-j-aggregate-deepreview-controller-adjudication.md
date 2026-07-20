# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub work unit: `P3-J - Host durable schema and weak-contract hardening backlog`
- Gate: aggregate deepreview
- Accepted plan commit: `f91cd6d5`
- Accepted slice commits: S1 `a63a27c7`, S2 `2b2718a2`, S3 `e8f32b77`, S4 `9ffb1a3d`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-deepreview-ds.md`

## Review Results

- AgentDS: `未发现实质性问题`。
- AgentMiMo: reported three Low findings around `RunRow.queue_policy` typed surface, `RunResultRow.terminal_status` validation clarity, and duplicate queue-policy parse / serialize in `insert_run`.

## Controller Judgment

### P3-J-AGG-F01 - Durable queue policy typed row surface and adjacent validation clarity

- Source findings:
  - MiMo finding 1: `RunRow.queue_policy` remains `str` while `RunResultRow.terminal_status` is typed.
  - MiMo finding 2: `_validate_run_result` uses serializer return-discarding as validation.
  - MiMo finding 3: `insert_run` repeats queue-policy parse / serialize after `_validate_run_for_insert`.
- Decision: `accepted`.
- Reason: P3-J S2 explicitly accepted `queue_policy` as a Host-owned typed durable contract. The current implementation is functionally protected by public validation, durable validation, decoder validation, and DDL, but the durable row dataclass still advertises `queue_policy` as raw text. Under AGENTS.md semantic ownership rules, this is a weak contract at the durable row boundary rather than just style. The validation helper cleanup is adjacent and reduces the same owner-boundary ambiguity.
- Owner boundary:
  - Producer / owner: `dayu.host.queue_policy.RunQueuePolicy` and parse / serialize helpers.
  - Durable persistence: `dayu/host/durable/state.py` must persist `.value` at SQLite boundary and decode to `RunQueuePolicy`.
  - Projection / read model: `dayu/host/durable/read_model.py` must validate terminal status through an explicit terminal-status validator or equivalent typed owner helper, not via a discarded serialization result.
  - Tests: Host durable state and projection tests must assert the typed surfaces.
- Required fix:
  - Change `RunRow.queue_policy` to `RunQueuePolicy`.
  - Make `_decode_run_queue_policy` return `RunQueuePolicy`.
  - Ensure SQLite writes serialize `RunQueuePolicy` exactly once at the persistence boundary.
  - Replace return-discarded serializer validation for `RunResultRow.terminal_status` with an explicit validation helper or a clearly named shared helper.
  - Update affected tests and README decisions if triggered.
- Required validation:
  - Focused Host durable / queue-policy / projection tests covering `RunRow.queue_policy` and `RunResultRow.terminal_status`.
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- Status: accepted, pending AgentCodex fix.

## Rejected / Deferred Findings

- None. AgentDS residual risks are recorded as low current-scope residuals and do not require independent fixes beyond `P3-J-AGG-F01`.

## Residual Risk

- Historical old-config filename references in design documents and review archives remain outside P3-J runtime public exposure.
- Direct SQL corruption tests may still construct invalid durable rows to prove fail-closed behavior; production owner write paths reject them.
- Event type producer-wide constant redirection remains a P3-J non-goal because append validation, row decoding, and DDL now share the typed owner.

## Next Gate

Dispatch AgentCodex for aggregate fix `P3-J-AGG-F01`, then run independent re-review by AgentMiMo and AgentDS before accepting the aggregate deepreview commit.
