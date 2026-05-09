# P8-S3 Fix Re-Review：AttemptSupervisor Lease Context 与 Renew Loop

## 结论：有条件通过

原 review 五个 finding（High-1 / High-2 / Medium-1 / Low-1 / Low-2）均已按建议修复到位，核心语义闭环：owner-lost 信号通过 `_next_engine_event_or_lose_owner` race 阻止 late Engine event 进入 EventLog；storage error 映射为独立 `STORAGE_ERROR` 而非伪装 fencing；diagnostic close 走 owner_token_hash + fencing_token CAS，CAS miss 不 fallback 到 legacy update。

有一个非阻断 finding（Low-3）：测试只覆盖 `_next_engine_event_or_lose_owner` helper 级 race，未覆盖 `_run_to_store` 端到端 `_handle_owner_lost` → Host failure terminal → EventLog 不含 stale fact 路径。helper 级覆盖已守住核心不变量，可接受进入 P8-S4，建议 P8-S4 补端到端集成测试。

## Scope

- Mode: P8-S3 fix re-review
- Branch: `migration/host-p8-attempt-lease-recovery`
- Base: 原 review `docs/host/phase8-s3-code-review.md` 的 High-1 / High-2 / Medium-1 / Low-1 / Low-2
- Re-reviewed changes: 当前 workspace 未提交改动（相对 `29dee8b`）

## 原 Finding 复审

### High-1：renew FENCED 后没有让 harness 停止 Engine 流或阻止后续 EventLog append [已修复]

**修复验证**：

1. **typed owner-lost signal**：`_LeaseSession` 持有 `owner_lost_event: asyncio.Event` 与 `loss_reason: AttemptOwnerLossReason | None`。`_mark_owner_lost` 在 FENCED / STORAGE_ERROR 时置位 `loss_reason` 并 set `owner_lost_event`。`wait_owner_lost` 暴露 typed reason。确认。

