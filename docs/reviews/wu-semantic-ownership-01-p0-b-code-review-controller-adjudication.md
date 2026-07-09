# WU-SEMANTIC-OWNERSHIP-01 P0-B Code Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P0-B`
- Gate: code review
- P0-A accepted commit: `6731b451`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p0-b-implementation-codex.md`
- Controller validation note: `docs/reviews/wu-semantic-ownership-01-p0-b-controller-validation.md`
- Review artifacts:
  - `docs/reviews/code-review-20260709-154254.md` (AgentDS)
  - `docs/reviews/code-review-20260709-154555.md` (AgentMiMo)
- Decision date: 2026-07-09

## Decision

`fix-required`

Both reviewers found no blocking or high-severity defect, and controller accepts that P0-B's main semantic direction is correct. However, the following low-severity findings are accepted and must be fixed before P0-B can proceed to accepted commit.

## Accepted Findings

### P0B-F01: `CnPipeline._build_upload_result` docstring edit landed on the wrong function

- Source: AgentDS 001.
- Severity: low.
- Decision: accepted.
- Rationale: The change made `company_meta_repository` claim it raises a payload/status `KeyError`, while `_build_upload_result` now actually can raise `KeyError` after removing the status fallback. This violates the project docstring constraint and should be fixed in place.
- Required fix:
  - Restore `company_meta_repository` Raises to `无。`
  - Update `_build_upload_result` Raises to include `KeyError: payload 缺少显式 status 时抛出。`

### P0B-F02: `_bounded_preprocess_summary` does not validate cross-field count consistency

- Source: AgentMiMo F-01 and AgentDS Open Question OQ-1.
- Severity: low.
- Decision: accepted.
- Rationale: `_bounded_preprocess_summary` is now the validation owner for preprocess summary counts. It should reject impossible count states instead of validating each bucket independently. This belongs in the Fins summary owner boundary, not in downstream consumers.
- Required fix:
  - Add a cross-field invariant that prevents categorized count sum from exceeding `selected_count`.
  - Preserve cancellation-safe partial summaries where `selected_count` can be greater than the categorized sum before cancellation closeout.
  - Add focused tests for invalid over-classified counts.

### P0B-F03: `result_status()` skipped-only success is implicit fallthrough

- Source: AgentMiMo F-02.
- Severity: low.
- Decision: accepted.
- Rationale: This is not a runtime defect, but the helper is now the semantic owner for preprocess status. The all-skipped success case should be explicit so future edits do not reinterpret the final fallthrough as a generic success default.
- Required fix:
  - Make the skipped-only success branch explicit, or document it inside the helper.
  - Keep current product semantics: processed > 0 is success; unsupported-only / failed / no selected docs are failure; skipped-only is success.
  - Add or adjust focused tests if needed.

## Rejected / Deferred Observations

| Observation | Decision | Rationale |
|---|---|---|
| `FinsUploadPipelineResult.status` is `str` rather than enum | deferred-with-owner | P0-B required typed validation and removal of missing-field fallback, not a full upload status enum taxonomy. Future upload status enum can be a later Fins contract hardening item if needed. |
| Tests assert storage `ingest_method` raw strings | rejected-with-reason | Tests are asserting storage JSON boundary, where business-readable strings are the correct public representation. |
| `docs/host/issues-implementation-control.md` is in diff | rejected-with-reason | This is controller gate state, not production P0-B implementation. |
| `read_runtime.py` `meta is None` fallback to upload | deferred-with-owner | Both reviewers judged this preserves existing behavior while `meta` present but missing `ingest_method` now fail-fast. It is not a current P0-B blocker; if product wants missing meta to be a hard data integrity error, handle in a later Fins read-path hardening item. |
| SEC `SecPipeline._build_result(...)` remains outside P0-B allowed files | deferred-with-owner | It is outside this sub WU's allowed files and current upload workflow emits explicit status before typed validation. |

## Next Gate

Proceed to P0-B fix by AgentCodex. After fix, run focused validation and send both reviewers through re-review. P0-B is not accepted until accepted findings P0B-F01 through P0B-F03 are closed.
