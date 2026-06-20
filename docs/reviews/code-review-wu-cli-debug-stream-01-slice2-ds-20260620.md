# WU-CLI-DEBUG-STREAM-01 Slice 2 — Deep Code Review

## Review Metadata

- **Review type**: deepreview (adversarial correctness / stability / maintainability)
- **Work unit**: WU-CLI-DEBUG-STREAM-01
- **Slice**: 2 — Host / Engine stream diagnostics level migration
- **Plan artifact**: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- **Implementation artifact**: `docs/reviews/implementation-wu-cli-debug-stream-01-slice2-20260620.md`
- **Accepted Slice 1 commit**: `f53762a5`
- **Reviewer**: DeepReview (Claude)
- **Date**: 2026-06-20

## Scope Assessment

Review covers the exact Slice 2 allowed files:

- `dayu/host/engine_ingest.py` — delta ingest log level migration
- `dayu/engine/runners/openai/runner.py` — stream idle heartbeat level migration
- `dayu/engine/runners/openai/sse_parser.py` — SSE done-token level migration
- `tests/host/test_logging.py` — renaming + gating test
- `tests/engine/runners/openai/test_runner_diagnostics.py` — stream diagnostics level gating test
- `docs/reviews/implementation-wu-cli-debug-stream-01-slice2-20260620.md` — implementation artifact (reviewed as claim source, not production code)

Controller-owned file `docs/host/issues-implementation-control.md` excluded per review instructions.

## Validation Verification

Implementation claims independently verified:

| Claim | Expected | Actual | Status |
|-------|----------|--------|--------|
| pytest (13 tests) | passed | `13 passed in 0.69s` | ✓ confirmed |
| pyright (full) | 0 errors/warnings/info | `errors=0, warnings=0, informations=0` | ✓ confirmed |
| git diff --check | clean | clean | ✓ confirmed |

## Findings

### Finding 1 — [info] SSE done-token log 消息字符串缺少结构化标识符

**Severity**: informational (可接受，不阻塞合入)
**File**: `dayu/engine/runners/openai/sse_parser.py:347`

**Evidence**:

```python
_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, "sse.done_token received")
```

**Analysis**: `sse.done_token received` 日志消息在当前 slice 中仅包含事件标识符，未附带 `provider_request_id`。虽然 `SSEParser` 实例持有 `self._provider_request_id`，但该日志没有把它写进消息，导致多 provider 并发场景下无法把 done_token 与具体请求关联。

对比同模块其他日志——例如 `sse.protocol_error` 系列全部带 `code=` 参数——done_token 日志的信息密度偏低。然而 `LOG_LEVEL_STREAM_DEBUG` 已在 plan 中定位为高频 stream 诊断，此日志的 provider_request_id 上下文可通过上游 `runner.http.response` 的 DEBUG 日志间接关联——后者记录了 `provider_request_id`。

**Recommendation**: 建议将消息改为 `"sse.done_token received provider_request_id=%s", self._provider_request_id`，保持与同模块其他诊断日志一致的结构化风格。优先级低——不阻塞 Slice 2 合入，可在后续 slice 或独立 cleanup 中处理。

**Adjudication**: accepted / rejected-with-reason / deferred-with-owner / needs-more-evidence

---

### Finding 2 — [info] `_engine_ingest_log_level` docstring 措辞可更精确

**Severity**: informational (可接受，不阻塞合入)
**File**: `dayu/host/engine_ingest.py:3256-3260`

**Evidence**:

```python
def _engine_ingest_log_level(engine_event_type: EngineEventType) -> int:
    """根据 Engine event 类型选择 ingest 诊断日志级别。

    :param engine_event_type: 待记录的 Engine event 类型。
    :returns: stdlib logging level 数值。
    """
```

**Analysis**: docstring 的 `:returns:` 写"stdlib logging level 数值"，但在 Slice 2 变更后，delta 路径返回的是 `STREAM_DEBUG_LOG_LEVEL`（值为 `logging.DEBUG - 1 = 9`），这是 Dayu 自定义级别常量而非 stdlib 预定义常量（`logging.DEBUG=10`, `logging.INFO=20`, ...）。Python logging 框架支持任意整数级别，`STREAM_DEBUG_LOG_LEVEL=9` 确实可作为 `logging.log()` 的有效 level 参数；但 docstring 中的"stdlib"措辞暗示该值是 Python 标准库定义的级别常量之一，与事实有微妙偏差。

