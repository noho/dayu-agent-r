# Engine cancel / suspend boundary discussion

本文档记录 Engine cancel、suspend、resume 边界的讨论结论草案。它不是设计真源；定稿前不得把本文内容直接视为 `docs/engine/design.md` 的稳定规则。

## 背景问题

当前 Engine 已提供：

- `cancellation_token`
- `ToolExecutor.execute(request)`
- `ToolAwaitingOutcome(await_spec, snapshot)`
- `tool_awaiting`
- `run_suspended`
- `run_cancelled`
- `final_answer`

需要进一步确认的问题是：取消在 Runner、ToolExecutor、final answer、awaiting suspend 等边界上的优先级到底如何定义。

## 初步共识

取消不应被理解为“随时覆盖一切终态”。更合理的规则是：取消在可中断边界生效；一旦某个结果已经越过对应 commit boundary，Engine 不应再用迟到的取消吞掉已经提交的事实。

统一原则：

```text
observable fact already received
  -> emit / accept the fact first
  -> cancellation only prevents future work
```

这条原则覆盖 RunnerEvent stream 中已经收到的 content / reasoning / usage / protocol facts，也覆盖 ToolExecutor 已经返回的 completed / failed / awaiting outcome。

`ToolExecutor.execute` 应被理解为 run 内工具调用的 bounded execution handshake：短工具返回结果，长工具返回可恢复等待事实；Engine 等待 handshake outcome，但不托管长事务生命周期。

## ToolExecutor.execute 执行模型

Engine 视角下，`ToolExecutor.execute(request)` 是 call and wait：

```text
Runner.call
  -> model requests tool
  -> Engine calls ToolExecutor.execute(ToolExecutionRequest)
  -> Engine awaits ToolExecutionOutcome
```

Engine 必须等到明确 outcome，才能决定下一步：

```text
completed / failed
  -> tool_result_accepted
  -> inject tool message
  -> observe cancellation_token
  -> if cancelled: run_cancelled
  -> otherwise: next Runner iteration / fallback

awaiting
  -> tool_awaiting
  -> run_suspended

cancel / exception
  -> run_cancelled / run_failed
```

但这个 wait 只等待“工具执行决策或提交事实”，不等待外部长事务终态。

ToolExecutor 实现视角下，`execute()` 应尽快在有界边界内返回三类结果之一：

```text
short tool finished
  -> ToolCompletedOutcome / ToolFailedOutcome

long tool accepted / external job started
  -> ToolAwaitingOutcome(await_spec, snapshot)

cannot start / execution error
  -> ToolFailedOutcome or exception
```

关键边界：

- Runner 只负责模型调用，不执行工具。
- ToolExecutor 是 Engine 和调用者工具执行环境之间的唯一握手入口。
- Engine 可以 `await execute()`，但这个 await 不代表 Engine 托管长任务。
- 长工具一旦启动并需要上层接管，应返回 `ToolAwaitingOutcome`，把 `await_spec` / `snapshot` 交给上层。
- Engine 不轮询 job，不持久化 wait record，不监控终态，不在同一个 Agent 实例里 resume。

## ToolExecutor.execute timeout

`ToolExecutor.execute` 需要 timeout，但 timeout 的对象必须定义清楚。

建议区分三类 timeout：

```text
ToolExecutor.execute handshake timeout
  -> 限制 execute() 多久必须返回一个 ToolExecutionOutcome

external job timeout
  -> 限制 ToolAwaitingOutcome 背后的外部长事务多久必须终态

tool internal timeout
  -> 限制具体工具内部 HTTP / DB / sandbox 等子操作
```

Engine 应关心的是第一类：handshake timeout。它防止 Engine 被工具执行环境无限挂住。

建议规则：

```text
ToolExecutor.execute starts
  -> Engine passes ToolExecutionContext.timeout_seconds
  -> ToolExecutor / tool may observe timeout_seconds
  -> Engine also enforces timeout around execute()
  -> timeout before outcome
      -> run_failed(tool_execution_timeout)
```

长工具不能通过超长 `execute()` 表达“还在跑”。如果工具已经启动外部长事务并需要上层接管，必须在 handshake timeout 内返回 `ToolAwaitingOutcome(await_spec, snapshot)`。

