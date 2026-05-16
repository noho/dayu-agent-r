# Gateflow Deepreview Fix Re-Review - AgentMiMo

## Gate

- 当前 gate：aggregate deepreview re-review。
- Work unit：full repository deepreview fix gate。
- Branch：`fix/host-p1-p7-awaiting-production-wiring`。
- 角色：review agent only；未修改生产代码或测试，未 commit，未 push，未创建 PR。

## Source Artifacts

- Controller adjudication：`docs/reviews/gateflow-deepreview-controller-adjudication-20260516-1619.md`。
- Fix artifact：`docs/reviews/gateflow-deepreview-fix-agentcodex-20260516.md`。
- Source review：`docs/reviews/repo-review-20260516-1551.md`。
- Source review：`docs/reviews/repo-review-20260516-1557.md`。

## Changed Files Inspected

- `dayu/contracts/tool_schema.py`
- `dayu/host/durable/transaction.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/tool_runtime.py`
- `tests/contracts/test_tool_declaration.py`
- `tests/contracts/test_tool_schema.py`
- `tests/host/test_durable_transaction.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_phase6_toolruntime_integration.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`

## Per-Finding Final Status

### DS-1：已修复

`engine_ingest.py:1865-1882` 新增 `_cancel_request_event_id_from_cancelling`，从 `RUN_CANCELLING` payload 读取 `cancel_request_event_id` 时 catch `HostDurableError` 并返回 `None`。`_close_active_cancel`（line 681）检查返回值为 `None` 时走 rejected diagnostic，reason 为 `run_cancelled_invalid_active_cancel_payload`。不再让 malformed payload 解析异常逃逸出事务边界。

测试覆盖：`test_engine_ingest_mapping.py:684` `test_run_cancelled_with_malformed_active_cancel_payload_is_rejected` 写入缺少 `cancel_request_event_id` 的 `RUN_CANCELLING` fact，断言返回 `REJECTED` 且 reason 正确，Run/Attempt 状态不变。

### DS-2：已修复

`transaction.py:359-367` `_is_busy_or_locked` 改为调用 `_sqlite_base_error_code`，后者用 `_SQLITE_EXTENDED_RESULT_CODE_MASK`（`0xFF`）mask 掉 extended 信息后比较 `SQLITE_BUSY` / `SQLITE_LOCKED`。`_sqlite_base_error_code`（line 370-383）与 `_sqlite_error_code`（line 386-400）分层清晰。

测试覆盖：`test_durable_transaction.py:285-300` parametrize 了 `SQLITE_BUSY | (1 << 8)` 和 `SQLITE_LOCKED | (2 << 8)` 两个 extended code，断言 `_is_busy_or_locked` 返回 `True`。

### DS-4：已修复

`tool_runtime.py:2419-2459` `_dispatch_tool_call_with_bounds` 在 dispatch 前计算剩余 batch timeout（`_remaining_batch_timeout_seconds`），timeout 已耗尽时直接返回 governed failure；否则按是否有 timeout 分别调用 `await_or_cancel` 或 `await_or_cancel_or_timeout`，传入 `context.cancellation_token`。`WaitCancelled` 和 `WaitTimedOut` 都转为 governed failure outcome，不会让业务工具无限挂起。

测试覆盖：
- `test_toolruntime_executor.py:517` `test_tool_runtime_timeout_returns_governed_failure`：blocking callable 超时后返回 `tool_runtime_timeout` governed error，callable 被取消。
- `test_toolruntime_executor.py:541` `test_tool_runtime_pre_cancelled_context_returns_governed_failure`：已取消 token 不调用业务工具，返回 `tool_runtime_cancelled` governed error。

### DS-5：已修复

`tool_schema.py:120` `ToolTruncateSpec.strategy` 类型为 `ToolTruncationStrategy | None`。`__post_init__`（line 134-137）检查 `strategy` 必须是 `ToolTruncationStrategy` 实例，否则抛 `TypeError`。

测试覆盖：`test_tool_schema.py:27-38` `test_truncate_spec_rejects_raw_string_strategy` 用 `cast` 传入 raw string，断言抛 `TypeError`。

