# Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-engine-next`
- Base: `main` (selected base ref)
- Output file: `docs/reviews/wu-life-03-slice2-code-review-mimo.md`
- Included scope: Slice 2 当前未提交 workspace 变更（`git diff` unstaged），覆盖以下 11 个文件：
  - `dayu/host/api.py` — `OpenHostOptions` / `HostLocalExecutionOptions` 新增 `active_cancel_timeout_seconds` 字段及校验
  - `dayu/host/command.py` — `ActiveCancelWatchdogWakeupPort` Protocol、`HostCommandHandle` watchdog wakeup 注入、cancel commit 唤醒
  - `dayu/host/dispatch.py` — `HostDispatchScheduler` watchdog tick/loop/wakeup、candidate scan、projection catch-up、queue promotion
  - `dayu/host/open_host.py` — startup ordering（watchdog tick → recovery scan）、`defer_accepted_cancel_to_watchdog` 注入
  - `dayu/host/recovery.py` — `StartupRecoveryScanner.defer_accepted_cancel_to_watchdog` 字段、`_has_accepted_cancel_fact`、`DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG` decision
  - `dayu/host/README.md` — cancel / dispatch / startup recovery 章节更新
  - `docs/host/design.md` — cancel 章节 watchdog timeout 语义与 startup recovery ordering 更新
  - `docs/host/issues-implementation-control.md` — gate / status 更新
  - `tests/host/test_active_cancel_dispatch.py` — watchdog timeout、noop、multi-run、promotion、replay、scheduler close 测试
  - `tests/host/test_open_host_runtime.py` — public watch / reopen / reopen-before-timeout 测试
  - `tests/host/test_recovery_scan.py` — watchdog-enabled deferral、watchdog-disabled orphan policy 测试
- Excluded scope: Slice 1 已提交变更（`ef2d3644`）、未变更文件
- Parallel review coverage: 无

## Findings

### 1-未修复-中-`_has_accepted_cancel_fact` 未处理 malformed `RUN_CANCELLING` payload 异常

- **入口/函数**: `dayu/host/recovery.py::_has_accepted_cancel_fact(transaction, event_log_store, run_id)`
- **文件(行号)**: `dayu/host/recovery.py:674-679`
- **输入场景**: Host startup recovery scan 扫描到一个 `CANCELLING` Run，该 Run 的 `RUN_CANCELLING` EventLog event payload 为 malformed（例如非 JSON 对象、字段类型错误）。
- **实际分支**: `event_payload_object(transaction, cancelling, payload_label=...)` 对 malformed payload 抛出 `HostDurableError`，`_has_accepted_cancel_fact` 未 catch 该异常。
- **预期行为**: 与 `dayu/host/dispatch.py::_read_linked_cancel_requested_event` 一致——malformed payload 时 gracefully 返回 `False`，让 recovery 继续按默认 orphan 策略处理，而不是 crash 整个 startup scan。
- **实际行为**: `HostDurableError` 向上冒泡穿过 `_classify_run` → `scan` → `operation`，导致整个 startup recovery scan 事务失败，所有后续 Run 的分类被跳过。
- **直接证据**:
  - `recovery.py:674-679`: `event_payload_object(...)` 调用未包裹 try/except。
  - `dispatch.py:4592-4597`: 同功能的 `_read_linked_cancel_requested_event` 正确包裹了 `try: ... except HostDurableError: return None`。
- **影响**: malformed `RUN_CANCELLING` payload 会导致 startup recovery scan 全局失败，所有非终态 Run（包括 `RUNNING`、`RECOVERING`、`ACCEPTED`、`QUEUED`）的 recovery 分类全部被阻断。Host 重启后无法恢复任何 orphan Run。
- **建议改法和验证点**: 在 `_has_accepted_cancel_fact` 中将 `event_payload_object(...)` 调用包裹在 `try: ... except HostDurableError: return False`，与 `_read_linked_cancel_requested_event` 行为一致。补充测试用例：seed 一个 `CANCELLING` Run 带 malformed `RUN_CANCELLING` payload，验证 recovery scan 不 crash 且该 Run 走默认 orphan 策略。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中——生产中 malformed payload 概率低，但一旦发生会阻断整个 startup recovery。

