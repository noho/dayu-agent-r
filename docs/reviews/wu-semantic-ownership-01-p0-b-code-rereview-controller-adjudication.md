# WU-SEMANTIC-OWNERSHIP-01 P0-B Code Re-review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P0-B`
- Gate: code re-review
- P0-A accepted commit: `6731b451`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p0-b-implementation-codex.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p0-b-fix-codex.md`
- Initial code review artifacts:
  - `docs/reviews/code-review-20260709-154254.md` (AgentDS)
  - `docs/reviews/code-review-20260709-154555.md` (AgentMiMo)
- Initial controller adjudication: `docs/reviews/wu-semantic-ownership-01-p0-b-code-review-controller-adjudication.md`
- Re-review artifacts:
  - `docs/reviews/code-review-20260709-155805.md` (AgentDS)
  - `docs/reviews/code-review-20260709-155918.md` (AgentMiMo)
- Decision date: 2026-07-09

## Decision

`accepted`

Both re-reviewers concluded that P0B-F01, P0B-F02 and P0B-F03 are closed. Controller accepts the closure and finds no new P0-B blocker. P0-B can proceed to accepted commit.

## Accepted Finding Closure

| Finding | Required fix | Re-review result | Controller decision |
|---|---|---|---|
| P0B-F01 | Restore `company_meta_repository` Raises to `无。`; document `_build_upload_result` missing-status `KeyError`. | AgentDS and AgentMiMo both verified the docstring ownership is now correct. | Closed. |
| P0B-F02 | Reject preprocess summaries where categorized counts exceed `selected_count`, while preserving cancellation-safe partial summaries. | Both reviewers verified `_bounded_preprocess_summary` enforces `processed + skipped + failed + not_supported <= selected_count` and focused tests cover over-classified rejection plus partial acceptance. | Closed. |
| P0B-F03 | Make skipped-only preprocess success explicit. | Both reviewers verified `result_status()` now has an explicit skipped success branch and tests cover skipped-only success vs unsupported-only failure. | Closed. |

## Deferred / Rejected Item Integrity

The re-review artifacts confirm deferred and rejected observations from the initial adjudication were not accidentally treated as current fixes:

- `FinsUploadPipelineResult.status` remains a typed string field; upload status enum hardening is still deferred to a future Fins contract item if needed.
- Storage boundary tests continue to assert raw business-readable `ingest_method` strings.
- `read_runtime.py` `meta is None` fallback remains unchanged and is not claimed as fixed.
- SEC result status default hardening remains outside P0-B.

## Validation Basis

Controller accepts the implementation and fix validation recorded in:

- `docs/reviews/wu-semantic-ownership-01-p0-b-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-p0-b-fix-codex.md`

Reported validation:

- Focused preprocess/upload tests: passed.
- `pytest tests/fins tests/service/test_fins_direct.py tests/cli/test_fins_commands.py`: passed, 399 passed, 1 skipped.
- `pytest tests/tools/test_doc_tools_provider.py`: passed, 47 passed.
- `pyright`: passed, 0 errors.
- `git diff --check`: passed.

## Propagation Audit

P0-B semantic propagation now has a single owner boundary for each affected fact:

- Fins ingest method: produced as `FinsIngestMethod`, persisted as the existing storage JSON business string, and projected through read/runtime paths from the same enum conversion.
- Preprocess result status: derived by `FinsPreprocessResultSummary.result_status()` after `_bounded_preprocess_summary` validation, then reused by direct result, progress payload, JSON summary and job record projection.
- Upload status presence: produced by `CnPipeline._build_upload_result` through explicit status payload, validated by `FinsUploadPipelineResult.from_pipeline_json()`, and no longer fabricated by upload runtime fallbacks.

No downstream display, test fixture or single-entry special case is used to mask the fixed semantics.

## Next Gate

Proceed to P0-B accepted commit. After the commit, continue the umbrella WU with ordered sub WU P1-A. This does not close `WU-SEMANTIC-OWNERSHIP-01`; the umbrella still requires P1-A, P1-B, P1-C, P2-A, P2-B, P2-C and later full-repository deepreview rounds before final closeout.
