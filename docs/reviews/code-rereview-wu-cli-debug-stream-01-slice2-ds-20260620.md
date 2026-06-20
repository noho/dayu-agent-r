# WU-CLI-DEBUG-STREAM-01 Slice 2 — AgentDS Re-Review

## Review Metadata

- **Reviewer**: AgentDS (Claude Code Agent)
- **Review type**: deepreview re-review — 验证 fix gate 后三项 accepted findings 关闭状态
- **Work unit**: WU-CLI-DEBUG-STREAM-01
- **Slice**: 2 — Host / Engine stream diagnostics level migration
- **Plan artifact**: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- **Fix artifact**: `docs/reviews/fix-wu-cli-debug-stream-01-slice2-20260620.md`
- **Adjudication artifact**: `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-adjudication-20260620.md`
- **Original reviews**: `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-mimo-20260620.md`; `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-ds-20260620.md`
- **Date**: 2026-06-20

## Re-Review Scope

本 re-review 严格按 adjudication 四项重点问题审查 fix 后状态，并验证四项附加要求。不覆盖 adjudication 已 reject/defer 的 findings。

## Validation Verification

独立重新运行验证：

| Claim | Expected | Actual | Status |
|-------|----------|--------|--------|
| pytest (affected 13 tests) | passed | `13 passed in 0.69s` | ✓ |
| pyright (full dayu/ tests/ utils/) | 0 errors/warnings/info | `0 errors, 0 warnings, 0 informations` | ✓ |
| git diff --check | clean | clean | ✓ |

## Focused Checks

### Check 1: 已接受 Findings 是否真正关闭

#### 1a — Slice 2 新增 type-ignore 是否已移除

**入口/函数**: `tests/engine/runners/openai/test_runner_diagnostics.py:_collect_stream_diagnostic_events`
**直接证据**: 行 534 使用 `cast(_RunnerWithDelayedSessionClient, runner)` 替代原 `type: ignore[attr-defined]`

验证路径：
- 新增测试 helper `_DelayedSessionClient`（行 213-238）封装 `_DelayedSession`，提供 `session()` 方法镜像生产 `HTTPClient.session()` 契约。
- `_RunnerWithDelayedSessionClient` Protocol（行 241-244）声明 `_http_client: _DelayedSessionClient` 类型槽位。
- `cast()` 调用将 `AsyncOpenAIRunner` 断言为 Protocol 类型，然后赋值 `runner_with_client._http_client = _DelayedSessionClient(session)`。
- 全量 grep 确认：文件中无新增 `type: ignore`（仅 4 处预存在行 267/347/437/478，均为 Slice 2 前已有）。
- 无新增 `Any`、`object`、脆弱 private seam——`cast()` + Protocol 是标准类型安全测试注入模式。

**结论**: ✓ 已关闭。type-ignore 已移除，替换方案类型安全，无新增反模式。

#### 1b — SSE done-token 是否仍 STREAM_DEBUG 且 provider_request_id 结构化

**入口/函数**: `dayu/engine/runners/openai/sse_parser.py:_dispatch_event_payload`
**直接证据**: 行 347-351

```python
_LOGGER.log(
    STREAM_DEBUG_LOG_LEVEL,
    "sse.done_token received provider_request_id=%s",
    self._provider_request_id,
)
```

验证路径：
- 日志级别使用 `STREAM_DEBUG_LOG_LEVEL`（= 9），未被降级为普通 DEBUG。
- 消息格式使用 `provider_request_id=%s` 结构化字段，与同模块 `sse.protocol_error code=%s` 风格一致。
- 未泄露 SSE chunk 正文、content delta、token 值。
- 测试行 323-325 断言了具体消息内容 `"sse.done_token received provider_request_id=req-stream-1"`，fake response 设置了 `"x-request-id": "req-stream-1"`。

**结论**: ✓ 已关闭。STREAM_DEBUG 级别保持，provider_request_id 已结构化。

#### 1c — `_engine_ingest_log_level` docstring 是否准确

**入口/函数**: `dayu/host/engine_ingest.py:_engine_ingest_log_level`
**直接证据**: 行 3260-3261

```python
:returns: Python logging 可消费的整数级别；delta 事件使用 Dayu
    自定义 STREAM_DEBUG 级别。
```

验证路径：
- 原 docstring 写 "stdlib logging level 数值"——现改为 "Python logging 可消费的整数级别"。
- 明确说明 delta 使用 Dayu 自定义 `STREAM_DEBUG` 级别，不再暗示返回值是 stdlib 预定义常量。
- 函数行为未变：delta 类型返回 `STREAM_DEBUG_LOG_LEVEL`（= 9），非 delta 返回 `VERBOSE_LOG_LEVEL`（= 15）。
- 两处调用点（行 701、759）均以 `_LOGGER.log(returned_level, msg, ...)` 消费——Python logging 的 `log()` 接受任意整数 level，行为正确。

