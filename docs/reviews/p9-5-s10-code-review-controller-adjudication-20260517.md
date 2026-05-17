# P9.5 S10 Code Review Controller Adjudication

日期：2026-05-17
总控 Agent：AgentController

## 审查对象

- Implementation artifact：`docs/reviews/p9-5-s10-dispatch-runinput-non-recovery-cleanup-implementation-20260517.md`
- AgentMiMo review：`docs/reviews/p9-5-s10-code-review-mimo-20260517.md`
- AgentDS review：`docs/reviews/p9-5-s10-code-review-ds-20260517.md`
- 当前未提交 S10 diff：
  - `dayu/host/dispatch.py`
  - `dayu/host/waiting.py`
  - `dayu/host/README.md`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_wait_cancel_late_result.py`

## 设计真源裁决

S10 的动机成立。`docs/host/design.md` 明确 lane 只表达 runtime capacity claim，不是 Host truth、lease、fencing token 或 Attempt owner；Host dispatch 在 worker side effect 前必须重新检查 durable precondition。当前实现通过 targeted tests 证明 lane acquire 后的 cancel race 会释放 lane token、跳过 worker 调用，并保持 durable state 由 Host 状态机收口。

`resolve_wait` 的设计真源要求成功等待结果才创建 resume Attempt，并由 common pipeline 写入 canonical facts。late rejection 只应保留 diagnostic / public rejection，不应创建 canonical tool fact、推进 Run 或创建 Attempt。当前实现把 `_LateRejectResult` 分支放到 projection catch-up 之前，消除了 rejection path 的冗余 catch-up，未改变 first-committer-wins、wait cancel / resolve 竞态或 public error code。

本 slice 没有引入 Phase 11 recovery、RECOVERING dispatch、startup recovery scan、orphan proof、RemoteProxy 或状态机语义变更。

## Review Finding 裁决

| 来源 | Finding | 裁决 | 理由 |
|---|---|---|---|
| AgentMiMo | `_drain_loop` CancelledError 日志区分依赖 `self._closed` 时序 | rejected-with-reason | 正常 close 路径先设置 `_closed` 再 cancel drain task，日志区分符合当前 lifecycle；外部 cancel 仅影响诊断文本，不改变语义。 |
| AgentMiMo | `_drain_loop` 异常退出后不重新启动 | deferred-with-owner | S10 目标是 logs-only observability。后台重启、watchdog 或 recovery startup scan 属于 Phase 11 lifecycle / recovery owner；当前实现保留 residual risk，不在本 slice 扩 scope。 |
| AgentMiMo | late rejection 不触发 projection catch-up 后的 read model 即时性 | accepted-as-non-blocking | 这是本 slice 的有意行为。late rejection 已提交 diagnostic 但不创建 canonical resume fact；调用方若需要 projection 刷新，应依赖后续成功 command 或显式 repair / catch-up。 |
| AgentDS | F1 `_drain_loop` 异常退出后无自动重启 | deferred-with-owner | 同 MiMo 对应 finding，归 Phase 11 lifecycle / recovery owner；不阻塞 S10。 |
| AgentDS | F2 `LaneAcquireCancelled + _closed` 无独立 closeout 测试 | rejected-with-reason | close 不是 cancel，进程退出路径不应写 durable terminal closeout；当前 S10 不实现 startup recovery scan。该行为符合设计边界。 |
| AgentDS | F3 pre-accept recheck 与 `_start_worker` 之间存在 TOCTOU 窗口 | rejected-with-reason | 最终 `_accept_worker_running` transaction CAS 是 Host truth 防线。窗口只可能浪费 pre-call work，不会越过 durable acceptance。 |
| AgentDS | F4 `_consume_worker_events` finally 单点清理路径 | accepted-as-non-issue | reviewer 确认证据充分，非问题。 |
| AgentDS | F5 `clear_run` 在 durable write transaction 外执行 | rejected-with-reason | duplicate governance registry 是 run-local in-memory runtime structure，不是 durable truth；当前 `clear_run` 不参与 EventLog / state CAS。 |
| AgentDS | F6 `_reject_late_result` 内 `HostApiError` 传播路径不同 | rejected-with-reason | 最终 public error code 与幂等语义正确；把内部 late rejection conflict 统一转为 `HostApiError` 是当前 `_reject_late_result` 的局部职责。 |
| AgentDS | F7 测试 helper 重复 | deferred-with-owner | broader test hardening 只在具体 owner 有真实收益时处理；不阻塞 S10。 |
| AgentDS | F8 stale `session_id` / `run_id` 未专项测试 | rejected-with-reason | S10 目标是 optimistic dispatch snapshot identity 中当前缺口字段；现有路径已 fail closed。错误消息精度不足不影响本 slice 的状态机目标。 |
| AgentDS | F9 只覆盖 `WAIT_CANCELLED` late rejection reason | accepted-as-non-blocking | `_reject_late_result` 是共享实现，当前 targeted test 覆盖核心 no catch-up / no resume / no duplicate diagnostic 语义；其它 reason 可在后续 wait-specific hardening 中补充。 |
| AgentDS | F10 README 未列内部常量 / event class | rejected-with-reason | Host README 是开发手册，不应变成内部常量索引；当前文档已准确描述稳定行为。 |

## 验证

Controller 复跑验证：

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py`：65 passed。
- `source .venv/bin/activate && pytest tests/host`：532 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`：0 errors / 0 warnings / 0 informations。
- `source .venv/bin/activate && python -m pyright dayu tests`：0 errors / 0 warnings / 0 informations。
- `git diff --check`：clean。

## 结论

P9.5 S10 code review gate passed。两份独立 review 均无 blocking / medium finding；controller 不接受任何需要 S10 fix pass 的 finding。S10 可进入 accepted slice commit。

剩余风险均有 owner：

- `_drain_loop` 异常退出后的重启 / watchdog / recovery startup scan：Phase 11 lifecycle / recovery owner。
- late rejection 后 projection 不即时 catch-up：当前 S10 accepted behavior；需要即时 read model 的调用方通过后续成功 command 或显式 repair / catch-up 处理。
- 测试 helper 复用与其它 late rejection reason 的更细专项测试：后续 wait/test hardening owner，非当前 blocker。