### DS-6：已修复

`tool_schema.py:126-155` `__post_init__` 校验完整：
- disabled 时 strategy 必须为 `None`，limits 必须为空（line 138-143）。
- enabled 时 strategy 不能为 `None`（line 144-145）。
- limits 的 key 必须精确匹配策略对应的 limit key（line 146-149）。
- limit 值必须为正整数，排除 `bool`（line 151-155）。

测试覆盖：`test_tool_schema.py:41-67` parametrize 覆盖 6 种不一致组合（enabled+无 strategy、enabled+空 limits、enabled+错误 key、enabled+零值、disabled+有 strategy、disabled+有 limits），全部断言抛 `ValueError`。

### DS-18：已修复

`tool_runtime.py:1390-1391` `fetch_more` 成功补读后对 single-use cursor 执行 `self._cursors.pop(cursor.cursor_id, None)`。`tool_runtime.py:1379-1380` 校验失败且 cursor 已过期时也删除。`_cleanup_expired_cursors`（line 1439-1458）每次 `_store_cursor`、`fetch_more` 入口和各校验/读取路径都调用，有界扫描 `_TRUNCATION_EXPIRED_CLEANUP_SCAN_LIMIT`（256）并删除最多 `_TRUNCATION_EXPIRED_CLEANUP_LIMIT`（64）个过期 cursor。

测试覆盖：`test_toolruntime_truncation_fetch_more.py:267` `test_store_cursor_cleans_expired_cursors_bounded` 将第一个 cursor 设为已过期，创建第二个 cursor 后断言第一个已被删除。`test_toolruntime_truncation_fetch_more.py:173` `test_fetch_more_dispatches_as_normal_tool_and_is_single_use` 断言第二次 fetch_more 同一 cursor 返回 `cursor_already_used`。

### MiMo-2：已修复

accepted 行为变更均有直接测试覆盖：
- DS-1 测试：`test_engine_ingest_mapping.py:684`。
- DS-2 测试：`test_durable_transaction.py:292`。
- DS-4 测试：`test_toolruntime_executor.py:517`、`test_toolruntime_executor.py:541`。
- DS-5/DS-6 测试：`test_tool_schema.py:12`、`test_tool_schema.py:27`、`test_tool_schema.py:52`。
- DS-18 测试：`test_toolruntime_truncation_fetch_more.py:173`、`test_toolruntime_truncation_fetch_more.py:267`。

## New Blockers

未发现。

## Validation Notes

- Controller 已本地验证：`pytest` 69 tests passed，`pyright` 0 errors。
- 代码审查未发现架构违反：修复均在 accepted scope 内，未引入反向依赖、God object 或兼容性 shim。
- `_cancel_request_event_id_from_cancelling` 用 `except HostDurableError` 精确捕获 durable 域异常，不会掩盖非 durable 错误。
- `_sqlite_base_error_code` 用 `getattr` 读取 `sqlite_errorcode` 有充分理由（类型 stub 声明不足），与 CLAUDE.md 约束一致。
- ToolRuntime timeout/cancellation 通过 `dayu.runtime.cancellation` 的 `await_or_cancel` / `await_or_cancel_or_timeout` 实现，复用公共运行时基础设施，符合分层约束。

## README Decision

fix artifact 决定不更新 README，理由成立：本次变更均为内部 contract / implementation 细节，现有 README 未记录 raw-string strategy、malformed payload 处理、SQLite extended code retry 或 cursor 存储行为。

## Residual Risks

- 与 fix artifact 一致：ToolRuntime timeout/cancellation 约束的是业务工具 dispatch，Host accept-port 工作仍由既有 accept retry policy 约束。
- 与 fix artifact 一致：expired cursor cleanup 是每次操作有界清理，极大 cursor map 需要多次操作推进。

## Conclusion

**PASS**

所有 accepted findings（DS-1, DS-2, DS-4, DS-5, DS-6, DS-18, MiMo-2）均已修复，测试覆盖充分，无回归，无新 blocker。

## Artifact Path

`docs/reviews/gateflow-deepreview-fix-re-review-mimo-20260516.md`
