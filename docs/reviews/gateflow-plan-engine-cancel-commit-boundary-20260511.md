# Gateflow Plan: engine-cancel-commit-boundary-and-tool-timeout

## 0. Plan Status

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Current gate**: plan
- **Repository**: `/Users/leo/workspace/dayu-agent-r`
- **Branch**: `host/phase_0_design`
- **Baseline commit**: `dddaaf3`
- **Ready for plan review**: yes
- **Blocking open questions**: none

本计划只定义后续实现边界，不包含本次 plan gate 的生产代码、测试、提交、PR 或 closeout 动作。

## 1. Goal And Motivation

目标是把已经定稿的 Engine 取消提交边界与 ToolExecutor bounded handshake timeout 落到可实施计划中：

1. **Cancellation commit boundary**：取消只阻止未来工作，不能吞掉已经被 Engine 接收并接受的 observable fact，包括 RunnerEvent delta、普通工具 outcome、awaiting 事实与 final answer。
2. **ToolExecutor.execute handshake timeout**：`ToolExecutor.execute(request)` 是 Engine 与 Host / EngineWorker 工具执行环境之间的有界握手。Engine 必须把 policy timeout 写入 `ToolExecutionContext.timeout_seconds`，并主动围绕 execute 等待执行同一个 timeout；握手超时必须收口为不可恢复 `run_failed(tool_execution_timeout)`，不能伪装成 `ToolFailedOutcome`。

动机成立。直接设计真源已经明确当前稳定规则：

- `docs/engine/design.md:518-524`：已经收到的 observable fact 必须先 emit / accept；late cancel 不能覆盖工具结果、awaiting 或 final answer。
- `docs/engine/design.md:526-533`：`AgentPolicy.tool_execution_timeout_seconds` 是 ToolExecutor handshake timeout 真源，必须为正数；timeout before outcome 时 Engine 取消 execute await task 并产出不可恢复 `run_failed(tool_execution_timeout)`。
- `docs/engine/design.md:535-544`：`ToolAwaitingOutcome` 是 suspend 唯一来源；outcome 已返回后 awaiting / suspended 事实优先于迟到取消。
- `docs/engine/design.md:575-590`：取消是 Host 真源映射来的 run-local token；Engine 只观察 token，取消只阻止未来工作。
- `docs/engine/cancel-suspend-boundary-discussion.md:28-33`、`:104-117`、`:197-210`、`:228-241`、`:248-258`：讨论稿留痕与最终设计一致。

## 2. Non-goals And Scope Boundary

本 work unit 不做以下事项：

- 不实现 Host ToolRuntime、ToolRegistry、外部长事务 monitor、job reconcile、cleanup hook 或 orphan scanner。
- 不改变 `ToolExecutionOutcome` 的封闭联合类型，不新增 detached/progressing/approval 等后续治理状态。
- 不把 timeout 伪造成工具业务失败，不把 `tool_execution_timeout` 写进 `ToolFailedOutcome.result.error`。
- 不新增 Engine 公共 cancel command；`CancelRun(...)` 仍属于 Host / 进程适配层。
- 不改变 resume 机制；`run_suspended` 与 `run_cancelled` 后续恢复都由调用方构造新的 `AgentRunRequest.messages`。
- 不改变 Runner provider 协议解析、SSE idle timeout、HTTP retry timeout 或 OpenAI runner 的已存在等待语义。
- 不引入兼容性 wrapper、兼容性 re-export 或弱类型 extra payload。

## 3. Direct Code Evidence

当前问题真实存在，且不是表面假设。

### 3.1 Final Answer 仍会被 late cancel 抢占

- `dayu/engine/agent.py:588-590` 与 `:607`：final decision 已经形成后调用 `_make_final_or_cancelled_after_close(...)`。
- `dayu/engine/agent.py:1637-1656`：`_make_final_or_cancelled_after_close` 在构造 `final_answer` 前检查 `_is_cancelled()`，若 token 此时已取消会返回 `run_cancelled`。
- `tests/engine/test_agent_phase2.py:627-654`：现有测试 `test_cancel_before_final_answer_wins_over_final` 断言 final 前取消优先于最终回答；这与 `docs/engine/design.md:524` 和 `:586` 的 final commit boundary 相冲突。

