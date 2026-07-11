# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: 4ba17c92
- Output file: docs/reviews/wu-semantic-ownership-01-p3-j-s1-code-review-mimo.md
- Included scope:
  - dayu/host/lifecycle_events.py
  - dayu/host/durable/event_log.py
  - dayu/host/durable/schema.py
  - tests/host/test_lifecycle_events.py, test_event_log_store.py, test_projection_runner.py, test_projection_checkpoint.py, test_durable_schema.py, test_durable_concurrency_matrix.py, test_durable_connection.py, test_durable_transaction.py, test_public_event_stream.py, test_payload_store.py, test_artifact_store.py, test_storage_orphan_proof.py, test_event_log_multiprocess.py, test_idempotency_store.py, test_purge_session.py, test_wait_record_state.py, test_state_schema.py, test_tool_trace_projection.py
  - docs/reviews/wu-semantic-ownership-01-p3-j-s1-implementation-codex.md
  - docs/reviews/wu-semantic-ownership-01-p3-j-s1-controller-validation.md
- Excluded scope: P3-J S2/S3/S4, umbrella WU 其它未实现 findings
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 分析摘要

S1 实现正确完成了声明目标：EventLog event_type owner legal set 收敛、append validation、row decoder fail-closed、fresh schema CHECK。以下逐项确认：

**1. Semantic ownership boundary 正确收敛**

`dayu/host/lifecycle_events.py` 是 `event_type` 合法集合的唯一 owner。`all_host_event_type_values()` 从 `HOST_EVENT_TYPE_CATEGORIES`（由各分类 tuple 组成）生成完整合法集合。`schema.py` 和 `event_log.py` 均从该 owner 导入，未自行复制或重建合法集合。

**2. Append validation 落在 owner 边界**

`_validate_append_request`（`event_log.py:1129`）在 `_require_non_empty_text` 之后调用 `parse_host_event_type(request.event_type)`，未知值抛出 `HostDurableError("EventLog event_type is unknown")`。校验在编码、digest 计算和写入之前完成，是正确的 early rejection。

**3. Row decoder fail-closed 正确实现**

`_event_log_row_from_host_row`（`event_log.py:1251-1253`）在读取 `event_type` 文本后、构造 `EventLogRow` 前调用 `parse_host_event_type` 验证。外部篡改（绕过 SQLite CHECK）的行在 decoder 层被拒绝，不会泄漏到下游 projection 或 read API。测试 `test_row_decoder_rejects_mutated_unknown_event_type` 通过 `PRAGMA ignore_check_constraints=ON` 模拟外部篡改，验证了 fail-closed 行为。

**4. Fresh schema DDL CHECK 从 owner 派生**

`schema.py:226-228` 调用 `all_host_event_type_values()` 生成 `_EVENT_LOG_EVENT_TYPE_CHECK_VALUES_SQL`，渲染到 `event_log.event_type` 的 `CHECK (event_type IN (...))` 约束中。`HOST_SCHEMA_VERSION` 从 21 正确 bump 到 22。`_sql_text_in_values` 正确处理了 SQL 引号转义（`value.replace("'", "''")`）。

**5. 测试 fixture 迁移到合法 production event type**

所有任意 fixture 字面量（`TYPE_A`、`TYPE_B`、`TEST_EVENT`、`host.test`、`host.nulls` 等）已替换为合法 Host EventLog 值（`USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`ENGINE_EVENT_DIAGNOSTIC`、`REASONING_DELTA`、`USAGE_REPORTED` 等）。非法值仅保留在显式拒绝测试中。这确保测试断言的是 owner contract 行为而非偶然 fixture 行为。

**6. 完整合法集合覆盖测试**

`test_all_host_event_type_values_preserves_owner_categories` 断言了 `HOST_EVENT_TYPE_CATEGORIES` 的分类完整性、各分类 tuple 的成员顺序、以及 `all_host_event_type_values()` 的无重复性。`test_parse_and_serialize_host_event_type_round_trip_full_legal_set` 验证了 parse/serialize 的完整 round-trip 覆盖。

**7. tool_trace_projection fixture 修正**

`test_tool_call_chain_projects_hot_rows_and_cold_lines` 添加了 `resolution_kind` 和 `tool_fact_kind` 字段。controller-validation.md 解释了根因：fixture 缺少 accept-barrier-owned typed status 字段，`AcceptedResultProjection` 不从 raw outcome 推断 accepted status。修正落在 fixture 而非 production code，符合语义所有权原则。

## Open Questions

- 无。

## Residual Risk

- S1 关闭了 EventLog event_type 集合。未来新增 durable event type 必须先加入 `dayu/host/lifecycle_events.py`，否则 append 和 fresh schema 会拒绝。这是 by design 的约束，不是遗漏。
- 旧 SQLite 数据库不在此 WU 迁移范围内（fresh-schema only policy）。
- `serialize_host_event_type` 的 `is` identity check 是过度防御（输入类型已约束为 `HostEventType`），但无实际风险。
