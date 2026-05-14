# Host Phase 2 Durable Store / EventLog Plan Review

## Review Gate Name

Phase 2 handoff-ready plan review.

## Reviewed Target

- `docs/host/phase2-durable-store-eventlog-plan.md`

## Reviewer Conclusion

**Ready for plan re-review after addressing 2 minor findings.**

Plan is substantially handoff-ready and code-generation-ready. Motivation and scope are well-anchored in design true sources. No Phase 3+ scope creep detected. Architecture boundaries (`dayu.host.durable`, no `dayu.runtime` pollution) are correct. Slices are ordered, file-bounded, and tests are distributed across slices rather than deferred. SQLite schema, transaction runner, EventLog contract, idempotency primitive, payload descriptor, artifact write ordering, and host instance liveness foundation are concrete enough for implementation.

However, 2 minor findings require clarification before implementation agent can proceed without making implicit architectural decisions. 5 additional observations are noted but do not block.

---

## Findings

### 1-未修复-[minor]-`HostCASPreconditionFailedError` 在 Phase 2 无使用上下文

**Evidence**: `docs/host/phase2-durable-store-eventlog-plan.md:328` 定义了 `HostCASPreconditionFailedError` 作为 error type，但 Phase 2 的所有 contract、behavior、slice 和 test 中均无 CAS precondition 语义。CAS state transition 属于 Phase 3 Session / Run / Attempt 状态机（`docs/host/implementation-control.md:450` "CAS-style state transition"）。

**Impact**: Implementation agent 可能误以为 Phase 2 需要实现 CAS precondition 语义，或在 transaction runner 中预留无用的 CAS 判断分支。

**Suggestion**: 将 `HostCASPreconditionFailedError` 从 Phase 2 error taxonomy 移除，或在 plan 中显式标注 "Phase 3 使用，Phase 2 只预留类型定义"。

**Controller Decision Status**: `pending-controller-decision`

---

### 2-未修复-[minor]-`record_idempotent_result` 缺少 `result_kind` 参数

**Evidence**:

- `docs/host/phase2-durable-store-eventlog-plan.md:408-411` 定义 `record_idempotent_result(transaction, scope, semantic_input_digest, result_ref) -> IdempotencyRecord`。
- `docs/host/phase2-durable-store-eventlog-plan.md:207` idempotency table DDL 包含 `result_kind TEXT NOT NULL`。
- `docs/host/phase2-durable-store-eventlog-plan.md:396-400` `IdempotencyResultRef` 包含 `result_kind: str` 和 `result_ref: str`。
- `docs/host/design.md:1171` 明确要求保存 `result_kind`。

**Impact**: Implementation agent 需要自行决定 `result_kind` 的来源——是作为 `record_idempotent_result` 的显式参数、从 `result_ref` 推导、还是作为 scope 的隐式属性。不同 agent 可能做出不同选择。

**Suggestion**: 在 `record_idempotent_result` 签名中增加 `result_kind: str` 参数，与 DDL 和 `IdempotencyResultRef` 保持一致。

**Controller Decision Status**: `pending-controller-decision`

---

### 3-未修复-[minor]-`HostTransaction` 内部 API shape 未指定

**Evidence**: `docs/host/phase2-durable-store-eventlog-plan.md:281` 仅描述 "exposes only typed DB helpers required by foundation modules; if it exposes raw `sqlite3.Connection`, it must remain internal and never reach `dayu.host` package root"，但未列出这些 typed DB helpers 的签名或职责。

**Impact**: Implementation agent 需要自行决定 `HostTransaction` 是薄 wrapper（暴露 execute / fetchone / fetchall）还是领域 typed helper（如 `append_event_row(...)`, `insert_payload_row(...)`）。两种路径都可行但架构风格不同。

**Suggestion**: 补充 `HostTransaction` 最小内部 API 的一行说明，例如 "提供 `execute(sql, params)` / `fetchone(sql, params)` / `fetchall(sql, params)` 级别的 typed wrapper，不暴露 connection 对象" 或 "直接暴露 typed insert / update helpers per table"。

**Controller Decision Status**: `pending-controller-decision`

---

### 4-未修复-[minor]-`event_body_digest` 计算字段与规范化未明确

