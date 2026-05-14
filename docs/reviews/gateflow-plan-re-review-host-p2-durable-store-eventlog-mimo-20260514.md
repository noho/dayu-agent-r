# Host Phase 2 Durable Store / EventLog Plan Re-Review

## Review Gate Name

Phase 2 plan re-review。

## Reviewed Target

`docs/host/phase2-durable-store-eventlog-plan.md`

## Fix Artifact Path

`docs/reviews/gateflow-plan-fix-host-p2-durable-store-eventlog-codex-20260514.md`

## Source Review Artifacts

- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-mimo-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-ds-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`

## Reviewer Scope

只 re-review controller-accepted findings 的 fixes，不重新做完整 plan review，除非 fix 引入新 blocker。

## Per-Finding Re-Review

### MIMO-1 / HostCASPreconditionFailedError 移除 — fixed

Plan error taxonomy（§Error Types, lines 332-349）不再包含 `HostCASPreconditionFailedError`。Non-goals（line 68）保留 "CAS 状态迁移" 排除，Phase 2 error types 只包含实际使用的错误类型。Transaction retry 语义（line 297）列出 non-retryable 错误中无 CAS precondition failure。

### MIMO-2 / record_idempotent_result 显式接收 IdempotencyResultRef — fixed

函数签名（line 443）已改为 `record_idempotent_result(transaction: HostTransaction, scope: IdempotencyScope, semantic_input_digest: str, result: IdempotencyResultRef) -> IdempotencyRecord`。Behavior 段（line 452）明确 "`result_kind` must come from explicit `IdempotencyResultRef.result_kind`; implementation must not infer it from `result_ref`, scope, event id or string prefix"。与 DDL `result_kind TEXT NOT NULL` 和 `IdempotencyResultRef.result_kind: str` 一致。

### MIMO-3 / HostTransaction 最小 internal typed wrapper API — fixed

§Transaction Runner Typed API（lines 283-288）明确 `HostTransaction` wrapper API：

- `execute(sql: str, parameters: SQLParameters = ()) -> HostExecuteResult`
- `fetchone(sql: str, parameters: SQLParameters = ()) -> HostRow | None`
- `fetchall(sql: str, parameters: SQLParameters = ()) -> tuple[HostRow, ...]`

明确 `SQLParameters` 是 typed tuple / mapping of SQLite scalar values，`HostRow` 是 typed row view。明确 "implementation must not use `Any`, `object` or untyped row payloads"（line 287）。明确 raw `sqlite3.Connection` 不暴露到 durable foundation 外部（line 282）。明确 `HostTransaction` 不成为 domain store（line 288）。

### MIMO-4 + DS-F1 / event_body_digest 输入字段集合明确 — fixed

§EventLog Row Typed Contract Behavior（lines 395-411）显式枚举 `event_body_digest` 输入字段：

- 包含：`event_class`, `session_id`, `run_id`, `attempt_id`, `execution_id`, `event_type`, `occurred_at`, `actor`, `source`, `client_request_id`, `idempotency_key`, `policy_decision_json`, `reason_json`, `payload_json`, `payload_ref`, `payload_digest`（共 16 个 request-assigned 字段）。
- 排除：`event_id`, `event_sequence`, `appended_at` 和 "every other DB-assigned or non-request field"。

明确 "duplicate identity detection compares the request body, not ledger placement metadata"（line 411）。

### MIMO-5 / payload_id 生成责任明确 — fixed

§Payload Descriptor And Artifact Ref（line 493）明确 "`payload_id` is provided by the caller and must follow the project TEXT durable id convention; payload store only validates, persists and links it through descriptor rows. It must not generate a hidden payload id or derive it from content digest." `SQLitePayloadWriteRequest` 的 `payload_id: str` 字段（line 465）与调用方提供一致。

### MIMO-6 / HostDurableStore 最小职责清楚 — fixed

§Storage Policy Options（lines 323-328）明确 `HostDurableStore` 最小职责：

- "It is an internal Host durable handle returned by `open_host_durable_store(options)`"（line 325）。
- "It is not exported from `dayu.host` package root and is not a public API"（line 325）。
- "It holds the validated `HostDurableStoreOptions`, the connection factory / ownership needed to open configured SQLite connections, and the `HostTransactionRunner`"（line 326）。
- "It must not become a God object: it must not implement EventLog, idempotency, payload, artifact, liveness, command path, projection, recovery or Engine dispatch behavior directly"（line 328）。

### MIMO-7 / artifact path 验证覆盖 null byte、symlink、traversal — fixed

§Payload Descriptor And Artifact Ref Artifact write ordering（lines 497-498）：

- Step 1: "Reject null bytes, absolute paths and `..` traversal before filesystem access"。
- Step 2: "Resolve symlinks for artifact root, candidate parent directories and final path, then perform a resolved-path containment check so symlink or traversal cannot escape artifact root"。

`test_artifact_store.py` tests（line 852）覆盖 "relative path cannot be absolute, contain null byte, traverse with `..`, or escape artifact root through symlink resolution"。

### DS-F2 / register_current_instance 错误和幂等语义确定 — fixed

§Host Instance Liveness Primitive Behavior（lines 539-540）使用确定性 MUST 措辞：

- "Register inserts current instance as `running`; if the same `HostInstanceIdentity` already exists, it MUST idempotently refresh `heartbeat_at` and status `running`"（line 539）。
- "If the same `host_instance_id` exists with a different `process_start_token`, register MUST raise `HostInstanceIdentityConflictError`, which is non-retryable by the transaction runner"（line 540）。

### DS-F3 / heartbeat_current_instance 错误语义确定 — fixed

§Host Instance Liveness Primitive Behavior（lines 542-543）明确：

- "Heartbeat missing the current row MUST raise `HostInstanceNotRegisteredError`"（line 542）。
- "heartbeat with matching `host_instance_id` but mismatched `process_start_token` MUST raise `HostInstanceIdentityConflictError`"（line 542）。
- "Both are dedicated non-retryable errors; heartbeat must not return `None` or silently skip"（line 543）。

Error types（lines 342-343）包含 `HostInstanceIdentityConflictError` 和 `HostInstanceNotRegisteredError`。Non-retryable error list（line 349）包含 "host instance identity conflict" 和 "host instance missing registration"。

### DS-F4 / WAL second independent connection test — fixed

§Slice 1 tests（line 655）明确："a second independent connection to the same DB returns `wal` from `PRAGMA journal_mode`, proving WAL mode is persisted rather than only assumed on the original connection"。

Expected assertions（line 669）："`PRAGMA journal_mode` is `wal` on a reopened independent connection"。

### DS-F5 / artifact temp area / temp filename strategy — fixed

§Payload Descriptor And Artifact Ref Artifact write ordering（lines 499-500）：

- Step 3: "Write temp file under `artifact_root/.tmp/`"。
- Step 4: "Temp filename must be unguessable and multi-process safe, using cryptographic random id or `tempfile` exclusive creation; never use timestamp / pid alone"。

`test_artifact_store.py` tests（line 853）覆盖 "temp files are created under `artifact_root/.tmp/` with unguessable random id or `tempfile` exclusive creation, so concurrent writers do not collide"。

### DS-F6 / missing payload_ref FK test — fixed

§Slice 2 tests（line 748）明确："EventLog append with a non-existent non-null `payload_ref` raises `HostForeignKeyError` and transaction runner does not retry it"。

Expected assertions（line 767）："missing `payload_ref` FK violation is wrapped as `HostForeignKeyError` and is not retried"。

Expected failure paths（line 947）："EventLog append referencing missing `payload_ref` raises `HostForeignKeyError` and is not retried"。

## Fix 引入新 Blocker 检查

Fix 引入了两个新 error types：`HostInstanceIdentityConflictError` 和 `HostInstanceNotRegisteredError`。检查结论：

- 这两个错误类型是 controller-accepted findings DS-F2 / DS-F3 收敛错误语义所必需的。
- 它们限定在 liveness primitive 内部，不扩展到 lease / fencing / recovery classifier。
- Non-retryable error list 正确包含它们。
- 不引入新 blocker。

`HostTransaction` row / parameter typed aliases 在 plan 中要求但具体 type alias 形状留给 implementation agent 落地。这是实现细节，不阻塞 plan re-review，且 fix artifact 已标注此点。

## 汇总

| Finding ID | 原始 Severity | Fix Status |
| --- | --- | --- |
| MIMO-1 | minor | fixed |
| MIMO-2 | minor | fixed |
| MIMO-3 | minor | fixed |
| MIMO-4 + DS-F1 | minor / LOW | fixed |
| MIMO-5 | minor | fixed |
| MIMO-6 | minor | fixed |
| MIMO-7 | minor | fixed |
| DS-F2 | LOW | fixed |
| DS-F3 | LOW | fixed |
| DS-F4 | LOW | fixed |
| DS-F5 | INFO | fixed |
| DS-F6 | INFO | fixed |

## New Blockers

无。

## Residual Risk

- `HostTransaction` row / parameter typed aliases 具体 type alias 形状需 implementation agent 在不使用 `Any` / `object` 的前提下落地。这是实现细节，不阻塞 plan re-review。
- Artifact orphan cleanup policy 仍按原 plan deferred to later cleanup / diagnostics work unit，本次未改变。
- 新增 `HostInstanceIdentityConflictError` / `HostInstanceNotRegisteredError` 的错误粒度没有扩大到 lease / fencing / recovery classifier；后续 phase plan review 应确认此边界。

## Controller Decision Status

`pending-controller-decision`

## Artifact Path

`docs/reviews/gateflow-plan-re-review-host-p2-durable-store-eventlog-mimo-20260514.md`
