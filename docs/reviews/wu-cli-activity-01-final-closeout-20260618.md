# WU-CLI-ACTIVITY-01 Final Closeout

## Scope

- Work unit: WU-CLI-ACTIVITY-01
- GitHub issue: #144
- Draft PR: https://github.com/noho/dayu-agent-r/pull/149
- Branch: `wu-cli-activity-01`

## Outcome

- Activity stream path is implemented through Host public `HostEvent` activity projection, Service activity callback, and CLI rendering.
- CLI output/logging separation is implemented: diagnostic logs default to temp log files, `--log-file` is global, and `prompt --detail / --no-detail` controls activity stream visibility.
- Interactive composer / run view supports multiline input, history/editor behavior, running cancel behavior, and transcript/activity switching.
- Prompt/interactive existing-session startup semantics are implemented according to the user裁决: prompt stays one-shot; interactive handles existing-session backfill/reconnect/barrier before the REPL.
- Follow-up EventLog/projection hardening is implemented:
  - `content_delta`, `reasoning_delta`, and `tool_call_delta` are accepted without durable EventLog rows.
  - ProjectionRunner uses filter-aware EventLog reads with covered cursor semantics.
  - Conversation Memory projection catch-up/rebuild has no semantic budget.
  - Host hot paths do not run unbounded Conversation Memory catch-up.
  - RunInputBuilder inline memory repair shares the Conversation Memory projection filter truth.

## Review Gates

- Follow-up aggregate reviews:
  - `docs/reviews/mimo-aggregate-wu-cli-activity-01-followup-20260618-081816.md`
  - `docs/reviews/ds-aggregate-wu-cli-activity-01-followup-20260618-081532.md`
- Follow-up focused re-reviews:
  - `docs/reviews/mimo-aggregate-rereview-wu-cli-activity-01-followup-20260618.md`
  - `docs/reviews/ds-aggregate-rereview-wu-cli-activity-01-followup-20260618-082351.md`
- PR reviews:
  - `docs/reviews/wu-cli-activity-01-pr-review-mimo-20260618.md`
  - `docs/reviews/wu-cli-activity-01-pr-review-ds-20260618.md`
- PR review fix:
  - `docs/reviews/wu-cli-activity-01-pr-review-fix-codex-20260618.md`
- PR focused re-reviews:
  - `docs/reviews/wu-cli-activity-01-pr-rereview-mimo-20260618.md`
  - `docs/reviews/wu-cli-activity-01-pr-rereview-ds-20260618.md`

All final review gates are PASS with no blocking findings.

## Validation

- `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q`
  - 348 passed
- `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q`
  - 114 passed, 3 third-party edgar deprecation warnings
- `python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean

## Residual Risk

- `WU-CLI-ACTIVITY-01-PR-R1` tracks two Host smoke tests that fail on `main` as well. They are deferred to a future Host public multiturn / memory smoke stabilization WU and are not blockers for PR #149.
- GitHub reports no checks for branch `wu-cli-activity-01`; validation for this closeout is local plus dual-agent review.
