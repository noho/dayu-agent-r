# WU-SEMANTIC-OWNERSHIP-01 P1-A Fix Controller Validation

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: code fix validation
- P1-A accepted plan commit: `fd630672`
- Code review adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-fix-codex.md`
- Validation date: 2026-07-09

## Controller Validation Commands

- `source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py`
  - Result: passed, 11 passed.
- `source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py`
  - Result: passed, 46 passed.
- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_host_activity_event_projection.py`
  - Result: passed, 221 passed.
- `source .venv/bin/activate && pytest tests/host/test_compact_pipeline.py`
  - Result: passed, 11 passed.
- `source .venv/bin/activate && rg -n "_readable_query_text_from_envelope|_tool_result_query_text|_tool_result_status|def _llm_facing_evidence_source_text|_is_internal_evidence_source_part|_readable_source_text_from_refs|source_note|tool_call_request_atoms" dayu/host`
  - Result: passed by classification. Remaining matches are compaction schema `source_note` fields, the projection-cleaned `source_note=block.readable_source_text` assignment, the projection owner `tool_call_request_atoms` call, and primitive definition/export.
- `source .venv/bin/activate && pyright`
  - Result: passed, 0 errors.
- `git diff --check`
  - Result: passed.

## Accepted Finding Closure Basis

- P1A-CR-F01: Conversation Memory no longer rebuilds accepted evidence from envelope/raw outcome when projection fields are absent; missing fields produce a limited-signal text.
- P1A-CR-F02: Compact pipeline consumes `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` from the projection owner.
- P1A-CR-F03: Misleading payload fallback helper was replaced by request-unavailable limited-signal behavior.
- P1A-CR-F04: Projection helper focused tests now cover identity mismatch, wait-resolution priority, source filtering, descriptor behavior, unsafe arguments, raw `result.ok == false`, and details extraction.
- P1A-CR-F05: A cross-consumer equivalence test now verifies one accepted result across Tool Trace, durable/Conversation Memory, RunInputBuilder and CompactMaterial.

## Decision

Controller validation passes. Proceed to P1-A code re-review by AgentMiMo and AgentDS.
