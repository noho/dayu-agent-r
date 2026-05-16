# Gateflow Deepreview Fix Re-Review

## Scope

- Gate: aggregate deepreview re-review
- Branch: `fix/host-p1-p7-awaiting-production-wiring`
- Controller adjudication: `docs/reviews/gateflow-deepreview-controller-adjudication-20260516-1619.md`
- Fix artifact: `docs/reviews/gateflow-deepreview-fix-agentcodex-20260516.md`
- Re-reviewer: AgentDS
- Re-review target: fixes for accepted findings DS-1, DS-2, DS-4, DS-5, DS-6, DS-18, MiMo-2

## Per-Finding Re-Review

### DS-1: engine_ingest malformed cancel payload

**状态**: 已修复

**验证证据**:
- `dayu/host/engine_ingest.py:1865-1882` 新增 `_cancel_request_event_id_from_cancelling`，内部用 `try/except HostDurableError` 包裹原 `_required_payload_text`，payload 缺失或非法时返回 `None` 而非抛异常。
- `dayu/host/engine_ingest.py:680-686` 在 `_close_active_cancel` 中调用该函数，`None` 时返回 `REJECTED` diagnostic，reason=`run_cancelled_invalid_active_cancel_payload`，不传播异常到 `_consume_worker_events` 的 `except Exception` 分支。
- `tests/host/test_engine_ingest_mapping.py:654-678` `test_run_cancelled_without_active_cancel_is_rejected`：缺少 RUN_CANCELLING fact 时 rejected。
- `tests/host/test_engine_ingest_mapping.py:684-716` `test_run_cancelled_with_malformed_active_cancel_payload_is_rejected`：RUN_CANCELLING payload 缺少 `cancel_request_event_id` 时 rejected，Run/Attempt 保持 RUNNING。

**残余风险**: 无。

### DS-2: SQLite busy/locked retry extended error codes

**状态**: 已修复

**验证证据**:
- `dayu/host/durable/transaction.py:370-383` 新增 `_sqlite_base_error_code`，通过 `code & 0xFF` mask 出 base result code。
- `dayu/host/durable/transaction.py:359-367` `_is_busy_or_locked` 改为调用 `_sqlite_base_error_code` 后比较 base code。
- `dayu/host/durable/transaction.py:30` 定义 `_SQLITE_EXTENDED_RESULT_CODE_MASK = 0xFF`，不使用魔法数字。
- `tests/host/test_durable_transaction.py:285-300` `test_busy_locked_classification_accepts_extended_result_codes`：用 `setattr` 注入扩展错误码 `SQLITE_BUSY | (1<<8)` 和 `SQLITE_LOCKED | (2<<8)`，验证分类正确。
- Python 3.11 `sqlite3.Error.sqlite_errorcode` 确实返回扩展码；SQLite 保证低 8 位等于 base code，mask 操作安全。

**残余风险**: 无。

### DS-4: ToolRuntime timeout/cancellation enforcement

**状态**: 已修复

**验证证据**:
- `dayu/host/tool_runtime.py:2419-2459` 新增 `_dispatch_tool_call_with_bounds`：
  - 通过 `_batch_timeout_deadline` 将批级 `timeout_seconds` 转为单调时钟 deadline，各次调用通过 `_remaining_batch_timeout_seconds` 计算剩余秒数。
  - 剩余 timeout ≤ 0 时直接返回 governed failure，不调用业务工具。
  - `timeout_seconds=None` 时使用 `await_or_cancel`（仅取消监听），否则使用 `await_or_cancel_or_timeout`（三方 race）。
  - 返回 `WaitCompleted` 时透传业务 outcome，`WaitCancelled` / `WaitTimedOut` 时转为 governed failure。
