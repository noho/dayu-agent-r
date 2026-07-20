# WU-SEMANTIC-OWNERSHIP-01 P2-D implementation controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-D`
- Gate: implementation validation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-codex.md`

## Motivation And Owner Boundary

The implementation addresses the accepted public compact smoke residual at the
shared accepted-result projection owner. It does not alter durable
`TOOL_RESULT_ACCEPTED` schema and does not add compact-material, memory,
RunInput, Tool Trace, Read API, or test-fixture fallback branches for source
text.

Owner boundary remains:

1. ToolRuntime / Host accept path persists accepted tool result truth.
2. `dayu/host/accepted_result_projection.py` projects query/status/result/source
   into LLM-facing semantics.
3. Downstream consumers consume the projection and do not reconstruct source
   from event id, payload ref, digest, cursor, policy, ToolRuntime or Host
   governance fields.

## Diff Review

Production changes:

- `dayu/host/accepted_result_projection.py`
  - Adds `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT`.
  - Tightens `AcceptedToolResultSourceProjection.text` to `str`.
  - Makes unavailable source branches return the shared LLM-facing text while
    preserving `state` and `diagnostic_reason`.
- `dayu/host/durable/memory.py`
  - Docstring-only sync for `evidence_source_text`.

Test changes cover projection, compact material, RunInputBuilder, Conversation
Memory, Tool Trace and public compact smoke. The public smoke sets
`selected_recent_window_turn_floor=0` for the specific fact-generation scenario
so the newly produced raw accepted evidence is compactable; it does not add
source refs to the fixture and does not change production selection policy.

## Controller Validation

Controller reran:

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence -q
```

Result: `1 passed`.

```bash
source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py -q
```

Result: `13 passed`.

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
```

Result: `206 passed`.

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q
```

Result: `46 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: passed.

Required source-leak scan:

```bash
rg -n "event_id|payload_ref|payload_digest|cursor|policy|ToolRuntime|Host governance|digest" dayu/host/accepted_result_projection.py tests/host/test_accepted_result_projection.py
```

Result: hits are limited to internal implementation fields, diagnostic payload
refs, digest validation paths, test fixture inputs, and no-leak assertions. The
new source-unavailable text does not contain internal refs or governance terms.

## Review Focus

Reviewers must specifically verify:

1. The source-unavailable text belongs in the shared projection owner and is
   not duplicated downstream.
2. Tightening `AcceptedToolResultSourceProjection.text` to `str` does not create
   unsafe contract churn.
3. The public smoke `selected_recent_window_turn_floor=0` change is a valid
   test-goal setup for compacting newly produced evidence, not a fixture mask.
4. Memory, compact material, RunInput and Tool Trace visible outputs do not leak
   internal refs or Host / ToolRuntime governance terms.
5. README trigger decisions are correct.
