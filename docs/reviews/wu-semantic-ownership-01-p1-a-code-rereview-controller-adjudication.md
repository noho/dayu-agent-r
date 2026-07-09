# WU-SEMANTIC-OWNERSHIP-01 P1-A Code Re-review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: code re-review
- P0-A accepted commit: `6731b451`
- P0-B accepted commit: `750af328`
- P1-A accepted plan commit: `fd630672`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-implementation-codex.md`
- Code review adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-fix-codex.md`
- Fix validation: `docs/reviews/wu-semantic-ownership-01-p1-a-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/code-review-20260709-p1-a-rereview-mimo.md`
  - `docs/reviews/code-review-20260709-p1-a-rereview-ds.md`
- Decision date: 2026-07-09

## Decision

`accepted`

Both re-reviewers concluded `pass`. Controller accepts that P1A-CR-F01 through P1A-CR-F05 are closed and that the fix introduced no new blocker. P1-A can proceed to accepted commit.

## Closure Summary

| Finding | Required fix | Re-review result | Controller decision |
|---|---|---|---|
| P1A-CR-F01 | Conversation Memory must not rebuild accepted evidence from envelope/raw outcome when projection fields are missing. | Both reviewers verified payload reconstruction is removed and missing projection fields produce limited-signal text. | Closed. |
| P1A-CR-F02 | Compact pipeline must use projection owner unavailable-query text. | Both reviewers verified local fallback text is removed and `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` is imported from projection owner. | Closed. |
| P1A-CR-F03 | Misleading payload fallback helper must be clarified. | Both reviewers verified `_arguments_fallback_query` is gone and request-unavailable query is limited signal. | Closed. |
| P1A-CR-F04 | Projection tests must cover accepted plan completion signals. | Both reviewers verified focused tests now cover identity mismatch, wait-resolution priority, source filtering, descriptor behavior, unsafe arguments, raw outcome mapping and details extraction. | Closed. |
| P1A-CR-F05 | Cross-consumer equivalence test must exist. | Both reviewers verified one accepted result is checked across Tool Trace, Conversation Memory, RunInputBuilder and CompactMaterial using projection-owner output. | Closed. |

## Controller Validation Basis

Controller independently validated after the fix:

- `pytest tests/host/test_accepted_result_projection.py`: 11 passed.
- `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py`: 46 passed.
- `pytest tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_host_activity_event_projection.py`: 221 passed.
- `pytest tests/host/test_compact_pipeline.py`: 11 passed.
- grep residual scan: remaining matches classified as compaction schema fields, projection-cleaned source assignment, projection-owner request-atom use, and payload primitive definition/export.
- `pyright`: 0 errors.
- `git diff --check`: passed.

## Residual Risk

- `_contains_unsafe_argument_key` remains a bounded projection-owner heuristic. This is a future hardening option, not a consumer-side workaround.
- `source_note` remains compaction schema vocabulary; accepted-result values are projection-cleaned.

No unowned P1-A residual risk remains.

## Propagation Audit

P1-A now has a single Host projection owner for accepted tool result query/status/source/result semantics:

- Produce: ToolRuntime / wait-resume accept barriers produce accepted result facts and request atoms.
- Validate: `project_accepted_tool_result(...)` validates envelope, payload descriptor, request identity, unsafe query exposure, status mapping and source filtering.
- Persist: EventLog, payload descriptor and request atom durable state remain unchanged.
- Project: Tool Trace, canonical Read API activity, Durable Memory, Conversation Memory, RunInputBuilder, CompactMaterial and compact pipeline consume projection output or direct projection-derived fields.
- LLM-facing output: unavailable-query text and missing-projection limited-signal text come from the projection owner; downstream consumers do not reconstruct accepted evidence.

## Next Gate

Proceed to P1-A accepted commit. After the commit, continue to ordered sub WU P1-B.
