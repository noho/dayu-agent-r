# WU-DUR-P01 Slice 2 Implementation - Codex

## status

implemented

## changed files

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/agent.py`
- `dayu/engine/__init__.py`
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/schema.py`
- `dayu/host/tool_trace.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_tool_trace_projection.py`
- `dayu/engine/README.md`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-implementation-codex.md`

## implementation summary

- Engine `IterationStartedData` now carries Engine-owned runner input observations: `message_count`, `role_sequence_digest`, and `runner_input_serializer_schema_version`.
- Engine computes `role_sequence_digest` from the actual `AgentMessage.role.value` sequence immediately before the Runner call.
- Host `RunInputBuilder` writes a `RUNNER_CALL_INPUT_ASSEMBLED` canonical event for ordinary runner input assembly and stores the manifest body through a `runner_call_input_manifest` payload descriptor.
- The manifest body contains refs, digests, message summaries, source refs, input projection digest, role digest, and projector metadata. It does not inline full message content, full prompts, compact material, memory snapshot content, provider raw request / response, or raw provider dicts.
- Host Engine ingest copies Engine-owned `iteration_started` observations into preview payloads and validates them against an existing Host manifest signal when one exists. Missing manifest is recorded as `limited_signal`, not converted into a fabricated Host manifest truth.
- Tool Trace projection now copies `RUNNER_CALL_INPUT_ASSEMBLED` read-model signal into trace summaries: manifest ref / digest, message count, role sequence digest, input projection digest, projector metadata summary, and diagnostic summary.

## contract decisions

- Engine contract remains Host-neutral. It does not carry `runner_call_index`, manifest ref / digest, source refs, memory / compact refs, tool schema refs, or Host projector metadata.
- Host is the only writer of `runner_call_index`, manifest identity, source refs, manifest descriptor, and `RUNNER_CALL_INPUT_ASSEMBLED` canonical fact.
- `RunInputBuilder` records the manifest after constructing the same `messages` tuple returned in `AgentRunRequest`, so ordinary path `message_count` and role digest share the same source as the actual request.
- Engine ingest validates only against committed Host manifest signal. It does not write a manifest from Engine observations because Engine lacks Host source refs and projector metadata.
- Tool Trace is only a read model copy and is not a truth source for reconstructing runner input.

## tests run

- `source .venv/bin/activate && pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py`
  - Result: `153 passed in 1.10s`

## pyright result

- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright reported only an available version update notice.

## README sync

- `dayu/engine/README.md` documents the new Engine-owned `iteration_started` runner input observations and Host-neutral boundary.
- `dayu/host/README.md` documents Host-owned `RUNNER_CALL_INPUT_ASSEMBLED`, manifest payload descriptor semantics, ingest validation, and Tool Trace signal copy boundary.
- `tests/README.md` documents the added coverage for Engine role digest, bounded runner-call manifest, ingest validation, and Tool Trace projection.

## remaining risks

- This slice covers the ordinary `RunInputBuilder` runner-call path. Tool-loop continuation calls inside Engine expose Engine-owned role digest and message count, but Host does not yet have the source-ref-rich manifest writer for those continuation messages in this slice.
- Manifest bodies are bounded summaries and the large-input test verifies no full message content is inlined. This slice stores the manifest body through the existing SQLite payload descriptor path; artifact-store fallback wiring is not expanded because the relevant composition root is outside the allowed file set.

## stop condition check

- No blocker was hit for the ordinary runner-call path; `message_count` and role digest are sourced from the same `messages` tuple returned to Engine.
- Did not implement Slice 3 compactor internal manifest.
- Did not implement Slice 4 full Tool Trace reconstruction query or analyzer.
- Did not implement Slice 5 compact query readability.
- Did not implement Slice 6 prompt rewrite.
- Did not implement Slice 7 public smoke closeout.
- Did not commit, push, open PR, or enter re-review.

## ready for code review

yes