**Evidence**: `docs/host/phase2-durable-store-eventlog-plan.md:173` DDL 包含 `event_body_digest TEXT NOT NULL`；line 378 说 "Append computes canonical JSON for structured fields and `event_body_digest` before insert"；line 457 说 "digest string format is `sha256:<64 lowercase hex chars>`"。但未明确 `event_body_digest` 包含哪些字段、排除哪些字段、是否排除 `event_sequence` / `appended_at` 等数据库分配字段。

**Impact**: Implementation agent 需要自行决定 digest 输入。若选择不当（如包含 `event_sequence`），则 duplicate `event_id` 检测逻辑会出错——同一逻辑事件在不同 append 中因 `event_sequence` 不同而 digest 不同，被误判为 identity conflict 而非 duplicate。

**Suggestion**: 补充一句："`event_body_digest` 基于 `(event_class, event_type, session_id, run_id, attempt_id, execution_id, occurred_at, actor, source, client_request_id, idempotency_key, policy_decision_json, reason_json, payload_json, payload_ref, payload_digest)` 的 canonical JSON 计算；排除 `event_sequence`、`event_id` 和 `appended_at`"。

**Controller Decision Status**: `pending-controller-decision`

---

### 5-未修复-[minor]-`payload_id` 生成责任未指定

**Evidence**: `docs/host/phase2-durable-store-eventlog-plan.md:431` `SQLitePayloadWriteRequest` 包含 `payload_id: str`，暗示调用方提供。但 `docs/host/phase2-durable-store-eventlog-plan.md:779` `write_sqlite_payload(transaction, request) -> PayloadDescriptor` 的签名表明 store 接收 request 并返回 descriptor。未说明 `payload_id` 是调用方生成还是 store 生成。

**Impact**: Implementation agent 需要自行决定。两种选择都可行，但可能导致不同 slice 间风格不一致（例如 `event_id` 由调用方提供，`event_sequence` 由 store 分配）。

**Suggestion**: 明确 "`payload_id` 由调用方提供，遵循 TEXT durable id 约定" 或 "由 store 生成"。

**Controller Decision Status**: `pending-controller-decision`

---

### 6-未修复-[minor]-`HostDurableStore` 为 plan 新增抽象，设计文档无定义

**Evidence**: `docs/host/phase2-durable-store-eventlog-plan.md:591` Slice 1 target types 包含 `HostDurableStore` 和 `open_host_durable_store(options) -> HostDurableStore`。此抽象未出现在 `docs/host/design.md` 或 `docs/host/implementation-control.md` 中。

**Impact**: 轻微。`HostDurableStore` 作为 Host durable foundation 的入口 facade 是合理的架构选择。但 plan 未描述其职责、生命周期、是否持有 connection pool、是否为 context manager、是否暴露 transaction runner。

**Suggestion**: 补充一行说明 `HostDurableStore` 的最小职责：持有 connection 和 transaction runner，提供 `transaction_runner` 属性，实现 context manager 或 explicit close。

**Controller Decision Status**: `pending-controller-decision`

---

### 7-未修复-[minor]-artifact path 验证未覆盖 symlink 和 null byte

**Evidence**: `docs/host/phase2-durable-store-eventlog-plan.md:461-462` 只求 "relative path stays under artifact root and contains no absolute path or `..` traversal"。未提及 symlink resolution（`os.path.realpath`）或 null byte injection（`\x00`）。

**Impact**: 低。Python `open()` 在大多数平台上遇到 null byte 会抛异常，symlink 攻击需要 artifact root 可写权限。但显式覆盖更安全。

**Suggestion**: 在 artifact write ordering step 1 补充："resolve symlinks before containment check; reject paths containing null bytes"。

**Controller Decision Status**: `pending-controller-decision`

---

## Open Questions / Residual Risk

### Non-blocking Observations

1. **`result_kind` 有效值未枚举**: `idempotency_records.result_kind TEXT NOT NULL` 无 CHECK 约束。Implementation agent 可自由选择字符串值。Phase 2 可以不枚举（留给具体 operation 的 accept path 定义），但 plan 应说明这是有意为之。

2. **`created_event_id` 和 `created_event_sequence` 可独立 NULL**: idempotency record 可以在没有关联 EventLog event 时存在（例如纯幂等缓存）。Plan 未说明这种场景是否为 Phase 2 预期用法。不阻塞，但 implementation agent 应理解这两个字段可以同时为 NULL。

3. **Multi-process test 是 timing-sensitive 的**: `docs/host/phase2-durable-store-eventlog-plan.md:957` 已识别此风险。Plan 正确地建议 "write tests around invariants rather than exact sleep counts"。

