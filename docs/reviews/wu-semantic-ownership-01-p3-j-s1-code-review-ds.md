# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `4ba17c92` (docs: record p3-j accepted plan state)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-j-s1-code-review-ds.md`
- Included scope:
  - `dayu/host/lifecycle_events.py` — EventLog event_type 合法集合 owner
  - `dayu/host/durable/event_log.py` — append validation / row decoder fail-closed
  - `dayu/host/durable/schema.py` — fresh schema DDL CHECK
  - `tests/host/` — 本 slice 修改的 EventLog/schema/projection 与 tool trace fixture
  - `docs/reviews/wu-semantic-ownership-01-p3-j-s1-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-j-s1-controller-validation.md`
- Excluded scope: P3-J S2/S3/S4、umbrella WU 的其它 findings、非本 slice 修改的文件
- Parallel review coverage: 无

## S1 目标确认

S1 要解决：
1. EventLog `event_type` 合法集合由 `dayu/host/lifecycle_events.py` 统一 owner
2. `EventLogAppendRequest` 校验在 append 边界拒绝未知 event_type
3. `EventLogRow` decoder 对 durable row 被外部破坏后 fail-closed
4. Fresh schema `event_log.event_type` 通过 `CHECK IN (...)` 约束，值从 owner 派生

S1 非目标：
- 迁移各模块本地 `_EVENT_TYPE_*` 字符串常量到 owner import
- 迁移旧 SQLite 数据库
- 下游 consumer（projection、memory、read API）统一使用 owner parser

## Findings

未发现实质性问题。

### 逐项走读记录

以下记录对核心变更的逐行走读结论，均未发现可报告的 defect：

#### 1. owner 模块 `lifecycle_events.py` — 合法事件类型集合

- **新增 7 个 category enum**：`HostSessionEventType`、`HostAdmissionCommandEventType`、`HostToolWaitEventType`、`HostContextGovernanceEventType`、`HostRunnerInputEventType`、`HostEngineDiagnosticEventType`、`HostPreviewEventType`。
- **已有 enum 扩展**：`HostAttemptEventType` 新增 `ATTEMPT_STARTED`、`ATTEMPT_RUNNING` 两个非终态成员（原 docstring 声明"当前 P3-A 只定义 terminal 成员"）。
- **`HostEventType` union**：包含全部 9 个 category enum，类型完备。
- **`HOST_EVENT_TYPE_CATEGORIES`**：按固定顺序排列全部分类 tuple，供 DDL 和测试稳定断言使用。各分类内部成员互不重叠，无重复值风险。
- **`_HOST_EVENT_TYPE_BY_VALUE`**：从 categories 构建 `dict[str, HostEventType]`，O(1) 查找。所有 StrEnum 成员值均为唯一大写字符串，无碰撞。
- **`all_host_event_type_values()`**：按 categories 顺序展开全部值的 tuple，供 `schema.py` DDL 渲染使用。
- **`parse_host_event_type()`**：dict lookup，`None` 表示未知值，调用方据此拒绝。
- **`serialize_host_event_type()`**：identity check `parse_host_event_type(event_type.value) is event_type` 利用 StrEnum 单例特性做 round-trip 校验。当前无生产调用方，仅测试覆盖。
- **`host_event_type_values()`**：泛型 typed→text 转换 helper。当前无生产调用方，仅测试覆盖。

**走读结论**：owner 模块设计正确：
- 合法集合完整覆盖全部 9 个语义类别（与 engine_ingest scan 结果一致）
- `CONTENT_DELTA` 和 `TOOL_CALL_DELTA` 经 `_is_transient_delta_event()` 确认为 transient，不进入 EventLog（`engine_ingest.py:5264-5278`），因此不在合法集合中，正确
- `REASONING_DELTA` 虽然也在 `_DELTA_ENGINE_EVENT_TYPES` 中，但通过 `engine_ingest.py:1012-1016` 的特殊路径 `_append_preview_event()` 持久化为 PREVIEW EventLog row，因此在合法集合中，正确
- `parse_host_event_type` dict lookup 与 `parse_host_run_event_type` StrEnum 构造两种实现模式是需求差异导致（前者需覆盖 union type），非不一致 defect