非阻塞：此函数是模块级私有函数，仅被同模块的 ingest 日志调用点使用，docstring 的"stdlib"措辞不会误导 API 消费者。但按 AGENTS.md 的"完整中文 docstring"要求，精确性是期望的。

**Recommendation**: 将 `:returns: stdlib logging level 数值。` 改为 `:returns: 日志级别整数值（可能为 Dayu 自定义 STREAM_DEBUG 或 VERBOSE）。`

**Adjudication**: accepted / rejected-with-reason / deferred-with-owner / needs-more-evidence

---

### Finding 3 — [info] gating 测试只验证 CONTENT_DELTA 级别，未覆盖 REASONING_DELTA / TOOL_CALL_DELTA 的日志发射路径

**Severity**: informational (可接受，不阻塞合入)
**File**: `tests/host/test_logging.py:206-234`

**Evidence**:

```python
def test_engine_ingest_delta_stream_debug_records_are_gated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ...
    message = "host.engine_ingest.accepted engine_event_type=content_delta"

    with caplog.at_level(logging.DEBUG, logger="dayu.host.engine_ingest"):
        logger.log(
            _engine_ingest_log_level(EngineEventType.CONTENT_DELTA),
            message,
        )
    assert message not in caplog.text
    ...
```

**Analysis**: 该测试只使用 `EngineEventType.CONTENT_DELTA` 验证 gating 行为。`_engine_ingest_log_level` 对三种 delta 类型（`CONTENT_DELTA`, `REASONING_DELTA`, `TOOL_CALL_DELTA`）都返回 `STREAM_DEBUG_LOG_LEVEL`，因为它们都通过 `_DELTA_ENGINE_EVENT_TYPES` frozenset 判断。从实现机制看，测试一个 delta 类型即可覆盖该 frozenset 成员检查逻辑——这是单路径决策，不是多分支分发。

然而从"反例思维"看：如果未来有人误从 `_DELTA_ENGINE_EVENT_TYPES` 中移除某个类型，当前两个测试（级别断言 + gating）都只用 `CONTENT_DELTA` 做 gating 验证，不会捕获该移除。但 `test_engine_ingest_delta_events_use_stream_debug_log_level` 已显式断言三种 delta 的返回值为 `STREAM_DEBUG_LOG_LEVEL`，形成互补覆盖。

**Recommendation**: 不需要改。现有两个测试的组合（级别断言覆盖三种 delta + gating 覆盖代表性 delta）已构成充分覆盖。

**Adjudication**: accepted（无需修改）

---

### Finding 4 — [info] `test_stream_diagnostics_require_stream_debug_log_level` 依赖定时 heartbeat 机制

**Severity**: informational (可接受，不阻塞合入)
**File**: `tests/engine/runners/openai/test_runner_diagnostics.py:252-292`

**Evidence**:

```python
stream_idle_heartbeat_seconds=0.02,
...
delay_seconds=0.06,
```

**Analysis**: 测试通过 `readany` 的 0.06s 延迟 + 0.02s heartbeat 间隔来确保触发心跳。在 0.06s 的 readany 等待期间，heartbeat 每 0.02s 触发一次（共 2 次），这是确定性行为——heartbeat 的触发不依赖竞态，因为 `_runtime_wait_for_or_cancel` 的 timeout 逻辑是同步确定的：readany 需要 0.06s，heartbeat 每 0.02s check-in，心跳一定在数据到达前触发。

测试还设置了 `stream_idle_timeout_seconds=0.5`，即使在极端慢的 CI 环境下，0.5s 也远大于 0.06s × 2 chunks = 0.12s 的理论完成时间。

风险很低，不构成 fragile 测试。但如果未来 CI 环境极端异常（如 CPU 饥饿导致 0.06s sleep 实际耗时 >0.5s），可能触发 idle timeout 而非 heartbeat。这属于极端边缘情况，当前参数选择已充分保守。

**Recommendation**: 不需要改。当前参数选择（heartbeat=0.02s, delay=0.06s, timeout=0.5s）给出的安全边际足够。

**Adjudication**: accepted（无需修改）

---

### Finding 5 — [info] 测试新增 `_Delayed*` 类与 `_fakes.py` 存在结构平行但无法复用

**Severity**: informational (可接受，不阻塞合入)
**File**: `tests/engine/runners/openai/test_runner_diagnostics.py:78-210`

