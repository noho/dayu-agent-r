# P8-S3 Code Review：AttemptSupervisor Lease Context 与 Renew Loop

## 结论：不通过

当前实现已完成 `DurableHarnessConfig.attempt_lease_config` 装配入口、`AttemptSupervisor.lease_context(...)` acquire + renew loop 基础、owner token masked logging，以及 `LocalRunHarness` 获取 `AttemptOwnerContext` 的薄委托入口；public `StartRunRequest` 未暴露 TTL，store 仍只接收 `lease_expires_at`。

但 P8-S3 的关键可见语义尚未闭环：renew 失败后没有通知 harness 停止 Engine 流或阻止后续 append；renew storage error 也没有按 plan 收口。这会让丢失 lease 的旧 owner 继续向 EventLog 写事实，直接破坏 P8-S4/P8-S5 的前置假设，因此本 slice 不应进入 P8-S4。

## Scope

- Mode: current uncommitted changes review
- Branch: `migration/host-p8-attempt-lease-recovery`
- Base: `HEAD=29dee8b host: make observer sinks async`
- Reviewed changes: uncommitted P8-S3 workspace changes
- Output file: `docs/host/phase8-s3-code-review.md`

## Findings

### High-1：renew FENCED 后没有让 harness 停止 Engine 流或阻止后续 EventLog append [已修复]

- **证据路径**：`docs/host/phase8-plan.md:551`、`docs/host/phase8-plan.md:709`、`docs/host/phase8-plan.md:718`、`dayu/host/_attempt_supervisor.py:383-401`、`dayu/host/_run_harness.py:541-608`、`dayu/host/_run_harness.py:623-627`、`tests/host/test_phase8_attempt_supervisor.py:197-226`
- **语义影响**：P8-S3 plan 明确写了“renew 失败后阻止后续 append 并取消 / 收口当前 engine run”，完成信号也包含“renew rowcount=0 后停止 append”。当前 `_renew_loop` 在 `AttemptLeaseDecision.FENCED / TERMINAL / BUSY` 后只设置 `session.fenced=True` 并返回；`LocalRunHarness._run_to_store` 在 `anext(engine_events)` 之后仍直接 `event_store.append(...)`，没有读取 `attempt_supervisor.is_owner_active(...)`，也没有读取其它 fence state / loss signal 来取消或收口当前 engine run。现有测试只断言 `is_owner_active()` 变为 `False`，没有覆盖 fenced 后 Engine 继续产出事件时是否还能 append。
- **是否阻断 P8-S4**：是。P8-S4 要把 terminal append + close 原子化，但如果 P8-S3 已允许旧 owner 在 lease 丢失后继续 append 普通 Engine event，S4 的 terminal close CAS 只能拦住末尾终态，不能修复前面已经写入的 stale facts。
- **建议修复方式**：在 Host 层把 renew-loss 变成可等待的强类型信号，不把 owner/lease 语义泄漏给 Engine。`AttemptSupervisor` 可提供 `wait_owner_lost(owner_context)` 或把 `_ActiveAttempt` 持有一个 lease-loss future；`LocalRunHarness` 在拉取 Engine event 时与该 signal race，一旦 FENCED/TERMINAL/BUSY/lease expired，关闭 Engine iterator，停止后续 append，并按 P8-S3 诊断 close 路径把 attempt 收口为 `STALE` / `LOST` 或 storage failure 语义。测试需要模拟 renew fenced 后 proxy 继续产出事件，断言 late event 不进入 EventLog。
- **关于 S5 CAS append 的边界判断**：S5 才做 `AttemptScopedRunEventAppender` / `verify_owner` CAS append 是合理边界；但这不等于 S3 可以不停止 append。S3 的职责是运行时层面在 lease loss 后让 harness 停止继续消费 / append；S5 的职责是在事务写入层面做最终 CAS 防线。若实施方坚持把“停止 append”整体后移到 S5，则 `phase8-plan.md:709` 和 `phase8-plan.md:718` 必须降级修正，但这会削弱 P8-S4/P8-S5 的前置安全性，不建议降级。

### High-2：renew storage error 会作为后台 task 异常静默结束，session 仍可能被判定 active [已修复]

