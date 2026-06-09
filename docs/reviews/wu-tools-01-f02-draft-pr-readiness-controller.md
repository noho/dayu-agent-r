# WU-TOOLS-01-F02 Draft PR Readiness

## Status

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Gate: ready-to-open-draft-PR
- Date: 2026-06-09
- Branch: `phase/wu-tools-01-f02`
- Accepted commits:
  - Plan: `ded9e690`
  - Slice 1: `8f5bb379`
  - Slice 2: `6984c514`
  - Slice 3: `89604aa0`
  - Aggregate deepreview: `0f843b34`

## Delivered Scope

WU-TOOLS-01-F02 migrated the opt-in Web diagnostics pipeline into the current repository:

- `utils/diag_web.sh`
- `utils/diag_web_batch.sh`
- `utils/web_ci_urls.jsonl`
- `utils/diagnose_web_access.py`
- `tests/tools/web/test_diagnose_web_access.py`

The diagnostic script supports single URL and URL-file batch modes, raw requests evidence, current `fetch_web_page` through the current `ToolDefinition.callable` boundary, optional Playwright evidence, storage-state path handling, batch result/summary artifacts, and deterministic tests.

## Validation

Latest Controller validation:

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q`: `27 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: `0 errors`
- `bash -n utils/diag_web.sh utils/diag_web_batch.sh`: passed
- `git diff --check`: passed
- precise forbidden import / wide-type scan: no matches

## Non-Goals Preserved

- No default live CI workflow was added.
- No Web smoke pass/fail/skip gate was defined.
- `WU-TOOLS-01-S5-R2` remains owned by WU-TOOLS-01-F03.
- OLD `ToolRegistry`, OLD truncation manager, OLD `fetch_more`, OLD `dayu.web`, and UI paths were not restored.
- Host, Engine, ToolRuntime, durable schema, EventLog, and production Web tool behavior were not changed.

## Residual Risks

| Risk | Status | Owner / Destination |
|---|---|---|
| Live network, real Playwright, storage-state cookies, anti-bot challenge behavior, and provider/API availability are not proven by deterministic tests. | deferred-with-owner | WU-TOOLS-01-F03 |
| F03 may need to consume diagnostic JSON fields beyond the F02 minimum stable subset. | deferred-with-owner | WU-TOOLS-01-F03 plan must declare the consumed fields and mismatch behavior. |
| Batch diagnostics are serial and may be slow for large URL files. | deferred-with-owner | WU-TOOLS-01-F03 or later maintenance only if this becomes a practical bottleneck. |

## Readiness Decision

Ready to push `phase/wu-tools-01-f02` and create a draft PR.