4. **`HostAfterCommitError` 可能让调用方在 durable success 后观察到异常**: `docs/host/phase2-durable-store-eventlog-plan.md:959` 已识别此风险。Phase 2 tests 必须覆盖此行为，后续 command path 需要决定 result reporting semantics。

5. **`event_body_digest` 在 `docs/host/design.md` 中无对应字段**: `event_log` row specification（`docs/host/design.md:1135-1153`）不包含 `event_body_digest`。此字段是 plan 为 duplicate detection 引入的实现级 detail，不是架构真源变更。合理，但 implementation agent 应理解这是 plan-level decision。

### 持续追踪风险（来自 controller adjudication）

- Payload artifact orphan cleanup 触发时机（startup / periodic / on-error）未在本 plan 中定义，deferred to later cleanup / diagnostics work unit。
- Host instance liveness foundation 不得被扩展为 positive orphan proof classifier——Phase 2 plan 正确遵守此边界。
- `payload_inline_threshold_bytes=65536` 和 `busy_timeout_seconds=5.0` 是 plan-level defaults，composition root 必须可覆盖。

---

## Scope Enforcement

| 检查项 | 是否出现 | 证据 |
| --- | --- | --- |
| Session / Run / Attempt 状态机 | 否 | Non-goals section (line 68) 明确排除 |
| Host command path | 否 | Non-goals section (line 69) 明确排除 |
| Engine dispatch | 否 | Non-goals section (line 70) 明确排除 |
| Projection / Memory / Audit / Trace / Outbox | 否 | Non-goals section (line 71) 明确排除 |
| ToolRuntime / fetch_more | 否 | Non-goals section (line 72) 明确排除 |
| Recovery classifier / positive orphan proof | 否 | Non-goals section (line 73) 明确排除；liveness section (line 505) 明确禁止 |
| Lease / fencing / takeover | 否 | Non-goals section (line 74) 明确排除 |
| Remote transport | 否 | Non-goals section (line 70) 明确排除 |
| 旧库兼容 migration | 否 | Non-goals section (line 75) 明确排除 |
| `dayu.runtime` 承载 Host durable truth | 否 | Contract section (line 150) 明确禁止 |

无 Phase 3+ scope creep。

## Architecture Boundary Verification

| 边界检查 | 通过 | 证据 |
| --- | --- | --- |
| `dayu.host.durable` 是 Host 内部子包 | 通过 | line 85-89, line 146-149 |
| 不从 `dayu.host` 包根导出 durable 类型 | 通过 | line 148 |
| `dayu.runtime` 不承载 durable truth | 通过 | line 150 |
| 不修改 `docs/host/design.md` | 通过 | line 133, line 915 |
| 不修改 `docs/host/implementation-control.md` | 通过 | line 134, line 915 |
| 不修改 `dayu/runtime/**` | 通过 | line 135 |
| 不修改 `dayu/engine/**` | 通过 | line 136 |

## Slice Quality Assessment

| 检查项 | 通过 | 证据 |
| --- | --- | --- |
| Slices 有序且有依赖链 | 通过 | S1 -> S2 -> S3，each requires previous committed |
| Slices file-bounded | 通过 | 每个 slice 列出 allowed files / modules |
| Tests 分布在各 slice | 通过 | S1: 2 test files, S2: 3 test files, S3: 3 test files |
| 每个 slice 有 completion signal | 通过 | 各 slice 有 Completion signal section |
| 每个 slice 有 stop condition | 通过 | 各 slice 有 Stop condition section |
| 每个 slice 有 explicit non-goals | 通过 | 各 slice 有 Explicit non-goals section |

## Validation Commands Assessment

| 检查项 | 通过 | 证据 |
| --- | --- | --- |
| pytest 命令覆盖所有 test files | 通过 | lines 857-866 |
| pyright 命令覆盖 production 和 test | 通过 | lines 883-885 |
| Expected failure paths 列表完整 | 通过 | lines 888-901 |
| Coverage expectation 指定 | 通过 | lines 903-905 |
| README trigger rules 遵守 | 通过 | lines 907-915 |

## Controller Decision Status

**Status = `pending-controller-decision`**

7 minor findings。Controller 需确认：

1. Finding 1-4 是否需要在 plan 中修复后重新 review，或 controller 接受 implementation agent 自行决定。
2. Finding 5-7 是否属于 plan gap 或可接受的 implementation-level detail。

## Artifact Path

`docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-mimo-20260514.md`