- `dayu/runtime/cancellation.py:85-144` `await_or_cancel`：拥有 awaitable 所有权，token 命中时取消并等待 target task 收口，防后台孤儿协程泄漏。
- `dayu/runtime/cancellation.py:204-270` `await_or_cancel_or_timeout`：三方 race，cancellation 优先于 timeout，target task 同样被取消收口。
- `tests/host/test_toolruntime_executor.py:517-538` `test_tool_runtime_timeout_returns_governed_failure`：`_BlockingCallable` 被 timeout 命中，验证 `callable_.cancelled=True`、accept candidate 携带 `tool_runtime_timeout` reason_code、Engine 侧只看到 `ToolFailedOutcome`。
- `tests/host/test_toolruntime_executor.py:541-561` `test_tool_runtime_pre_cancelled_context_returns_governed_failure`：context token 已取消时不调用业务工具，返回 `tool_runtime_cancelled` governed failure。

**残余风险**:
- 同步 Host accept-port 工作仍由既有 accept retry policy 约束，未纳入 async dispatch race；与 DS-4 accepted scope 一致。
- 如果将来 Engine 需要在 timeout/cancellation 后重试整批，当前实现返回 governed failure 走正常 accept 路径，不会阻塞该扩展。

### DS-5: ToolTruncateSpec.strategy enum typing

**状态**: 已修复

**验证证据**:
- `dayu/contracts/tool_schema.py:120` `strategy` 字段类型变为 `ToolTruncationStrategy | None`。
- `dayu/contracts/tool_schema.py:134-137` `__post_init__` 显式校验 strategy 非 None 时必须是 `ToolTruncationStrategy` 实例。
- `dayu/contracts/tool_schema.py:158-164` `__all__` 导出 `ToolTruncationStrategy`。
- 生产调用方 `dayu/host/tool_runtime.py` 全部使用枚举值（line 3821, 3926, 3938-3944），无 raw string 兼容 shim。
- `tests/contracts/test_tool_declaration.py:70-79` `_truncate_spec()` 使用 `ToolTruncationStrategy.TEXT_CHARS`。
- `tests/contracts/test_tool_schema.py:27-38` `test_truncate_spec_rejects_raw_string_strategy`：用 `cast` 绕过类型检查传入 raw string，验证 `TypeError`。

**残余风险**: 无。`ToolTruncationStrategy` 是 `StrEnum`，是 `str` 子类型，现有 `==` 比较不受影响。

### DS-6: ToolTruncateSpec field combination validation

**状态**: 已修复

**验证证据**:
- `dayu/contracts/tool_schema.py:126-155` `__post_init__` 完整校验：
  - disabled 时 strategy 必须为 None，limits 必须为空。
  - enabled 时 strategy 必须非 None，limits 必须仅含与策略匹配的 key，且值必须为正整数。
  - 使用 `_TRUNCATE_LIMIT_KEYS_BY_STRATEGY` 映射（line 89-94）避免硬编码。
- `tests/contracts/test_tool_schema.py:41-67` `test_truncate_spec_rejects_inconsistent_enabled_strategy_limits`：parametrized 覆盖 6 种非法组合——enabled+None strategy、enabled+空 limits、enabled+不匹配 limits key、enabled+limit=0、disabled+strategy 非 None、disabled+非空 limits。

**残余风险**: 无。构造期校验阻止所有非法组合到达 ToolRuntime。

### DS-18: TruncationManager cursor cleanup

**状态**: 已修复