**Evidence**: 新增了 `_DelayedContent`, `_DelayedResponse`, `_DelayedRequestContext`, `_DelayedSession` 四个类，它们与 `_fakes.py` 中的 `FakeContent`, `FakeResponse`, `_FakeRequestContext`, `FakeSession` 在结构上高度平行，区别仅在于注入可控延迟。

**Analysis**: 这不构成代码重复——延迟注入是 heartbeat 测试的必要条件，且注入点（`readany` 中的 `asyncio.sleep`）是 `FakeContent` 的方法覆盖，无法通过参数化实现而不改变共享 fake 的接口契约。将延迟逻辑放入共享 fake 会影响所有使用 `FakeContent` 的其他测试。

`_DelayedContent` 继承 `FakeContent` 并覆盖 `readany`，`_DelayedResponse` 继承 `FakeResponse` 并覆盖 `content` 属性——这是标准的多态扩展模式，不是重复代码。

**Recommendation**: 不需要改。

**Adjudication**: accepted（无需修改）

---

## Cross-Cutting Checks

### Architecture boundary verification

- ✓ 无 `dayu.runtime` 到 `dayu.host` / `dayu.engine` 的反向依赖。`dayu.runtime.log_levels` 仅被 `dayu.host.engine_ingest`、`dayu.engine.runners.openai.runner`、`dayu.engine.runners.openai.sse_parser` 单向导入——这是层中立基础能力被上层消费的正确方向。
- ✓ 无 Slice 3/4 边界穿越：未触及 `dayu/cli/`、`tests/cli/`、prompt/interactive 测试。
- ✓ 无 README 修改——Slice 2 仅迁移动态诊断日志级别，用户可见行为由 Slice 1（CLI flag）和 Slice 4（README）负责。
- ✓ 无 runtime/CLI/README 改动。

### Weak typing / Any / object / type-ignore regression

- ✓ 新增代码全部有完整类型注解。
- ✓ `_DelayedContent.__init__` 参数 `chunks: list[bytes]` 与实际传入类型一致。
- ✓ `_DelayedResponse.__init__` 参数 `delay_seconds: float` 类型正确。
- ✓ `_DelayedSession.post` 返回类型 `_DelayedRequestContext` 明确。
- ✓ `_collect_stream_diagnostic_events` 返回类型 `list[RunnerEvent]` 明确。
- ✓ 唯一的 `type: ignore[attr-defined]` 在 `runner._http_client._session = session` 行——这是测试注入模式，预存在于本文件其他测试中，非 Slice 2 新增。
- ✗ 无新增 `Any`、`object`、无类型参数。

### Chinese docstring compliance

- ✓ `test_engine_ingest_delta_events_use_stream_debug_log_level` — 中文 docstring。
- ✓ `test_engine_ingest_delta_stream_debug_records_are_gated` — 中文 docstring。
- ✓ `test_stream_diagnostics_require_stream_debug_log_level` — 中文 docstring。
- ✓ `_collect_stream_diagnostic_events` — 中文 docstring。
- ✓ `_DelayedContent`, `_DelayedResponse`, `_DelayedRequestContext`, `_DelayedSession` — 各有中文 docstring。
- ✓ `_engine_ingest_log_level` 已有中文 docstring（仅 Finding 2 的措辞精确性建议）。

### Content leakage prevention

- ✓ Host ingest accepted / committed 日志仅记录 ids、worker_event_index、event_type、status、counts——不记录 delta 文本。
- ✓ Stream idle heartbeat 仅记录 elapsed / timeout——不记录 response body 或 chunk 内容。
- ✓ SSE done_token 仅记录事件标识符——不记录 token 值或 response body。
- ✓ 无新增 content delta / reasoning delta / final answer / tool arguments 进入日志。

### Warnings / errors remain at correct level

- ✓ `runner.attempt.terminal` — WARNING（不变）。
- ✓ `runner.attempt.exhausted` — WARNING（不变）。
- ✓ `runner.attempt.retry` — WARNING（不变）。
- ✓ `runner.stream_idle.timeout` — WARNING（不变）。
- ✓ `sse.protocol_error` — WARNING（不变）。
- ✓ `runner.pending_readany_cancel_failed` — WARNING（不变）。
- ✓ `engine_ingest.compact.rejected_diagnostic_write_failed` — WARNING（不变）。
- ✓ `runner.cancelled` — VERBOSE（不变）。
- ✓ `runner.call.start` / `runner.call.done` — VERBOSE（不变）。

