# WU-DUR / WU-OBS / WU-CM Closeout Slice 1 Re-Review Controller Adjudication

## Verdict

pass. Slice 1 durable `TOOL_CALL_REQUESTED` accepted request atoms are accepted for this phase.

## Reviewed Inputs

- `docs/reviews/wu-dur-obs-cm-closeout-slice1-implementation-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice1-code-review-controller-adjudication.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice1-fix-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice1-rereview-mimo.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice1-rereview-ds.md`
- Current workspace diff for Slice 1 production code, tests, and README updates.

## Accepted Fix Verification

| Accepted finding | Controller decision |
|---|---|
| Storage kind constants duplicated between write and read modules | Fixed. `dayu.host.durable.schema` is the single source for descriptor kind and storage kind constants; `tool_runtime` and `payload_resolution` import the same constants. |
| Inline arguments / semantic query reader ignores incompatible payload refs | Fixed. `payload_resolution.tool_call_request_atoms()` now rejects `inline_json` with `arguments_payload_ref` and `inline_text` with `semantic_query_payload_ref`; focused malformed payload tests cover both cases. |

## Re-Review Findings

No blocking findings were accepted.

MiMo reported one low maintenance observation about duplicated `_payload_size_bytes`; this was already outside the accepted fix set and is not a correctness blocker for Slice 1.

DS reported one low advisory finding: descriptor-path malformed payloads that also carry inline fields are ignored rather than explicitly rejected. Controller does not accept this for immediate fix because the production writer does not emit that shape, descriptor body and digest validation remain authoritative, and the current accepted fix scope was specifically the inline storage kind carrying forbidden payload refs. This may be revisited in a future durable hardening cleanup, but it does not block Slice 1 acceptance.

The previously deferred `ToolAcceptCall.accepted_arguments` requiredness question remains deferred. Re-review did not add new blocking evidence.

## Validation Status

Sub-agent validation:

- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_durable_schema.py`: 119 passed.
- `pyright`: 0 errors.

Controller validation:

- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_durable_schema.py`: 119 passed.
- `pyright`: 0 errors.

## Residual Risk

- Tool Trace hot projection refs/digests remain later WU-OBS-P00 scope.
- Compact evidence readable query consumption remains WU-CM-01-F02 scope.
- Public conversation memory smoke remains WU-CM-01-F01 final validation scope.

## Decision

Slice 1 is ready for accepted commit after controller validation.
