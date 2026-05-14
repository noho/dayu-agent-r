# Host Phase 2 Durable Store / EventLog Plan Review Controller Adjudication

## Work Gate Name

Phase 2 plan review controller adjudication。

## Reviewed Artifacts

- `docs/host/phase2-durable-store-eventlog-plan.md`
- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-mimo-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-ds-20260514.md`

## Controller Conclusion

Plan 方向、scope 与 slice 编排成立，但 review findings 中多项会让 implementation agent 自行补 typed contract 或错误语义。Controller 裁决为：所有 findings 均 accepted，必须在 plan fix 中修复后进入 plan re-review。

## Accepted Findings

- MIMO-1 / `HostCASPreconditionFailedError` 在 Phase 2 无使用上下文：accepted。Phase 2 不实现 CAS state transition；该错误类型应从 Phase 2 plan 移除，不做预留类型。
- MIMO-2 / `record_idempotent_result` 缺少 `result_kind` 参数：accepted。签名必须显式接收 `IdempotencyResultRef` 或 `result_kind` + `result_ref`，不得从 `result_ref` 或 scope 隐式推导。
- MIMO-3 / `HostTransaction` 内部 API shape 未指定：accepted。Plan 必须写清最小内部 wrapper API，例如 typed `execute` / `fetchone` / `fetchall`，且不暴露 raw `sqlite3.Connection` 到 Host 包根。
- MIMO-4 + DS-F1 / `event_body_digest` 计算字段集合未显式枚举：accepted。Plan 必须明确 digest 输入字段，排除 `event_sequence`、`event_id`、`appended_at` 等非请求或 DB-assigned fields。
- MIMO-5 / `payload_id` 生成责任未指定：accepted。Plan 必须明确 `payload_id` 由调用方提供，遵守 TEXT durable id 约定；store 只校验和持久化。
- MIMO-6 / `HostDurableStore` 为 plan 新增抽象但职责未定义：accepted。Plan 必须写清它是内部 handle，持有 options、connection factory / transaction runner，不是 public API，不做 God object。
- MIMO-7 / artifact path 验证未覆盖 symlink 和 null byte：accepted。Plan 必须要求拒绝 null byte，使用 resolved path 做 containment check，防止 symlink / traversal 逃逸 artifact root。
- DS-F2 / `register_current_instance` 使用非确定性 `may`：accepted。Plan 必须改成 MUST：同 identity 重复 register 幂等 refresh heartbeat/status；同 id 不同 process token 抛 dedicated non-retryable conflict。
- DS-F3 / `heartbeat_current_instance` 缺失 / 不匹配行错误语义未指定：accepted。Plan 必须明确缺失或 process token 不匹配时抛 dedicated non-retryable error，不返回 None、不静默跳过。
- DS-F4 / WAL 启用后未要求验证 journal_mode 持久化：accepted。Slice 1 tests 必须增加第二个独立连接验证 `PRAGMA journal_mode` 仍为 `wal`。
- DS-F5 / Artifact temp 文件命名策略未指定：accepted。Plan 必须明确 temp area 位于 artifact root 下，例如 `.tmp/`，temp filename 使用不可猜测随机 id 或 `tempfile` 独占创建，避免多进程冲突。
- DS-F6 / EventLog.payload_ref FK 约束违规缺少显式测试：accepted。Plan 必须增加 append EventLog 引用不存在 `payload_ref` 时抛 `HostForeignKeyError` 且 transaction runner 不 retry 的测试。

## Rejected / Deferred Findings

无。

## Fix Requirements

Plan fix 只能修改 `docs/host/phase2-durable-store-eventlog-plan.md`，并写 fix artifact `docs/reviews/gateflow-plan-fix-host-p2-durable-store-eventlog-codex-20260514.md`。Fix 后必须进入 plan re-review，不得直接进入 user confirmation。

## Artifact Path

`docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`