**结论**: ✓ 已关闭。docstring 精确描述返回值语义。

### Check 2: --debug 与 --debug-stream 语义

逐项验证：

| 诊断类别 | 记录点 | 级别 | 普通 DEBUG 可见 | STREAM_DEBUG 可见 |
|---------|--------|------|:---:|:---:|
| Runner lifecycle | `runner.call.start` / `runner.call.done` / `runner.cancelled` | VERBOSE (15) | ✗ | ✗ |
| Runner attempt | `runner.attempt.start` | DEBUG (10) | ✓ | ✓ |
| HTTP request | `runner.http.post` | DEBUG (10) | ✓ | ✓ |
| HTTP response | `runner.http.response` | DEBUG (10) | ✓ | ✓ |
| Retry decision | `runner.attempt.retry` | WARNING (30) | ✓ | ✓ |
| Terminal error | `runner.attempt.terminal` | WARNING (30) | ✓ | ✓ |
| Stream heartbeat | `runner.stream_idle.heartbeat` | STREAM_DEBUG (9) | ✗ | ✓ |
| SSE done-token | `sse.done_token received` | STREAM_DEBUG (9) | ✗ | ✓ |
| Host delta ingest | `host.engine_ingest.accepted` / `committed` (delta) | STREAM_DEBUG (9) | ✗ | ✓ |
| Host non-delta ingest | `host.engine_ingest.accepted` / `committed` (non-delta) | VERBOSE (15) | ✗ | ✗ |

验证路径：
- Runner heartbeat：`_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, "runner.stream_idle.heartbeat ...")`（runner.py:897-898）。
- Runner attempt: `_LOGGER.debug("runner.attempt.start ...")`（runner.py:373）——未改动。
- HTTP: `_LOGGER.debug("runner.http.post ...")`（runner.py:581）、`_LOGGER.debug("runner.http.response ...")`（runner.py:607）——未改动。
- Warnings: retry（runner.py:514）、terminal（runner.py:479）——均为 `_LOGGER.warning(...)` 未改动。
- Host delta ingest: `_engine_ingest_log_level` 对 delta 返回 `STREAM_DEBUG_LOG_LEVEL`（engine_ingest.py:3264）。
- Host non-delta: 返回 `VERBOSE_LOG_LEVEL`（engine_ingest.py:3265）。
- 测试 `test_stream_diagnostics_require_stream_debug_log_level`（test_runner_diagnostics.py:288-328）端到端验证：普通 DEBUG 不捕获 heartbeat + done-token，STREAM_DEBUG 捕获两者。

**结论**: ✓ 完全符合 plan 语义。普通 DEBUG 不输出 stream heartbeat / SSE done / per-delta ingest；STREAM_DEBUG 可开启全部；HTTP / lifecycle DEBUG 与 warnings 不降级。

### Check 3: 新增测试的稳定性 / 类型安全 / 无内容泄露 / 无跨层反向依赖

#### 3a — 稳定性

- `test_stream_diagnostics_require_stream_debug_log_level`: `heartbeat=0.02s` + `delay_seconds=0.06s` + `timeout=0.5s`。0.06s delay 产生约 3 个 heartbeat 窗口，0.5s timeout 提供 ~4× 理论完成时间安全边际。heartbeat 是 `WaitTimedOut` 同步确定性触发，不依赖竞态。
- `test_engine_ingest_delta_stream_debug_records_are_gated`: 纯日志级别门控测试，无时序依赖。
- `test_engine_ingest_delta_events_use_stream_debug_log_level`: 纯函数返回值断言，无 IO。

#### 3b — 类型安全

- 新增代码完整类型注解：`_DelayedContent`, `_DelayedResponse`, `_DelayedRequestContext`, `_DelayedSession`, `_DelayedSessionClient`, `_RunnerWithDelayedSessionClient` Protocol。
- 无新增 `type: ignore`、`Any`、`object`。
- 注入使用 `cast(_RunnerWithDelayedSessionClient, runner)` + Protocol——编译期 + 运行期类型安全。

#### 3c — 内容泄露

- Host ingest 日志仅记录 id / worker_event_index / event_type / status / counts——不记录 delta 文本。
- Runner heartbeat 仅记录 elapsed / timeout——不记录 response body。
- SSE done-token 仅记录事件标识符 + provider_request_id——不记录 chunk 内容。
- 无新增 content delta / reasoning delta / tool arguments / final answer 进入日志。

#### 3d — 跨层反向依赖

