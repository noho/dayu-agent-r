# WU-LIFE-03 Slice 2 Fix - AgentCodex

## 范围

- Gate：Slice 2 fix gate
- 角色：implementation/fix
- 约束：仅处理 controller accepted findings S2-CR-F01 与 S2-CR-F02。
- 未执行 commit 或 push。

## 修复

### S2-CR-F01

- 更新 `dayu/host/recovery.py::_has_accepted_cancel_fact`，对 `event_payload_object(...)` 抛出的 `HostDurableError` 返回 `False`。
- malformed `RUN_CANCELLING` payload material 不再中断 `StartupRecoveryScanner.scan()`。
- 在 `tests/host/test_recovery_scan.py` 增加 `test_scan_malformed_cancelling_payload_uses_orphan_policy`。
- 该测试写入非 object 的 `RUN_CANCELLING` payload，并启用 watchdog defer，验证 recovery 不会把 Run 分类为 `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`，而是回到正常 cancelling orphan closeout 路径。

### S2-CR-F02

- 更新 `dayu/host/dispatch.py::_active_cancel_watchdog_loop`，单次 `tick_active_cancel_watchdog(...)` 的非 cancel 异常会记录为 `dispatch.active_cancel_watchdog.tick_failed`，随后 loop 继续下一轮。
- 保留 scheduler close 场景下 `asyncio.CancelledError` 的透传行为。
- 在 `tests/host/test_dispatch_scheduler.py` 增加 `test_active_cancel_watchdog_loop_continues_after_transient_tick_failure`。
- 该测试使用 scheduler 子类让第一次 watchdog tick 抛 `RuntimeError`、第二次 tick 记录进展，证明后台 loop 不会因一次 transient tick failure 永久退出。

## README 检查

- 已检查 `dayu/host/README.md` 的 Agent 更新约束。
- 已检查 `tests/README.md` 的 README 更新边界。
- 未更新 README，因为本轮只改变内部异常隔离并在既有 Host 测试层补测试；不改变 Host 公共契约、架构、用户工作流、测试层级或测试运行方式。

## 验证

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q
```

结果：`142 passed in 2.48s`

```bash
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q
```

结果：`123 passed in 1.20s`

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
source .venv/bin/activate && git diff --check
```

结果：通过，无输出。

## 剩余风险

- watchdog loop 测试是 loop-level deterministic coverage，使用测试子类而非真实注入 durable storage failure。这是为了隔离 accepted finding 的核心行为：一次 transient 非 cancel tick 异常不能终止后台 loop。
- DS non-blocking notes 未处理。
