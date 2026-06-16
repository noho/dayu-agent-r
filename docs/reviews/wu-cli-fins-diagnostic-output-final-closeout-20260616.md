# WU-CLI-FINS-DIAG-01 Final Closeout

## Scope

- Work unit: `WU-CLI-FINS-DIAG-01`
- Closed residuals:
  - `WU-CLI-FINS-OBS-01-R3`
  - `WU-CLI-FINS-OBS-01-R5`
- Design truth: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- Control doc: `docs/host/issues-implementation-control.md`

## Result

`WU-CLI-FINS-DIAG-01` is completed locally.

- Runtime / CLI diagnostics now use stderr by default; CLI `main()` explicitly passes `sys.stderr`.
- stdout remains the user UI / command-result channel.
- Fins CLI output no longer treats absolute paths as secrets; bounded text display remains.
- Fins direct verbose/debug diagnostics include bounded useful summaries and do not log raw payloads, job ids, sidecar/durable cursors, artifact refs or API keys.
- Prompt / interactive / Fins tests cover `--verbose` and `--debug` stdout cleanliness.

## Gate Artifacts

- Plan: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- Plan reviews:
  - `docs/reviews/wu-cli-fins-diagnostic-output-plan-review-ds-20260616.md`
  - `docs/reviews/plan-review-20260616-150120.md`
- Plan fix: `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-codex-20260616.md`
- Plan fix re-reviews:
  - `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-rereview-ds-20260616.md`
  - `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-rereview-mimo-20260616.md`
- Implementation: `docs/reviews/wu-cli-fins-diagnostic-output-implementation-codex-20260616.md`
- Implementation reviews:
  - `docs/reviews/wu-cli-fins-diagnostic-output-implementation-review-ds-20260616.md`
  - `docs/reviews/wu-cli-fins-diagnostic-output-implementation-review-mimo-20260616.md`
- Review fix: `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-controller-20260616.md`
- Review fix re-reviews:
  - `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-rereview-ds-20260616.md`
  - `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-rereview-mimo-20260616.md`

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q
```

Result: 121 passed, 3 warnings. Warnings are third-party `edgar` deprecation warnings already observed in prior validation.

Passed:

```bash
source .venv/bin/activate && pyright dayu/ tests/ utils/
```

Result: 0 errors, 0 warnings, 0 informations.

Passed:

```bash
git diff --check
```

Result: clean.

## Residual Reconciliation

- `WU-CLI-FINS-OBS-01-R3`: closed. The implementation removes path-as-secret redaction from Fins CLI display, keeps bounded display, and adds diagnostics that preserve useful document labels / business summaries unless they are actual secrets.
- `WU-CLI-FINS-OBS-01-R5`: closed. Runtime / CLI diagnostics now go to stderr, stdout remains user UI / command result, and prompt / interactive / Fins tests cover `--verbose` / `--debug` cleanliness.

No new active residual risk is introduced by this work unit.

Out-of-scope follow-ups remain in their existing destinations:

- Prompt / interactive user-visible activity stream UI: GitHub Issue #144 / `WU-CLI-ACTIVITY-01`.
- CLI session management resume/list/purge and `--new-session` removal: GitHub Issue #145 / `WU-CLI-SESSION-01`.
- Engine/provider diagnostic redaction policy was not changed by this work unit.

## Next Entry

Current local closeout returns to backlog selection. Default next work unit remains `WU-OBS-00`.
