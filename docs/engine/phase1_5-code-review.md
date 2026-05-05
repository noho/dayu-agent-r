# Phase 1.5 Log / Runner Diagnostics Code Review

## 1. Review 结论：通过

Phase 1.5 本轮修复后可以作为 Log / Runner diagnostics / SSE idle 的实施结果进入验收。

原 code review 中的 7 项阻塞 / 重要问题已逐项处理：SSE idle pending `readany()` 生命周期已收口；Runner / parser / close / idle timeout 诊断日志已补齐主要边界；`RunnerSpec` 允许 `heartbeat == timeout`；`dayu.runtime.log` 迁移了 `VERBOSE=15` 与第三方库默认静默；`cancellation` 私有 helper 去掉了 `asyncio.Task[object]`。指定测试与 pyright 均通过。

仍有少量非阻塞建议，主要是文档注释漂移和部分日志测试可继续锁得更细。

## 2. 阅读范围

已阅读 NEW：

- `AGENTS.md`
- `CLAUDE.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase1_5-plan.md`
- `docs/engine/phase1_5-plan-review.md`
- `docs/engine/phase1-runner-old-new-round2-review.md`
- `docs/code_review.md`
- `dayu/runtime/`
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/runners/openai/`
- `tests/runtime/`
- `tests/engine/contracts/test_runner_spec.py`
- `tests/engine/runners/openai/`
- `tests/engine/test_logger_import_boundary.py`

已复核 OLD 强参考源：

- `/Users/leo/workspace/dayu-agent/dayu/log.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/sse_parser.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_sse_parser.py`

## 3. `dayu.runtime` 边界结论

通过。

`dayu.runtime` 保持层中立，没有 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。`dayu.runtime.log` 是日志装配入口，不是 OLD `Log.debug/info/warn/error` 单例兼容 wrapper；Engine 也没有 import `dayu.runtime.log`。

`dayu.runtime.log.configure()` 默认只配置 `dayu` namespace logger，不污染 root logger；自有 handler 有 marker，重复 configure 会先清理旧 marker handler，避免重复输出。`LogLevel.VERBOSE = 15` 已迁移，模块导入时注册 `logging.addLevelName(15, "VERBOSE")`，`set_level_from_flags(verbose=True)` 映射到 `VERBOSE`。

第三方库静默已补齐为默认策略：`aiohttp`、`asyncio`、`urllib3`、`httpx`、`httpcore` 等 logger 默认设为 `WARNING`，并提供 `suppress_default_third_party=False` 与 `third_party_overrides` 供上层显式覆盖。

## 4. Logger diagnostics 结论

通过。

Runner 侧使用 `logging.getLogger(__name__)`，没有直接依赖 `dayu.runtime.log`。本轮已补齐主要诊断边界：

- `runner.attempt.start` / `runner.attempt.retry` / `runner.attempt.terminal` / `runner.attempt.exhausted`
- `runner.http.post`
- `runner.http.response`
- `runner.stream_idle.heartbeat`
- `runner.stream_idle.timeout`
- `runner.cancelled`
- `http_client.close`
- `sse.protocol_error` / `sse.done_token`
- `non_stream.protocol_error`

日志调用使用参数化格式，没有发现 f-string 过早求值。当前日志没有输出完整 messages、payload、headers、tool arguments、provider response body preview 或完整响应体。

## 5. cancellation runtime 结论

通过。

`await_or_cancel()` 拥有自己创建 / 包装的 target task；token 命中时会 cancel 并 await target task 收口。`wait_for_or_cancel()` 不取消调用方传入的 pending task，符合 Runner SSE idle 复用 pending `readany()` 的设计。两个 helper 都会清理自身 watcher / poller，`asyncio.CancelledError` 透传。

封闭联合 `WaitCompleted[T] | WaitCancelled | WaitTimedOut` 保持成立；没有新增公共取消异常。Runner 仍把 cancellation 翻译为私有 `_RunnerInterrupted`，没有进入公共契约。

关于“wait 3 秒，Host 刚开始就 cancel 是否要等满 3 秒”：当前实现不会等满 timeout。`wait_for_or_cancel()` 用 `asyncio.wait(..., return_when=FIRST_COMPLETED, timeout=timeout_seconds)` race pending task 与 cancellation watcher；Host cancel 后，最多受 token 轮询间隔影响，默认约 0.05 秒。

## 6. RunnerSpec idle 字段结论

通过。

`stream_idle_timeout_seconds` / `stream_idle_heartbeat_seconds` 属于 Runner 运行规格，而不是诊断 log 字段，也没有进入 RunnerEvent / EngineEvent。语义符合计划：

- `None + None` 禁用 idle 检测。
- timeout-only 合法。
- heartbeat-only 非法。
- 0 / 负数构造期拒绝。
- `heartbeat > timeout` 构造期拒绝。
- `heartbeat == timeout` 已放宽为合法。

需要修正文档注释漂移：`RunnerSpec.__post_init__()` 的中文 docstring 仍写“心跳必须严格小于 timeout”，与实现和参数说明不一致。

## 7. SSE idle heartbeat / timeout 结论

通过。

SSE idle 放在 Runner byte iterator 层，`SSEParser` 仍是纯 parser。`_iter_response_bytes_with_idle()` 跨循环复用 pending `readany()` task，正常 chunk 到达后退出内层 idle wait 并进入下一轮，idle 计时随新 pending 重置。

本轮关键修复是 pending task 生命周期：`pending = asyncio.ensure_future(response.content.readany())` 后已用 `try/finally` 包住整个等待路径，外层 `Task.cancel()`、generator `aclose()`、idle hard timeout、网络异常、正常完成都会进入 `_cancel_pending_readany()`。我用本地复现检查过旧 B1 场景，外层 cancel 后内部 read task 已取消，未发现 dangling task。

语义边界符合计划：

- heartbeat 只写 debug log，不进入事件流。
- hard timeout 进入 `RunnerHTTPErrorCode.TIMEOUT` / error done 收口。
- cancellation during idle wait 优先于 timeout，生成器自然终止，不补 `RunnerDoneData`。
- disabled path 保持原行为，仍走 `_iter_response_bytes_no_idle()`。
- idle timeout 通过 `_AttemptFailedRetriable(TIMEOUT)` 接入原 retry 策略。

据此，Phase 1.5 对 GitHub issue #6 的代码层要求已满足。

## 8. 架构与契约边界结论

通过。

没有发现新增 `RunnerEventType` / `EngineEventType`，也没有把 log / idle / heartbeat 字段塞进事件 data 或 metadata。没有新增公共取消异常或 idle timeout 异常。没有恢复 OLD `Log` 单例兼容 wrapper / facade / re-export，也没有引入 `set_tools`、`extra_payloads` 或旧 Runner 工具执行边界。

Runner 依赖仍局限在 Engine / runtime cancellation / aiohttp 等必要边界内，没有引入 Host / Service / UI / fins / trace / ToolExecutor / ToolRegistry。

## 9. 日志安全性结论

通过。

当前 diagnostics 字段以 endpoint、model、provider、attempt、status、content_type、error_code、elapsed / timeout、body byte length 等诊断事实为主。没有发现日志输出完整请求 payload、messages、headers、tool arguments、provider response body preview、完整 exception text 或财报内容。

HTTP 非 200 响应仍会把 body preview 放入 `RunnerHTTPErrorData.message`，这是 Phase 1 既有事件契约行为，不是本轮新增日志泄漏；本轮日志没有打印该 preview。

## 10. 测试与 pyright 结果

已按要求运行：

```bash
source .venv/bin/activate && pytest tests/runtime tests/contracts tests/engine -q
```

结果：`257 passed in 1.05s`。

已按要求运行：

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 同时输出 `File or directory "/Users/leo/workspace/dayu-agent-r/utils" does not exist.`，但退出码为 0。

覆盖结论：

- runtime import boundary、logger configure 幂等、root 不污染、VERBOSE、第三方 suppression 有测试覆盖。
- Engine 不 import `dayu.runtime.log` 有边界测试。
- cancellation helper 的 completed / timeout / cancelled / outer cancel cleanup 有测试覆盖。
- idle disabled / heartbeat / timeout / timeout-only / cancel wins / aclose / outer cancel 有测试覆盖。
- diagnostics logging、close logging、protocol warning、RunnerEvent 流不混日志有测试覆盖。

## 11. README 策略检查

通过。

本轮遵循用户明确策略：README 等全部迁移完毕后统一生成。当前没有新建或修改除 `tests/README.md` 外的 README；本次 diff 中也未见 README 变更。考虑到 Phase 1.5 仍处于迁移计划内，这个策略可接受。

## 12. 阻塞问题

无。

原 B1 / B2 / B3 已修复：

- B1：SSE idle pending `readany()` 外层 cancel / aclose 泄漏已通过 `try/finally` 收口。
- B2：Runner / parser / close / idle timeout 诊断日志已补齐主要边界。
- B3：新增 B3 补充测试并通过指定测试集。

## 13. 重要问题

无。

当前剩余问题不阻塞 Phase 1.5 验收。

## 14. 建议问题

### S1-低-`RunnerSpec.__post_init__` docstring 仍写“心跳必须严格小于 timeout”

- **文件路径**：`dayu/engine/contracts/runner_spec.py`
- **具体符号**：`RunnerSpec.__post_init__`
- **触发场景**：阅读构造期校验文档，或按文档理解 `heartbeat == timeout`。
- **直接证据**：参数说明与实现允许 `heartbeat <= timeout`，但 `__post_init__` docstring 仍写“心跳必须严格小于 timeout”。
- **影响**：实现语义正确，但文档注释会误导后续实现 / review Agent。
- **建议修复方向**：改为“心跳不得大于 timeout”。

### S2-低-协议错误日志覆盖可以继续扩到所有 protocol error 分支

- **文件路径**：`dayu/engine/runners/openai/sse_parser.py`、`dayu/engine/runners/openai/non_stream_parser.py`
- **具体符号**：`SSEParser._dispatch_event_payload`、`_emit_from_dict`
- **触发场景**：SSE payload 不是 object，或 non-stream 缺 `choices` / `choice` 不是 object。
- **直接证据**：invalid UTF-8 / invalid JSON 已有 WARN；部分结构性协议错误仍只产出 `RunnerProtocolErrorData`，没有对应 logger warning。
- **影响**：事件契约已能表达错误，但日志诊断不是完全逐分支覆盖。
- **建议修复方向**：对所有会产出 `RunnerProtocolErrorData` 的 fatal 分支统一补一条参数化 WARN，并补一两个代表性 caplog 测试即可，不必把 logging 实现细节测得过死。

### S3-低-日志安全测试可更精确锁定 no body preview / no payload

- **文件路径**：`tests/engine/runners/openai/`
- **具体符号**：Runner diagnostics 测试集合。
- **触发场景**：后续有人在 HTTP error / protocol error / retry 日志里加入 body preview 或 payload。
- **直接证据**：当前代码安全，但测试主要验证日志存在，没有专项断言“敏感 body / payload 不出现在 log record message”。
- **影响**：不是当前泄漏，但未来回归保护偏弱。
- **建议修复方向**：增加一条窄测试：构造包含醒目 sentinel 的 request message / error body，断言 caplog 中不存在该 sentinel。

### S4-低-B3 pending leak 测试使用 `asyncio.all_tasks()`，后续可收窄断言对象

- **文件路径**：`tests/engine/runners/openai/test_runner_b3_extra.py`
- **具体符号**：`test_sse_idle_aclose_does_not_leak_pending_task`、`test_sse_idle_outer_cancel_does_not_leak_pending_task`
- **触发场景**：未来测试环境引入同 event loop 背景 task。
- **直接证据**：测试用当前 loop 的 `asyncio.all_tasks()` 全集断言“没有任何 pending task”。
- **影响**：当前 pytest-asyncio strict 隔离下稳定，通过结果可信；但长期看可能偏脆。
- **建议修复方向**：若后续出现 flake，把 fake `readany()` 内部 task 或 session 状态暴露成强类型测试探针，只断言该 pending read task 被取消。

## 15. 总体验收判断

Phase 1.5 实施结果建议通过。

它保持了 Phase 1.5 范围：只做公共 runtime log / cancellation helper、Runner diagnostics、SSE idle heartbeat / timeout，没有提前实现 Phase 2 AsyncAgent，也没有污染事件契约或引入上层依赖。OLD Log 中本轮明确要求的 `VERBOSE=15` 与第三方库静默已迁移，同时没有把 OLD `Log` 单例直接照搬成新的 god object。

当前剩余事项都是非阻塞清理与测试加固。按现有证据，issue #6 的 SSE idle heartbeat / idle timeout 可以关闭。
