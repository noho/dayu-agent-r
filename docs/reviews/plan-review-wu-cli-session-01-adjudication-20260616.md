# WU-CLI-SESSION-01 Plan Review Adjudication

## Reviewed Artifacts

- Plan: `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`
- AgentDS review: `docs/reviews/plan-review-wu-cli-session-01-ds-20260616.md`
- AgentMiMo review: `docs/reviews/plan-review-wu-cli-session-01-mimo-20260616.md`

## Controller Decision

Plan review gate conclusion: `fix required before re-review`.

Both reviewers concluded `pass-with-risks` and reported no blocking open question. The plan direction is accepted: WU-CLI-SESSION-01 formally adds Host public `list_sessions`, removes obsolete `interactive --new-session`, and implements CLI `session list/resume/purge` on Host truth. The plan is not yet code-generation-ready because several contract details are still left to the implementation agent.

## Finding Decisions

| Finding | Decision | Reason / Required Plan Fix |
|---|---|---|
| DS F-01 timestamp conversion gap | accepted | The plan must specify how `SessionRow.created_at` / `closed_at` strings become public datetime values, preferably via existing UTC timestamp parsing helpers, and what error is raised for malformed durable data. |
| DS F-02 SessionListItem / SessionSnapshot asymmetry | accepted | The plan must explicitly decide this contract. Controller decision: keep `created_at` / `closed_at` on `SessionListItem` as list-summary fields for this WU; do not expand `SessionSnapshot` unless the plan fix proves it is necessary. State this intentional asymmetry clearly. |
| DS F-03 / MiMo F05 resume execution core underspecified | accepted | Slice S5 must define the minimal function boundary or two-stage split: session resolution separate from executing prompt / interactive on an existing `session_id`. Include parameters, return type, and stop condition. |
| DS F-04 / MiMo F03 label reverse mapping underspecified | accepted | Plan must define exact mapping from Host slot to CLI `KIND` / `LABEL`, including anonymous and non-CLI slots. |
| DS F-05 purge-by-label TOCTOU | accepted | Plan must state TOCTOU is resolved by Host command precondition checks and require CLI errors to include the original user selector plus Host error context. Add test expectation. |
| MiMo F01 Host Protocol / API export omissions | accepted | Plan must explicitly list `Host` Protocol, `dayu.host.api.__all__`, `dayu.host.__init__`, `_PublicHostHandle`, and `test_package_exports.py` changes. |
| MiMo F04 purge tombstone output format | accepted | Plan must freeze the successful purge output shape enough for tests. |
| DS F-06 list query amplification | deferred-with-owner | Current WU may use straightforward implementation if tests stay small. Owner: future list pagination / performance hardening follow-up if real Session volume grows. Plan may note this as residual risk, not blocker. |
| DS F-07 no ListSessionsRequest context | rejected-with-reason | Existing Host read APIs `get_session` and `get_run` use zero request envelope; keeping `list_sessions()` zero-argument is consistent and avoids unnecessary public surface. |
| DS F-08 list vs concurrent purge snapshot isolation | accepted | Plan should clarify list results are read-transaction snapshots and Host commands remain final truth. A focused test is optional; a stated invariant is required. |
| DS F-09 `interactive_process_slot_key` export cleanup | accepted | Plan S2 must explicitly include `host_context.__all__` cleanup if the helper is removed. |
| MiMo F02 resume-by-label full scan | rejected-with-reason | This is the intended no-overdesign choice for this WU. Do not add `get_session_by_label` unless future demand proves it. |

## Residual Risks

- `list_sessions` has no pagination in this WU. This is accepted as a deliberate first-version boundary.
- CLI resume by label depends on full list scan. This remains acceptable until workspace Session volume creates real pressure.

## Next Gate

Dispatch plan fix to AgentCodex. Expected output: update only `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md` and report how each accepted finding was closed.