### 3.2 ToolAwaitingOutcome 返回后 cancel 仍可抢占 suspended

- `dayu/engine/agent.py:1348-1356`：`ToolExecutor.execute` 返回后，代码先检查 `_is_cancelled()`；如果工具内部在返回 awaiting 前触发 token，Engine 会直接 `run_cancelled`，不会 emit `tool_awaiting`。
- `dayu/engine/agent.py:1357-1387`：即便已经 emit `tool_awaiting`，代码在 `:1381-1383` 再次检查取消，随后 `_make_suspended_or_cancelled_terminal_with_close(...)` 又会在 `:1682-1686` 让取消覆盖 `run_suspended`。
- `tests/engine/test_agent_phase3_tool_call.py:1167-1212`：现有测试断言 awaiting 前后取消都优先 `run_cancelled`，并且 after-awaiting 场景没有 `run_suspended`；这与 `docs/engine/design.md:523`、`:538-544` 相冲突。

### 3.3 Completed / Failed Tool Outcome 返回后 cancel 仍可吞掉 accepted fact

- `dayu/engine/agent.py:1348-1356`：`_execute_one_tool` 返回 `WaitCompleted` 后先检查 `_is_cancelled()`，因此 completed / failed outcome 已返回但可能不产出 `tool_result_accepted`。
- `dayu/engine/agent.py:1391-1404`：只有通过上述取消检查后才 emit `tool_result_accepted` 并记录 `_ToolOutcomeRecord`。
- `tests/engine/test_agent_phase3_tool_call.py:1581-1601`：现有测试断言工具 outcome 后 token 取消时不出现 `TOOL_RESULT_ACCEPTED`；这与 `docs/engine/design.md:522` 相冲突。

### 3.4 ToolExecutionContext.timeout_seconds 当前没有 policy 真源

- `dayu/engine/contracts/agent_policy.py:38-81`：`AgentPolicy` 只有 max iteration、continuation、fallback 与连续失败工具批次策略，没有 `tool_execution_timeout_seconds`。
- `dayu/contracts/tool_call.py:74-98`：`ToolExecutionContext.timeout_seconds` 字段存在，但语义仍写为 `None` 表示 Host 兜底。
- `dayu/engine/agent.py:1333-1340`：Agent 构造 `ToolExecutionContext` 时把 `timeout_seconds=None` 写死。

### 3.5 ToolExecutor.execute 缺少 handshake timeout

- `dayu/engine/agent.py:1434-1462`：`_execute_one_tool` 只调用 `await_or_cancel(self._request.tool_executor.execute(...), token=...)`；没有 timeout 分支。
- `dayu/runtime/cancellation.py:84-131`：`await_or_cancel` 只返回 `WaitCompleted | WaitCancelled`。
- `dayu/runtime/cancellation.py:133-188`：`wait_for_or_cancel` 支持 timeout，但它不拥有 pending task，不负责取消 target；ToolExecutor handshake 需要 Engine 拥有 execute task 并在 timeout / cancellation 后取消并等待 task 收口。

## 4. Affected Files / Modules

允许后续 implementation slices 修改以下文件。未列出的生产代码默认不应修改。

