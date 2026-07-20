# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Fix Re-Review (AgentDS)

## Scope

- Mode: current changes (fix re-review)
- Branch: `phaseflow/host-issues-control`
- Base: `6a208bec`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-fix-rereview-ds.md`
- Included scope: 当前未提交 diff 中针对 accepted findings 的修复验证
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci*`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`（unrelated dirty/untracked）
- Review artifacts:
  - MiMo: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-mimo.md`
  - DS: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-fix-codex.md`

## Accepted Findings Verification

### P3-J-S3-F1: Idempotency dataclass kind fields typed, construction/row decode validate through owner

**Controller required fix:**

1. Make `IdempotencyScope.scope_kind`, `IdempotencyResultRef.result_kind`, and decoded `IdempotencyRecord` kind fields typed as `IdempotencyScopeKind` / `IdempotencyResultKind`.
2. Validate/coerce at dataclass construction and row decode through the owner parser.
3. Preserve SQLite persistence as the enum `.value` / `StrEnum` text representation.
4. Add constructor-level rejection tests for unknown scope and result kind, plus any necessary consumer/test updates.
5. No idempotency DDL CHECK.

**Evidence chain:**

| # | Requirement | Location | Status |
|---|------------|----------|--------|
| 1a | `IdempotencyScopeKind(StrEnum)` 闭集定义 | `dayu/host/durable/idempotency.py:29-46` — 15 个成员 | ✅ |
| 1b | `IdempotencyResultKind(StrEnum)` 闭集定义 | `dayu/host/durable/idempotency.py:49-58` — 7 个成员 | ✅ |
| 1c | `IdempotencyScope.scope_kind: IdempotencyScopeKind` | `idempotency.py:126` | ✅ |
| 1d | `IdempotencyResultRef.result_kind: IdempotencyResultKind` | `idempotency.py:154` | ✅ |
| 1e | `IdempotencyRecord.scope_kind: IdempotencyScopeKind` | `idempotency.py:188` | ✅ |
| 1f | `IdempotencyRecord.result_kind: IdempotencyResultKind` | `idempotency.py:192` | ✅ |
| 2a | `IdempotencyScope.__post_init__` 调用 `parse_idempotency_scope_kind` | `idempotency.py:130-141` → `idempotency.py:61-77` | ✅ |
| 2b | `IdempotencyResultRef.__post_init__` 调用 `parse_idempotency_result_kind` | `idempotency.py:159-170` → `idempotency.py:80-96` | ✅ |
| 2c | `IdempotencyRecord.__post_init__` 调用两者 | `idempotency.py:198-214` | ✅ |
| 2d | Row decode: `parse_*_kind` 返回值赋给 `IdempotencyRecord` 构造参数（不再丢弃） | `idempotency.py:414-427` — `parsed_scope_kind`, `parsed_result_kind` 直接传入 | ✅ |
| 2e | `_validate_scope` / `_validate_result_ref` 改用 `parse_*_kind`（不再仅 `_require_non_empty_text`） | `idempotency.py:375, 388` | ✅ |
| 3a | SQLite INSERT 使用 `scope.scope_kind.value` / `result.result_kind.value` | `idempotency.py:307, 311` | ✅ |
| 3b | SQLite SELECT WHERE 使用 `scope.scope_kind.value` | `idempotency.py:360` | ✅ |
| 4a | Constructor rejection 测试 (`test_idempotency_dataclass_construction_rejects_unknown_kind`) | `tests/host/test_idempotency_store.py:1317-1332` | ✅ |
| 4b | Row decode rejection 测试 (`test_idempotency_read_rejects_mutated_unknown_result_kind`) | `tests/host/test_idempotency_store.py:1335-1376` | ✅ |
| 4c | Owner value stability 测试 (`test_idempotency_owner_values_match_current_host_baseline`) | `tests/host/test_idempotency_store.py:1286-1314` | ✅ |
| 4d | 生产调用方全部使用 typed enum 值: `admission.py`, `session_lifecycle.py`, `waiting.py`, `tool_runtime.py`, `purge.py` | 各文件 diff 中 `IdempotencyScopeKind.*` / `IdempotencyResultKind.*` 替换原裸字符串 | ✅ |
| 4e | Test helpers 更新: `_scope()` (close_session), `_result_ref()` (session), concurrency matrix (close_session/session) | `test_idempotency_store.py:69-70, 88`, `test_durable_concurrency_matrix.py:73-76` | ✅ |
| 5 | DDL CHECK 断言不存在 (`test_schema_constraints_are_explicit`) | `tests/host/test_durable_schema.py:1130-1132` — `assert "scope_kind TEXT NOT NULL CHECK" not in idempotency_sql` | ✅ |

**Verdict: CLOSED** ✅

### P3-J-S3-F2: payload_resolution consumes PayloadDescriptorKind owner directly

**Controller required fix:**

1. Update `payload_resolution.py` to consume `PayloadDescriptorKind` directly for expected descriptor kinds.
2. Keep `_validate_descriptor_kind(...)` as the single expected-kind parser/check boundary.

**Evidence chain:**

| # | Requirement | Location | Status |
|---|------------|----------|--------|
| 1a | Import `PayloadDescriptorKind` 和 `parse_payload_descriptor_kind` | `dayu/host/payload_resolution.py:15-16, 23` | ✅ |
| 1b | 不再 import `TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` / `TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND` | `payload_resolution.py` import 段中无此两项 | ✅ |
| 1c | `_read_arguments_json`: `expected_kind=PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON` | `payload_resolution.py:246`（来自 diff 行 853） | ✅ |
| 1d | `_read_semantic_query`: `expected_kind=PayloadDescriptorKind.TOOL_CALL_SEMANTIC_QUERY_TEXT` | `payload_resolution.py:294`（来自 diff 行 863） | ✅ |
| 2a | `_validate_descriptor_kind` 参数 `expected_kind: PayloadDescriptorKind` | `payload_resolution.py:318` | ✅ |
| 2b | expected_kind 通过 `parse_payload_descriptor_kind` 校验 | `payload_resolution.py:334` — `expected_descriptor_kind = parse_payload_descriptor_kind(expected_kind)` | ✅ |
| 2c | actual descriptor_kind 从 metadata JSON 提取后通过 `parse_payload_descriptor_kind` 校验 | `payload_resolution.py:339-342` — 显式空值检测 + parse + identity comparison | ✅ |
| 2d | 比较使用 enum identity (`is not`)，非字符串比较 | `payload_resolution.py:343` — `actual_descriptor_kind is not expected_descriptor_kind` | ✅ |
| 2e | `_validate_descriptor_kind` 仍为唯一的 expected-kind parse/check boundary | 函数签名、入参校验、actual 解析均在此函数内完成 | ✅ |

**Verdict: CLOSED** ✅

## New Material Issues Check

对 fix 引入的所有变更做了逐文件走读，未发现新的 material issue。以下是关键变更点的逐项确认：

### 1. `PayloadDescriptorKind(StrEnum)` 新增 (schema.py:235-246)

- 7 个成员覆盖所有现有 descriptor kind 值，包括 compaction_operation.py 中原为本地常量的 `compaction_rejected_attempt_diagnostic`
- `parse_payload_descriptor_kind()` (schema.py:249-266) 正确处理空字符串、空白字符串、非法值三种失败路径
- `payload_descriptor_metadata()` helper (schema.py:278-297) 在 `fields` 中检测到 `descriptor_kind` 时立即拒绝，防止调用方覆盖 owner 写入的 kind；descriptor_kind 先通过 `parse_payload_descriptor_kind` 校验再取 `.value` 写入 metadata，保证写入持久层的一定是合法值
- 旧字符串常量 (`TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` 等) 改为 `PayloadDescriptorKind.*.value` 派生，保持向后兼容，值完全相同

### 2. `_validate_payload_descriptor_metadata` 新增 (payload.py:498-515)

- 在 `_insert_payload_descriptor` 中新增调用 (`payload.py:459`)，写入边界校验 descriptor kind
- metadata 无 `descriptor_kind` 时静默放行（metadata 本身 schema-light，这是 plan 明确允许的行为）
- metadata 携带 `descriptor_kind` 时必须通过 owner 解析，拒绝非法值
- 测试 `test_payload_descriptor_rejects_unknown_descriptor_kind_before_write` 验证：非法 kind 被拒绝 + 无残留 durable row（count 0,0）

### 3. Compaction operation 迁移到 PayloadDescriptorKind (compaction_operation.py)

- 本地字符串常量 `_DIAGNOSTIC_DESCRIPTOR_KIND_COMPACTION_REJECTED_ATTEMPT = "compaction_rejected_attempt_diagnostic"` 被 `PayloadDescriptorKind.COMPACTION_REJECTED_ATTEMPT_DIAGNOSTIC` 替代，值相同
- 3 处 metadata 构造改用 `payload_descriptor_metadata()` helper，统一 owner 边界

### 4. Purge 模块 `_SESSION_FACT_SCOPE_KINDS` 更新 (purge.py:551-562)

- 元组元素从裸字符串改为 `IdempotencyScopeKind.*.value`，值完全相同
- 此处使用 `.value` 而非 enum 成员是正确的——该元组用于构造 SQL `IN (...)` 子句做 durable row 扫描，SQL 需要文本值

### 5. Purge test 外域 row 改为 direct SQL INSERT (test_purge_session.py:2518-2556)

- `_OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND` (`"external_projection_ack"`) 和 `result_kind="external_ack"` 的写入从 `IdempotencyStore().record_idempotent_result()` 改为 direct SQL INSERT
- 原因：`record_idempotent_result()` 现在在构造 `IdempotencyScope`/`IdempotencyResultRef` 时会拒绝这些非 owner 值；direct SQL 绕过 Python 层校验，正确模拟历史/外部 row 场景
- 这是 intentional design choice，在 DS original review 的 Residual Risk 中已明确记录为可接受

### 6. Whitespace 拒绝测试 (test_idempotency_store.py)

- `test_idempotency_rejects_whitespace_only_text_fields` 使用 `cast(IdempotencyScopeKind, " \t")` 绕过类型检查
- 运行时路径：`__post_init__` → `parse_idempotency_scope_kind(" \t")` → `_require_non_empty_text(" \t", ...)` 因空白字符拒绝
- 与原行为等价：原来在 `_validate_scope` 中拒绝，现在在 `parse_*_kind` 中拒绝，拒绝时机提前到构造边界，语义一致

### 7. Concurrency matrix test scope/result kind 更新 (test_durable_concurrency_matrix.py)

- `_SCOPE_KIND` 从 `"durable_matrix"` → `IdempotencyScopeKind.CLOSE_SESSION`
- `_RESULT_KIND` 从 `"event"` → `IdempotencyResultKind.SESSION`
- `_ReadIdempotencySummaryOperation` SQL WHERE 子句从 `_SCOPE_KIND` → `_SCOPE_KIND.value`
- 原值不在 owner 闭集内，更新为合法值后测试语义不变（concurrency matrix 依赖 scope_id + idempotency_key 唯一性，不依赖 kind 的具体值）

### 8. 新增测试覆盖

| 测试 | 文件 | 覆盖点 |
|------|------|--------|
| `test_idempotency_owner_values_match_current_host_baseline` | test_idempotency_store.py | owner 闭集值稳定性 |
| `test_idempotency_dataclass_construction_rejects_unknown_kind` | test_idempotency_store.py | Scope/ResultRef 构造边界拒绝 |
| `test_idempotency_read_rejects_mutated_unknown_result_kind` | test_idempotency_store.py | row decoder 拒绝（direct SQL 篡改后读取） |
| `test_descriptor_metadata_helper_rejects_descriptor_kind_override` | test_payload_store.py | metadata helper 拒绝 override |
| `test_payload_descriptor_rejects_unknown_descriptor_kind_before_write` | test_payload_store.py | 写入边界拒绝 + 无残留行 |
| `test_tool_call_request_atoms_reject_missing_descriptor_kind` | test_toolruntime_accept_barrier.py | consumer 端 missing kind fail closed |
| `test_tool_call_request_atoms_reject_mismatched_descriptor_kind` | test_toolruntime_accept_barrier.py | consumer 端 kind mismatch fail closed |
| `test_schema_constraints_are_explicit` (扩展) | test_durable_schema.py | 无 idempotency DDL CHECK |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **Purge 外域 row 测试的 direct SQL 路径**：`test_purge_session.py` 中 `_OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND` 的写入已改为 direct SQL INSERT 绕过 Python owner 校验。这是 intentional design——该测试模拟的是历史/外部 row 场景。但这也意味着 purge 的 end-to-end 路径不再有测试验证 `record_idempotent_result()` 对 out-of-scope kind 的拒绝行为。当前无生产代码尝试写入此类值，风险低。此风险在 original DS review Residual Risk 中已有记录，本次 fix 未扩大 blast radius。
- **旧字符串常量保留**：`TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` 等常量仍存在于 `schema.py`（从 `PayloadDescriptorKind.*.value` 派生）。当前无剩余生产消费者依赖这些常量（所有消费者已迁移到 `PayloadDescriptorKind` 或 `payload_descriptor_metadata()`），但测试 `test_tool_call_request_payload_descriptor_kinds_are_stable` 仍使用它们做稳定性断言。常量可视为 public API 的遗留兼容层，不在本次 S3 scope 内移除。

## Conclusion

**PASS** — 所有 accepted findings (P3-J-S3-F1, P3-J-S3-F2) 均已关闭，未引入新的 material issue。
