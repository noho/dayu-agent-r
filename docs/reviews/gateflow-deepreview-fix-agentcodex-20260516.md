# Gateflow Deepreview Fix - AgentCodex

## Gate

- 当前 gate：aggregate deepreview fix。
- Work unit：full repository deepreview fix gate。
- Branch：`fix/host-p1-p7-awaiting-production-wiring`。
- 角色：fix agent only；未启动 controller workflow，未 commit，未 push，未创建 PR，未进入 re-review。

## Source Review Artifacts

- Controller adjudication：`docs/reviews/gateflow-deepreview-controller-adjudication-20260516-1619.md`。
- Source review：`docs/reviews/repo-review-20260516-1551.md`。
- Source review：`docs/reviews/repo-review-20260516-1557.md`。

## Accepted Finding IDs

- DS-1
- DS-2
- DS-4
- DS-5
- DS-6
- DS-18
- MiMo-2

## Per-Finding Fix Status

- DS-1：已修复。`RUN_CANCELLED` closeout 现在会把缺失或非法的 `RUN_CANCELLING.cancel_request_event_id` 收敛为 rejected diagnostic，reason 为 `run_cancelled_invalid_active_cancel_payload`，不再让 durable payload 解析异常逃逸出 ingestion。
- DS-2：已修复。SQLite busy / locked retry 分类现在先把 extended result code mask 为 base result code，再与 `SQLITE_BUSY` / `SQLITE_LOCKED` 比较。
- DS-4：已修复。`ToolRuntimeExecutor` 现在用批级 `timeout_seconds` budget 与 `cancellation_token` 包裹业务工具 dispatch；timeout / cancellation 会转为 governed tool failure，并继续走正常 Host accept path。
- DS-5：已修复。`ToolTruncateSpec.strategy` 已改为 `ToolTruncationStrategy | None`；测试与调用方已改用 enum，不保留 raw string 兼容 shim。
- DS-6：已修复。`ToolTruncateSpec.__post_init__` 现在校验 enabled / disabled 组合，并要求启用时提供与策略匹配的正整数 limit key。
- DS-18：已修复。成功补读的 single-use `fetch_more` cursor 会被删除；过期的目标 cursor 在返回 expiry diagnostic 后删除；cursor 创建与补读路径都会执行有界 expired cursor cleanup。
- MiMo-2：已修复 accepted 行为覆盖。新增 / 扩展了 ToolRuntime timeout、cancellation、truncation cursor 生命周期和 ToolTruncateSpec contract 的直接测试。

## Changed Files

- `dayu/host/engine_ingest.py`
- `dayu/host/durable/transaction.py`
- `dayu/contracts/tool_schema.py`
- `dayu/host/tool_runtime.py`
- `tests/contracts/test_tool_declaration.py`
- `tests/contracts/test_tool_schema.py`
- `tests/host/test_durable_transaction.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_phase6_toolruntime_integration.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `docs/reviews/gateflow-deepreview-fix-agentcodex-20260516.md`

## Validation

- `source .venv/bin/activate && pytest tests/contracts/test_tool_schema.py tests/contracts/test_tool_declaration.py tests/host/test_durable_transaction.py tests/host/test_engine_ingest_mapping.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_phase6_toolruntime_integration.py`
  - 结果：通过，69 tests。
- `source .venv/bin/activate && pyright`
  - 结果：通过，0 errors，0 warnings，0 informations。
- `python -m compileall dayu/host/engine_ingest.py dayu/host/durable/transaction.py dayu/contracts/tool_schema.py dayu/host/tool_runtime.py tests/contracts/test_tool_schema.py tests/host/test_toolruntime_executor.py`
  - 结果：通过。

## Docs Decision

- 不需要更新 README。现有 README 没有记录 raw-string `ToolTruncateSpec.strategy`、malformed active-cancel payload 处理、SQLite extended-code retry 细节或 cursor 存储内部行为；本次变化已由 contract / Host 测试覆盖。

## Residual Risks

- ToolRuntime timeout / cancellation 当前约束的是业务工具 dispatch。同步 Host accept-port 工作仍由既有 accept retry policy 约束，未纳入 async dispatch race；这与 DS-4 accepted scope 一致，但仍是独立运行期边界。
- Expired cursor cleanup 是每次操作有界清理；如果单个 run 内 cursor map 已经极大，完全清空历史过期 cursor 需要多次后续操作推进。

## Stop Status

- implementation、focused tests、pyright validation、docs decision 与 fix artifact 已完成。
- 按 fix agent stop condition 停止，交回 controller 做 re-review。
