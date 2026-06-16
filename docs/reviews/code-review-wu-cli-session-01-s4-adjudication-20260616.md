# WU-CLI-SESSION-01 S4 Code Review Adjudication

## Reviewed Artifacts

- S4 implementation report: `docs/reviews/wu-cli-session-01-s4-implementation-codex.md`
- AgentDS code review: `docs/reviews/code-review-wu-cli-session-01-s4-ds-20260616.md`
- AgentMiMo code review: `docs/reviews/code-review-wu-cli-session-01-s4-mimo-20260616.md`

## Controller Decision

S4 code review gate conclusion: `PASS`.

Both reviewers found no actionable findings. The implementation is accepted because it satisfies the S4 contract:

- `session list` and `session purge` call only Host public `list_sessions()` / `purge_session(...)`.
- The Host opener runtime assembly uses the existing `prompt` scene as a carrier, while Host call context remains `cli_session`.
- Parser shape includes `list` / `resume` / `purge`; S4 leaves `resume` execution as not implemented.
- Purge selector behavior covers direct `--session-id`, label + kind slot resolution, mandatory `--yes`, and user-facing lookup errors.
- TOCTOU Host errors include original selector, resolved `session_id`, Host code and Host message.
- `INVALID_STATE` explains the closed Session + terminal Runs precondition and does not auto close/cancel.
- `PurgeSessionRequest` carries explicit context, client request id and reason fields without extra payload.
- Tests cover the missing `session` manifest regression by asserting `scene_id == "prompt"` and required context slots.

## Residual Risk

- Label purge still has the planned resolve-then-command TOCTOU window; Host purge preconditions remain the final truth.
- `session resume` is parser-only in S4 and is owned by S5.
- Full pytest was not run for S4; targeted CLI tests plus full pyright are sufficient for this slice.

## Next Gate

Create the S4 accepted slice commit, then dispatch WU-CLI-SESSION-01 S5.
