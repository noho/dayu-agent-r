# Host Phase 2 Durable Store / EventLog Plan Re-Review

## Review Gate Name

Phase 2 plan re-review — controller-accepted findings fix verification.

## Reviewed Target

`docs/host/phase2-durable-store-eventlog-plan.md`

## Fix Artifact Path

`docs/reviews/gateflow-plan-fix-host-p2-durable-store-eventlog-codex-20260514.md`

## Source Review Artifacts

- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-mimo-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-ds-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`

## Re-Review Scope

本次 re-review 仅验证 controller-accepted findings 的 fixes，不重新做完整 plan review。若 fix 引入新 blocker 则记录，否则不扩展检查范围。

## Per-Finding Fix Verification

### MIMO-1: 移除 HostCASPreconditionFailedError / CAS precondition retry 语义

**Fixed**。Plan error taxonomy（§Error Types）不再包含 `HostCASPreconditionFailedError`。transaction runner 的 retry / non-retryable error 描述中无 CAS precondition 语义。Non-goals 明确排除 CAS 状态迁移。全 plan 搜索无残留 `CAS` 或 `cas_precondition` 引用。

证据：
- §Error Types（lines 333-349）：13 个 error types，无 `HostCASPreconditionFailedError`。
- §Non-Goals（line 68）：明确排除 "CAS 状态迁移"。
- §Transaction Runner Typed API retry semantics（lines 296-299）：无 CAS precondition retry。

### MIMO-2: record_idempotent_result 显式接收 IdempotencyResultRef

**Fixed**。函数签名改为显式接收 `IdempotencyResultRef` result 参数。Behavior 段明确 `result_kind` 必须来自 `IdempotencyResultRef.result_kind`，不得从 `result_ref`、scope、event id 或字符串前缀隐式推导。

证据：
- §Idempotency Primitive Target functions（line 443）：`record_idempotent_result(transaction: HostTransaction, scope: IdempotencyScope, semantic_input_digest: str, result: IdempotencyResultRef) -> IdempotencyRecord`
- §Behavior（line 452）："result_kind must come from explicit IdempotencyResultRef.result_kind; implementation must not infer it from result_ref, scope, event id or string prefix."
- §Slice 2 Target functions（line 736）：签名一致。

### MIMO-3: HostTransaction 最小 internal typed wrapper API 清楚

**Fixed**。`HostTransaction` 的最小 API 已明确：typed `execute` / `fetchone` / `fetchall`，配套 `SQLParameters`、`HostRow`、`HostExecuteResult` 类型。明确不暴露 raw `sqlite3.Connection` 到 `dayu.host` 包根或 durable foundation 外部。

证据：
- §Transaction Runner Typed API（lines 280-288）：完整 API shape 定义。
- §Slice 1 Target types（lines 633-637）：`SQLiteScalar`、`SQLParameters`、`HostRow`、`HostExecuteResult`、`HostTransaction` 均列入 target。

### MIMO-4 + DS-F1: event_body_digest 输入字段集合明确且排除 DB-assigned / non-request fields

**Fixed**。`event_body_digest` 输入字段集合显式枚举了 16 个 request-assigned 字段，并明确排除 `event_id`、`event_sequence`、`appended_at` 及所有其他 DB-assigned / non-request fields。

证据：
- §EventLog Row Typed Contract Behavior（lines 394-411）：完整列出 16 个输入字段，并声明 "event_body_digest must exclude event_id, event_sequence, appended_at and every other DB-assigned or non-request field; duplicate identity detection compares the request body, not ledger placement metadata."

### MIMO-5: payload_id 生成责任明确

**Fixed**。`payload_id` 由调用方提供，遵守 TEXT durable id 约定；payload store 只校验、持久化和通过 descriptor row 链接，不隐式生成或从 digest 派生。

证据：
- §Payload Descriptor And Artifact Ref Digest semantics（line 493）："payload_id is provided by the caller and must follow the project TEXT durable id convention; payload store only validates, persists and links it through descriptor rows. It must not generate a hidden payload id or derive it from content digest."

### MIMO-6: HostDurableStore 最小职责清楚且不是 public API / God object

**Fixed**。`HostDurableStore` 定义为内部 handle，持有 validated options、connection factory / ownership、transaction runner。明确不从 `dayu.host` 包根导出，不是 public API，不直接实现 EventLog / idempotency / payload / artifact / liveness / command path / projection / recovery / Engine dispatch。

证据：
- §Storage Policy Options HostDurableStore minimum responsibility（lines 323-328）：完整职责定义和限制。

### MIMO-7: artifact path 验证覆盖 null byte、symlink / resolved containment、traversal

**Fixed**。artifact write ordering step 1-2 明确：拒绝 null byte、绝对路径和 `..` traversal；resolve symlinks 后做 resolved-path containment check。

证据：
- §Artifact write ordering steps 1-2（lines 497-498）："Reject null bytes, absolute paths and `..` traversal before filesystem access" + "Resolve symlinks for artifact root, candidate parent directories and final path, then perform a resolved-path containment check so symlink or traversal cannot escape artifact root."
- §Slice 3 tests for artifact（line 852）："relative path cannot be absolute, contain null byte, traverse with `..`, or escape artifact root through symlink resolution."

### DS-F2: register_current_instance 错误和幂等语义确定

**Fixed**。`register_current_instance` 改为 deterministic MUST：同 `HostInstanceIdentity` 重复 register 必须幂等 refresh `heartbeat_at` 和 status；同 `host_instance_id` 不同 `process_start_token` 必须抛 `HostInstanceIdentityConflictError`（non-retryable）。

证据：
- §Host Instance Liveness Primitive Behavior（lines 539-540）："if the same HostInstanceIdentity already exists, it MUST idempotently refresh heartbeat_at and status running" + "If the same host_instance_id exists with a different process_start_token, register MUST raise HostInstanceIdentityConflictError, which is non-retryable by the transaction runner."

### DS-F3: heartbeat_current_instance 错误和幂等语义确定

**Fixed**。`heartbeat_current_instance` 缺失当前 row 时抛 `HostInstanceNotRegisteredError`；同 `host_instance_id` 但 process token 不匹配时抛 `HostInstanceIdentityConflictError`。两者均为 dedicated non-retryable errors，不返回 `None`、不静默跳过。

证据：
- §Host Instance Liveness Primitive Behavior（line 542）："Heartbeat missing the current row MUST raise HostInstanceNotRegisteredError; heartbeat with matching host_instance_id but mismatched process_start_token MUST raise HostInstanceIdentityConflictError. Both are dedicated non-retryable errors; heartbeat must not return None or silently skip."

### DS-F4: WAL second independent connection test 已加入

**Fixed**。Slice 1 tests 增加第二个独立连接验证 `PRAGMA journal_mode` 返回 `wal`，expected assertions 同步记录。

证据：
- §Slice 1 Tests（line 654）："a second independent connection to the same DB returns wal from PRAGMA journal_mode, proving WAL mode is persisted rather than only assumed on the original connection."
- §Slice 1 Expected assertions（line 669）："PRAGMA journal_mode is wal on a reopened independent connection."

### DS-F5: artifact temp area / temp filename strategy 已加入

**Fixed**。明确 artifact temp area 为 `artifact_root/.tmp/`，temp filename 使用 cryptographic random id 或 `tempfile` exclusive creation，禁止 timestamp / pid alone。测试要求覆盖 temp area 与并发命名安全。

证据：
- §Artifact write ordering steps 3-4（lines 499-500）："Write temp file under artifact_root/.tmp/" + "Temp filename must be unguessable and multi-process safe, using cryptographic random id or tempfile exclusive creation; never use timestamp / pid alone."
- §Slice 3 tests for artifact（line 853）："temp files are created under artifact_root/.tmp/ with unguessable random id or tempfile exclusive creation, so concurrent writers do not collide."

### DS-F6: missing payload_ref FK test 已加入

**Fixed**。Slice 2 EventLog tests 增加 append 引用不存在的非空 `payload_ref` 时抛 `HostForeignKeyError` 且 transaction runner 不 retry 的测试。Expected assertions 和 expected failure paths 同步补充。

证据：
- §Slice 2 Tests（line 748）："EventLog append with a non-existent non-null payload_ref raises HostForeignKeyError and transaction runner does not retry it."
- §Slice 2 Expected assertions（line 766）："missing payload_ref FK violation is wrapped as HostForeignKeyError and is not retried."
- §Expected failure paths（line 946）："EventLog append referencing missing payload_ref raises HostForeignKeyError and is not retried."

## New Blockers

无。所有 12 个 controller-accepted findings 均为 **fixed**。

Fix artifact 提及的新增 error types（`HostInstanceIdentityConflictError`、`HostInstanceNotRegisteredError`）已在 plan error taxonomy 中正确注册（lines 344-345），且 plan 在 liveness primitive、non-goals 和 tests 中反复明确边界：无 lease、无 fencing、无 Attempt owner、无 takeover grant、无 orphan classifier。这些 error types 的语义粒度未扩大到 lease / fencing / recovery classifier。

## Residual Risk

- **Low**：`HostTransaction` 的 `SQLParameters`、`HostRow`、`HostExecuteResult` type alias 具体形状仍需 implementation agent 在不使用 `Any` / `object` 的前提下落地。这是实现细节，不阻塞 plan re-review。应由 implementation review 覆盖。
- **Low**：`HostAfterCommitError` 后 caller 观察到异常但数据已 durable 的语义需 implementation tests 覆盖——plan 已在 Risks（line 1012）和 Slice 1 tests 中要求。
- **Deferred**：artifact orphan cleanup policy 仍按原 plan deferred to later cleanup / diagnostics work unit，本次未改变。

## Fix Artifact Validation

Fix artifact 正确记录了 changed files（plan markdown + fix artifact itself），正确声明了未运行测试/pyright（plan-only fix），文本级核对确认了 12 个 findings 均已写入 plan。

## Controller Decision Status

`pending-controller-decision`

## Artifact Path

`docs/reviews/gateflow-plan-re-review-host-p2-durable-store-eventlog-ds-20260514.md`