- `dayu/engine/contracts/agent_policy.py`
- `dayu/engine/agent.py`
- `dayu/runtime/cancellation.py`
- `dayu/contracts/tool_executor.py`
- `dayu/contracts/tool_call.py`（只允许同步 docstring 语义，不改字段形状，除非 pyright 暴露必要性）
- `tests/runtime/test_cancellation.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `utils/smoke_async_agent_providers.py`（仅当 `AgentPolicy` 新增必填字段导致 pyright 失败时更新构造参数）
- `dayu/engine/README.md`
- `docs/engine/design.md`（仅做与最终稳定规则一致的文档去陈旧化）
- `tests/README.md`（仅当新增测试分层或运行约定发生变化；预计无需更新）

## 5. Public Contract / Schema / State-machine Changes

### 5.1 AgentPolicy

在 `AgentPolicy` 增加必填字段：

```python
tool_execution_timeout_seconds: float
```

决策：

- 字段放在 `allow_tool_calls` 之后、所有有默认值字段之前，保持 dataclass 非默认字段顺序合法。
- 不提供默认值。原因：设计真源要求该值是 handshake timeout 真源；默认值会让调用方误以为 Host / EngineWorker 可以不表达工具握手治理输入。
- `__post_init__` 必须校验 `tool_execution_timeout_seconds > 0`，否则抛 `ValueError("AgentPolicy.tool_execution_timeout_seconds must be > 0")`。
- 类型保持 `float`，不使用 `int | float`，调用方传入整数字面量可被 Python 接受但字段类型仍为浮点策略值。

### 5.2 ToolExecutionContext

字段形状不变：

```python
timeout_seconds: float | None
```

但 Engine 侧语义改变：

- Agent 构造 context 时必须传入 `request.agent_policy.tool_execution_timeout_seconds`。
- Engine 产出的 `ToolExecutionContext.timeout_seconds` 对 ToolExecutor 始终是正数，不再是 `None`。
- `None` 仍保留为共享契约允许值，供非 Engine 调用方或未来更底层协议表达“未配置”；本 work unit 不做字段收窄，避免把共享契约改成只能服务 Engine。

### 5.3 Runtime Wait Contract

新增 runtime 层中立 timeout outcome 与 helper：

```python
@dataclass(frozen=True, slots=True)
class WaitTimedOut:
    """等待对象超时。"""
```

并新增 helper，建议命名：

```python
async def await_or_cancel_or_timeout(
    awaitable: Awaitable[T],
    *,
    token: CancellationToken,
    timeout_seconds: float,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
) -> WaitOutcome[T]:
    ...
