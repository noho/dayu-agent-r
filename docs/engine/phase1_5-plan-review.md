# Phase 1.5 Log / Runner Diagnostics 计划复审

## 1. Review 结论：通过

新版 `docs/engine/phase1_5-plan.md` 已逐项修复上一轮阻塞与重要问题，可以作为 Phase 1 和 Phase 2 之间插入的 Log / Runner diagnostics 迁移计划进入实施。

本轮确认：

- `docs/engine/migration-plan.md` 已实际新增 Phase 1.5 行和「Phase 1.5 详细计划」。
- `OperationCancelled` 已移除，`dayu.runtime.cancellation` 改为封闭联合结果类型。
- `CancellableWaitResult` 双 bool 设计已替换为 `WaitCompleted[T] | WaitCancelled | WaitTimedOut`。
- caplog / `propagate=False` 的测试前提已拆清。
- `LogLevel.VERBOSE=15` 已取消，`verbose=True` 映射到 `DEBUG`。
- README 延后到 Phase 6 统一生成，已按用户决策写入计划和总控。

剩余只有一个重要澄清建议：`await_or_cancel()` 在 token 命中时应明确取消并等待它自己包装的 target task；`wait_for_or_cancel()` 才是不取消调用方传入 pending task 的复用型 helper。该项不阻塞进入实施，但建议在计划或实施时补进测试。

## 2. 阅读范围

已复审 NEW：

- `AGENTS.md`
- `CLAUDE.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase1_5-plan.md`
- `docs/engine/phase1-runner-old-new-review.md`
- `docs/engine/phase1-runner-old-new-round2-review.md`
- `docs/code_review.md`
- `dayu/contracts/cancellation.py`
- `dayu/engine/runners/openai/`
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/contracts/runner_events.py`
- `tests/README.md`

已复核 OLD 强参考源：

- `/Users/leo/workspace/dayu-agent/dayu/log.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/sse_parser.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/reasoning_protocol.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/xml_extractor.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_sse_parser.py`

## 3. OLD Log / diagnostics 证据审查

通过。计划保留了 OLD `dayu/log.py`、Runner、SSE parser、reasoning/xml extractor 与 OLD SSE parser tests 的证据，并正确区分协议事实和诊断辅助。

正确点：

- OLD `Log` 的统一配置思想可复用，但 `Log.debug/info/warn/error` 单例 wrapper 不迁移。
- OLD tool execution、ToolRegistry、trace、extra payload、Runner 层 `request_id` 不迁移。
- OLD idle heartbeat 是日志诊断，不是 RunnerEvent / EngineEvent 契约。
- OLD pending task early close / outer cancel 清理测试被纳入 NEW 测试计划。

## 4. Phase 1.5 插入点审查

通过。`docs/engine/migration-plan.md` 阶段总览已新增 Phase 1.5，Phase 2 输入也已改为 Phase 0 contracts、Phase 1 Runner、Phase 1.5 logger / cancellation runtime。

`docs/engine/migration-plan.md` 还新增了 `## 6.5 Phase 1.5 详细计划`，并明确 `docs/engine/phase1_5-plan.md` 是详细真源。Phase 0 不引入 Log、Phase 1.5 独立插在 Phase 2 AsyncAgent 前，这个阶段拆分合理。

## 5. Logger 模块边界审查

通过。计划采用 `dayu/runtime/log.py` 作为公共运行时 logger 装配入口，Engine Runner 只使用 stdlib `logging.getLogger(__name__)`，不 import `dayu.runtime.log`。

边界合理：

- `dayu.runtime.log.configure()` 是配置入口，不是 OLD `Log` 单例兼容 wrapper。
- Host / CLI 后续可以复用 `dayu.runtime.log.configure`。
- `configure()` 默认只配置 `dayu` namespace logger，不动 root，不动第三方 logger。
- 重复配置通过 marker handler 保持幂等。
- caplog 策略已拆为“未 configure 的 Runner 行为测试”和“configure 自身测试”，不再误判 root caplog 能捕获 `propagate=False` 的记录。
- `LogLevel` 已收敛为 DEBUG / INFO / WARN / ERROR 四档，`verbose=True` 映射 DEBUG。