### 2-未修复-低-watchdog loop 异常退出后无自动重启机制

- **入口/函数**: `dayu/host/dispatch.py::_active_cancel_watchdog_loop()`
- **文件(行号)**: `dayu/host/dispatch.py:2561-2609`
- **输入场景**: watchdog tick 执行过程中 `active_cancel_timeout_closeout_in_transaction` 或 `catch_up_projection_best_effort` 抛出非 `CancelledError` 异常。
- **实际分支**: `_active_cancel_watchdog_loop` 的 `except Exception` 分支记录 error log 后返回，后台 task 进入 done 状态。
- **预期行为**: watchdog 作为 Host 生命周期关键组件，异常退出后应有重启或至少明确的运维信号。
- **实际行为**: loop 静默退出（仅 error log），后续只有在新的 `wake_active_cancel_watchdog()` 调用时才通过 `_start_active_cancel_watchdog_loop` 重启。如果没有新的 cancel 请求到来，periodic fallback scan 永久丢失，已有的 `CANCELLING` Run 只能等下次 Host reopen。
- **直接证据**: `dispatch.py:2600-2609`: `except Exception as exc:` 分支只 log 不 restart；`_start_active_cancel_watchdog_loop` 只在 `wake_active_cancel_watchdog` 时被调用。
- **影响**: watchdog 一次异常后永久停止 periodic fallback scan。已有的 `CANCELLING` Run 如果没有新的 cancel 请求触发 wakeup，将悬挂到下次 Host reopen。这不违反 first-committer-wins 安全性，但违反 plan 中 "periodic fallback scan 覆盖丢失 wakeup 或 crash" 的设计意图。
- **建议改法和验证点**: 可选方案 A：在 `except Exception` 分支后自动重启 loop（需防止无限重启风暴，可加 backoff）。方案 B：在 error log 中增加明确运维提示，并在 `_start_active_cancel_watchdog_loop` 中增加 "task done but not cancelled" 检测以触发重启。方案 C：接受当前行为，但需在 README/design 中明确记录此限制。当前方案的风险较低（tick 本身是纯 SQL + CAS，异常概率极低），但 periodic fallback 的存在意义被削弱。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低——生产中 tick 异常概率极低，且 Host reopen 可恢复。

## Open Questions

无。

## Residual Risk

- `_has_accepted_cancel_fact`（Finding 1）在 Slice 2 代码中是新增路径，而 `_read_linked_cancel_requested_event`（dispatch.py）是同一逻辑的正确实现。两者行为不一致可能在后续维护中引入 confusion。
- `read_non_terminal_runs` 是全表扫描（`state.py:1756`），watchdog 每次 tick 都扫描所有非终态 Run 后再过滤 `CANCELLING`。在 Run 量大的场景下可能有性能影响。当前为 correctness review，不做 speculative 优化建议。
- `test_open_host_runtime.py::_force_cancel_requested_at` 直接操作 SQLite 写 `event_log` 表绕过 EventLogStore，测试专用 helper，不是生产代码风险。
- watchdog loop 使用 `datetime.now(UTC)` 直接获取当前时间（`dispatch.py:2583`），不可注入；deterministic 测试通过 `tick_active_cancel_watchdog(now)` 直接调用覆盖。loop 的 periodic fallback 行为无法 deterministic 测试，属于 residual test gap。
- Slice 2 未修改 `dayu/host/durable/run_transition.py` 和 `dayu/host/durable/state.py`，Slice 1 的 transition/state 变更未被本次 review 重新审查。

## Review Validation

- `source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q` → 49 passed in 0.99s
- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q` → 263 passed in 3.50s
- `source .venv/bin/activate && pyright` → 0 errors, 0 warnings, 0 informations
- `git diff --check` → 无 whitespace 错误

## Conclusion

**BLOCKING FINDINGS**: 1 项中等严重度 finding（`_has_accepted_cancel_fact` malformed payload 未处理），1 项低严重度 finding（watchdog loop 异常退出无自动重启）。Finding 1 修复成本极低且有现成参考实现（dispatch.py），建议修复后 re-review。