**验证证据**:
- `dayu/host/tool_runtime.py:1390-1391`：成功补读后 `self._cursors.pop(cursor.cursor_id, None)` 删除 single-use cursor。
- `dayu/host/tool_runtime.py:1379-1380`：TTL 过期校验失败时 `self._cursors.pop(cursor.cursor_id, None)` 删除过期 cursor。
- `dayu/host/tool_runtime.py:1439-1458` `_cleanup_expired_cursors`：有界扫描（`_TRUNCATION_EXPIRED_CLEANUP_SCAN_LIMIT=256`、`_TRUNCATION_EXPIRED_CLEANUP_LIMIT=64`），超过任一上限即停止，防止长 cursor map 下每次操作开销过大。
- 清理触发点：`fetch_more` 路径（line 1372, 1381, 1385, 1392）、`_store_cursor`（line 1417），覆盖所有 cursor 读写入口。
- `tests/host/test_toolruntime_truncation_fetch_more.py:173-199` `test_fetch_more_dispatches_as_normal_tool_and_is_single_use`：验证 first fetch_more 成功、cursor 已从 `_cursors` 删除、second fetch_more 返回 `missing_cursor`。
- `tests/host/test_toolruntime_truncation_fetch_more.py:249-263` `test_fetch_more_rejects_ttl_expiry`：验证 TTL 过期 cursor 已从 `_cursors` 删除。
- `tests/host/test_toolruntime_truncation_fetch_more.py:266-282` `test_store_cursor_cleans_expired_cursors_bounded`：manually 设置 cursor 过期时间，创建新 cursor 后验证过期 cursor 被清理。

**残余风险**:
- 如果单个 run 内 cursor map 已经极大（远超 256 个过期 cursor），完全清空历史过期 cursor 需要多次后续操作推进。这是 accept 的 bounded cleanup 设计，不是遗漏。

### MiMo-2: ToolRuntime direct tests for accepted behaviors

**状态**: 已修复

**验证证据**:
- 新增 `tests/contracts/test_tool_schema.py`：3 tests，覆盖 DS-5/DS-6 的 enum typing 与 field validation。
- 新增 `tests/host/test_toolruntime_executor.py`：12 tests，覆盖 DS-4 的 timeout/cancellation、accept barrier（rejected/timeout/retry-exhausted）、awaiting accept（success/rejected/timeout/missing-adapter/missing-external-job-ref）、scope enforcement、batch mixed outcomes、batch suspended by awaiting。
- 新增 `tests/host/test_toolruntime_truncation_fetch_more.py`：7 tests，覆盖 DS-18 的 cursor 生命周期（single-use pop、TTL expiry pop、bounded cleanup）、scope token、remainder digest、scope mismatch、missing cursor。
- 扩展 `tests/host/test_durable_transaction.py`：新增 extended error code param test（DS-2）。
- 扩展 `tests/host/test_engine_ingest_mapping.py`：新增 malformed cancel payload test（DS-1）。

**残余风险**: 无。所有 accepted finding 的生产行为变更均有直接测试覆盖，不依赖集成测试间接验证。

## Architecture Compliance

- 依赖方向：所有变更均在已有依赖方向上，`dayu.runtime` 新增 helper 已被 `dayu/host` 导入，符合分层架构。
- God module：本次未拆分 `tool_runtime.py`（DS-3 deferred），但变更未增加文件复杂度，均在既有边界内。
- `dayu.runtime` 未 import `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`，`await_or_cancel_or_timeout` 仅依赖 stdlib + `dayu.contracts.cancellation`。
- 无反向依赖、无新魔法数字/字符串（schema 内字面量符合例外）、无兼容性 shim。

## README Decision

验证：`dayu/host/README.md` 与 `tests/README.md` 当前不记录 raw-string `ToolTruncateSpec.strategy`、malformed active-cancel payload 处理、SQLite extended-code retry 分类细节、cursor 存储内部行为。本次变更均属实现细节增强，不改变现有 README 所描述的公共接口、架构边界或测试分层。README 不更新决策有效。

## Regression Check

- 69 tests 全部通过（pytest）。
- pyright 0 errors, 0 warnings。
- 未引入新类型错误或类型退化。
- 未修改 Engine 公共语义或 Host 公共 API 签名。
- `ToolTruncationStrategy` 是 `StrEnum` subclass of `str`，不破坏现有比较。

## Conclusion: PASS

所有 7 个 accepted finding (DS-1, DS-2, DS-4, DS-5, DS-6, DS-18, MiMo-2) 均**已修复**，有直接测试证据，无架构违规，无回归，README 决策有效。

无新 blocker。