```

决策：

- helper 拥有 awaitable，与 `await_or_cancel` 一样内部 `ensure_future`。
- awaitable 完成：返回 `WaitCompleted(value=...)`。
- cancellation 先到：取消 target task，等待 task done，返回 `WaitCancelled`。
- timeout 先到：取消 target task，等待 task done，返回 `WaitTimedOut`。
- cancellation 与 timeout 同时命中：返回 `WaitCancelled`，保持 `dayu.runtime.cancellation` 现有优先级。
- `asyncio.CancelledError` 透传。
- timeout_seconds 非正值由 `AgentPolicy` fail fast 保证；helper 不承担业务 policy 校验，但 docstring 要说明调用方必须传入正数。
- 本 work unit 选择 no-background-task ownership：timeout / cancellation 后 helper 会等待 target task 收口，不 detach 后台 task。
- 因此 `ToolExecutor.execute` 必须协作 task cancellation：Engine handshake timeout 触发时，execute coroutine 不得吞掉 `asyncio.CancelledError` 后无限运行。非协作 executor 属于协议违约；Engine 不能在没有 `await_spec` / `snapshot` 时替它恢复或监控外部长事务。

不使用 `asyncio.wait_for` 直接包在 Agent 里，因为这会绕开项目已有 cancellation race 语义，也会把可复用的层中立等待能力散落在 Engine 业务层。

### 5.4 Error Semantics

新增 Agent 内部错误码常量：

```python
_ERROR_TOOL_EXECUTION_TIMEOUT: str = "tool_execution_timeout"
_TOOL_EXECUTION_TIMEOUT_MESSAGE: str = "tool execution handshake timed out"
```

超时终态：

- Event：`EngineEventType.RUN_FAILED`
- Data：`RunFailedData(error_code="tool_execution_timeout", message=_TOOL_EXECUTION_TIMEOUT_MESSAGE, recoverable=False)`
- Outcome：`run_agent_and_wait` 映射为 `EngineRunOutcomeFailed`
- 不 emit `tool_result_accepted`
- 不生成 `ToolFailedOutcome`
- 不注入 `ToolMessage`
- 不进入下一轮 Runner

### 5.5 Cancellation Commit Boundary

状态机决策：

- RunnerEvent 已从 async iterator 收到后，先调用 `_consume_runner_event` 并 yield 对应 EngineEvent / 更新 accepted state；之后才观察取消。当前主链路已大体满足此点，测试需要固定。
- `_FinalDecision` 已经形成并被 Agent 接受后，`final_answer` 是 terminal commit boundary；late cancel 不覆盖 final。
- `ToolExecutor.execute` 返回 `ToolAwaitingOutcome` 后，先 emit `tool_awaiting`，再 emit terminal `run_suspended`；late cancel 不覆盖 suspended。
- `ToolExecutor.execute` 返回 `ToolCompletedOutcome | ToolFailedOutcome` 后，先 emit `tool_result_accepted`，把 `_ToolOutcomeRecord` 写入 accepted records；outer `run_messages` 根据 completed batch 调用 `_inject_tool_messages(...)`，随后观察取消。如果已取消，产出 `run_cancelled`，且不进入下一轮 Runner。
- `ToolExecutor.execute` 尚未返回时，取消仍可通过 runtime wait helper 抢占，收口为 `run_cancelled`。
- 进入下一轮普通 Runner、进入 continuation Runner、进入 force-answer Runner 前仍必须观察取消。

### 5.6 Runner Close Ordering

保持 `run_messages` 的 `finally: await self._close_runner_once()` 真正兜底关闭。

局部 helper 决策：

- Final answer 不需要提前 close 后再构造 terminal；terminal yield 后 `finally` 关闭 Runner。
- Cancelled terminal 仍可使用 `_make_cancelled_terminal_with_close()`，保持现有入口已取消测试里“先 close 再 emit cancelled”的可观察行为。
- Suspended terminal 不应在 close 前后重新检查取消；如需保持“挂起时先 close 再 emit suspended”的现有 ordering，可在 `_make_suspended_terminal_after_close(awaiting)` 中只 close，然后直接构造 `run_suspended`。
- 不在 close 失败时改变已接受 terminal 类型；`_close_runner_once` 已负责吞掉 close 异常并记录日志。

## 6. Implementation Slices

### Slice 1: contract-timeout-policy-and-runtime-helper

**Objective**：建立 timeout policy 真源与可复用的 owned awaitable cancellation/timeout helper，后续 Agent 不需要发明等待语义。

**Allowed files/modules**：

- `dayu/engine/contracts/agent_policy.py`
- `dayu/runtime/cancellation.py`
- `tests/runtime/test_cancellation.py`
- `tests/engine/test_agent_phase3_tool_call.py`（只允许更新 `AgentPolicy` 构造 helper / contract 字段断言）
- `tests/engine/test_agent_phase2.py`（只允许更新 `AgentPolicy` 构造 helper）
- `utils/smoke_async_agent_providers.py`（仅为 pyright 修复 `AgentPolicy` 构造）

**Exact changes**：

- 在 `AgentPolicy` 增加必填 `tool_execution_timeout_seconds: float`。
- 更新 `AgentPolicy` 中文 docstring，加入参数说明和异常说明。
- 在 `__post_init__` 增加正数校验。
- 在 `dayu.runtime.cancellation` 新增 `await_or_cancel_or_timeout`，复用现有 `_poll_cancellation` 与 `_cancel_task_and_wait`。
- 在 `dayu.runtime.cancellation` 新增 `WaitTimedOut`，并更新 Wait outcome 类型别名 / `__all__`。
- 更新 runtime 模块概览 docstring 与 `__all__`。
- 更新测试 helper 中所有 `AgentPolicy(...)` 构造，统一传入测试常量，例如 `_TOOL_EXECUTION_TIMEOUT_SECONDS: float = 5.0`，避免散落魔法数字。
- 更新 `test_contract_fields_are_explicit` 断言 policy 字段存在。
- 更新 `test_agent_policy_rejects_invalid_values`，覆盖 `0.0`、负数的 `tool_execution_timeout_seconds`。
- 新增 runtime tests：
  - awaitable 正常完成返回 `WaitCompleted`。
  - token 先命中返回 `WaitCancelled` 且 target task 被取消并收口。
  - timeout 先命中返回 `WaitTimedOut` 且 target task 被取消并收口。
  - timeout 先命中时 target task 内部收到 `asyncio.CancelledError`；测试用 executor/coroutine 必须协作退出，证明 no-background-task ownership 路径成立。
  - token 与 timeout 同时可见时返回 `WaitCancelled`。
  - awaitable 自身异常透传。
  - 外层 task cancel 透传 `asyncio.CancelledError`。

**Non-goals**：

- 不修改 Agent 工具执行流程。
- 不新增 `tool_execution_timeout` run_failed 行为。
- 不修改 `ToolExecutionContext` 字段类型。

**Tests / validation**：

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`

**Completion signal**：

- 所有 `AgentPolicy` 构造点通过 pyright。
- runtime helper 的 completion / cancellation / timeout / exception / outer cancel 分支均有测试。

