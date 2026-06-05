# WU-DUR / WU-OBS / WU-CM Closeout Slice 1 Fix

## status

- status: complete
- agent: AgentCodex
- scope: 仅执行 Slice 1 fix gate；未进入 re-review、Slice 2-7、commit、push、PR 或其它 gate

## changed files

- `dayu/host/durable/schema.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/payload_resolution.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `docs/reviews/wu-dur-obs-cm-closeout-slice1-fix-codex.md`

## fixed findings mapping

| accepted finding | fix |
|---|---|
| Storage kind constants are duplicated between write and read modules | 将 `TOOL_CALL_REQUESTED` arguments / semantic query storage kind 常量集中到 `dayu/host/durable/schema.py`，`tool_runtime` 写路径与 `payload_resolution` 读路径统一 import 同一组常量，移除两个模块中的重复私有定义。 |
| Inline arguments / semantic query reader ignores incompatible payload refs | `payload_resolution.tool_call_request_atoms()` 的 reader 在 `inline_json` arguments 携带 `arguments_payload_ref`、`inline_text` semantic query 携带 `semantic_query_payload_ref` 时 fail-closed 抛 `HostDurableError`。新增两个聚焦测试覆盖畸形 durable payload。 |

## tests run

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_durable_schema.py`
  - result: 119 passed

## pyright result

- `source .venv/bin/activate && pyright`
  - result: 0 errors, 0 warnings, 0 informations
  - note: pyright reported an available version update notice only.

## remaining risks

- `ToolAcceptCall.accepted_arguments` 仍按 controller adjudication 延后处理；本 gate 未改其必填性。
- 本 gate 只覆盖 accepted findings；未处理 Tool Trace hot projection atom refs/digests、Compact evidence query consumption 等后续 slice 风险。

## readiness for re-review

- ready for Slice 1 re-review.