外部长事务 timeout 不属于 Engine 等待范围。工具返回 `ToolAwaitingOutcome` 后，job 超时、丢失、重试、取消和终态监控由上层调用者 / 工具运行环境治理。

handshake timeout 只表示 Engine 不再等待 `ToolExecutor.execute`。它不证明工具内部工作已经停止。

```text
Engine handshake timeout
  -> cancel execute await task
  -> run_failed(tool_execution_timeout)
  -> close Runner
  -> Engine responsibility ends

ToolExecutor / ToolRuntime responsibility
  -> observe cancellation / timeout
  -> stop local work if possible
  -> if external job may have started, reconcile / cleanup / orphan control
```

Engine 能正确收口为 `run_failed(tool_execution_timeout)`，但不能保证工具线程、子进程、HTTP 请求或远端 job 已经停止。Engine 也不能恢复或监控可能已经启动的外部长事务，因为 timeout 路径没有 `await_spec` / `snapshot`。

因此 ToolExecutor 必须承担半提交治理：如果外部 job 可能已经启动但还没返回 `ToolAwaitingOutcome`，ToolExecutor / ToolRuntime 必须有自己的幂等 job id、cleanup hook 或 orphan scanner。Engine 不接受“可能启动了 job，但没有给 await_spec”的半提交状态作为可恢复事实。

当前待定点：

- timeout 真源应放在 `AgentRunRequest`、`AgentPolicy`，还是独立 Engine tool execution policy。
- `ToolExecutionContext.timeout_seconds` 当前字段已经存在，但 Engine 现在传入 `None`；如果落地，应由调用方显式配置后由 Engine 填入。
- timeout 后错误码可考虑 `tool_execution_timeout`。
- timeout 后 `recoverable` 是否为 `False`。当前倾向为 `False`，因为 Engine 无法确认工具是否已经安全启动；若工具已经启动但没有返回 `ToolAwaitingOutcome`，属于 ToolExecutor 违反 handshake 约定。

## 入口与耗时边界

run 入口必须检查 `cancellation_token`。如果入口处已经取消，Engine 直接以 `run_cancelled` 收口。

之后主要耗时边界是：

```text
RunnerEvent stream
ToolExecutor.execute
```

RunnerEvent stream 的建议规则：

```text
receive RunnerEvent
  -> lift / emit corresponding EngineEvent
  -> update accepted run-local state when needed
  -> observe cancellation_token
  -> if cancelled:
      close Runner
      run_cancelled
```

这样可以避免 Engine 在已经收到取消后继续读取 stream、继续进入工具执行或继续下一轮 Runner，同时不会丢掉已经由 Runner 产出的可观察事实。

例如：

```text
RunnerEvent.content_delta
  -> EngineEvent.content_delta
  -> observe cancellation_token

RunnerEvent.reasoning_delta
  -> EngineEvent.reasoning_delta
  -> observe cancellation_token
```

迟到取消可以在这些事件之后让 run 收口为 `run_cancelled`，但不能吞掉已经收到并提升的 delta。

ToolExecutor.execute 的建议规则：

```text
ToolExecutionContext(cancellation_token)
  -> ToolExecutor.execute(request)
      -> tool can observe cancellation_token
  -> Engine handles returned outcome by outcome boundary
```

Engine 必须把 `cancellation_token` 传入 `ToolExecutionContext`，允许工具在执行过程中主动检查取消。

## Final Answer 边界

`final_answer` 应被视为最终回答 commit boundary。

建议规则：

```text
cancel wins before final candidate is accepted
final_answer wins after final candidate is accepted
```

也就是说，如果 Runner stream 尚未完成、Engine 尚未接受 final candidate，取消可以收口为 `run_cancelled`。但如果 Engine 已经判定当前 iteration 得到了可接受的 final content，就不应在最终提交前再用迟到的取消把它改写成 `run_cancelled`。

这意味着类似“构造 final terminal 前再统一检查 cancellation token”的实现需要重新评估。取消检查应放在耗时边界和进入下一步工作前，而不是在已经接受 final answer 后抢占 final。

## Tool Awaiting 边界

`ToolAwaitingOutcome` 不是普通中间态，而是工具把外部长事务事实交给 Engine 的 commit boundary。

如果 `ToolExecutor.execute` 尚未返回，取消可以通过两条路径生效：