#### 2. append 校验 `event_log.py:_validate_append_request`

```python
# event_log.py:1129-1130
if parse_host_event_type(request.event_type) is None:
    raise HostDurableError("EventLog event_type is unknown")
```

**走读结论**：
- 校验位置正确：在 `_require_non_empty_text` 之后、payload 校验之前，确保非法值在 encoding/digest/write 前被拦截
- 错误类型正确：`HostDurableError` 是 durable 层通用错误，与 `HostPayloadReferenceError`（payload 专用）、`HostForeignKeyError`（FK 专用）语义区分清晰
- 错误消息可读：`"event_type is unknown"` 直接说明原因

#### 3. row decoder 校验 `event_log.py:_event_log_row_from_host_row`

```python
# event_log.py:1251-1253
event_type = _require_text(row.get("event_type"), field_name="event_type")
if parse_host_event_type(event_type) is None:
    raise HostDurableError("EventLog row has invalid event_type")
```

**走读结论**：
- `_require_text` 先提取 raw text，再经 `parse_host_event_type` 校验，控制流正确
- 复用同一个 owner parser，不引入独立判断逻辑
- 错误消息 `"invalid event_type"` 与 append 校验的 `"unknown"` 有区分度（前者暗示 durable row 已被外部破坏）
- 读路径（`read_events_after_matching`、`read_event_by_id` 等）都经过此 decoder → 所有 `EventLogRow` 消费者受益

#### 4. fresh schema DDL `schema.py`

```python
# schema.py:226-229
_EVENT_LOG_EVENT_TYPE_CHECK_VALUES_SQL = _sql_text_in_values(
    all_host_event_type_values()
)
```

**走读结论**：
- `_sql_text_in_values` 的 SQL 转义使用标准 `'` → `''` doubling，对当前值集（仅大写字母和下划线）安全
- 入参校验拒绝空值和空白值（defense-in-depth），虽然当前 owner 不会产生空值
- `CREATE TABLE IF NOT EXISTS` — CHECK 仅对新库生效，不改变已有库，与 S1 "fresh schema only" 策略一致
- `HOST_SCHEMA_VERSION` 从 21 → 22，schema mismatch 检测正常工作
- `_EVENT_LOG_EVENT_TYPE_CHECK_VALUES_SQL` 是模块级常量（import 时计算），对 DDL 场景（每次 store open 时执行）足够

#### 5. 测试覆盖

**新增测试**（`test_event_log_store.py`）：
- `test_append_rejects_unknown_event_type` — append 边界拒绝 `INVALID_TEST_EVENT_TYPE`，断言 `"event_type is unknown"`
- `test_row_decoder_rejects_mutated_unknown_event_type` — 通过 `PRAGMA ignore_check_constraints=ON` 绕过 SQLite CHECK 后 UPDATE 行，再读回断言 `"invalid event_type"` → fail-closed 验证正确

**新增测试**（`test_durable_schema.py`）：
- `test_event_log_schema_rejects_unknown_event_type` — 直接 INSERT `INVALID_TEST_EVENT_TYPE`，断言 `sqlite3.IntegrityError` → fresh schema CHECK 验证正确
- `test_host_schema_version_is_event_type_check_version` — 断言版本号为 22
- `test_schema_constraints_are_explicit` 扩展 — 验证 `CREATE TABLE` SQL 中包含 `event_type TEXT NOT NULL CHECK` 且每个合法值都出现在 SQL 中

**新增测试**（`test_lifecycle_events.py`）：
- `test_all_host_event_type_values_preserves_owner_categories` — 完整验证 HOST_EVENT_TYPE_CATEGORIES 结构与内容、`all_host_event_type_values()` 返回完备集合、无重复值
- `test_parse_and_serialize_host_event_type_round_trip_full_legal_set` — 对全部合法值做 parse → serialize round-trip，未知值返回 None
- 已有 terminal/closeout 测试继续通过，无回归

