# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Fix Re-Review

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `P3-J S3 - Idempotency And Descriptor Kind Weak-Contract Closure`
- Gate: fix re-review
- Agent: AgentMiMo
- Artifact path: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-fix-rereview-mimo.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-controller-adjudication.md`

## Accepted Findings

### P3-J-S3-F1 — IdempotencyScope / IdempotencyResultRef / IdempotencyRecord kind fields typed and construction/row decode validate through owner

**Required fix:**
- Make `IdempotencyScope.scope_kind`, `IdempotencyResultRef.result_kind`, and decoded `IdempotencyRecord` kind fields typed as `IdempotencyScopeKind` / `IdempotencyResultKind`.
- Validate/coerce at dataclass construction and row decode through the owner parser.
- Preserve SQLite persistence as the enum `.value` / `StrEnum` text representation.
- Add constructor-level rejection tests for unknown scope and result kind, plus any necessary consumer/test updates.
- No idempotency DDL `CHECK`.

**Evidence of closure:**

1. **Enum owner定义**（`idempotency.py:29-58`）：`IdempotencyScopeKind(StrEnum)` 和 `IdempotencyResultKind(StrEnum)` 定义了完整的闭集。

2. **Dataclass字段类型化**（`idempotency.py:126,154,188,192`）：三个 dataclass 的 kind 字段类型从 `str` 改为对应 enum。

3. **构造边界校验**（`idempotency.py:130-141,159-170,198-214`）：三个 dataclass 的 `__post_init__` 方法均通过 owner parser（`parse_idempotency_scope_kind` / `parse_idempotency_result_kind`）归一 kind 值，非法值在构造边界抛出 `HostDurableError`。

4. **Row decode 校验**（`idempotency.py:410-425`）：`_idempotency_record_from_host_row` 先用 `_require_text` 取出文本，再通过 owner parser 解析为 enum，然后传入 `IdempotencyRecord` 构造。

5. **SQLite 持久化**（`idempotency.py:304-305,357,372`）：`record_idempotent_result` 和 `read_idempotency_record` 使用 `scope.scope_kind.value` / `result.result_kind.value` 序列化 enum 到 SQLite text。

6. **生产 producers 传 typed 值**：
   - `admission.py:166-176`：`_OPERATION_*` 和 `_IDEMPOTENCY_RESULT_KIND_*` 改为 `IdempotencyScopeKind.*` / `IdempotencyResultKind.*`。
   - `session_lifecycle.py:66-70`：`_OPERATION_*` 和 `_IDEMPOTENCY_RESULT_KIND_SESSION` 改为 typed enum。
   - `waiting.py:123-131`：所有 scope/result kind 常量改为 typed enum。
   - `tool_runtime.py:219-220`：`_TOOL_FACT_ACCEPT_SCOPE_KIND` 和 `_TOOL_FACT_ACCEPT_RESULT_KIND` 改为 typed enum。
   - `purge.py:68,70`：`PURGE_IDEMPOTENCY_SCOPE_KIND` 和 `PURGE_IDEMPOTENCY_RESULT_KIND` 改为 typed enum。

7. **purge.py SQL IN 子句**（`purge.py:139-150`）：`_SESSION_FACT_SCOPE_KINDS` 使用 `IdempotencyScopeKind.X.value` 提取文本值，符合 SQL IN 子句需求。

8. **无 DDL CHECK**：`schema.py` 中 `TABLE_IDEMPOTENCY_RECORDS` DDL 不含 `scope_kind TEXT NOT NULL CHECK` 或 `result_kind TEXT NOT NULL CHECK`。

9. **测试覆盖**：
   - `test_idempotency_store.py:415-513`：新增 `test_idempotency_owner_values_match_current_host_baseline`、`test_idempotency_dataclass_construction_rejects_unknown_kind`、`test_idempotency_read_rejects_mutated_unknown_result_kind`。
   - `test_durable_schema.py:1123-1135`：新增断言 idempotency DDL 不含 CHECK。
   - `test_purge_session.py:2534-2574`：out-of-scope idempotency row 改为 direct SQL 插入（模拟历史/外部行），绕过 owner 校验。
   - `test_durable_concurrency_matrix.py:76-77`：`_SCOPE_KIND` 和 `_RESULT_KIND` 改为 typed enum。

**结论：P3-J-S3-F1 已关闭。**

---

### P3-J-S3-F2 — payload_resolution consumes PayloadDescriptorKind owner directly

**Required fix:**
- Update `payload_resolution.py` to consume `PayloadDescriptorKind` directly for expected descriptor kinds.
- Keep `_validate_descriptor_kind(...)` as the single expected-kind parser/check boundary.

**Evidence of closure:**

1. **payload_resolution.py 使用 enum owner**（`payload_resolution.py:246,297`）：`_validate_descriptor_kind` 调用中 `expected_kind` 参数传入 `PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON` 和 `PayloadDescriptorKind.TOOL_CALL_SEMANTIC_QUERY_TEXT`，不再使用旧的 string 常量。

2. **`_validate_descriptor_kind` 参数类型化**（`payload_resolution.py:318`）：`expected_kind` 参数类型从 `str` 改为 `PayloadDescriptorKind`。

3. **`_validate_descriptor_kind` 保持 parse/check boundary**（`payload_resolution.py:334,342-344`）：
   - `expected_descriptor_kind = parse_payload_descriptor_kind(expected_kind)` 归一 expected 值。
   - `actual_descriptor_kind = parse_payload_descriptor_kind(descriptor_kind)` 归一 actual 值。
   - `actual_descriptor_kind is not expected_descriptor_kind` 使用 enum identity 比较。
   - 空/非文本 descriptor_kind 在 parse 前先拦截。

4. **旧 string 常量不再被 payload_resolution.py 消费**：`TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` 和 `TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND` 不再出现在 payload_resolution.py 的 import 或使用中。

5. **新增 `PayloadDescriptorKind` enum 和 `payload_descriptor_metadata` helper**（`schema.py:235-297`）：
   - `PayloadDescriptorKind(StrEnum)` 定义 descriptor kind 闭集。
   - `parse_payload_descriptor_kind` 作为 parse/check boundary。
   - `payload_descriptor_metadata` helper 在构造 metadata 时通过 owner 写入 `descriptor_kind`，并拒绝 `fields` 覆盖。
   - 旧 string 常量（`TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` 等）改为从 enum `.value` 派生。

6. **生产 producers 改用 `payload_descriptor_metadata` helper**：
   - `run_input.py`、`engine_ingest.py`、`tool_runtime.py`、`compaction_operation.py` 中所有手动构造 `{"descriptor_kind": ...}` 的代码改为 `payload_descriptor_metadata(PayloadDescriptorKind.X, {...})`。

7. **payload.py 写入边界校验**（`payload.py:459`）：`_insert_payload_descriptor` 在写入前调用 `_validate_payload_descriptor_metadata(metadata)`，若 metadata 携带 `descriptor_kind` 则通过 owner parser 校验。

8. **测试覆盖**：
   - `test_durable_schema.py:921-934`：新增 `test_tool_call_request_payload_descriptor_kinds_are_stable` 中断言 `payload_descriptor_kind_values()` 返回值稳定。

**结论：P3-J-S3-F2 已关闭。**

---

## New Material Issues

**未发现新实质性问题。**

验证要点：

1. **`_validate_descriptor_kind` 中 `is not` 比较**（`payload_resolution.py:343`）：使用 `actual_descriptor_kind is not expected_descriptor_kind` 做 enum identity 比较。因为 `StrEnum` 继承自 `str`，Python 对相同字符串值的 `StrEnum` 成员缓存为同一对象，`PayloadDescriptorKind(value)` 对合法值总是返回缓存的 enum 成员。此比较安全。

2. **`purge.py` 中 `_SESSION_FACT_SCOPE_KINDS` 使用 `.value`**：该 tuple 用于 SQL IN 子句查询，使用 `.value` 提取文本值正确。

3. **`test_purge_session.py` 中 out-of-scope row 使用 direct SQL**：`_insert_old_idempotency_rows` 中 `_OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND` 和 `"external_ack"` 通过 direct SQL 插入，绕过 owner 校验。这是有意为之——模拟历史/外部行，测试 purge 清理逻辑不受 owner 闭集约束。

4. **`payload_descriptor_metadata` helper 阻止 `fields` 覆盖 `descriptor_kind`**（`schema.py:291-292`）：调用方无法绕过 owner 写入非法 `descriptor_kind`。

5. **`_validate_payload_descriptor_metadata` 在 `_insert_payload_descriptor` 写入前调用**（`payload.py:459`）：非法 `descriptor_kind` 在写入 durable state 前被拦截。

---

## Conclusion

**PASS** — 两个 accepted findings（P3-J-S3-F1、P3-J-S3-F2）均已关闭，修复符合 controller adjudication 要求，未引入新实质性问题。
