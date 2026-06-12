# WU-OBS-SIGNALS-01 Aggregate Deepreview Fix - AgentCodex

## Scope

本次 fix 只处理 aggregate deepreview controller 接受的 DS finding 1：Tool Trace structured signal 常量与 bounded text 裁剪规则重复定义。

未处理 DS finding 2。跨 event read 当前是 bounded primary-key read，缺失时降级，不构成当前正确性或性能 blocker。

## Motivation

当前四类 signal 行为正确，但多个 Host 模块重复维护 signal schema version、status、failure kind 与 bounded text 上限。该重复不是单纯风格问题：这些值共同构成 producer / consumer contract，后续修改时若只改一侧，会形成 trace summary 写入与投影校验漂移。

## Changes

- 新增 `dayu/host/tool_trace_signals.py`：
  - 集中 `CONTEXT_PRESSURE_SCHEMA_VERSION`、`TOOL_TIMING_SCHEMA_VERSION`、`FAILURE_METADATA_SCHEMA_VERSION`、`PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION`。
  - 集中 tool timing status、partial tool-call status、failure kind closed union。
  - 集中 `TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS`。
  - 提供 `BoundedTraceSignalText` 与 `bound_trace_signal_text(...)`，作为 failure metadata bounded text 的生产端唯一裁剪 helper。
- 更新 `dayu/host/tool_runtime.py`：
  - 移除本地重复 signal 常量与本地 `_BoundedFailureText` / `_bounded_failure_text`。
  - 继续只生产 ToolRuntime 自己拥有的 `tool_failed`、`tool_cancelled`、`policy_blocked` failure metadata。
- 更新 `dayu/host/engine_ingest.py`：
  - 移除本地重复 provider protocol / partial tool-call / context pressure signal 常量。
  - 继续只消费 Engine bounded `PartialToolCallSummary`。
- 更新 `dayu/host/tool_trace.py`：
  - 移除本地重复 signal schema / status / failure kind / closed union / bounded text 上限常量。
  - projection 校验逻辑与异常类型保持不变。

## README

- 已检查 `dayu/host/README.md` 的 Agent 更新约束。当前 README 已说明 Tool Trace 投影 context pressure、tool timing、failure metadata 等只读结构化 signal。本次只收敛 Host 内部共享契约，不新增 stable developer-facing 接口，因此无需更新。
- `tests/README.md` 未触发更新：本次没有新增测试层级、运行方式或维护规则。

## Validation

```text
python -m py_compile dayu/host/tool_trace_signals.py dayu/host/tool_runtime.py dayu/host/tool_trace.py dayu/host/engine_ingest.py
OK

source .venv/bin/activate && python -m pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_phase6_toolruntime_integration.py
160 passed in 1.34s

source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations

git diff --check
OK
```

## Residual Risk

无新增 active residual risk。

WU-OBS-00 analyzer 未落地仍是本 work unit 的既有后续 owner，不由本 fix 处理。