**Fixture 迁移**：
- 全部 23 个测试文件中，通用 EventLog fixture 从 `TYPE_A`/`TYPE_B`/`DIAG_A`/`host.test` 等非法值迁移到 `USER_INPUT_ACCEPTED`/`RUN_ACCEPTED`/`ENGINE_EVENT_DIAGNOSTIC`/`REASONING_DELTA`/`USAGE_REPORTED` 等合法值
- 仅 `INVALID_TEST_EVENT_TYPE` 和 `INVALID_MUTATED_EVENT_TYPE` 保留在显式 rejection 测试中
- controller validation 发现的 `test_tool_trace_projection.py` fixture 缺失 `resolution_kind`/`tool_fact_kind` 问题已在 fixture 侧修复（`tests/host/test_tool_trace_projection.py:393-394`），未改动 production code

**走读结论**：测试覆盖 append/decoder/DDL 三个核心边界的 happy path 和 failure path，fixture 迁移彻底，无固化错误语义。

#### 6. 生产 append path 审计

扫描全部生产 `event_type=` 赋值（去除 read_model/projection/memory/tool_trace 等 consumer 侧的 `event_type=row.event_type` 透传）：

| 模块 | 使用的 event_type 值 | 是否在 legal set |
|---|---|---|
| `admission.py` | `USER_INPUT_ACCEPTED`, `STEER_REQUESTED`, `ATTEMPT_STEERED`, `RUN_STARTED`, `ATTEMPT_STARTED`, `RETRY_REQUESTED`, `REPLAY_REQUESTED` | ✓ |
| `run_transition.py` | `RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, `RUN_CANCELLING`, `RUN_RECOVERING`, `RUN_SUCCEEDED`/`FAILED`/`CANCELLED`/`LOST`, `ATTEMPT_STARTED`/`RUNNING`/`SUCCEEDED`/`FAILED`/`CANCELLED`/`LOST`, `CANCEL_REQUESTED`, `RESUME_REQUESTED`, `TOOL_RESULT_ACCEPTED` | ✓ |
| `tool_runtime.py` | `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED`, `TOOL_RESULT_ACCEPTED` | ✓ |
| `waiting.py` | `TOOL_CALL_REQUESTED`, `TOOL_AWAITING`, `WAIT_LATE_RESULT_REJECTED` | ✓ |
| `session_lifecycle.py` | `SESSION_CREATED`, `SESSION_CLOSED` | ✓ |
| `dispatch.py` | `CONTEXT_COMPACTION_REQUESTED`, `CONTEXT_COMPACTED`, `CONTEXT_COMPACTION_FAILED`, `CONTEXT_COMPACTION_ATTEMPT_REJECTED`, `ATTEMPT_RUNNING` | ✓ |
| `engine_ingest.py` | `ENGINE_EVENT_DIAGNOSTIC`, `ENGINE_EVENT_REJECTED`, `HOST_LIFECYCLE_DIAGNOSTIC`, `PROVIDER_DIAGNOSTIC`, `PROVIDER_PROTOCOL_ERROR`, `USAGE_REPORTED`, preview events via `_host_event_type()` | ✓ |
| `run_input.py` | `RUNNER_CALL_INPUT_ASSEMBLED` | ✓ |
| `compaction_operation.py` | `RUNNER_CALL_INPUT_ASSEMBLED` | ✓ |

全部生产 append path 使用的 event_type 值均落在 `all_host_event_type_values()` 返回的合法集合内。无遗漏。

#### 7. adversarial failure pass

按 deepreview 技能要求的 adversarial 维度逐项检查：

- **auth/permissions/tenant isolation**：本 slice 不改动 auth 相关路径，不适用
- **data loss/corruption/duplication**：append 校验在 write 前拒绝非法值，无数据丢失风险；row decoder fail-closed 防止已损坏数据被消费
- **rollback safety/retries/idempotency**：`parse_host_event_type` 是纯函数，无副作用，可安全重试
- **race conditions/ordering**：所有校验在单个 transaction 内完成，无跨事务竞态
- **empty-state/null/timeout/cancellation**：`_require_non_empty_text` 先检查空值，`parse_host_event_type` 再检查合法性，顺序正确；空字符串被 `_require_non_empty_text` 拦截，不会被 dict lookup 误判
- **duplicate requests**：event_type 校验不涉及去重，idempotency 由既有机制保证
- **version skew/schema drift**：`HOST_SCHEMA_VERSION` bump 确保旧库被检测为 mismatch；`CREATE TABLE IF NOT EXISTS` 不修改已有表，无静默升级风险
- **observability gaps**：两处 `HostDurableError` 消息有区分度（`"unknown"` vs `"invalid"`），排障可定位
- **external protocol/API boundaries**：不适用，本 slice 只改内部 durable 边界
- **overcoupling**：`schema.py` 通过 `all_host_event_type_values()` 依赖 owner，而非直接 import 各 category tuple，依赖方向正确（schema → lifecycle_events，不反向）；但各生产模块仍使用本地 `_EVENT_TYPE_*` 常量而非从 owner import（S1 非目标）
- **semantic ownership drift**：append/decoder/DDL 三条路径均通过同一个 `parse_host_event_type` 或 `all_host_event_type_values()` 做判断，语义真源单一；不存在下游 fallback、特例或兼容 shim 补契约
- **statically provable performance**：`parse_host_event_type` 是 O(1) dict lookup；`_HOST_EVENT_TYPE_BY_VALUE` 在模块 load 时构建一次，后续零开销；`_sql_text_in_values` 在模块 load 时计算一次，DDL 直接使用字符串常量；无性能问题

### 次要观察（非 defect，不阻塞 ship）

以下观察不属于 S1 scope 内 defect，记录供后续 slice 参考：

1. **`host_event_type_values()` 和 `serialize_host_event_type()` 无生产调用方**：两个函数已在 owner 模块定义并测试覆盖，但当前无生产代码调用。这是 S1 的预期状态——先建立 owner contract，后续 slice 再逐步迁移 consumer。

2. **各模块仍使用本地 `_EVENT_TYPE_*` 字符串常量**：如 `admission.py`、`run_transition.py`、`tool_runtime.py` 等模块各自定义 `_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"` 等常量，未从 `lifecycle_events.py` import。这是 S1 明确非目标——S1 只关闭 append/decoder/DDL 边界，consumer 迁移留给后续 slice。

