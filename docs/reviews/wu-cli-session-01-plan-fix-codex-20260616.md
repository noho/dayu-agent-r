# WU-CLI-SESSION-01 Plan Fix Report

## Gate

- Work unit: `WU-CLI-SESSION-01`
- Gate: plan fix
- Agent: AgentCodex
- Date: 2026-06-16
- Target plan: `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`
- Controller adjudication: `docs/reviews/plan-review-wu-cli-session-01-adjudication-20260616.md`

## Fixed Findings Mapping

| Adjudication finding | Plan change location |
|---|---|
| DS F-01 timestamp conversion gap | Section 6 `Host API dataclass` now states `SessionRow.created_at` / `closed_at` are durable UTC timestamp strings, must be parsed with `dayu.host.durable.codec.parse_utc_timestamp(...)`, and malformed durable data must fail as `HostDurableError`. Section 9 S1 and Section 10 add implementation and test expectations. |
| DS F-02 SessionListItem / SessionSnapshot asymmetry | Section 6 now explicitly records the controller decision: keep `created_at` / `closed_at` only on `SessionListItem` as list-summary fields, do not expand `SessionSnapshot` in this WU unless direct implementation evidence proves it necessary. Section 10 adds the expected assertion. |
| DS F-03 / MiMo F05 resume execution core underspecified | Section 9 S5 now defines the two-stage boundary: `session.py` resolves an existing open session, while `prompt.py` / `interactive.py` expose narrow execute-on-existing-session helpers. It lists parameters, return values, exceptions/error propagation, and stop conditions. |
| DS F-04 / MiMo F03 label reverse mapping underspecified | Section 7 now freezes Host slot to CLI `KIND` / `LABEL` mapping for anonymous, `cli.prompt`, `cli.interactive`, and other slots, including labels containing dots. Section 9 S3 and Section 10 add helper/test expectations. |
| DS F-05 purge-by-label TOCTOU | Section 7 now states resolve-then-command TOCTOU is handled by Host command preconditions and requires CLI errors to include original selector plus Host context. Section 9 S4 and S5 add purge/resume TOCTOU tests. |
| MiMo F01 Host Protocol / API export omissions | Section 6 now explicitly lists `dayu/host/api.py` Host Protocol and `dayu.host.api.__all__`, `dayu/host/read_api.py` and `read_api.__all__`, `_PublicHostHandle`, `dayu/host/__init__.py`, and `tests/host/test_package_exports.py`. Section 9 S1 and Section 10 repeat the implementation/test expectations. |
| MiMo F04 purge tombstone output format | Section 7 now fixes success output as `Purged session <session_id> (tombstone: <tombstone_ref_prefix>...)`, with prefix length rules. Section 9 S4 and Section 10 add stable output assertions. |
| DS F-08 list vs concurrent purge snapshot isolation | Section 6 durable helper notes `list_sessions` is a read transaction snapshot and later Host commands are final truth. Section 8 `Purged Session` repeats the user-visible invariant. |
| DS F-09 `interactive_process_slot_key` export cleanup | Section 9 S2 now requires removing `interactive_process_slot_key` from `host_context.__all__` if the helper is removed. |
| Rejected/deferred findings | Section 12 now states DS F-06 is a deferred performance/pagination risk, DS F-07 does not add `ListSessionsRequest`, MiMo F02 does not add `get_session_by_label`, and this WU does not add pagination. |

## Files Changed

- `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`
- `docs/reviews/wu-cli-session-01-plan-fix-codex-20260616.md`

## Validation

- This gate is documentation-only. I did not run pytest or pyright.
- Ran `git diff --check -- docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md docs/reviews/wu-cli-session-01-plan-fix-codex-20260616.md`; it passed.

## Residual Risks

- No implementation validation was run because the user explicitly scoped this gate to plan fix only.
- `list_sessions` still intentionally has no pagination; this remains a deferred follow-up if real Session volume grows.
- Resume-by-label still intentionally uses `list_sessions` full scan; future pressure can justify a separate Host API.
- S5 implementation complexity remains, but the plan now defines the minimum acceptable split and stop conditions.

## Completion Status

Accepted plan-review findings were addressed in the plan. Ready for re-review gate, but this agent did not enter re-review.