- **证据路径**：`docs/host/phase8-plan.md:552`、`dayu/host/_attempt_supervisor.py:352-405`、`dayu/host/_attempt_supervisor.py:421-440`
- **语义影响**：P8 plan 明确写“storage error 不是 fencing；supervisor 应停止 renew loop、停止后续 append，并把 run/attempt 以 Host storage failure 路径收口；如果 storage 已不可写，至少记录安全日志并让后台 task 失败暴露”。当前 `_renew_loop` 的 docstring 说非取消异常会记录 error、置 `fenced` 并通过 task 暴露；实际代码只有 `except asyncio.CancelledError`，`lease_store.renew(...)` 或 `storage.transaction()` 抛 storage error 时会直接让 task failed，`session.fenced` 不会置位。更糟的是 `_stop_session` 只有在 `renew_task is not None and not renew_task.done()` 时才 await task；如果 renew task 已经异常结束，退出 context 时不会读取 `task.exception()`，也不会记录 `host.attempt.lease_renew_task_failed`。此时 `is_owner_active()` 在 context 仍打开期间会继续返回 `True`，harness 也没有其它 storage-failure state 可读。
- **是否阻断 P8-S4**：是。Plan §9 明确 storage error 不是 fencing，但 supervisor 必须停止 renew loop、停止后续 append，并走 Host storage failure 收口；当前实现既没有停止 append，也没有可靠暴露后台失败，P8-S4 在此基础上做 terminal close 会继承 silent failure 窗口。
- **建议修复方式**：在 `_renew_loop` 捕获非取消异常，写入 `session.fenced` 或单独的 `storage_failed` typed 状态，设置 loss signal，并记录不含 token 明文的 error 日志；退出路径无论 task 是否已 done 都应检查异常并完成诊断。测试应使用抛异常的 fake lease store，断言 owner inactive、日志 masked、harness 不继续 append，并确认异常不包含 owner token 明文。
- **关于是否置 `session.fenced=True` 的直接结论**：普通异常目前不会置 `session.fenced=True`。但严格语义上 storage error 不应被标为 fencing；可以用独立 `storage_failed` / `lost_reason=STORAGE_ERROR` 状态表达，同时必须让 `is_owner_active()` 或等价 gate 返回不可继续 append。

### Medium-1：diagnostic close 仍走非 owner-aware legacy update，且先丢弃 owner session 再写终态 [已修复]

- **证据路径**：`dayu/host/_run_harness.py:1297-1362`、`dayu/host/_run_state_store.py:245-290`
- **语义影响**：`_finish_attempt_if_durable` 在 supervisor 路径先 `lease_exit_stack.aclose()`，这会从 supervisor `_sessions` 中移除 owner；随后用 `AttemptStateStore.update_state(...)` 直接 `UPDATE host_attempts SET state=... WHERE attempt_id=?`。该 legacy update 没有 `owner_token_hash / fencing_token / lease_expires_at > now` CAS，也不检查 rowcount。P8-S3 可以暂不做 terminal event position 原子写入，但 plan §9 对异常退出的 diagnostic close 仍要求经过 owner fencing；当前路径会在 owner 已失效或行已被未来 recovery 改写时仍可能覆盖状态。
- **是否阻断 P8-S4**：是，作为前置语义阻断。P8-S4 应替换 terminal close 为 fenced 原子 API；但 P8-S3 的异常 / stale 诊断 close 如果继续使用非 owner-aware update，会给 P8-S4 留下另一个未治理关闭通道。
- **建议修复方式**：把 diagnostic close 基础下沉到 `AttemptSupervisor`，至少在同一事务内 `verify_owner(tx, owner_context)` 后再写 `STALE` / `FAILED` / `LOST` 诊断状态；不要先移除 active session 再尝试 DB close。terminal event append + `terminal_event_position` 仍可留给 P8-S4，但 owner fencing 的诊断 close 不应依赖 legacy `AttemptStateStore.update_state`。

### Low-1：新增测试 stub 依赖 `object` + `type: ignore[arg-type]` 掩盖内部协议缺口 [已修复]

- **证据路径**：`tests/host/test_phase8_attempt_supervisor.py:176-194`、`tests/host/test_phase8_attempt_supervisor.py:212-215`、`tests/host/test_phase8_attempt_supervisor.py:355-361`、`tests/host/test_phase8_attempt_supervisor.py:444-465`
- **语义影响**：`_FencingLeaseStore` / `_BusyStore` 使用 `**kwargs: object` 再用 `type: ignore[arg-type]` 转发，`_RecordingSupervisor` 注入 `LocalRunHarness.attempt_supervisor` 也需要 `type: ignore[arg-type]`。这不直接影响生产语义，但说明 harness / supervisor 的 internal seam 目前只有具体类类型，没有稳定测试替身协议；后续 P8-S4/S5 会继续扩展 supervisor API，类型忽略容易把协议漂移藏住。
- **是否阻断 P8-S4**：否，不是本轮主要阻断项。
- **建议修复方式**：短期可把测试 fake 改成显式同签名方法，删除 `object` 和 `type: ignore`；若后续 harness 还需要 fake supervisor，建议在 P16 interface freeze 或 P8 follow-up 引入内部 `Protocol`，例如 `AttemptSupervisorPort`，由 `LocalRunHarness` 依赖 protocol 而非具体 dataclass。
- **Owner**：P16 interface freeze；若 P8-S3 修 High findings 时继续增加 fake，建议一并做 P8-S3 cleanup。

### Low-2：README 触发同步未完成，当前 Host README 仍称 supervisor / renew loop 未接入 [已修复]

