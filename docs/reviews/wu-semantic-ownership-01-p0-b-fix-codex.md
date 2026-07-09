# WU-SEMANTIC-OWNERSHIP-01 P0-B Fix

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P0-B`
- Role: AgentCodex fix
- Date: 2026-07-09
- Scope: only accepted findings in `docs/reviews/wu-semantic-ownership-01-p0-b-code-review-controller-adjudication.md`

## Owner Boundary

Preprocess summary count semantics are owned by `dayu.fins.ingestion_runtime.FinsPreprocessResultSummary` and its validation helper `_bounded_preprocess_summary`. The helper is the first shared validation boundary before status calculation, JSON summary projection, direct event details, progress payload and legacy job record projection.

CN upload result status presence is produced by `CnPipeline._build_upload_result`; its fail-fast behavior and docstring belong at that producer boundary. `company_meta_repository` is an unrelated repository getter and must not document upload payload exceptions.

## Accepted Finding Closure

| Finding | Status | Fix |
|---|---|---|
| P0B-F01 docstring placement | Closed | Restored `CnPipeline.company_meta_repository` Raises to `无。`; updated `CnPipeline._build_upload_result` Raises to document missing explicit `status` `KeyError`. |
| P0B-F02 preprocess summary cross-field invariant | Closed | `_bounded_preprocess_summary` now rejects `processed_count + skipped_count + failed_count + not_supported_count > selected_count`. It still allows `selected_count` greater than categorized count for cancellation-safe partial summaries. |
| P0B-F03 explicit skipped-only success semantics | Closed | `FinsPreprocessResultSummary.result_status()` now has an explicit `skipped_count > 0` success branch while preserving existing processed / unsupported / failed / no-selection semantics. |

## Changed Files

- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `docs/reviews/wu-semantic-ownership-01-p0-b-fix-codex.md`

README checks were performed for `dayu/fins/README.md` and `tests/README.md`. No README update was needed because this fix changes internal validation/documentation and focused coverage, not Fins public capability, user workflow or test layering.

## Propagation Audit

Preprocess summary counts:

- Producer: `_execute_preprocess_request` creates `FinsPreprocessResultSummary` with selected, processed, skipped, not-supported and failed counts.
- Validation owner: `_bounded_preprocess_summary` validates non-negative counts, count-to-ID cardinality and the cross-field upper bound against `selected_count`.
- Status projection: `result_status()` consumes the same validated summary and keeps `processed_count > 0` success, no selected / failed / unsupported failure, and skipped success.
- JSON / event / job projection: `to_json_summary()`, `_preprocess_result_details()`, `_preprocess_summary_progress_payload()` and legacy job records derive from the same summary fields.
- Test coverage: `test_preprocess_result_status_rejects_over_classified_counts` covers invalid over-classification and cancellation-safe partial summary acceptance.

CN upload result:

- Producer: `_build_upload_result` requires payload `status` through `payload.pop("status")`.
- Validation downstream: `FinsUploadPipelineResult.from_pipeline_json()` continues to require explicit non-empty `status`.
- Documentation: docstrings now match the producer behavior and no unrelated repository getter claims the upload exception.

## Validation Results

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -k "preprocess_result_status or upload_pipeline_result_requires_status or unsupported_document_records_not_supported"`: passed, 4 selected.
- `source .venv/bin/activate && pytest tests/fins tests/service/test_fins_direct.py tests/cli/test_fins_commands.py`: passed, 399 passed, 1 skipped.
- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py`: passed, 47 passed.
- `source .venv/bin/activate && pyright`: passed, 0 errors.
- `git diff --check`: passed.

## Residual Risk

- No known residual risk for the three accepted findings.
- Existing P0-B deferred items from the adjudication remain out of scope for this fix, including upload status enum hardening and SEC download result status defaults.