```text
tool observes cancellation_token
  -> stop before starting external job
  -> Engine receives cancellation path

Engine wait boundary observes cancellation
  -> stop waiting
  -> run_cancelled
```

如果 `ToolExecutor.execute` 已经返回 `ToolAwaitingOutcome(await_spec, snapshot)`，说明工具已经进入“外部长事务已开始 / 已交出恢复事实”的状态。此时 Engine 不应因为返回后 token 已取消而吞掉 awaiting 事实。

建议规则：

```text
ToolExecutor.execute returns ToolAwaitingOutcome
  -> append tool_awaiting
  -> close Runner
  -> append run_suspended
```

取消要抢在 awaiting 前，只能在 `ToolAwaitingOutcome` 返回前生效。工具如果已经启动外部长事务并需要上层接管，应返回 `ToolAwaitingOutcome`，而不是只抛异常，否则 `await_spec` / `snapshot` 会丢失，外部长事务可能变成孤立任务。

## Completed / Failed Tool Outcome 边界

普通工具 completed / failed outcome 不是 run terminal，但它是已经完成的工具事实。Engine 不应在 outcome 返回后因为迟到取消而丢掉该工具结果。

建议规则是：

```text
ToolExecutor.execute returns completed / failed
  -> tool_result_accepted
  -> inject ToolMessage into run-local messages / accepted context
  -> observe cancellation_token
  -> if cancelled: run_cancelled
  -> otherwise: continue / fallback
```

原因是 caller 后续 resume 需要知道“工具已经返回了什么”。如果直接收口 `run_cancelled`，这一轮工具事实会丢失。

这里的取消只阻止下一次 Runner 调用，不覆盖已经返回的 completed / failed tool outcome。上层可通过 `tool_result_accepted` 事件和 run-local accepted context 重构新的 `AgentRunRequest.messages`。

## Force Answer 边界

`FORCE_ANSWER` 是一次真实 Runner 调用，不是简单错误映射。

建议规则：

```text
before FORCE_ANSWER Runner call
  -> observe cancellation_token

FORCE_ANSWER Runner returns final candidate
  -> final_answer commit boundary
```

因此进入 force-answer 前应检查取消；但 force-answer 已经得到可接受 final content 后，应按 final answer commit boundary 处理，不应再被迟到取消覆盖。

## Resume 统一机制

Engine 层不区分两套 resume 机制。无论上一 run 是 `run_suspended` 还是 `run_cancelled`，恢复都应表现为调用方构造新的 `AgentRunRequest`：

```text
previous run reached terminal
  -> caller builds new AgentRunRequest(messages=...)
  -> Engine treats it as a new run
```

Engine 不复用旧 Agent，不复用旧 Runner，不持有 hidden continuation state，不读取 Host wait record，也不读取 cancel registry。

差别只在恢复输入来源：

```text
suspend -> resume
  -> caller uses await_spec / snapshot
  -> waits external job terminal
  -> builds messages with tool result / recovery input

cancel -> resume
  -> caller uses already accepted transcript / partial facts / user intent
  -> builds messages with recovery input or revised user request
```

因此可统一表述为：

> Resume in Engine is always a new run with explicit messages. `suspended` 和 `cancelled` 只是上一 run 的不同 terminal reason；恢复动作都由调用方构造新的 `AgentRunRequest` 完成。

## 实现落地检查项

- 检查 Engine 实现是否需要调整 `_make_final_or_cancelled_after_close` 这类“terminal 构造前取消抢占”的 helper，使其符合 final commit boundary。
- 检查 `ToolAwaitingOutcome` 返回后是否仍存在 `tool_awaiting` 与 `run_suspended` 之间插入取消的实现路径；定稿规则应禁止迟到取消吞掉 awaiting / suspended。
- 检查 `WaitCancelled` 与工具内部主动取消异常的映射，避免工具已经启动外部长事务但没有机会返回 `ToolAwaitingOutcome`。
- 用测试明确锁定：
  - final candidate accepted 后 late cancel 不覆盖 final。
  - awaiting returned 后 late cancel 不覆盖 suspended。
  - RunnerEvent content / reasoning delta 已收到后先 emit 对应 EngineEvent，late cancel 只阻止继续读取 stream 或进入下一步。
  - completed / failed tool outcome returned 后先接受工具结果并注入 ToolMessage，late cancel 只阻止下一轮 Runner。
