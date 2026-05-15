# Full Repository Review Controller Adjudication

## 结论

Controller 裁决：**PR 54 进入 full-repo review accepted-fix gate**。

本轮纳入两份并行全仓 review：

- `docs/reviews/repo-review-20260515-1338.md`
- `docs/reviews/repo-review-20260515-1346.md`

这两份 review 的范围超过 PR 54 Phase 5 本地执行闭环，包含 Engine、Contracts、Runtime、Host、测试覆盖和长期架构债务。Controller 按当前 PR 风险、设计真源、项目硬约束和变更半径裁决：只把可在当前 PR 安全修复、且不会重排 phase 边界的 finding 纳入 accepted-current；其余进入 rejected / deferred / needs-design。

## Accepted Current Fix Items

| ID | 来源 | 裁决 | 修复要求 |
| --- | --- | --- | --- |
| A1 | `1338` F1、`1346` F004/F005 | accepted-blocking | `dayu.runtime.lane` 在 `asyncio.shield(...)` 遇到外层 `CancelledError` 时，必须等待 release task 收口并保持内存状态一致，然后重新抛出 `CancelledError`。`_try_claim_once` 释放已插入但未登记 claim 失败时不得吞掉外层取消语义；release 失败可记录并依赖 TTL 回收。补 runtime lane 取消/释放竞态测试。 |
| A2 | `1346` F003 | accepted-blocking | `HostDispatchScheduler._drain_loop` 不得在空队列二次检查后提前退出造成 wakeup race；应保持后台 drain loop 持续轮询直到 scheduler close，或采用等价不会丢 wakeup 的结构。补 sleep 窗口入队测试。 |
| A3 | `1338` F3 | accepted | `BatchToolExecutionRequest.__post_init__` 必须拒绝重复 `tool_call_id`，契约层提前阻止输入侧非双射。补 contracts 测试。 |
| A4 | `1346` F002 | accepted | `is_retriable` 的 `match RunnerHTTPErrorCode` 必须加 `assert_never` 穷尽守卫。补或更新现有分类测试。 |
| A5 | `1338` F13 | accepted | `ToolCancelledOutcome.__post_init__` 必须拒绝空字符串 / 纯空白 `hint`，避免 `None` 与空文本双重无提示状态。补 contracts 测试。 |
| A6 | `1338` F17 | accepted | 修正 `wait_for_or_cancel` docstring：当前实现会读取 `pending.result()` 并透传 pending 异常。 |
| A7 | `1346` F012 | accepted | `_HostCancellationToken` 显式声明实现 `CancellationToken` Protocol，保留当前行为。 |
| A8 | `1346` F006 | accepted | 抽取 `run_input.py` 与 `engine_ingest.py` 重复的 EventLog payload object / required text helper 为 Host 内部单一 helper，保持层内依赖，不放入 `dayu.runtime`。补或复跑相关测试。 |
| A9 | `1346` F007 | accepted | 抽取 `api.py` 与 `tooling.py` 重复的 Host public string validation helper 为 Host 内部单一 helper，避免重复硬编码。补或复跑 public contracts / tooling 相关测试。 |
| A10 | `1346` F018 | accepted | 修复 `run_input.py` 死导入；若 A8 改为直接复用模块级 reader 则保留有效导入，否则删除。 |

## Rejected With Reason

| 来源 | 裁决 | 理由 |
| --- | --- | --- |
| `1338` F2 executor 内部 `CancelledError` 应转 `ToolCancelledOutcome` | rejected | 当前 Engine 代码与 docstring 明确把未命中 run-level cancellation token 的 executor `CancelledError` 归为工具执行异常，避免把 Python task cancellation 与工具协议级取消混淆。协议级取消应由 ToolExecutor 返回 `ToolCancelledOutcome`，不是抛 `asyncio.CancelledError` 表达。 |
| `1338` F4 idempotency SELECT-then-INSERT 竞态 | rejected-needs-evidence | Host write transaction 当前由 SQLite `BEGIN IMMEDIATE` / transaction runner 串行化；两个 writer 不能在同一 key 上同时完成 SELECT-then-INSERT 窗口。review 未证明现有 transaction 边界会暴露该竞态。 |
| `1338` F8 `_consume_worker_events` 检查 cancellation token | rejected-current / deferred | 该建议等同 active cancel watchdog / post-cancel timeout。P5 设计已明确留给 Phase 11 lifecycle / recovery hardening；当前在 consumer 内简单检查 token 不能打断阻塞中的 `anext(events)`。 |
| `1338` F9 DefaultLocalEngineWorker.cancel no-op | rejected-current | 当前 `local_proxy.py` docstring 已明确 Phase 5 只通过 Host cancellation token 观察取消；`cancel()` 保留 handle 边界且不把 dispatch record / lane token 当 worker truth。 |
| `1346` F013 CANCELLED terminal payload 分支 | rejected-current | `terminal_closeout_in_transaction` 当前已通过 `_validate_terminal_input` 拒绝 CANCELLED terminal event type；active cancel 使用专用 `active_cancel_closeout_in_transaction`，不走该 payload helper。 |

## Deferred / Owner

| 风险 | 裁决 | Owner |
| --- | --- | --- |
| Engine runner injection / `AsyncOpenAIRunner` 硬编码 | needs-design | 后续 Engine composition / provider abstraction phase；不能在 PR 54 临时扩展 `AgentRunRequest` 公共 contract。 |
| `_make_final_after_close` 命名 / close 窗口 | non-blocking | 后续 Engine cleanup。当前 `run_messages()` finally 仍保证关闭。 |
| HTTP error diagnostic 字段丢失 | non-blocking | 后续 Engine observability / contract refinement。 |
| lane heartbeat 单 lane 错误全局关闭 controller | needs-design | 后续 runtime lane design refinement；当前全局 close 是保守 fail-closed 语义。 |
| God module / God class | non-blocking | 后续 architecture cleanup；不得在 PR 54 大规模拆分。 |
| engine/contracts 与 reasoning_protocol 测试覆盖缺口 | non-blocking | 后续 test hardening；当前只接受 A3/A5 的契约测试。 |
| `_is_sse_response` 未知 Content-Type fallback | needs-evidence | 后续 runner provider compatibility review。 |
| non-stream parser dict 查表 | non-blocking | 后续 parser exhaustive cleanup。 |
| `_make_tool_timeout_terminal_with_close` 取消竞态 | non-blocking | 后续 Engine cancellation precision cleanup。 |
| unknown RunnerEvent 无日志、filelock marker 恢复静默、log import side effect、schema DDL 事务、EventLogStore DI、engine_ingest dead code | non-blocking | 后续 observability / cleanup。 |
| RunnerEvent public export、engine `__init__` re-export、aiohttp `response.release()` 同步性、ToolResultFailure 非空、EngineEventType completeness | needs-design / needs-evidence | 后续 contract/export review。 |

## 当前 Gate

进入 full-repo review accepted-fix gate。修复完成后必须：

1. 运行受影响 tests：runtime lane、contracts tool call/outcome、engine runner classifier、host dispatch、host public/tooling/run_input/engine_ingest。
2. 运行 `pytest tests/host tests/runtime tests/contracts tests/engine -q`。
3. 运行 `python -m pyright dayu/ tests/ utils/`。
4. 按触发规则同步 README。
5. 写 fix artifact，然后由至少两名 review Agent 做 re-review。
6. Controller final adjudication 后回写 `docs/host/implementation-control.md` 并推送 PR 54。
