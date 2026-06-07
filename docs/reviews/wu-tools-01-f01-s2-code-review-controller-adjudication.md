# WU-TOOLS-01-F01 Slice S2 Code Review Controller Adjudication

## Gate Metadata

- Gate: code review adjudication.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S2 - Preprocess / Process Runtime Pipeline`.
- Branch: `host-wu-tools-01-f01`.
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s2-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f01-s2-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s2-code-review-ds.md`
  - `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`

## Summary

Both reviewers returned `pass-with-findings`. The implementation stays within the approved S2 boundary, uses `dayu.fins.storage` repository protocols for source and processed document access, and passes the required focused tests and pyright according to both reviewers.

Two findings are accepted for the Slice S2 fix gate. No finding is rejected or deferred.

## Findings

### F01-S2-001 - accepted

- Source: AgentDS.
- Severity: medium.
- File: `dayu/fins/ingestion_runtime.py:1025`.
- Finding: `_MAX_PREPROCESS_DOCUMENTS` is checked before form/deleted/ingest-complete filtering. A ticker with more than 50 total source documents but fewer than or equal to 50 matching the request filters is incorrectly rejected.
- Controller judgment: accepted. The S2 plan requires whole-ticker processing with bounded selection. The bound must apply to the actual selected work set after request filters, not the unfiltered repository inventory. This is a correctness issue in the current slice, not a future provider concern.
- Required fix:
  - Move the max-count check to the filtered document id set.
  - Add a regression test where whole-ticker selection sees more than `_MAX_PREPROCESS_DOCUMENTS` source documents but the form filter narrows the processed set below the bound.

### F01-S2-002 - accepted

- Source: AgentMiMo and AgentDS.
- Severity: low.
- File: `dayu/fins/ingestion_runtime.py:1240`.
- Finding: `_save_failed_from_exception` silently swallows secondary job-store failures while trying to persist a failed terminal record.
- Controller judgment: accepted. The method should remain best-effort and must not crash the daemon thread, but silent loss of terminalization diagnostics weakens production observability and makes future wait-adapter lost-state debugging harder.
- Required fix:
  - Add bounded diagnostic logging when terminalization itself fails.
  - Keep the non-throwing behavior.
  - Add a focused test proving the path logs diagnostic context without propagating the secondary exception.

## Rejected Findings

None.

## Deferred Findings

None.

## Required Validation For Fix Gate

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`
- `source .venv/bin/activate && pyright`

## Next Gate

Proceed to Slice S2 fix gate with AgentCodex. Do not commit, push, open PR, or enter re-review until the fix artifact is available.
