# Code Re-Review

## Scope

- Mode: current changes
- Branch: wu-cli-debug-stream-01
- Base: main
- Output file: `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice2-mimo-20260620.md`
- Included scope: WU-CLI-DEBUG-STREAM-01 Slice 2 fix 后状态；Host/Engine stream diagnostic level migration
- Excluded scope: Slice 1（已通过 re-review）；prompt/interactive compatibility guard；README slice
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## 已接受 Findings 关闭验证

### 1. type: ignore 移除且未以 Any/object/脆弱 private seam 替代

**状态：已关闭 ✅**

- `tests/engine/runners/openai/test_runner_diagnostics.py` 第 534-535 行：使用 `cast(_RunnerWithDelayedSessionClient, runner)` 替代原 `type: ignore[attr-defined]`
- 新增 `_RunnerWithDelayedSessionClient(Protocol)`（第 241-244 行）提供类型安全的 `_http_client` 声明
- diff 确认 Slice 2 新增的 `type: ignore` 已移除，未引入新的 `Any`、`object` 或类型绕过
- 现有 Slice 1 的 `type: ignore`（第 267、347、437、478 行）不在本 slice 修改范围

### 2. SSE done-token 仍 STREAM_DEBUG 且 provider_request_id 结构化

**状态：已关闭 ✅**

- `dayu/engine/runners/openai/sse_parser.py` 第 347-351 行：
  ```python
  _LOGGER.log(
      STREAM_DEBUG_LOG_LEVEL,
      "sse.done_token received provider_request_id=%s",
      self._provider_request_id,
  )
  ```
- 仍使用 `STREAM_DEBUG_LOG_LEVEL`，未泄露 SSE chunk 正文或 content delta
- `provider_request_id` 已结构化添加，与同模块其他诊断记录风格一致

### 3. _engine_ingest_log_level docstring 准确

**状态：已关闭 ✅**

- `dayu/host/engine_ingest.py` 第 3260-3261 行：
  ```
  :returns: Python logging 可消费的整数级别；delta 事件使用 Dayu
      自定义 STREAM_DEBUG 级别。
  ```
- docstring 准确说明返回值语义：stdlib logging 可消费的整数，delta 使用自定义 STREAM_DEBUG

## --debug 与 --debug-stream 语义验证

### ordinary DEBUG 不输出 stream heartbeat/SSE done/per-delta ingest

**状态：符合 plan ✅**

- `runner.py` 第 897-903 行：stream idle heartbeat 使用 `STREAM_DEBUG_LOG_LEVEL`
- `sse_parser.py` 第 347-351 行：SSE done-token 使用 `STREAM_DEBUG_LOG_LEVEL`
- `engine_ingest.py` 第 3264-3265 行：delta 事件（CONTENT_DELTA/REASONING_DELTA/TOOL_CALL_DELTA）使用 `STREAM_DEBUG_LOG_LEVEL`
- 测试验证：
  - `test_stream_diagnostics_require_stream_debug_log_level`（第 288-328 行）断言 ordinary DEBUG 不捕获 heartbeat/done-token
  - `test_engine_ingest_delta_stream_debug_records_are_gated`（第 206-237 行）断言 ordinary DEBUG 不捕获 delta ingest

### STREAM_DEBUG 可开启

**状态：符合 plan ✅**

- 测试验证 `STREAM_DEBUG_LOG_LEVEL` 可捕获 stream heartbeat、SSE done-token、delta ingest
- `test_stream_diagnostics_require_stream_debug_log_level` 第 311-326 行断言 STREAM_DEBUG 下捕获 `"runner.stream_idle.heartbeat"` 和 `"sse.done_token received provider_request_id=req-stream-1"`
- `test_engine_ingest_delta_stream_debug_records_are_gated` 第 229-237 行断言 STREAM_DEBUG 下捕获 delta message

### HTTP/lifecycle DEBUG 与 warnings 不降级

**状态：符合 plan ✅**

- runner.py 中 `runner.attempt.start`、`runner.http.post`、`runner.http.response` 保持 ordinary `DEBUG`（未在 Slice 2 修改）
- 测试验证：`test_stream_diagnostics_require_stream_debug_log_level` 第 301-303 行断言 ordinary DEBUG 捕获这些诊断

## 新增测试质量验证

### 稳定性

- `_DelayedContent`/`_DelayedResponse`/`_DelayedSession` 使用可控 `asyncio.sleep` 触发 heartbeat
- 参数设置：`delay_seconds=0.06`、`heartbeat=0.02`、`timeout=0.5`，提供足够余量
- 不依赖 wall-clock 绝对值，只验证 bounded idle wait 行为

### 类型安全

- 所有新增类提供完整类型注解
- `_RunnerWithDelayedSessionClient(Protocol)` 替代 `type: ignore`
- `cast()` 用法类型安全

### 无内容泄露

- 测试不记录 SSE chunk 正文、content delta、reasoning delta 或 tool arguments
- 只验证 `provider_request_id` 结构化字段

### 无跨层反向依赖

- 测试只从 `dayu.runtime.log_levels` 导入层中立常量
- fake 对象在测试模块内定义，不穿透 production 代码边界

## memory_repair.catch_up.budget_exhausted 验证

按 plan gate 约束，本 finding 不作为 Slice 2 review 项。验证 diff 中未引入该 stop reason 回归：`dayu/host/memory_repair.py` 未在 Slice 2 修改范围内。

## Open Questions

无

## Residual Risk

- 未运行完整测试套件；本 re-review 按要求验证了受影响 Host/Engine logging 测试和全量 pyright
- 现有 Slice 1 测试中的 `type: ignore` 不在本 slice 修改范围，属于 accepted technical debt

## Conclusion

**PASS**

Slice 2 fix 已正确关闭所有 accepted findings：

1. type: ignore 已移除，使用类型安全的 Protocol + cast 替代
2. SSE done-token 保持 STREAM_DEBUG 且 provider_request_id 结构化
3. _engine_ingest_log_level docstring 准确

--debug 与 --debug-stream 语义符合 plan，新增测试稳定、类型安全、无内容泄露、无跨层反向依赖。