## 6. RunnerSpec idle 字段审查

通过。新增字段：

- `stream_idle_timeout_seconds: float | None = None`
- `stream_idle_heartbeat_seconds: float | None = None`

这两个字段属于 Runner 运行规格，不是诊断 log 字段，不污染事件契约。计划已明确 `None+None` 禁用、timeout-only 合法、heartbeat-only 非法，负数 / 0 / `heartbeat > timeout` 构造期拒绝。

## 7. Idle heartbeat / idle timeout 设计审查

通过。idle 逻辑放在 Runner byte iterator 层，`SSEParser` 保持纯 parser，这个位置正确。

设计已覆盖：

- 跨循环复用 pending `readany()` task。
- 正常 chunk 到达后重置 idle 计时。
- heartbeat 只打 log，timeout 才进入 `_AttemptFailedRetriable(TIMEOUT)`。
- cancellation 优先于 timeout，Runner 看到 `WaitCancelled` 后翻译为 `_RunnerInterrupted`。
- disabled path 走 `_iter_response_bytes_no_idle`。
- retry 复用现有 Runner retry loop。
- generator `aclose()` / outer `Task.cancel()` 通过 finally 清理 pending task。
- 不新增 RunnerEvent / EngineEvent。

重要澄清建议：

- 文件路径：`docs/engine/phase1_5-plan.md:143`
- 具体章节或符号：`dayu/runtime/cancellation.py` 的 `await_or_cancel`
- 问题原因：计划明确 `wait_for_or_cancel` 不取消调用方传入的 `pending` task，但没有同样明确 `await_or_cancel` 在 token 命中时必须取消并等待它自己创建的 target task。
- 影响：实施 Agent 可能把两个 helper 都实现成“不取消目标 awaitable”，导致 HTTP POST、response body read、retry sleep 等路径在取消后留下后台 task。
- 建议修改方向：补一句“`await_or_cancel` 若内部用 `ensure_future` 包装 awaitable，token 命中时必须 cancel target task 并 await 收口；若 awaitable 是未调度 coroutine 且 token 已预先命中，应 close coroutine”。测试增加 target task 被取消并收口的断言。

## 8. 日志字段与安全性审查

通过。计划明确禁止记录：

- provider response body preview。
- 完整 exception text。
- messages / payload / headers / tool arguments / prompt 片段。
- f-string 直接拼接日志参数。

endpoint、attempt、status、error_code、retry_after_used、sleep_seconds、idle_total_seconds 等字段足够诊断，且不会把财报内容或 provider payload 泄漏进日志。

## 9. 架构边界审查

通过。计划继续禁止：

- Engine import Host / Service / UI / fins / trace / ToolExecutor / ToolRegistry。
- Engine import `dayu.runtime.log`。
- `dayu.runtime.*` import Engine / Host / Service / UI / fins。
- Log 读取财报文件或接触 fins storage。
- Log 替代 RunnerEvent / EngineEvent。
- 迁移 OLD `Log` 单例或兼容 wrapper。
- Runner 层发明 `request_id`。

`dayu.runtime.cancellation` 被明确为层中立公共 runtime helper，Engine Runner 可 import；这个边界与 `AGENTS.md` / `CLAUDE.md` 新增硬约束一致。

## 10. 测试计划审查

通过。测试计划覆盖面充分，且没有把日志实现细节锁得过死。

已覆盖：

- `dayu.runtime.log` configure 幂等、root 不污染、third-party override。
- `dayu.runtime` 不反向 import 上层。
- Engine 不 import `dayu.runtime.log`，允许 import `dayu.runtime.cancellation`。
- `await_or_cancel` / `wait_for_or_cancel` 封闭结果、outer cancel 透传、watcher / poller 清理。
- HTTP error / retry / protocol error / cancellation / close logging。
- no body preview。
- idle disabled / heartbeat / timeout / timeout-only / cancel wins / retry / aclose / outer cancel cleanup。
- RunnerSpec idle 字段 contract。
- RunnerEvent / EngineEvent 无 log / idle 污染。