### Plan alignment

逐项对照 Slice 2 plan 的 "Exact changes" 与 "Expected assertions"：

| Plan requirement | Implementation | Status |
|-----------------|----------------|--------|
| Import `STREAM_DEBUG_LOG_LEVEL` where needed | engine_ingest.py:203, runner.py:89, sse_parser.py:65 | ✓ |
| Change `_engine_ingest_log_level()` delta → `STREAM_DEBUG_LOG_LEVEL` | engine_ingest.py:3264 | ✓ |
| Non-delta remains `VERBOSE_LOG_LEVEL` | engine_ingest.py:3265 | ✓ |
| Change `runner.stream_idle.heartbeat` to `STREAM_DEBUG_LOG_LEVEL` | runner.py:897-898 | ✓ |
| Change `sse.done_token received` to `STREAM_DEBUG_LOG_LEVEL` | sse_parser.py:347 | ✓ |
| Rename test to stream-debug-specific name | test_logging.py:180 | ✓ |
| Add test: ordinary DEBUG does not capture stream-debug | test_logging.py:206-234 (gating) | ✓ |
| Add test: stream-debug level does capture | test_logging.py:226-234 (gating) | ✓ |
| Protocol warnings remain WARNING | Unchanged | ✓ |
| Runner lifecycle DEBUG tests unchanged | test_runner_diagnostics.py:212-249 | ✓ |
| `_engine_ingest_log_level(CONTENT_DELTA) == STREAM_DEBUG_LOG_LEVEL` | test_logging.py:188-189 | ✓ |
| `_engine_ingest_log_level(REASONING_DELTA) == STREAM_DEBUG_LOG_LEVEL` | test_logging.py:191-193 | ✓ |
| `_engine_ingest_log_level(TOOL_CALL_DELTA) == STREAM_DEBUG_LOG_LEVEL` | test_logging.py:195-197 | ✓ |
| `_engine_ingest_log_level(ITERATION_STARTED) == VERBOSE_LOG_LEVEL` | test_logging.py:199-201 | ✓ |
| Runner attempt / HTTP diagnostics still appear under DEBUG | test_runner_diagnostics.py:266-268 | ✓ |
| Stream heartbeat / SSE done-token only appear at STREAM_DEBUG | test_runner_diagnostics.py:269-289 | ✓ |

无遗漏。

## Residual Risks

1. **TOOL_CALL_DELTA 的 SSE 流诊断未被集成测试端到端覆盖。** 现有 stream diagnostics gating 测试使用 `content` delta 的 SSE chunk，未验证 tool_call delta 在 SSE 流中同样触发正确的 `sse.done_token received` 日志。但这属于"不同 SSE chunk 类型共享同一 done_token 逻辑"的合理推断——done_token 处理在 `_dispatch_event_payload` 中与 chunk 内容类型无关。风险低。

2. **Heartbeat 测试的 CI 稳定性。** 已在 Finding 4 中分析——参数选择保守，风险可忽略。

3. **`_engine_ingest_log_level` 作为私有函数被测试直接导入。** 这是预存在模式，非 Slice 2 引入。如果该函数签名或返回语义未来变化，测试需要同步更新。但这正是测试该函数的目的。

## Summary

Slice 2 变更在四个维度上均通过审查：

- **Correctness**: 三处生产代码日志级别迁移逻辑正确，无遗漏、无过度迁移。普通 DEBUG 不再发出 stream 诊断，STREAM_DEBUG 发出所有 stream 诊断 + 普通 DEBUG。无内容泄漏。
- **Stability**: 测试验证确定性 gating 行为。Heartbeat 测试时间参数保守。无竞态条件。
- **Maintainability**: 变更最小化——仅修改日志级别常量和对应 import，不引入新抽象或间接层。测试覆盖补全了 delta 诊断门控。
- **Architecture**: 严格遵循分层依赖方向（runtime → host/engine），无 Slice 边界穿越，无反向依赖。

无 must-fix 或 should-fix 级别问题。两个 informational findings（Finding 1: done_token 日志缺少 provider_request_id；Finding 2: docstring 措辞）均为低优先级改进建议，不阻塞合入。

**Verdict**: Slice 2 可通过 code review gate。
