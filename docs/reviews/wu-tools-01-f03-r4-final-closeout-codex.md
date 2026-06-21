# WU-TOOLS-01-F03-R4 Final Closeout

## Status

Final closeout is blocked on external issue comment authorization.

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
- Broad affected suite excluding classified non-WU web smoke residual: `866 passed, 1 skipped`.
- PR review confirmed PR body accuracy, issue-133 completeness, residual owners, and no blocking PR issues.

## Remaining Risks / Owners

- `WU-TOOLS-01-F03-R4-POLICY-R1`: Future Host / policy design owns unified local file-read authorization if needed.
- `WU-TOOLS-01-F03-R4-PATH-R1`: Future provider path-boundary hardening owns any stronger symlink policy.
- `WU-TOOLS-01-F03-R4-SCENE-R1`: Future scene manifest maintenance owns dynamic default-scene discovery hardening.
- `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1`: Web smoke / CI owner owns the stdout-vs-logging capture mismatch in `tests/tools/web/test_smoke_web_ci.py`.

## Issue Link Status

- PR body uses `Closes #133`.
- This is correct because GitHub issue-133's six requested Tools Discovery spec items are implemented, tested, and documented.

## Blocking Item

Final closeout pass still requires posting a closeout comment to GitHub issue-133. External issue comments require user authorization, so the work unit is stopped at this authorization point.
