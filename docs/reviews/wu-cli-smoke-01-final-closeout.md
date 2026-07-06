# WU-CLI-SMOKE-01 Final Closeout

## Gate

- Work unit: WU-CLI-SMOKE-01
- Gate: final closeout
- Date: 2026-07-06
- Draft PR: https://github.com/noho/dayu-agent-r/pull/172
- Branch: `phase/host-issues-control`
- Base: `main`
- Issue: none by user decision

## What Changed

- Fixed `dayu-cli interactive` idle Ctrl+C behavior to match Codex / Claude Code style: first idle Ctrl+C asks for confirmation, second exits.
- Fixed MANUAL-F01 root cause: Host awaiting snapshot digest is now stable and accepted by the entrypoint awaiting path.
- Aligned `dayu-cli prompt` and `dayu-cli interactive` display semantics:
  - `--thinking` / `--no-thinking` are CLI display toggles only.
  - `--detail` / `--no-detail` are available for both prompt and interactive.
  - Both default to `--thinking --detail`.
  - thinking / detail are running-state displays and do not enter final answer, activity, outbox terminal projection, canonical replay, or interactive final transcript.
- Added Host public thinking projection:
  - Engine `REASONING_DELTA`
  - Host `PREVIEW` row / `HostThinkingView`
  - Service `EntrypointThinking` callback
  - CLI stderr renderer
- Updated README, Host / Service / tests README, design truth, tests, and control document.

## Accepted Commits

- Plan: `c0b79339`
- Slice S1 idle Ctrl+C: `52e4fcd3`
- MANUAL-F01 awaiting fix: `164072b0`
- MANUAL-F01 control record: `78a26006`
- Display semantics implementation: `c1b546ac`
- Display semantics control record: `14442e6f`
- Draft PR record: `23ed37e1`
- PR review fix / accepted PR review: `632c1f34`

## Review Artifacts

- Display semantics implementation/fix: `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`
- Display semantics reviews and re-reviews:
  - `docs/reviews/wu-cli-smoke-01-display-semantics-review-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-review-ds.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-rereview-ds.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-final-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-final-rereview-ds.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-prompt-lifecycle-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-prompt-lifecycle-rereview-ds.md`
- PR review and re-review:
  - `docs/reviews/pr-172-review-20260706-210832.md`
  - `docs/reviews/pr-172-review-ds.md`
  - `docs/reviews/pr-172-review-fix-codex.md`
  - `docs/reviews/pr-172-rereview-mimo.md`
  - `docs/reviews/pr-172-rereview-ds.md`

## Validation

- `source .venv/bin/activate && pytest tests/cli -q`
  - `225 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/host/test_engine_ingest_mapping.py tests/host/test_host_activity_event_projection.py -q`
  - `126 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/host/test_host_activity_event_projection.py -q`
  - `17 passed`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed
- `gh pr checks 172`
  - no checks reported on branch `phase/host-issues-control`

## Residual Risks

| ID | Status | Owner / Destination | Notes |
|---|---|---|---|
| WU-CLI-SMOKE-01-R1 | deferred-with-owner | WU-RET-03 / GitHub Issue #78 under #43 retention lane | `REASONING_DELTA` thinking text is stored as a `PREVIEW` row for live watcher projection; retention / purge governance should classify PREVIEW cleanup policy. |
| WU-CLI-SMOKE-01-R2 | deferred-with-owner | Future CLI UI enhancement / user decision | CLI thinking remains a single-line 160-character running-state display. |
| DS-F03 | deferred-with-owner | Future CLI UI/runtime hardening | `CliThinkingRenderer._seen_dedupe_keys` is unbounded within one renderer lifetime; current per-turn lifecycle makes this low risk. |

## Closeout

Final closeout passes. Draft PR #172 is open and remains draft. No issue closeout comment is needed because this work unit intentionally has no GitHub Issue owner. After PR #172 is merged, pull latest `main` and resume phaseflow from `docs/host/issues-implementation-control.md` next entry point to select the next active backlog work unit.