2. **harness race**：`_next_engine_event_or_lose_owner` ([_run_harness.py:783-855](dayu/host/_run_harness.py#L783-L855)) 先做无锁 `is_owner_active` 快照检查，已失活直接抛 `_OwnerLostDuringEngineWait`；否则构造 `next_event_task` 与 `owner_lost_task`，通过 `asyncio.wait(FIRST_COMPLETED)` race。owner_lost 先到或两者同时就绪时均抛 `_OwnerLostDuringEngineWait`。确认。

3. **停止 append**：`_run_to_store` ([_run_harness.py:586-603](dayu/host/_run_harness.py#L586-L603)) 捕获 `_OwnerLostDuringEngineWait` 后调用 `_handle_owner_lost`，后者先执行 `_finish_attempt_if_durable`（owner-aware CAS close），再追加 Host-owned failure terminal，然后 `return`。`current_active_attempt` 被置 `None`，finally 块不重复收口。engine iterator 在 `_close_engine_events_if_supported` 中关闭。后续不再 append。确认。

4. **测试覆盖**：`test_owner_lost_during_engine_wait_stops_late_event_append` ([test_phase8_attempt_supervisor.py:877-973](tests/host/test_phase8_attempt_supervisor.py#L877-L973)) 使用 `_ManualLossSupervisor` fake，在 `_next_engine_event_or_lose_owner` 层面验证 race 后 `late_event_appended == []`。

**finding**：测试只覆盖 helper 级 `_next_engine_event_or_lose_owner`，未走 `_run_to_store` → proxy stream → owner lost → Host failure terminal → EventLog 不含 stale fact 的端到端路径。核心 race 不变量已被 helper 级测试守住，不阻断 P8-S4。见 Low-3。

### High-2：renew storage error 会作为后台 task 异常静默结束，session 仍可能被判定 active [已修复]

**修复验证**：

1. **独立 `STORAGE_ERROR` reason**：`_renew_loop` ([_attempt_supervisor.py:508-526](dayu/host/_attempt_supervisor.py#L508-L526)) 在 `except Exception as exc` 分支调用 `_mark_owner_lost(loss_reason=AttemptOwnerLossReason.STORAGE_ERROR, fence_reason=None)`，然后 `return`。`AttemptOwnerLossReason.STORAGE_ERROR` 是独立枚举值，不是 FENCED。确认。

2. **renew task 已 done 时读取 exception**：`_stop_session` ([_attempt_supervisor.py:639-660](dayu/host/_attempt_supervisor.py#L639-L660)) 在 `renew_task.done()` 分支调用 `renew_task.exception()`，非 `CancelledError` 时记录 ERROR 日志并 `_mark_owner_lost(STORAGE_ERROR)`。确认。

3. **storage error 后 owner 不再 active**：`is_owner_active` ([_attempt_supervisor.py:170-197](dayu/host/_attempt_supervisor.py#L170-L197)) 检查 `session.loss_reason is not None` 时返回 `False`。`_mark_owner_lost` 只在 `loss_reason is None` 时写入，不会被后续调用覆盖。确认。

4. **日志不泄露 token 明文**：storage error 日志 ([_attempt_supervisor.py:511-520](dayu/host/_attempt_supervisor.py#L511-L520)) 使用 `owner_context.owner_token.masked()`，`type(exc).__name__` 不含 token。`_stop_session` 同理 ([_attempt_supervisor.py:624-633](dayu/host/_attempt_supervisor.py#L624-L633))。确认。

5. **测试覆盖**：`test_renew_storage_error_marks_owner_lost_with_storage_reason` ([test_phase8_attempt_supervisor.py:716-762](tests/host/test_phase8_attempt_supervisor.py#L716-L762)) 使用 `_StorageErrorLeaseStore` fake，断言 `is_owner_active` 为 `False`、`wait_owner_lost` 返回 `STORAGE_ERROR`、日志含 masked token 不含明文。确认。

### Medium-1：diagnostic close 仍走非 owner-aware legacy update，且先丢弃 owner session 再写终态 [已修复]

**修复验证**：

1. **CAS 更新**：`close_attempt_with_diagnostic_state` ([_attempt_supervisor.py:350-379](dayu/host/_attempt_supervisor.py#L350-L379)) 在 `BEGIN IMMEDIATE` 事务内调用 `lease_store.update_state_owner_aware`，WHERE 包含 `owner_token_hash` + `fencing_token` + `state='running'`。CAS miss 返回 `False`，记录 WARNING 日志，不 fallback 到 legacy update。确认。

2. **不走 legacy update**：`_finish_attempt_if_durable` ([_run_harness.py:1537-1558](dayu/host/_run_harness.py#L1537-L1558)) 在 supervisor 路径调用 `close_attempt_with_diagnostic_state` 后 `lease_exit_stack.aclose()`，然后 `return`。不进入下方 legacy `attempt_state_store.update_state` 分支。确认。

3. **CAS miss 不 fallback**：`close_attempt_with_diagnostic_state` 返回 `False` 时调用方不重试、不退化。确认。

4. **terminal_event_position 仍为 None**：`_finish_attempt_if_durable` 调用时传 `terminal_event_position=None`，符合 S3 边界。确认。

5. **测试覆盖**：`test_diagnostic_close_owner_cas_miss_returns_false` ([test_phase8_attempt_supervisor.py:765-799](tests/host/test_phase8_attempt_supervisor.py#L765-L799)) 直接把 attempt 状态改为 STALE 让 CAS miss，断言返回 `False`、行仍是 STALE。`test_local_run_harness_thin_delegates_to_supervisor` ([test_phase8_attempt_supervisor.py:437-538](tests/host/test_phase8_attempt_supervisor.py#L437-L538)) 验证 `_finish_attempt_if_durable` 通过 `_RecordingSupervisor.close_attempt_with_diagnostic_state` 完成 owner-aware 收口。确认。

### Low-1：新增测试 stub 依赖 `object` + `type: ignore[arg-type]` 掩盖内部协议缺口 [已修复]

**修复验证**：

- `_FencingLeaseStore` ([test_phase8_attempt_supervisor.py:184-265](tests/host/test_phase8_attempt_supervisor.py#L184-L265))：显式同签名方法 `acquire_new_attempt` / `renew` / `verify_owner` / `update_state_owner_aware`，无 `**kwargs: object`，无 `type: ignore[arg-type]`。确认。
- `_BusyStore` ([test_phase8_attempt_supervisor.py:541-611](tests/host/test_phase8_attempt_supervisor.py#L541-L611))：同上。确认。
- `_StorageErrorLeaseStore` ([test_phase8_attempt_supervisor.py:642-713](tests/host/test_phase8_attempt_supervisor.py#L642-L713))：同上。确认。
- `_RecordingSupervisor` ([test_phase8_attempt_supervisor.py:369-435](tests/host/test_phase8_attempt_supervisor.py#L369-L435))：显式 `lease_context` / `is_owner_active` / `wait_owner_lost` / `close_attempt_with_diagnostic_state` 方法，无 `type: ignore`。确认。
- `_ManualLossSupervisor` ([test_phase8_attempt_supervisor.py:802-875](tests/host/test_phase8_attempt_supervisor.py#L802-L875))：同上。确认。
- `cast(AttemptSupervisor, recording)` 在注入时使用：这是 protocol-compatible fake 注入的正确方式，不掩盖协议缺口。确认。

### Low-2：README 触发同步未完成 [已修复]

**修复验证**：

- `dayu/host/README.md` 第 326-337 行：准确描述 P8-S3 已落地的 owner lease acquire / renew / owner-aware diagnostic close / owner-lost signal / STORAGE_ERROR 路径；明确标注 terminal event 原子写入 / ToolRuntime CAS append / recovery scan / 多进程未落地及归属。确认。
- `tests/README.md` 第 172-181 行：覆盖 P8-S3 测试条目，描述与测试用例一致。确认。

## S3 边界确认

| 边界检查 | 结论 |
|---|---|
| P8-S4 terminal append + close 同事务未提前实现 | 通过。`terminal_event_position` 传 `None`，无原子写入逻辑。 |
| P8-S5 ToolRuntime / EventLog CAS append 未提前实现 | 通过。`event_store.append(...)` 仍为直接调用，无 verify_owner CAS。 |
| owner-lost 后 append Host failure terminal 符合 S3 语义 | 通过。`_handle_owner_lost` 写 `RUN_FAILED(error_code=attempt_lease_lost)` 是 Host run 收口事件，不写 stale Engine attempt facts。Engine iterator 被关闭，后续 Engine event 不进入 EventLog。 |
| recovery scan 未提前实现 | 通过。无 `_recovery_scan` 逻辑。 |
| multiprocessing 未提前实现 | 通过。无多进程逻辑。 |

## 新发现 Finding

### Low-3：owner-lost 路径缺少 `_run_to_store` 端到端集成测试

- **证据路径**：`tests/host/test_phase8_attempt_supervisor.py:877-973`
- **语义影响**：当前 `test_owner_lost_during_engine_wait_stops_late_event_append` 只覆盖 `_next_engine_event_or_lose_owner` helper 级 race，断言 `late_event_appended == []`。未覆盖 `_run_to_store` 主循环：proxy stream → owner lost → `_handle_owner_lost` → Host failure terminal append → EventLog 不含 stale Engine fact → `_finish_attempt_if_durable` owner-aware CAS close 的端到端路径。
- **是否阻断 P8-S4**：否。helper 级测试已守住核心 race 不变量（owner-lost 先到时不拉取 / append late event）。`_handle_owner_lost` 与 `_finish_attempt_if_durable` 已由 `test_local_run_harness_thin_delegates_to_supervisor` 覆盖。端到端集成测试是防御性补充，不改变已验证的语义。
- **Owner**：P8-S4 集成测试，与 terminal event 原子写入测试一起补。

## 验证结果

| 命令 | 结果 |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py -q` | 10 passed |
| `source .venv/bin/activate && pytest tests/host/test_phase6_durable_harness_integration.py tests/host/test_phase6_review_fixes.py -q` | 16 passed |
| `source .venv/bin/activate && pytest tests/host -q` | 256 passed |
| `source .venv/bin/activate && python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过，无 whitespace 问题 |

## 残余风险

| 风险 / 未覆盖项 | Owner | 说明 |
|---|---|---|
| Terminal event append + attempt close 同事务原子写入 | P8-S4 | S3 未实现，`terminal_event_position` 传 `None`，符合非目标。P8-S4 必须覆盖。 |
| EventLog / ToolRuntime attempt-scoped append 的 `verify_owner` CAS | P8-S5 | 当前仍有 direct `event_store.append(...)`，符合 S3 非目标。P8-S5 必须覆盖 Engine-sourced event、context facts、ToolRuntime facts。 |
| Recovery scan / `MARK_RECOVERING_AND_CREATE_ATTEMPT` | P8-S6 | 当前未实现，符合 S3 非目标。 |
| Deterministic multiprocessing stress | P8-S7 / issue #38 | 当前未实现，符合 S3 非目标。 |
| owner-lost 端到端集成测试 | P8-S4 | Low-3：`_run_to_store` 端到端路径未覆盖，helper 级 race 已守住核心不变量。P8-S4 与 terminal event 原子写入测试一起补。 |
| fake supervisor 的稳定 stub 协议 | P16 / issue #28 | 当前 fake 使用 `cast(AttemptSupervisor, ...)` 注入，可接受；P16 interface freeze 时引入 `AttemptSupervisorPort` 协议。 |