- **证据路径**：`dayu/host/README.md:326-328`；本 slice 修改了 `dayu/host/_attempt_supervisor.py`、`dayu/host/_durable_harness.py`、`dayu/host/_run_harness.py` 与 `tests/host/test_phase8_attempt_supervisor.py`
- **语义影响**：AGENTS.md 规定修改 `dayu/host/` 后需检查并更新 `dayu/host/README.md`，修改 `tests/` 后需检查 `tests/README.md`。当前 README 仍写“`LocalRunHarness` 主路径、supervisor、renew loop、recovery scan 与 public lifecycle governance 仍未接入”，但代码已经装配 `AttemptSupervisor` 并在 durable harness 主路径进入 `lease_context`。这会误导下一位实施 / review Agent。
- **是否阻断 P8-S4**：否，不阻断代码修复；但阻断 P8-S3 slice closeout 合规。
- **建议修复方式**：在 High/Medium 修复后同步 `dayu/host/README.md` 的 P8 状态：说明 P8-S3 已接入 durable harness acquire + renew + owner context，terminal 原子 close、ToolRuntime/EventLog fencing、recovery scan、多进程仍未落地；`tests/README.md` 可补充 `test_phase8_attempt_supervisor.py` 的定向运行入口。

## 逐项审查确认

| 审查点 | 结论 |
|---|---|
| `DurableHarnessConfig.attempt_lease_config` 是否为装配入口 | 通过。`DurableHarnessConfig` 新增 `attempt_lease_config`，`build_durable_harness` 用它构造 `AttemptSupervisor`。 |
| public `StartRunRequest` / `start_run` 是否暴露 TTL | 通过。`StartRunRequest` 未新增 TTL 字段。 |
| store 是否仍只接 `lease_expires_at` | 通过。`AttemptLeaseStore.acquire_new_attempt/renew` 仍由调用方传入 `lease_expires_at`。 |
| `lease_context` 是否在事务内 acquire owner | 通过。`_acquire_in_transaction` 使用 `async with storage.transaction()`。 |
| 是否启动 renew loop | 部分通过。loop 启动了，但 lease-loss 没有联动 harness。 |
| 是否正确计算 `lease_expires_at = clock.now() + ttl` | 通过。`_compute_lease_expiry()` 使用注入 clock 与 config ttl。 |
| close / exception 是否可靠停止 renew loop | 部分通过。主动退出会 cancel renew task；已异常结束的 renew task 未可靠记录 / 收口。 |
| FENCED / TERMINAL / BUSY 语义 | 不通过。supervisor 内部标记 fenced，但 harness 仍可继续 append。 |
| storage error 语义 | 不通过。后台 task 异常未转为 typed storage failure 收口。 |
| owner token 明文是否泄漏 | 通过。日志使用 `masked()`，`AttemptFencingError` 不包含 token；未发现 EventLog 写 token。 |
| `LocalRunHarness` 是否薄委托 | 结构上通过。没有新增 lease SQL；但缺少 lease-loss 消费。 |
| legacy `attempt_state_store` 路径是否保留 | 通过。无 supervisor 时仍走 P6 legacy create/update。 |
| `_finish_attempt_if_durable` S3 仍走 legacy update 是否可接受 | 部分接受。terminal position 留给 P8-S4 合理；diagnostic close 无 owner fencing 不满足 P8-S3 语义。 |
| Scope 边界 | 通过。未实现 recovery scan、ToolRuntime facts fencing、multiprocessing；未修改 Engine。 |

## 验证结果

| 命令 | 结果 |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py -q` | 7 passed |
| `source .venv/bin/activate && pytest tests/host/test_phase6_durable_harness_integration.py tests/host/test_phase6_review_fixes.py -q` | 16 passed |
| `source .venv/bin/activate && pytest tests/host -q` | 253 passed |
| `source .venv/bin/activate && python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过，无 whitespace 问题 |

## Open Questions

- 无。当前阻断项都有直接代码路径证据，不依赖推测。

## Residual Risk

| 风险 / 未覆盖项 | Owner | 说明 |
|---|---|---|
| Terminal event append + attempt close 同事务原子写入 | P8-S4 | 当前未实现，符合 S3 非目标；但必须在进入 P8-S4 前先修复本报告 High findings。 |
| EventLog / ToolRuntime attempt-scoped append 的 `verify_owner` CAS | P8-S5 | 当前仍有 direct `event_store.append(...)`，符合 S3 非目标；P8-S5 必须覆盖 Engine-sourced event、context facts、ToolRuntime facts。 |
| Recovery scan / `MARK_RECOVERING_AND_CREATE_ATTEMPT` | P8-S6 | 当前未实现，符合 S3 非目标。 |
| Deterministic multiprocessing stress | P8-S7 / issue #38 | 当前未实现，符合 S3 非目标。 |
| fake supervisor / fake lease store 的稳定 stub 入口 | P16 或 P8 follow-up | 当前测试用 `type: ignore[arg-type]` 可短期接受，但接口冻结前应清理。 |
| README / tests README 同步 | P8-S3 closeout | 修复代码后按 AGENTS.md 触发规则同步，只写已落地事实。 |