3. **`test_all_host_event_type_values_preserves_owner_categories` 内联复制了 category 定义**：测试在 lines 66-95 手写 expected_categories tuple，与生产 `HOST_EVENT_TYPE_CATEGORIES` 内容重复。当未来新增 event type 时需同步更新两处。这个维护成本是 exhaustive assertion 的必然代价，当前可接受。

## Open Questions

无。

## Residual Risk

- **旧 SQLite 数据库无迁移路径**：`HOST_SCHEMA_VERSION` bump 到 22 后，使用 schema 21 的已有数据库会被 `HostSchemaMismatchError` 拒绝。当前策略是 fresh-schema only，若后续需要兼容旧库，需额外 migration slice。
- **未来新增 event type 需同时更新 owner 和 DDL**：新增 event type 必须先在 `lifecycle_events.py` 对应 enum 和 category tuple 中添加，`all_host_event_type_values()` 和 fresh schema CHECK 会自动同步。若遗漏 owner 更新而仅在本地 `_EVENT_TYPE_*` 常量中定义，append 会被拒绝。这个约束是 owner 收敛的预期行为，不是 risk。
- **测试未覆盖全部生产 append path 的集成验证**：当前测试在单元层验证 append/decoder/DDL 行为，但没有端到端测试验证所有生产 append path 实际使用了合法 event_type。依赖 code review 和 `rg` scan 做人工审计。