**Stop condition**：

- 如果新增必填 policy 字段需要修改未列出的生产模块，停止并回报 Controller，除非只是 pyright 暴露的直接构造点。

### Slice 2: agent-tool-handshake-timeout

**Objective**：Agent 在 ToolExecutor.execute handshake 上同时执行 cancellation race 与 timeout race，并把 timeout 收口为 Engine run failure。

**Allowed files/modules**：

- `dayu/engine/agent.py`
- `dayu/contracts/tool_executor.py`
- `dayu/contracts/tool_call.py`（docstring only）
- `tests/engine/test_agent_phase3_tool_call.py`

**Prerequisites**：Slice 1 已完成。

**Exact changes**：

- `agent.py` import `WaitTimedOut` 与 `await_or_cancel_or_timeout`。
- 新增 `_ERROR_TOOL_EXECUTION_TIMEOUT` 与 `_TOOL_EXECUTION_TIMEOUT_MESSAGE` 常量。
- `_execute_one_tool` 返回类型改为包含 `WaitTimedOut`，或引入私有封闭联合，例如 `_ToolExecuteResult = WaitCompleted[ToolExecutionOutcome] | WaitCancelled | WaitTimedOut`。
- `_execute_one_tool` 调用：

```python
await_or_cancel_or_timeout(
    self._request.tool_executor.execute(tool_request),
    token=self._request.cancellation_token,
    timeout_seconds=self._request.agent_policy.tool_execution_timeout_seconds,
)
```

- `_execute_tool_batch` 构造 `ToolExecutionContext.timeout_seconds` 时填入 `self._request.agent_policy.tool_execution_timeout_seconds`。
- `_execute_tool_batch` 收到 `WaitTimedOut` 时设置 `_last_tool_batch_result = RunFailedData(error_code="tool_execution_timeout", message=..., recoverable=False)` 并 return；由调用方现有 `RunFailedData` 分支 yield `run_failed`。
- timeout 不进入 `except Exception`，不生成 `ToolFailedOutcome`。
- `ToolExecutor.execute` docstring 补充：实现可观察 `request.context.timeout_seconds`，但 Engine 也会主动执行 handshake timeout；timeout 不作为协议 `:raises:` 暴露。
- `ToolExecutor.execute` docstring 补充：Engine-enforced timeout / cancellation 会通过 coroutine task cancellation 终止等待；实现必须协作 `asyncio.CancelledError`，不得吞掉取消后无限运行。若外部 job 已启动但未返回 `ToolAwaitingOutcome`，cleanup / reconcile / orphan control 属于 ToolExecutor / ToolRuntime 责任。
- `ToolExecutionContext.timeout_seconds` docstring 补充 Engine 侧会传入 policy 正数。

**Non-goals**：

- 不改变工具 outcome 类型。
- 不改变 Host 外部长事务治理边界。
- 不实现外部 job cleanup。

**Tests / validation**：

- 新增测试 `test_tool_execution_context_receives_policy_timeout`：fake executor 记录 request，断言 `context.timeout_seconds == policy.tool_execution_timeout_seconds`。
- 新增测试 `test_tool_executor_execute_timeout_fails_run_without_tool_failed_outcome`：
  - fake executor 挂起超过 timeout；
  - 事件 terminal 为 `RUN_FAILED`；
  - `RunFailedData.error_code == "tool_execution_timeout"`；
  - `recoverable is False`；
  - 没有 `TOOL_RESULT_ACCEPTED`；
  - runner 没有第二轮调用；
  - fake executor 的 pending coroutine 被取消并完成；
  - 不出现 `ToolFailedOutcome`。
- 运行：
  - `source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py -q`
  - `source .venv/bin/activate && pytest tests/engine -q`
  - `source .venv/bin/activate && pyright`
  - `git diff --check`

**Completion signal**：

- timeout 路径产出唯一 terminal `run_failed(tool_execution_timeout)`。
- `ToolExecutionContext.timeout_seconds` 不再为 `None`。

**Stop condition**：

- 如果 timeout 与 cancellation 同时触发导致测试不稳定，停止并回报；不要用 sleep 放大或弱断言掩盖 race，应通过 runtime helper 的 cancellation-priority 语义固定。

