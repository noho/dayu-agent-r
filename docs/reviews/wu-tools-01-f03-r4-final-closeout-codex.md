# WU-TOOLS-01-F03-R4 Final Closeout

## Status

Final closeout pass is complete.

## Completed Gates

- Draft PR: https://github.com/noho/dayu-agent-r/pull/160
- PR state: OPEN / draft
- Base: `main`
- Head: `phase/wu-tools-01-f03-r4`
- PR review pass pushed HEAD: `ecf83c5f13d4b74d7f58f120c46bac3fa389c64f`
- PR review artifacts:
  - `docs/reviews/wu-tools-01-f03-r4-pr-review-mimo.md`, verdict `pass`
  - `docs/reviews/wu-tools-01-f03-r4-pr-review-ds.md`, verdict `pass-with-findings`, no blocking findings
- Accepted PR review commit:
  - `ecf83c5f` (`gateflow: accept PR review for WU-TOOLS-01-F03-R4`)
- Final push after PR review:
  - pushed `ecf83c5f` to `github/phase/wu-tools-01-f03-r4`
- Issue closeout comment:
  - posted to GitHub issue-133 at https://github.com/noho/dayu-agent-r/issues/133#issuecomment-4760536817

## What Changed

- Removed provider-level `allow_empty` from Tools Discovery config/runtime/service mapping while preserving scene `tool_selection.allow_empty`.
- Removed Fins read provider `include_read_tools`.
- Set packaged Fins `workspace_root` default to `workspace/` and resolved it in Service to effective absolute provider config.
- Migrated Doc / Fins limits into packaged `tool_discovery.json`.
- Removed upload `allowed_upload_roots` and local tool-owned allowlist enforcement.
- Kept Fins repository writes under `dayu.fins.storage`.
- Prevented default non-upload scenes from selecting `start_fins_upload` through broad Fins / ingestion tags.
- Updated README / design / tests / control doc, including a new anti-over-splitting constraint in Slice 切分原则.

## Verification

- Focused WU suites passed as recorded in final validation and PR review artifacts.
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`.
- Broad affected suite excluding historical web smoke caveat: `866 passed, 1 skipped`.
- Post-reconciliation `python utils/smoke_web_ci.py --output-dir workspace/output/web_smoke/manual-wu-tools-f03-r4-final --run-label manual-wu-tools-f03-r4-final`: `SMOKE STATUS passed`, `SMOKE EXIT_CODE 0`, `SMOKE FAILURES 0`.
- Post-reconciliation `pytest tests/tools/web -q`: `76 passed`, with 3 upstream `edgar` deprecation warnings.
- PR review confirmed PR body accuracy, issue-133 completeness, residual owners, and no blocking PR issues.

## Remaining Risks / Owners

- No active WU-TOOLS-01-F03-R4 residual risk remains after residual reconciliation.

## Issue Link Status

- PR body uses `Closes #133`.
- This is correct because GitHub issue-133's six requested Tools Discovery spec items are implemented, tested, and documented.

## Blocking Item

No remaining closeout blocker. The work unit is at final-closeout-pass and awaits user merge / PR disposition for draft PR 160.
