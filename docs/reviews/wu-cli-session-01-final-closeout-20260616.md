# WU-CLI-SESSION-01 Final Closeout

## Scope

- Work unit: WU-CLI-SESSION-01
- Gate: final closeout
- Pull Request: PR-146 https://github.com/noho/dayu-agent-r/pull/146
- Design sources:
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `docs/host/issues-implementation-control.md`

## What Changed

- Host formally added `list_sessions` as a public read API:
  - `Host.list_sessions`
  - `dayu.host.read_api.list_sessions`
  - public result types `SessionListItem` and `ListSessionsResult`
  - package-root exports and package-export tests
- CLI session management was implemented in this work unit:
  - `dayu-cli session list`
  - `dayu-cli session resume`
  - `dayu-cli session purge`
- `interactive --new-session` was removed from the CLI surface.
- CLI session identity and output helpers were added so list / resume / purge use user-facing identity labels without exposing Host internal governance fields.
- `session resume` executes only against an existing OPEN Session. It does not create or ensure a Session and does not use Host wait-resume semantics.
- `session purge` requires `--yes`, routes through Host public `purge_session`, and does not auto close or auto cancel a Session.
- Documentation and README files were synchronized with the final contract:
  - `docs/host/design.md`
  - `dayu/host/README.md`
  - `dayu/README.md`
  - `tests/README.md`

## Verification

- Targeted tests:
  - `pytest tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q`
  - Result: 120 passed, 3 third-party edgar deprecation warnings.
- Type check:
  - `python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors.
- Whitespace / patch integrity:
  - `git diff --check`
  - Result: clean.
- Aggregate deepreview:
  - `docs/reviews/deepreview-wu-cli-session-01-aggregate-ds-20260616.md`
  - `docs/reviews/deepreview-wu-cli-session-01-aggregate-mimo-20260616.md`
  - `docs/reviews/deepreview-wu-cli-session-01-aggregate-adjudication-20260616.md`
  - Result: PASS.
- PR review:
  - `docs/reviews/pr-146-review-wu-cli-session-01-mimo-20260616-222711.md`
  - `docs/reviews/pr-146-review-wu-cli-session-01-ds-20260616.md`
  - `docs/reviews/pr-146-review-wu-cli-session-01-adjudication-20260616.md`
  - Result: PASS; no code fix required.

## Finding Status

- Plan review findings: fixed or explicitly accepted before implementation.
- Slice S1-S6 code review findings: fixed or accepted as non-blocking within the approved slice boundary.
- Aggregate deepreview findings: no blocking findings; PASS.
- PR review findings:
  - Cross-module private narrow-entrypoint coupling: deferred-with-owner. Current design intentionally keeps existing prompt / interactive execution behavior in their original modules and lets `session resume` route through narrow sibling-module entrypoints. Future owner is CLI command-entrypoint refactor or WU-CLI-ACTIVITY-01 if that work changes prompt / interactive execution ownership.
  - `list_sessions` future scale / pagination: deferred-with-owner. Current Host API intentionally ships without pagination, search DSL, callback, profile, or query object. Future owner is a Host session-list scale / pagination hardening work unit if real cardinality or external consumers require it.

## Remaining Risks / Owners

No blocking residual risk remains.

Non-blocking risks with owner / destination:

| Risk | Owner / Destination | Closeout Decision |
|---|---|---|
| `list_sessions` has no pagination or query contract. | Future Host session-list scale / pagination hardening work, only when real cardinality or API consumers require it. | Deferred; not part of WU-CLI-SESSION-01 first formal API. |
| CLI session list uses simple tab-separated output and does not crop or align long labels beyond the current text table format. | Future CLI UX refinement if operator feedback requires it. | Deferred; current output is stable and tested. |
| `session.py` imports narrow existing-session entrypoints from prompt / interactive sibling modules. | Future CLI command-entrypoint refactor or WU-CLI-ACTIVITY-01 if execution ownership changes. | Deferred; current coupling avoids duplicating submit / watch / cancel behavior. |
| Draft PR has no reported CI checks. | Pre-merge review / repository branch protection. | Local validation is the controller truth for this gate. |

## Draft PR / Issue Status

- Draft PR: PR-146 https://github.com/noho/dayu-agent-r/pull/146
- GitHub Issue owner: issue-145.
- Issue closeout: issue-145 was closed on 2026-06-17 after explicit user authorization.

## Next Entry Point

WU-CLI-SESSION-01 is final-closeout complete.

Next entry point after user merge / issue decision: work unit selection. `WU-CLI-ACTIVITY-01` is no longer blocked by WU-CLI-SESSION-01, while the control document still lists `WU-OBS-00` as the default next work unit unless the user selects the CLI activity follow-up.