建议补强一条：`tests/runtime/test_cancellation_await_or_cancel.py` 增加“token 命中时 target task 被取消并 await 收口”的断言，避免 §7 提到的泄漏风险。

## 11. README / docs 同步审查

通过。用户已明确 README 等全部迁移完毕后统一生成，计划和总控均写明 Phase 1.5 不修改、不新建任何 README，统一推迟到 Phase 6。

这与默认 README 触发规则存在阶段策略差异，但当前已有用户明确决策，本 review 不作为问题处理。实施 PR 说明中需要显式写明“本期不动 README，Phase 6 统一同步”。

## 12. 阻塞问题

无。

上一轮阻塞项均已修复：

- B1：`docs/engine/migration-plan.md` 已插入 Phase 1.5。
- B2：`OperationCancelled` 已移除，公共取消结果改为封闭联合。

## 13. 重要问题

### I1：`await_or_cancel` 的 target task 取消语义需要补一句

- 文件路径：`docs/engine/phase1_5-plan.md:143`
- 具体章节或符号：`await_or_cancel`
- 问题原因：计划只明确 watcher / poller 清理，没有明确 token 命中时 target task 是否被取消并 await。
- 影响：若实现 Agent 误解，会在非 idle 的阻塞边界留下后台 task。
- 建议修改方向：按 §7 的说明补充语义与测试。该项不阻塞进入实施，但建议实施前或实施中补齐。

## 14. 建议问题

### S1：已决事项可从“待确认”移出

- 文件路径：`docs/engine/phase1_5-plan.md:448`、`docs/engine/migration-plan.md:304`
- 具体章节或符号：用户确认点
- 问题原因：Phase 1.5 已写入总控、`LogLevel.VERBOSE=15` 已暂不保留、cancellation 结果类型已选封闭联合，但部分条目仍放在“待确认 / 用户确认点”。
- 影响：不影响实施，但会让后续 Agent 误以为这些问题仍未决。
- 建议修改方向：把这些条目改成“决策记录”；只保留真正需要用户确认的 RunnerSpec 字段落地时机或进入实施确认。

### S2：idle 伪代码可直接使用 `WaitCompleted.value`

- 文件路径：`docs/engine/phase1_5-plan.md:334`
- 具体章节或符号：`case WaitCompleted(value=chunk_bytes)`
- 问题原因：伪代码匹配出 `chunk_bytes` 后又调用 `pending.result()`，语义略重复。
- 影响：不影响方案正确性，但实现时容易让人误会 `WaitCompleted.value` 是否可信。
- 建议修改方向：如果 `wait_for_or_cancel` 已负责取出 task 结果并透传异常，Runner 直接使用 `chunk_bytes`；或者明确 `WaitCompleted` 只表示 task done、不承载结果。推荐前者。

## 15. 需要总控 / 用户确认的问题

实施前只剩一个流程性确认：

- 用户确认可以从计划 review 进入 Phase 1.5 实施。

以下问题已经在计划中形成决策，不再需要作为阻塞确认：

- Phase 1.5 写入总控。
- README 延后到 Phase 6。
- `LogLevel.VERBOSE=15` 暂不保留。
- cancellation 结果类型采用封闭联合。
- idle 放在 Runner byte iterator 层。

## 16. 总体验收判断

Phase 1.5 计划现在可以通过 review。它满足插入阶段、runtime logger、Runner diagnostics、RunnerSpec idle 字段、SSE idle heartbeat / hard timeout、事件契约隔离、架构边界、安全日志字段和测试计划要求。

建议实施 Agent 在开始编码前顺手补清 `await_or_cancel` target task 取消语义，并把已决事项从“待确认”移动到“决策记录”，但这两项不影响本计划作为 Phase 1.5 实施依据。