### Slice 3: agent-cancellation-commit-boundary

**Objective**：落地 observable fact / cancellation commit boundary，修正 final、awaiting、completed/failed tool outcome 的 late cancel 行为。

**Allowed files/modules**：

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`

**Prerequisites**：Slice 1 已完成；可与 Slice 2 顺序执行，但建议在 Slice 2 后做，避免工具 execute 返回分支重复调整。

**Exact changes**：

- 删除或替换 `_make_final_or_cancelled_after_close` 的取消抢占语义：
  - 建议改名为 `_make_final_terminal(decision)` 或 `_make_committed_final_terminal(decision)`。
  - 不在 final terminal 构造前检查 `_is_cancelled()`。
  - 所有 final decision 已接受的调用点改用新 helper。
- 修改 `_make_suspended_or_cancelled_terminal_with_close`：
  - 建议改名为 `_make_suspended_terminal_after_close(awaiting)`。
  - 不在 awaiting outcome 已返回后检查 `_is_cancelled()`。
  - 保持 close ordering 后直接 `run_suspended`。
- 修改 `_execute_tool_batch`：
  - `WaitCancelled` 仍直接 `run_cancelled`，因为 execute 尚未返回 outcome。
  - `WaitCompleted` 后不要在 outcome 分类前检查取消。
  - `ToolAwaitingOutcome`：先 emit `TOOL_AWAITING`，再 emit `RUN_SUSPENDED`；中间不允许 late cancel 覆盖。
  - `ToolCompletedOutcome | ToolFailedOutcome`：先 emit `TOOL_RESULT_ACCEPTED` 并 append records。
- 修改 outer `run_messages` 的 completed batch 后续路径：
  - `_execute_tool_batch` 不持有 `messages`，不负责注入 ToolMessage，不新增 `messages` 参数。
  - `run_messages` 读取 `_last_tool_batch_result` 后，保持由 `_inject_tool_messages(messages=..., decision=..., records=...)` 完成 AssistantMessage + ToolMessage 注入。
  - `_inject_tool_messages(...)` 必须发生在取消检查前；注入完成后再检查 `_is_cancelled()`。
  - 若此时已取消，emit `RUN_CANCELLED` 并 return，不进入下一轮 Runner。
- 保留以下取消观察点：
  - run 入口。
  - iteration 起点。
  - Runner 调用开始前。
  - RunnerEvent 已消费并 yield 后的下一步边界。
  - ToolExecutor.execute 尚未返回时。
  - 下一轮 Runner / continuation / force-answer 进入前。

**Non-goals**：

- 不改变 provider protocol error 与 cancellation 的先后规则，除非测试证明它吞掉已 emit 的 provider error event。
- 不改变 close 异常处理。
- 不新增持久化 transcript；accepted run-local context 仅指当前 Agent messages 列表。

**Tests / validation**：

更新或新增以下断言：

- `final late cancel 不覆盖 final`：
  - 替换 `tests/engine/test_agent_phase2.py:627-654` 的旧断言；
  - Runner 已产出 completed content / done 后 token 触发；
  - terminal 必须是 `FINAL_ANSWER`，且没有 `RUN_CANCELLED`。
- `RunnerEvent content/reasoning delta 已收到后先 emit`：
  - content delta 后 token 触发时，事件序列包含 `CONTENT_DELTA` 后才是 `RUN_CANCELLED`；
  - reasoning delta 同理包含 `REASONING_DELTA` 后才是 `RUN_CANCELLED`。
- `awaiting returned 后 late cancel 不覆盖 suspended`：
  - executor 返回 `ToolAwaitingOutcome` 并触发 token；
  - 事件序列包含 `TOOL_AWAITING` 与 terminal `RUN_SUSPENDED`；
  - 没有 `RUN_CANCELLED`；
  - `await_spec` / `snapshot` 在两个事件中保留同一对象。
- `completed/failed tool outcome returned 后先 tool_result_accepted + inject ToolMessage`：
  - completed outcome 返回并触发 token；
  - 事件序列包含 `TOOL_RESULT_ACCEPTED` 后 terminal `RUN_CANCELLED`；
  - runner 只有第一轮调用，不进入下一轮 Runner；
  - late cancel 场景的稳定可观察契约是 `TOOL_RESULT_ACCEPTED` 已 emit 且下一轮 Runner 被阻止；不要为了证明内部 list append 而新增 public API、monkeypatch `_inject_tool_messages` 或读取 `_last_tool_batch_result`。
  - ToolMessage 注入的具体内容继续由现有正常 completed / failed 下一轮测试覆盖；本 slice 如发现正常路径缺少 failed ToolMessage projection 断言，可以在非 cancel 场景补足。
  - failed outcome 同样覆盖 late cancel 事件顺序，断言 `TOOL_RESULT_ACCEPTED` 的 outcome 是 `ToolFailedOutcome`。
- `late cancel 只阻止下一轮 Runner`：
  - completed/failed outcome accepted 后 token 取消，`runner.call_count == 1`。

运行：

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
- `source .venv/bin/activate && pytest tests/engine -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`

**Completion signal**：

- 所有旧“cancel wins over committed fact”的测试已替换为设计真源断言。
- final、awaiting、completed/failed tool outcome 三条 commit boundary 都有回归测试。

**Stop condition**：

- 如果必须为了测试注入状态而暴露新的 public API，停止并回报 Controller；不得为了测试便利扩大 Engine 公共契约。

### Slice 4: docs-sync-and-full-validation

**Objective**：同步文档到当前实现与最终稳定规则，运行完整受影响验证。

**Allowed files/modules**：

- `dayu/engine/README.md`
- `docs/engine/design.md`
- `tests/README.md`（预计无需修改；只有测试运行约定变化时允许）

**Prerequisites**：Slices 1-3 已完成。

**Exact changes**：

- `dayu/engine/README.md` 必须更新，因为当前 README `:339-345` 仍写“工具执行前后观察 token”以及“取消优先于挂起、最终回答和失败候选”，与最终稳定规则冲突。
- README 应写当前事实：
  - Engine 入口和阻塞边界观察取消；
  - 已接受 observable fact 优先；
  - final answer、awaiting/suspended、completed/failed tool result 的 commit boundary；
  - ToolExecutor handshake timeout policy 来自 `AgentPolicy.tool_execution_timeout_seconds`；
  - timeout 收口为不可恢复 `run_failed(tool_execution_timeout)`。
- `docs/engine/design.md` 原则上是设计真源且 `:518-544` 已正确；但 `:341-355` 仍有早期表述“在提交 final_answer 前必须再次检查取消”“工具超时由 Host ToolRuntime 负责”，容易误导实现。允许做最小去陈旧化，使该处指向稳定规则而不是重复冲突规则。
- `docs/engine/design.md` 中 AgentPolicy 字段列表必须补充 `tool_execution_timeout_seconds`，并说明它是 ToolExecutor handshake timeout 真源。
- `docs/engine/design.md` 早期 cancellation 分析段落如果保留“取消命中后不能继续产出 final_answer”这类旧行为证据，必须明确标注为历史行为或改写为“final candidate accepted 前取消可生效；final accepted 后 late cancel 不覆盖 final”。
- `tests/README.md` 预计无需更新，因为只新增同层测试，不改变测试分层、运行方式或维护规则。

**Non-goals**：

- 不新增未来设计、版本记录或过程状态。
- 不改根目录 README，除非实现改动影响用户手册命令或配置入口；本 work unit 预计不影响。

**Tests / validation**：

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`

