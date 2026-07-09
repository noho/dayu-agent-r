# WU-SEMANTIC-OWNERSHIP-01 P1-A Code Review Fix

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: code review fix
- Agent: AgentCodex
- Date: 2026-07-09
- Scope: only controller accepted findings `P1A-CR-F01` through `P1A-CR-F05`
- Commit / push: not performed by task constraint

## Owner Boundary

- 事实产生：ToolRuntime / wait-resume accept barrier 产生 `TOOL_RESULT_ACCEPTED` durable fact、accepted evidence envelope、raw outcome payload 与 `TOOL_CALL_REQUESTED` request atom。
- 事实校验：`dayu.host.accepted_result_projection.project_accepted_tool_result(...)` 是 accepted result query/status/source/result 的唯一 projection owner，负责 envelope、payload descriptor、request atom identity、unsafe arguments 与 status 归一校验。
- 事实持久化：EventLog、payload descriptor / SQLite payload 与 request atom 表仍是 durable truth；本次不写新 durable schema。
- 事实投影：Tool Trace、durable memory payload view、Conversation Memory、RunInputBuilder、CompactMaterial 与 compact pipeline 只消费 projection owner 输出或其直接派生字段。

## Finding Status

### P1A-CR-F01

- Status: fixed.
- Files:
  - `dayu/host/memory.py`
  - `tests/host/test_memory_projection.py`
  - `dayu/host/README.md`
  - `tests/README.md`
- Fix: Conversation Memory 缺少 `evidence_tool_name` / `evidence_result_text` projection 字段时不再读取 accepted envelope 或 raw outcome payload，不再从下游重建 accepted evidence；只输出单条 limited-signal 文本。正常路径仍使用 durable memory consumer 传入的 projection query/tool/result/source 字段。
- Tests: added focused coverage proving projection fields are used and payload-only fields do not leak; updated missing projection fields expectation to fail closed.

### P1A-CR-F02

- Status: fixed.
- Files:
  - `dayu/host/compact_pipeline.py`
- Fix: removed local `_UNAVAILABLE_TOOL_QUERY`; compact pipeline now imports `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` from `dayu.host.accepted_result_projection`.
- Tests: `tests/host/test_compact_pipeline.py` passes; the legal `RunInputMaterialBlock` accepted evidence contract requires readable query, so the None fallback remains a defensive path verified by code review and grep rather than an invalid fixture.

### P1A-CR-F03

- Status: fixed.
- Files:
  - `dayu/host/accepted_result_projection.py`
- Fix: replaced `_arguments_fallback_query(payload, reason)` with `_request_unavailable_query(reason)`. Request atom unavailable remains limited-signal and does not imply result payload can be a query source.
- Tests: missing request atom and identity mismatch tests assert limited-signal query.

### P1A-CR-F04

- Status: fixed.
- Files:
  - `tests/host/test_accepted_result_projection.py`
- Fix: added durable store write/read coverage for request atom identity mismatch, wait `resolution_kind` priority, internal source ref filtering, descriptor payload read plus missing descriptor diagnostic, unsafe argument keys, raw outcome `result.ok == false`, and structured result details extraction.
- Tests: `tests/host/test_accepted_result_projection.py` now has 11 passing tests.

### P1A-CR-F05

- Status: fixed.
- Files:
  - `tests/host/test_accepted_result_projection.py`
  - `tests/README.md`
- Fix: added cross-consumer equivalence test for one shared accepted result. The test writes real durable request/result/current-input facts, then verifies equivalent query/source/result/status semantics through Tool Trace, durable-memory-to-Conversation-Memory projection, RunInput evidence rendering, and CompactMaterial pre-dispatch material.
- Fixture boundary: assertions compare consumer outputs to the projection owner result; the fixture does not reimplement query/source/result/status projection rules.

## Propagation Audit

- Produce: accepted result facts and request atoms are still produced by Host accept barriers; no producer schema change.
- Validate: `project_accepted_tool_result(...)` validates accepted envelope, payload descriptor / digest availability, request atom identity, unsafe argument keys, status priority and source filtering.
- Persist: EventLog, payload descriptor / SQLite payload and request atom durable state remain unchanged; projection outputs are not persisted as new truth.
- Trace: Tool Trace hot row and cold JSONL consume projection query/status/result/source; request argument rendering remains display-only.
- Durable / Conversation Memory: durable memory converts accepted result rows into projection-cleaned fields; Conversation Memory consumes those fields and fails closed when they are absent.
- RunInputBuilder: accepted evidence material rendering consumes projection-cleaned material fields and does not rebuild source or query.
- CompactMaterial / compact pipeline: CompactMaterial builds accepted evidence blocks from projection owner; compact pipeline only renders those cleaned fields and uses projection owner unavailable-query text.
- LLM-facing output: unavailable query text has one owner; missing projection fields produce limited-signal text rather than downstream reconstructed evidence.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py`: 11 passed.
- `source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py`: 46 passed.
- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_host_activity_event_projection.py`: 221 passed.
- Additional focused validation: `source .venv/bin/activate && pytest tests/host/test_compact_pipeline.py`: 11 passed.
- Additional focused validation: `source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_pipeline.py -q`: 80 passed.
- `source .venv/bin/activate && rg -n "_readable_query_text_from_envelope|_tool_result_query_text|_tool_result_status|def _llm_facing_evidence_source_text|_is_internal_evidence_source_part|_readable_source_text_from_refs|source_note|tool_call_request_atoms" dayu/host`: remaining matches are allowed schema fields `source_note`, projection-owner `tool_call_request_atoms` usage, and payload primitive definition/export.
- `source .venv/bin/activate && pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.

## README Decision

- `dayu/host/README.md` updated because Host current implementation changed: Conversation Memory now consumes accepted-result projection fields and fails closed when they are absent.
- `tests/README.md` updated because Host tests now cover accepted-result projection completion signals and cross-consumer equivalence.
- No root README update: no user-visible install, CLI/Web/WeChat workflow, logging location, workspace location, or final-user troubleshooting behavior changed.

## Residual Risk

- Fixed in current slice: downstream Conversation Memory accepted evidence reconstruction from payload is removed.
- Fixed in current slice: compact pipeline unavailable-query text no longer has a second LLM-facing truth.
- Fixed in current slice: accepted result projection completion-signal tests and cross-consumer equivalence tests are present.
- Residual: `_contains_unsafe_argument_key` remains a bounded heuristic owned by projection owner; broader sensitive key taxonomy is still future hardening, not a consumer-side workaround.
- Residual: `source_note` remains compaction schema vocabulary, but accepted-result values come from projection-cleaned source text.