- `dayu.runtime.log_levels` → `dayu.host.engine_ingest`、`dayu.engine.runners.openai.runner`、`dayu.engine.runners.openai.sse_parser`：层中立基础设施 → 上层消费——正确方向。
- 测试仅依赖对应层的生产模块 + 测试 fakes：`tests.host.test_logging` ← `dayu.host.engine_ingest`，`tests.engine.runners.openai.test_runner_diagnostics` ← `dayu.engine.runners.openai.runner`——无跨越。
- 无测试依赖 CLI、Service 或 UI 层代码。

**结论**: ✓ 新增测试稳定、类型安全、无内容泄露、无跨层反向依赖。

### Check 4: memory_repair.catch_up.budget_exhausted 噪音项排除

- 变更文件清单（`dayu/host/engine_ingest.py`, `dayu/engine/runners/openai/runner.py`, `dayu/engine/runners/openai/sse_parser.py`, `tests/host/test_logging.py`, `tests/engine/runners/openai/test_runner_diagnostics.py`）中无任何 `budget_exhausted`、`BUDGET_EXHAUSTED`、`MemoryProjectionRepairStopReason` 引用。
- 全量 diff 中 `dayu/host/memory_repair.py` 未被修改。
- 无回归证据。

**结论**: ✓ 无回归。本项不作为 finding。

## Additional Adversarial Checks

### A. STREAM_DEBUG 级别数值与 caplog gating 一致性

`STREAM_DEBUG_LOG_LEVEL = logging.DEBUG - 1 = 9`。`logging.DEBUG = 10`。当 caplog 设置为 `logging.DEBUG`（10）时，level 9 的 `STREAM_DEBUG` 记录不会被 handler 捕获——这正是 gating 机制。

验证：`caplog.at_level(logging.DEBUG, logger="dayu")` 将 dayu logger 级别设为 10。`_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, ...)`（level=9）不通过 logger 级别过滤。

当 caplog 设置为 `STREAM_DEBUG_LOG_LEVEL`（9）时，level 9+ 的记录全部通过，因此 STREAM_DEBUG 同时捕获 stream 诊断（9）和普通 DEBUG（10）——符合 plan 中 "--debug-stream 包含普通 DEBUG 诊断以及 stream-only 诊断" 的语义。

无矛盾。

### B. 生产代码变更最小性

三处生产代码变更均为 level 常量替换，不引入新抽象、间接层或条件分支：

| 文件 | 变更 | 新增行数 |
|------|------|---------|
| `runner.py` | import + `_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, ...)` | 3 行 |
| `sse_parser.py` | import + `_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, ...)` + provider_request_id | 6 行 |
| `engine_ingest.py` | import + return 值替换 + docstring 修正 | 5 行 |

总生产代码变更 14 行，无结构性改动。

### C. 预存在 type-ignore 注记

test_runner_diagnostics.py 中 4 处预存 `type: ignore[attr-defined]`（行 267/347/437/478）均为 Slice 2 前已有模式，用于非 stream 测试中直接注入 `runner._http_client._session`。这些不属于本 slice 修复范围，adjudication 也未要求移除。新的 stream 诊断测试已使用 `cast()` + Protocol 方案，证明团队有能力在后续迭代中统一迁移旧注入模式。

## Findings

### 未发现实质性问题

三项 accepted findings 均已关闭，四项重点问题验证通过。生产代码变更最小且语义正确，测试覆盖完整且类型安全。

## Open Questions

无。

## Residual Risk

1. **预存 `type: ignore[attr-defined]` 测试注入模式**（test_runner_diagnostics.py 行 267/347/437/478）：非本 slice 引入，adjudication 已裁决不纳入 Slice 2 fix。建议在后续独立 cleanup 中统一迁移至 `cast()` + Protocol 模式。
2. **CI 环境下 heartbeat 时序稳定性**：当前参数（heartbeat=0.02s, delay=0.06s, timeout=0.5s）保守，但极端 CPU 饥饿可能触发 idle timeout 而非 heartbeat。风险极低——0.5s timeout 对应 8× 理论完成时间。
3. **完整测试套件未运行**：Slice 2 验证限于受影响的 13 个测试。建议在合并前运行完整测试套件。

## Conclusion

**PASS**

三项 accepted findings 均已真正关闭：type-ignore 已移除且替换方案类型安全；SSE done-token 保持 STREAM_DEBUG 级别并包含结构化 provider_request_id；`_engine_ingest_log_level` docstring 精确。`--debug` / `--debug-stream` 语义完全符合 plan：普通 DEBUG 不输出 stream heartbeat / SSE done / per-delta ingest；STREAM_DEBUG 可开启全部；HTTP / lifecycle DEBUG 与 warnings 不降级。新增测试稳定、类型安全、无内容泄露、无跨层反向依赖。`memory_repair.catch_up.budget_exhausted` 无回归。无 must-fix finding。