**Completion signal**：

- README 与 design doc 不再保留“取消覆盖已接受 final/suspend/tool result”的旧术语。
- `docs/engine/design.md` 不再存在未限定的旧稳定口径，例如“取消优先于挂起、最终回答”或“取消命中后不能继续产出 final_answer”。
- `AgentPolicy.tool_execution_timeout_seconds` 在 README 与 design 的公共契约 / 策略字段说明中均可找到。
- 所有验证命令通过，或失败有直接原因与后续 owner。

**Stop condition**：

- 如果文档更新需要改写 Host / EngineWorker 边界或配置入口，停止并回报 Controller；这超出本 work unit 的 docs sync。

## 7. Review Gates

计划 gate 后续应执行：

1. **Plan review**：重点 review contract 是否足够明确、timeout policy 是否应为必填字段、runtime helper 是否符合层中立约束、slice 是否足够小。
2. **Plan fix / re-review**：所有 accepted findings 必须修复并重新审查。
3. **User confirmation**：plan re-review 通过后等待用户确认，不得直接 implementation。
4. **Implementation review per slice**：每个 slice 完成后只 review assigned slice diff，不提前 review 未执行 slice。
5. **Fix / re-review per slice**：accepted code findings 必须修复并 re-reviewed。
6. **User confirmation per slice**：每个 slice re-review 后等待用户确认再 accepted slice commit。

