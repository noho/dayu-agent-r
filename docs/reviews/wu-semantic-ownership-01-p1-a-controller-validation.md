# WU-SEMANTIC-OWNERSHIP-01 P1-A Controller Validation

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: implementation validation
- P0-A accepted commit: `6731b451`
- P0-B accepted commit: `750af328`
- P1-A accepted plan commit: `fd630672`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-implementation-codex.md`
- Validation date: 2026-07-09

## Controller Validation Commands

- `source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py`
  - Result: passed, 4 passed.
- `source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py`
  - Result: passed, 46 passed.
- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_host_activity_event_projection.py`
  - Result: passed, 220 passed.
- `source .venv/bin/activate && rg -n "_readable_query_text_from_envelope|_tool_result_query_text|_tool_result_status|def _llm_facing_evidence_source_text|_is_internal_evidence_source_part|_readable_source_text_from_refs|source_note|tool_call_request_atoms" dayu/host`
  - Result: passed by classification. Remaining matches are allowed schema fields in `dayu/host/compaction.py`, the cleaned accepted source assignment in `dayu/host/compact_material.py`, the projection owner call to `tool_call_request_atoms` in `dayu/host/accepted_result_projection.py`, and the primitive definition/export in `dayu/host/payload_resolution.py`.
- `source .venv/bin/activate && pyright`
  - Result: passed, 0 errors.
- `git diff --check`
  - Result: passed.

## README / Design Checks

- `dayu/host/README.md` was checked and updated because P1-A changes `dayu/host/` and establishes the implemented accepted result projection boundary.
- `tests/README.md` was checked and updated because P1-A adds/updates Host tests for accepted result projection and consumer migration.
- `docs/host/design.md` and `docs/engine/design.md` were not updated. P1-A does not change durable schema, Host/Engine layering, or public design truth; it implements the already accepted Host projection owner boundary inside `dayu.host`.

## Propagation Audit

- Produce: existing ToolRuntime / waiting accepted result facts and request atoms remain the durable producers.
- Validate: `dayu.host.accepted_result_projection.project_accepted_tool_result(...)` centralizes payload, envelope, request atom identity, status, query and source validation.
- Persist: EventLog row, payload store and request atom tables remain durable truth; the projection helper does not write derived truth back to durable state.
- Trace / Read API: Tool Trace and canonical Read API activity consume projection status/query/result/source; PREVIEW activity remains preview-only.
- Memory: durable memory projection and Conversation Memory consume projection-cleaned query/result/source.
- Run input / compact: RunInputBuilder, CompactMaterial and compact pipeline consume projection-cleaned accepted evidence and no longer own request back-query or source blacklist semantics.
- LLM-facing output: limited-signal query text and cleaned source text now come from the projection owner, not from downstream consumer fallbacks.

## Residual Risk Classification

- Conversation Memory still has a legacy fallback for missing projection fields. Controller classifies this as a historical-input degradation path, not the new accepted-result owner path. Reviewers should verify it cannot mask current projection drift.
- `source_note` remains as a compaction schema field. Controller classifies this as allowed schema vocabulary as long as accepted-result values are produced from the projection helper.
- `tool_call_request_atoms` remains as a lower-level payload primitive and is called by the projection owner. Downstream consumers must not call it to re-own query/status/source semantics.

## Decision

Controller validation passes. Proceed to P1-A code review by AgentMiMo and AgentDS.
