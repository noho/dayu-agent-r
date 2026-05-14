# Host Phase 2 Durable Store / EventLog Plan Fix

## Work Gate Name

Phase 2 plan fix。

## Source Review Artifact Paths

- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-mimo-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-ds-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`

## Controller-Accepted Finding IDs

- MIMO-1
- MIMO-2
- MIMO-3
- MIMO-4
- MIMO-5
- MIMO-6
- MIMO-7
- DS-F1
- DS-F2
- DS-F3
- DS-F4
- DS-F5
- DS-F6

## Per-Finding Fix Status

### MIMO-1 - fixed

移除 Phase 2 error taxonomy 中的 `HostCASPreconditionFailedError`，并从 transaction retry / non-retryable error 描述中移除 CAS precondition failure。Phase 2 只保留 non-goal 中对 CAS 状态迁移的排除，不预留 CAS 错误类型。

### MIMO-2 - fixed

将 `record_idempotent_result` 改为显式接收 `IdempotencyResultRef`：`record_idempotent_result(transaction: HostTransaction, scope: IdempotencyScope, semantic_input_digest: str, result: IdempotencyResultRef) -> IdempotencyRecord`。Plan 同时明确 `result_kind` 必须来自 `IdempotencyResultRef.result_kind`，不得从 `result_ref`、scope、event id 或字符串前缀隐式推导。

### MIMO-3 - fixed

补充 `HostTransaction` 最小内部 API shape：typed `execute` / `fetchone` / `fetchall` wrapper、`SQLParameters`、`HostRow`、`HostExecuteResult`，并明确 raw `sqlite3.Connection` 不暴露到 `dayu.host` 包根或 durable foundation 外部。

### MIMO-4 - fixed

显式枚举 `event_body_digest` 输入字段集合，并明确排除 `event_id`、`event_sequence`、`appended_at` 以及其它 DB-assigned / non-request fields。

### MIMO-5 - fixed

明确 `payload_id` 由调用方提供，遵守 TEXT durable id 约定；payload store 只负责校验、持久化和通过 descriptor row 链接，不隐式生成或从 digest 派生。

### MIMO-6 - fixed

补充 `HostDurableStore` 最小职责：它是内部 handle，持有 options、connection factory / ownership 与 transaction runner；不从 `dayu.host` 包根导出，不作为 public API，不直接实现 EventLog / payload / liveness / command path / recovery 等业务能力，避免 God object。

### MIMO-7 - fixed

artifact path 验证补充 null byte 拒绝、resolved path containment check、symlink / traversal 防逃逸要求。

### DS-F1 - fixed

同 MIMO-4，已明确 `event_body_digest` 输入字段集合，并排除 `event_sequence`、`event_id`、`appended_at` 等非请求或 DB-assigned fields。

### DS-F2 - fixed

将 `register_current_instance` 改为 deterministic MUST：同 `HostInstanceIdentity` 重复 register 必须幂等 refresh heartbeat/status；同 id 不同 process token 必须抛 `HostInstanceIdentityConflictError`。

### DS-F3 - fixed

明确 `heartbeat_current_instance` 缺失当前 row 时抛 `HostInstanceNotRegisteredError`；同 id 但 process token 不匹配时抛 `HostInstanceIdentityConflictError`。两者均为 dedicated non-retryable errors，不返回 `None`、不静默跳过。

### DS-F4 - fixed

Slice 1 tests 增加第二个独立连接验证 `PRAGMA journal_mode` 返回 `wal`，并在 expected assertions 中同步记录。

### DS-F5 - fixed

明确 artifact temp area 为 `artifact_root/.tmp/`，temp filename 使用不可猜测随机 id 或 `tempfile` 独占创建，避免多进程冲突；测试要求覆盖 temp area 与并发命名安全。

### DS-F6 - fixed

Slice 2 EventLog tests 增加：append 引用不存在的非空 `payload_ref` 时抛 `HostForeignKeyError`，且 transaction runner 不 retry；expected assertions 和 expected failure paths 同步补充。

## Changed Files

- `docs/host/phase2-durable-store-eventlog-plan.md`
- `docs/reviews/gateflow-plan-fix-host-p2-durable-store-eventlog-codex-20260514.md`

## Validation Status

- 未运行测试：本 gate 只修 handoff plan 文档，不修改生产代码或测试代码。
- 未运行 pyright：本 gate 只修 Markdown plan / fix artifact，不产生 Python 类型检查输入变化。
- 已做文本级核对：确认 plan 中不再保留 `HostCASPreconditionFailedError` 或 CAS precondition retry 语义；确认 `record_idempotent_result` 已改为显式 `IdempotencyResultRef` 签名；确认 WAL second-connection、artifact `.tmp/`、null byte / symlink、missing `payload_ref` FK、liveness dedicated errors 均已写入 plan。

## Finding Title Status Update Result

Source review artifacts 不在本 handoff 的 allowed files 中，因此未修改 review artifact 标题状态词。本 fix artifact 按 controller-accepted finding ids 记录最终 fix status，供后续 plan re-review 使用。

## New Risks / Open Questions

- 无新增 blocking open question。
- 新增 `HostInstanceIdentityConflictError` 与 `HostInstanceNotRegisteredError` 是为 accepted findings 收敛错误语义所需的 Phase 2 durable error types；后续 re-review 应确认该错误粒度没有扩大到 lease / fencing / recovery classifier。
- `HostTransaction` row / parameter typed aliases 已在 plan 中要求，但具体 type alias 形状仍需 implementation agent 在不使用 `Any` / `object` 的前提下落地；这是实现细节，不阻塞 plan re-review。

## Residual Risk Classification

- Accepted findings: fixed in current plan fix。
- Residual risk: low。剩余风险仅为后续 implementation 是否严格按 plan 落地 typed aliases、SQLite error wrapping 与 artifact path resolution；这些应由 implementation review 覆盖。
- Deferred risk: artifact orphan cleanup policy 仍按原 plan deferred to later cleanup / diagnostics work unit，本次未改变。

## Artifact Path

`docs/reviews/gateflow-plan-fix-host-p2-durable-store-eventlog-codex-20260514.md`