## 8. Global Stop Conditions

后续 implementation agent 必须停止并交回 Controller的情况：

- 发现 `AgentPolicy.tool_execution_timeout_seconds` 放在 `AgentPolicy` 会造成无法局部修复的上层公共契约冲突。
- 需要修改 Host / Service / UI 层才能让 pyright 通过。
- 需要引入新的 public Engine API、schema migration、storage change 或 Host resume 协议。
- timeout 语义无法在不伪造成 `ToolFailedOutcome` 的情况下实现。
- 为测试 commit boundary 必须暴露生产 public API 或加入仅测试用 seam。
- 发现 `docs/engine/design.md` 与讨论稿存在新的 material 冲突，且无法通过本计划现有决策收敛。

## 9. Risks And Residual Risks

- **Risk: 必填 policy 字段扩大修改面**。pyright include 覆盖 `dayu`、`tests`、`utils`，因此 `utils/smoke_async_agent_providers.py` 可能需要同步构造参数。该风险可在 Slice 1 内直接解决。
- **Risk: async timeout 测试易抖动**。应使用短 timeout + executor 内部 `asyncio.Event` / cancellation acknowledgement，而不是依赖真实长 sleep。
- **Risk: close ordering 改变测试可观察时间**。保留 cancelled 入口“先 close 再 emit”现有行为；final/suspended 只保证 terminal 类型与唯一性，close 由 finally 兜底。
- **Risk: accepted ToolMessage 注入在 late cancel 场景不可直接观察**。验收以稳定可观察契约为准：`TOOL_RESULT_ACCEPTED` 已 emit、terminal 为 `RUN_CANCELLED`、无下一轮 Runner；ToolMessage projection 内容由正常 completed/failed 下一轮测试覆盖，不用私有 monkeypatch 或新增 public seam。
- **Residual risk: timeout 后工具侧实际工作是否停止不可由 Engine 保证**。这是设计真源明确接受的边界；ToolRuntime / ToolExecutor 负责 cleanup / orphan control，不在本 work unit 内解决。

## 10. Open Questions

### Blocking Open Questions

None.

### Non-blocking Notes

- `ToolExecutionContext.timeout_seconds` 仍保留 `float | None` 是共享契约保守决策；Engine 本次实现会始终传正数。如果未来希望契约整体收窄为 `float`，应另开 contract cleanup work unit。
- `tool_execution_timeout` message 文案只用于诊断，不是外部协议稳定字段；稳定字段是 `error_code` 与 `recoverable=False`。

## 11. Required Validation Commands

后续实现完成后至少运行：

```bash
source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine -q
source .venv/bin/activate && pyright
git diff --check
```

用户要求的最低命令也必须覆盖：

```bash
source .venv/bin/activate && pytest tests/engine -q
source .venv/bin/activate && pyright
git diff --check
```

## 12. Implementation Completion Report Format

每个 implementation slice 完成后，implementation agent 必须写 durable artifact，并在报告中包含：

```markdown
## Implementation Report

- Work gate: implementation
- Work unit: engine-cancel-commit-boundary-and-tool-timeout
- Assigned slice: <slice id and name>
- Approved plan path: docs/reviews/gateflow-plan-engine-cancel-commit-boundary-20260511.md
- Changed files:
  - <path>
- Plan items implemented:
  - <item>
- Plan items not implemented:
  - <item and reason, or none>
- Validation:
  - `<command>`: passed/failed/not run, with reason
- Documentation decision and result:
  - <updated/not updated and why>
- Plan gaps or Controller decisions needed:
  - <none or details>
- Residual risks / uncovered areas:
  - <risk>: fixed in current slice / covered by later slice <id> / later work unit / existing issue / requires user decision
- Completion signal:
  - <met/not met>
- Stop condition status:
  - <none hit / hit with reason>
- Artifact path:
  - docs/reviews/<artifact-name>.md
```
